import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from kubernetes import client, config
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
import subprocess
import re

load_dotenv()

# Windows-specific fix for "ConnectionResetError" noise in uvicorn/asyncio
import sys
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI(title="OnCallBench AI Debugger API")

# Enable CORS for the GUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize K8s client
K8S_MODE = "kubeconfig"
try:
    config.load_kube_config()
except Exception:
    try:
        config.load_incluster_config()
        K8S_MODE = "in-cluster"
    except Exception:
        K8S_MODE = "error"
        print("Warning: Could not load K8s config. Ensure you are in a K8s context.")

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# Gemini Config
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

class DiagnosticRequest(BaseModel):
    namespace: str
    pod_name: Optional[str] = None

class CommandExecutionRequest(BaseModel):
    command: str

class PodStatus(BaseModel):
    name: str
    status: str
    restarts: int
    age: str
    is_healthy: bool

@app.get("/info")
async def get_info():
    return {
        "mode": K8S_MODE,
        "api_ready": GOOGLE_API_KEY is not None,
        "version": "1.0.0"
    }

import shlex

def _repair_json(s):
    """Repair common AI-generated JSON errors (mismatched braces/brackets, extra closers)."""
    import json as _json
    # Try as-is first
    try:
        return _json.dumps(_json.loads(s))
    except (ValueError, _json.JSONDecodeError):
        pass
    
    # Strategy 1: Stack-based brace/bracket rebalancing
    stack = []
    result = []
    in_string = False
    escape_next = False
    
    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            result.append(ch)
            continue
        if ch in '{[':
            stack.append(ch)
            result.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
                result.append(ch)
            elif stack and stack[-1] == '[':
                stack.pop()
                result.append(']')
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()
                result.append(ch)
            elif stack and stack[-1] == '{':
                stack.pop()
                result.append('}')
        else:
            result.append(ch)
    
    while stack:
        opener = stack.pop()
        result.append('}' if opener == '{' else ']')
    
    repaired = ''.join(result)
    try:
        return _json.dumps(_json.loads(repaired))
    except (ValueError, _json.JSONDecodeError):
        pass
    
    # Strategy 2: Trim trailing junk
    for trim in range(1, min(8, len(s))):
        try:
            return _json.dumps(_json.loads(s[:-trim]))
        except (ValueError, _json.JSONDecodeError):
            continue
    
    return None


def _prepare_kubectl_command(cmd):
    """
    Platform-agnostic kubectl command preparation.
    For patch commands: extracts JSON, repairs, writes to --patch-file.
    For other commands: cleans shell quotes and returns arg list.
    Returns: (args_list, temp_file_path_or_None)
    """
    import tempfile
    import json as _json
    
    temp_path = None
    has_patch_flag = ("-p " in cmd or "-p'" in cmd or '-p"' in cmd
                      or "--patch " in cmd or "--patch=" in cmd)
    is_patch = "patch" in cmd.lower() and has_patch_flag
    
    if is_patch:
        # Strip all single quotes (shell-only, never valid JSON)
        cmd_clean = cmd.replace("'", "")
        
        brace_idx = cmd_clean.find('{')
        bracket_idx = cmd_clean.find('[')
        
        if bracket_idx != -1 and (brace_idx == -1 or bracket_idx < brace_idx):
            start_idx = bracket_idx
        elif brace_idx != -1:
            start_idx = brace_idx
        else:
            start_idx = -1
        
        if start_idx != -1:
            raw_json = cmd_clean[start_idx:].rstrip()
            clean = raw_json.replace('\\"', '"').replace('\\\\', '\\')
            
            repaired = _repair_json(clean) or _repair_json(raw_json)
            
            if repaired:
                if "--type=json" in cmd:
                    parsed = _json.loads(repaired)
                    if isinstance(parsed, dict):
                        repaired = _json.dumps([parsed])
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                                  encoding='utf-8', delete=False) as f:
                    f.write(repaired)
                    temp_path = f.name
                
                # Build args list directly — never pass file paths through shlex
                # (shlex treats backslashes as escape chars, breaking Windows paths)
                patch_match = re.search(r'(-p|--patch)\s*', cmd_clean)
                prefix = (cmd_clean[:patch_match.start()].strip()
                          if patch_match else cmd_clean[:start_idx].strip())
                prefix_args = shlex.split(prefix)  # safe: no file paths here
                args = prefix_args + [f'--patch-file={temp_path}']
                
                print(f"[CMD] Patch rewritten -> {' '.join(args)}")
                return args, temp_path
            else:
                print(f"[CMD] WARN: JSON repair failed, attempting raw execution")
    
    # Non-patch (or patch fallback): clean quotes and split
    try:
        args = shlex.split(cmd)
    except ValueError:
        args = shlex.split(cmd.replace("'", ""))
    
    return args, temp_path


@app.post("/execute")
async def execute_command(request: CommandExecutionRequest):
    cmd = request.command.strip()
    
    if not cmd.startswith("kubectl"):
        raise HTTPException(status_code=400,
                            detail="Only 'kubectl' commands are allowed for security.")
    
    # Restored permissive blacklist: block cluster/resource deletes, but allow 'delete pod'
    blacklist = [
        "delete namespace", "delete clusterrole", "delete node", "delete pv",
        "delete deployment", "delete statefulset", "delete replicaset",
        "delete service", "delete daemonset", "delete all",
    ]
    if any(b in cmd.lower() for b in blacklist):
        raise HTTPException(status_code=400,
                            detail="Destructive resource-level deletes are blocked. Use 'kubectl patch' to fix resources or 'kubectl delete pod' to restart them.")

    temp_path = None
    try:
        args, temp_path = _prepare_kubectl_command(cmd)
        
        is_win = sys.platform == 'win32'
        if is_win:
            # On Windows, shell=True is more reliable for finding binaries and handling strings
            # We reconstruct the command string from args to keep our --patch-file changes
            cmd_to_run = " ".join(f'"{a}"' if " " in a or "\\" in a else a for a in args)
            result = subprocess.run(cmd_to_run, capture_output=True, text=True, timeout=30, shell=True)
        else:
            result = subprocess.run(args, capture_output=True, text=True, timeout=30, shell=False)
            
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504,
                            detail="Command timed out after 30 seconds.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

# BASE_DIR is project root
BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = BASE_DIR / "scenarios"

@app.get("/namespaces")
async def get_namespaces():
    try:
        ns_list = v1.list_namespace()
        return [ns.metadata.name for ns in ns_list.items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/pods")
async def get_pods(namespace: str):
    try:
        pods = v1.list_namespaced_pod(namespace)
        pod_list = []
        for p in pods.items:
            # Check health
            is_healthy = True
            if p.status.phase != "Running":
                is_healthy = False
            for container_status in p.status.container_statuses or []:
                if not container_status.ready:
                    is_healthy = False
            
            pod_list.append(PodStatus(
                name=p.metadata.name,
                status=p.status.phase,
                restarts=sum([cs.restart_count for cs in (p.status.container_statuses or [])]),
                age=str(p.metadata.creation_timestamp),
                is_healthy=is_healthy
            ))
        return pod_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Workloads endpoints ──────────────────────────────────────────

@app.get("/namespaces/{namespace}/deployments")
async def get_deployments(namespace: str):
    try:
        deps = apps_v1.list_namespaced_deployment(namespace)
        result = []
        for d in deps.items:
            conditions = []
            for c in (d.status.conditions or []):
                conditions.append({
                    "type": c.type, "status": c.status,
                    "reason": c.reason or "", "message": c.message or ""
                })

            # Determine rollout status
            desired = d.spec.replicas or 0
            ready = d.status.ready_replicas or 0
            updated = d.status.updated_replicas or 0
            available = d.status.available_replicas or 0
            unavailable = d.status.unavailable_replicas or 0

            if unavailable > 0:
                rollout_status = "Degraded"
            elif updated < desired:
                rollout_status = "Progressing"
            elif ready >= desired:
                rollout_status = "Healthy"
            else:
                rollout_status = "Waiting"

            containers = d.spec.template.spec.containers or []
            images = [c.image for c in containers]

            result.append({
                "name": d.metadata.name,
                "namespace": d.metadata.namespace,
                "replicas": desired,
                "ready_replicas": ready,
                "updated_replicas": updated,
                "available_replicas": available,
                "unavailable_replicas": unavailable,
                "images": images,
                "strategy": d.spec.strategy.type if d.spec.strategy else "RollingUpdate",
                "rollout_status": rollout_status,
                "conditions": conditions,
                "labels": dict(d.metadata.labels or {}),
                "selector": dict(d.spec.selector.match_labels or {}) if d.spec.selector else {},
                "age": str(d.metadata.creation_timestamp),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/statefulsets")
async def get_statefulsets(namespace: str):
    try:
        sts_list = apps_v1.list_namespaced_stateful_set(namespace)
        result = []
        for s in sts_list.items:
            desired = s.spec.replicas or 0
            ready = s.status.ready_replicas or 0
            current = s.status.current_replicas or 0
            containers = s.spec.template.spec.containers or []
            images = [c.image for c in containers]

            if ready >= desired:
                status = "Healthy"
            elif ready > 0:
                status = "Degraded"
            else:
                status = "Unhealthy"

            result.append({
                "name": s.metadata.name,
                "namespace": s.metadata.namespace,
                "replicas": desired,
                "ready_replicas": ready,
                "current_replicas": current,
                "images": images,
                "status": status,
                "service_name": s.spec.service_name or "",
                "labels": dict(s.metadata.labels or {}),
                "selector": dict(s.spec.selector.match_labels or {}) if s.spec.selector else {},
                "age": str(s.metadata.creation_timestamp),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/daemonsets")
async def get_daemonsets(namespace: str):
    try:
        ds_list = apps_v1.list_namespaced_daemon_set(namespace)
        result = []
        for d in ds_list.items:
            desired = d.status.desired_number_scheduled or 0
            ready = d.status.number_ready or 0
            current = d.status.current_number_scheduled or 0
            updated = d.status.updated_number_scheduled or 0
            available = d.status.number_available or 0
            containers = d.spec.template.spec.containers or []
            images = [c.image for c in containers]

            if ready >= desired and desired > 0:
                status = "Healthy"
            elif ready > 0:
                status = "Degraded"
            else:
                status = "Unhealthy"

            result.append({
                "name": d.metadata.name,
                "namespace": d.metadata.namespace,
                "desired": desired,
                "current": current,
                "ready": ready,
                "updated": updated,
                "available": available,
                "images": images,
                "status": status,
                "labels": dict(d.metadata.labels or {}),
                "selector": dict(d.spec.selector.match_labels or {}) if d.spec.selector else {},
                "age": str(d.metadata.creation_timestamp),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Events endpoint ──────────────────────────────────────────────

@app.get("/namespaces/{namespace}/events")
async def get_events(namespace: str):
    try:
        events = v1.list_namespaced_event(namespace)
        result = []
        for e in events.items:
            result.append({
                "type": e.type or "Normal",
                "reason": e.reason or "",
                "message": e.message or "",
                "object_kind": e.involved_object.kind or "",
                "object_name": e.involved_object.name or "",
                "source": e.source.component if e.source else "",
                "first_seen": str(e.first_timestamp or e.metadata.creation_timestamp),
                "last_seen": str(e.last_timestamp or e.metadata.creation_timestamp),
                "count": e.count or 1,
            })
        result.sort(key=lambda x: x["last_seen"], reverse=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Networking endpoints ─────────────────────────────────────────

networking_v1 = client.NetworkingV1Api()

@app.get("/namespaces/{namespace}/services")
async def get_services(namespace: str):
    try:
        svc_list = v1.list_namespaced_service(namespace)
        result = []
        for s in svc_list.items:
            # Get endpoint count
            endpoint_count = 0
            try:
                ep = v1.read_namespaced_endpoints(s.metadata.name, namespace)
                for subset in (ep.subsets or []):
                    endpoint_count += len(subset.addresses or [])
            except Exception:
                pass

            ports = []
            for p in (s.spec.ports or []):
                ports.append({
                    "name": p.name or "",
                    "port": p.port,
                    "target_port": str(p.target_port),
                    "protocol": p.protocol or "TCP",
                    "node_port": p.node_port,
                })

            result.append({
                "name": s.metadata.name,
                "namespace": s.metadata.namespace,
                "type": s.spec.type or "ClusterIP",
                "cluster_ip": s.spec.cluster_ip or "",
                "external_ips": s.spec.external_i_ps or [],
                "ports": ports,
                "selector": dict(s.spec.selector or {}),
                "endpoint_count": endpoint_count,
                "labels": dict(s.metadata.labels or {}),
                "age": str(s.metadata.creation_timestamp),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/ingresses")
async def get_ingresses(namespace: str):
    try:
        ing_list = networking_v1.list_namespaced_ingress(namespace)
        result = []
        for i in ing_list.items:
            rules = []
            for r in (i.spec.rules or []):
                paths = []
                if r.http:
                    for p in (r.http.paths or []):
                        paths.append({
                            "path": p.path or "/",
                            "path_type": p.path_type or "Prefix",
                            "backend_service": p.backend.service.name if p.backend and p.backend.service else "",
                            "backend_port": p.backend.service.port.number if p.backend and p.backend.service and p.backend.service.port else 0,
                        })
                rules.append({
                    "host": r.host or "*",
                    "paths": paths,
                })

            lb_ips = []
            if i.status and i.status.load_balancer and i.status.load_balancer.ingress:
                for lb in i.status.load_balancer.ingress:
                    lb_ips.append(lb.ip or lb.hostname or "")

            result.append({
                "name": i.metadata.name,
                "namespace": i.metadata.namespace,
                "class_name": i.spec.ingress_class_name or "",
                "rules": rules,
                "load_balancer_ips": lb_ips,
                "tls": [{"hosts": t.hosts or [], "secret": t.secret_name or ""} for t in (i.spec.tls or [])],
                "labels": dict(i.metadata.labels or {}),
                "age": str(i.metadata.creation_timestamp),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/networkpolicies")
async def get_network_policies(namespace: str):
    try:
        np_list = networking_v1.list_namespaced_network_policy(namespace)
        result = []
        for n in np_list.items:
            ingress_rules = len(n.spec.ingress or []) if n.spec.ingress is not None else 0
            egress_rules = len(n.spec.egress or []) if n.spec.egress is not None else 0
            policy_types = n.spec.policy_types or []

            result.append({
                "name": n.metadata.name,
                "namespace": n.metadata.namespace,
                "pod_selector": dict(n.spec.pod_selector.match_labels or {}) if n.spec.pod_selector else {},
                "policy_types": policy_types,
                "ingress_rules_count": ingress_rules,
                "egress_rules_count": egress_rules,
                "labels": dict(n.metadata.labels or {}),
                "age": str(n.metadata.creation_timestamp),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Topology endpoint ────────────────────────────────────────────

@app.get("/namespaces/{namespace}/topology")
async def get_topology(namespace: str):
    """Build a resource dependency graph for visualization."""
    try:
        deps = apps_v1.list_namespaced_deployment(namespace)
        sts = apps_v1.list_namespaced_stateful_set(namespace)
        ds = apps_v1.list_namespaced_daemon_set(namespace)
        pods = v1.list_namespaced_pod(namespace)
        svcs = v1.list_namespaced_service(namespace)

        nodes = []
        edges = []

        # Add workload nodes
        workload_selectors = {}  # name -> selector labels for service matching
        for d in deps.items:
            node_id = f"deploy/{d.metadata.name}"
            ready = d.status.ready_replicas or 0
            desired = d.spec.replicas or 0
            nodes.append({
                "id": node_id, "label": d.metadata.name, "kind": "Deployment",
                "status": "healthy" if ready >= desired else "degraded" if ready > 0 else "unhealthy",
                "detail": f"{ready}/{desired} ready",
            })
            if d.spec.selector and d.spec.selector.match_labels:
                workload_selectors[node_id] = dict(d.spec.selector.match_labels)

        for s in sts.items:
            node_id = f"sts/{s.metadata.name}"
            ready = s.status.ready_replicas or 0
            desired = s.spec.replicas or 0
            nodes.append({
                "id": node_id, "label": s.metadata.name, "kind": "StatefulSet",
                "status": "healthy" if ready >= desired else "degraded" if ready > 0 else "unhealthy",
                "detail": f"{ready}/{desired} ready",
            })
            if s.spec.selector and s.spec.selector.match_labels:
                workload_selectors[node_id] = dict(s.spec.selector.match_labels)

        for d in ds.items:
            node_id = f"ds/{d.metadata.name}"
            ready = d.status.number_ready or 0
            desired = d.status.desired_number_scheduled or 0
            nodes.append({
                "id": node_id, "label": d.metadata.name, "kind": "DaemonSet",
                "status": "healthy" if ready >= desired and desired > 0 else "degraded" if ready > 0 else "unhealthy",
                "detail": f"{ready}/{desired} ready",
            })
            if d.spec.selector and d.spec.selector.match_labels:
                workload_selectors[node_id] = dict(d.spec.selector.match_labels)

        # Add pod nodes and connect to owners
        for p in pods.items:
            is_healthy = p.status.phase == "Running"
            for cs in (p.status.container_statuses or []):
                if not cs.ready:
                    is_healthy = False

            pod_id = f"pod/{p.metadata.name}"
            nodes.append({
                "id": pod_id, "label": p.metadata.name, "kind": "Pod",
                "status": "healthy" if is_healthy else "unhealthy",
                "detail": p.status.phase,
            })

            # Trace owner chain: Pod → ReplicaSet → Deployment
            if p.metadata.owner_references:
                owner = p.metadata.owner_references[0]
                if owner.kind == "ReplicaSet":
                    try:
                        rs = apps_v1.read_namespaced_replica_set(owner.name, namespace)
                        if rs.metadata.owner_references:
                            parent = rs.metadata.owner_references[0]
                            edges.append({"from": f"deploy/{parent.name}", "to": pod_id})
                        else:
                            edges.append({"from": f"rs/{owner.name}", "to": pod_id})
                    except Exception:
                        pass
                elif owner.kind == "StatefulSet":
                    edges.append({"from": f"sts/{owner.name}", "to": pod_id})
                elif owner.kind == "DaemonSet":
                    edges.append({"from": f"ds/{owner.name}", "to": pod_id})

        # Add service nodes and connect to workloads via selector matching
        for svc in svcs.items:
            svc_id = f"svc/{svc.metadata.name}"
            svc_selector = dict(svc.spec.selector or {})

            # Count endpoints
            ep_count = 0
            try:
                ep = v1.read_namespaced_endpoints(svc.metadata.name, namespace)
                for subset in (ep.subsets or []):
                    ep_count += len(subset.addresses or [])
            except Exception:
                pass

            nodes.append({
                "id": svc_id, "label": svc.metadata.name, "kind": "Service",
                "status": "healthy" if ep_count > 0 else "warning",
                "detail": f"{svc.spec.type} · {ep_count} endpoints",
            })

            # Match service selector to workload selectors
            if svc_selector:
                for wl_id, wl_labels in workload_selectors.items():
                    if all(svc_selector.get(k) == v for k, v in wl_labels.items()) or \
                       all(wl_labels.get(k) == v for k, v in svc_selector.items()):
                        edges.append({"from": svc_id, "to": wl_id})

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats(namespace: Optional[str] = None):
    try:
        total = 0
        unhealthy = 0
        running = 0
        ns_count = 0
        
        try:
            if namespace and namespace != "all":
                pods = v1.list_namespaced_pod(namespace)
                ns_count = 1
            else:
                pods = v1.list_pod_for_all_namespaces()
                ns_count = len(v1.list_namespace().items)
            
            total = len(pods.items)
            for p in pods.items:
                is_p_healthy = True
                if p.status.phase != "Running":
                    is_p_healthy = False
                
                for cs in (p.status.container_statuses or []):
                    if not cs.ready:
                        is_p_healthy = False
                
                if is_p_healthy:
                    running += 1
                else:
                    unhealthy += 1
        except Exception as k8s_err:
            print(f"K8s Data Fetch Error: {k8s_err}")
            # Fallback to empty if we can't even list
            pass
                
        return {
            "total_pods": total,
            "running_pods": running,
            "unhealthy_pods": unhealthy,
            "namespaces": ns_count,
            "health_score": int(((total - unhealthy) / total * 100)) if total > 0 else 100,
            "cluster_connected": True
        }
    except Exception as e:
        print(f"General Stats Error: {e}")
        return {
            "total_pods": 0,
            "running_pods": 0,
            "unhealthy_pods": 0,
            "namespaces": 0,
            "health_score": 0,
            "cluster_connected": False,
            "error": str(e)
        }

@app.get("/scenarios")
async def list_scenarios():
    print(f"Checking scenarios in: {SCENARIOS_DIR}")
    scenarios = []
    if not SCENARIOS_DIR.exists():
        print("SCENARIOS_DIR does not exist")
        return []
        
    for d in SCENARIOS_DIR.iterdir():
        if d.is_dir():
            gt_path = d / "ground_truth.json"
            if gt_path.exists():
                try:
                    with open(gt_path, "r") as f:
                        gt = json.load(f)
                        scenarios.append({
                            "id": d.name,
                            "name": gt.get("name", d.name),
                            "description": gt.get("root_cause", "No description available")
                        })
                except Exception as e:
                    print(f"Error loading scenario {d.name}: {e}")
            else:
                print(f"Ground truth not found for {d.name}")
    return scenarios

@app.get("/benchmarks")
async def get_benchmarks():
    reports_dir = BASE_DIR / "data" / "reports"
    benchmarks = []
    if not reports_dir.exists():
        return []
        
    for report_file in reports_dir.glob("score_*.json"):
        try:
            with open(report_file, "r") as f:
                data = json.load(f)
                benchmarks.append(data)
        except Exception as e:
            print(f"Error loading report {report_file}: {e}")
            
    return benchmarks

@app.post("/inject/{scenario_id}")
async def inject_failure(scenario_id: str):
    manifest_path = SCENARIOS_DIR / scenario_id / "manifest.yaml"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    try:
        # We'll use the CLI tool logic but inside the API
        cmd = ["kubectl", "apply", "-f", str(manifest_path)]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"status": "success", "message": f"Scenario {scenario_id} injected"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"kubectl error: {e.stderr or e.stdout or str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/diagnose")
async def diagnose(request: DiagnosticRequest):
    try:
        # 1. Collect enhanced live data
        try:
            pod = v1.read_namespaced_pod(request.pod_name, request.namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                raise HTTPException(status_code=404, detail=f"Pod '{request.pod_name}' no longer exists. It likely was replaced during remediation. Please refresh and select the new pod.")
            raise e
        events = v1.list_namespaced_event(request.namespace, field_selector=f"involvedObject.name={request.pod_name}")
        
        # Get related resources (Deployment/ReplicaSet)
        owner_info = "Standalone Pod"
        parent_spec = None
        if pod.metadata.owner_references:
            owner = pod.metadata.owner_references[0]
            owner_info = f"{owner.kind}/{owner.name}"
            try:
                if owner.kind == "ReplicaSet":
                    rs = apps_v1.read_namespaced_replica_set(owner.name, request.namespace)
                    if rs.metadata.owner_references:
                        parent = rs.metadata.owner_references[0]
                        owner_info = f"{parent.kind}/{parent.name}"
                        if parent.kind == "Deployment":
                            parent_spec = apps_v1.read_namespaced_deployment(parent.name, request.namespace).to_dict()
                elif owner.kind == "StatefulSet":
                    parent_spec = apps_v1.read_namespaced_stateful_set(owner.name, request.namespace).to_dict()
            except Exception:
                pass

        logs = ""
        try:
            logs = v1.read_namespaced_pod_log(request.pod_name, request.namespace, tail_lines=150)
        except Exception:
            try:
                # Try previous logs if it's crashlooping
                logs = v1.read_namespaced_pod_log(request.pod_name, request.namespace, tail_lines=150, previous=True)
                logs = f"PREVIOUS LOGS:\n{logs}"
            except Exception:
                logs = "No logs available."

        # Determine current health
        is_healthy = pod.status.phase == "Running"
        container_statuses_summary = []
        for cs in (pod.status.container_statuses or []):
            if not cs.ready:
                is_healthy = False
            container_statuses_summary.append({
                "name": cs.name,
                "ready": cs.ready,
                "restart_count": cs.restart_count,
                "state": str(cs.state)
            })

        # 2. Build context for Gemini
        context = {
            "metadata": {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "owner": owner_info,
                "creation_timestamp": str(pod.metadata.creation_timestamp)
            },
            "parent_controller_spec": parent_spec,
            "current_health": {
                "phase": pod.status.phase,
                "is_healthy": is_healthy,
                "containers": container_statuses_summary
            },
        }

        if is_healthy:
            # For healthy pods: minimal context, clear healthy framing
            context["summary"] = "Pod is Running with all containers Ready. No current issues detected."
            prompt = f"""
            You are a Kubernetes Expert (Lens-style assistant).
            
            VERDICT: THIS POD IS CONFIRMED HEALTHY.
            - Phase: Running
            - All containers: Ready
            - The pod is functioning normally.
            
            DATA:
            {json.dumps(context, default=str)}
            
            Respond with a JSON health report confirming the pod is healthy:
            - root_cause: state that the pod is healthy and operating normally
            - symptoms: empty list or list with "No issues detected"
            - fix_summary: state no action needed, pod is running as expected
            - fix_steps: list 1-2 optional best-practice suggestions with type "manual"
            - confidence_score: 0.95 or higher
            - risk_level: "Low"
            
            Output MUST be valid JSON only.
            """
            response = model.generate_content(prompt)
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            diagnosis_data = json.loads(text.strip())
        else:
            # For unhealthy pods: use the autonomous DebuggerAgent loop!
            context["status"] = pod.status.to_dict()
            context["events"] = [{
                "type": e.type, "reason": e.reason, 
                "message": e.message, 
                "last_timestamp": str(e.last_timestamp)
            } for e in events.items]
            context["logs_preview"] = logs[-2000:]

            from agent import DebuggerAgent
            agent = DebuggerAgent(provider="google")
            diagnosis_data = agent.diagnose(context)

        # POST-PROCESS FIXES: Validate and repair AI-generated kubectl commands
        if "fix_steps" in diagnosis_data:
            for step in diagnosis_data["fix_steps"]:
                cmd = step.get("command", "")
                if "patch" in cmd and ("-p " in cmd or "-p'" in cmd):
                    try:
                        cmd_clean = cmd.replace("'", "")
                        brace_idx = cmd_clean.find('{')
                        bracket_idx = cmd_clean.find('[')
                        start = bracket_idx if (bracket_idx != -1 and (brace_idx == -1 or bracket_idx < brace_idx)) else brace_idx if brace_idx != -1 else -1
                        
                        if start != -1:
                            raw = cmd_clean[start:].rstrip()
                            clean = raw.replace('\\"', '"').replace('\\\\', '\\')
                            repaired = _repair_json(clean) or _repair_json(raw)
                            if repaired:
                                prefix_match = re.search(r'(-p|--patch)\s*', cmd_clean)
                                prefix = cmd_clean[:prefix_match.start()].strip() if prefix_match else cmd_clean[:start].strip()
                                step["command"] = f"{prefix} -p '{repaired}'"
                    except Exception as e:
                        print(f"Post-process patch cleanup error: {e}")

            # Filter out any 'delete' steps
            diagnosis_data["fix_steps"] = [
                step for step in diagnosis_data["fix_steps"]
                if step.get("command", "").strip()
                and "delete" not in step.get("command", "").lower()
            ]
                        
        return diagnosis_data
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
