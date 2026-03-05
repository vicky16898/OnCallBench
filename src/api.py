import os
import json
import subprocess
import re
import sys
import asyncio
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel
from dotenv import load_dotenv
from kubernetes import client

# Local imports
from schemas import DiagnosticRequest, CommandExecutionRequest, PodStatus
from utils import _repair_json, _prepare_kubectl_command, extract_json_from_text
from k8s_service import (
    K8S_MODE, get_namespaces_logic, get_pods_logic, get_deployments_logic,
    get_statefulsets_logic, get_daemonsets_logic, get_events_logic,
    get_services_logic, get_ingresses_logic, get_network_policies_logic,
    get_topology_logic, get_stats_logic, gather_pod_data_for_diagnosis
)

load_dotenv()

# Windows-specific fix for "ConnectionResetError" noise in uvicorn/asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import threading

app = FastAPI(title="OnCallBench AI Debugger API")
injection_lock = threading.Lock()

# Enable CORS for the GUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gemini Config via modern google-genai
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client_genai = None
model_name = "gemini-2.0-flash"
if GOOGLE_API_KEY:
    try:
        client_genai = genai.Client(api_key=GOOGLE_API_KEY)
    except Exception as e:
        print(f"Error initializing Gemini: {e}")
else:
    print("Warning: GOOGLE_API_KEY not found in .env")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = BASE_DIR / "scenarios"

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "k8s_mode": K8S_MODE,
        "ai_ready": GOOGLE_API_KEY is not None,
        "scenarios_count": len(list(SCENARIOS_DIR.glob("*")))
    }

@app.get("/info")
def get_info():
    return {
        "mode": K8S_MODE,
        "api_ready": GOOGLE_API_KEY is not None,
        "version": "1.0.0"
    }

@app.post("/execute")
def execute_command(req: CommandExecutionRequest):
    cmd = req.command.strip()
    if not cmd.startswith("kubectl"):
        raise HTTPException(status_code=400, detail="Only 'kubectl' commands are allowed for security.")
    
    blacklist = [
        "delete namespace", "delete clusterrole", "delete node", "delete pv",
        "delete all", "edit ", "exec -it", "--force", 
        "rm -rf", "kill -9"
    ]
    
    # Block destructive resource deletes unless they are specifically part of a allowed fix
    if "delete" in cmd.lower() and not any(kind in cmd.lower() for kind in ["pod", "configmap", "secret", "pvc"]):
         if any(b in cmd.lower() for b in ["deployment", "service", "statefulset", "daemonset", "ingress"]):
              raise HTTPException(status_code=400, detail="Resource-level deletions for managed workloads are blocked. Use 'patch' instead.")
    if any(b in cmd.lower() for b in blacklist):
        raise HTTPException(status_code=400, detail="Destructive resource-level deletes are blocked.")

    all_temp_paths = []
    is_win = sys.platform == 'win32'
    
    try:
        # Robustly handle pipes vs single commands
        if '|' in cmd:
            parts = [p.strip() for p in cmd.split('|')]
            for part in parts:
                if not part.startswith('kubectl'):
                    raise HTTPException(status_code=400, detail="Only 'kubectl' commands are allowed in pipes.")
            
            processed_segments = []
            for p in parts:
                args, t_path = _prepare_kubectl_command(p)
                if t_path: all_temp_paths.append(t_path)
                
                if is_win:
                    processed_segments.append(subprocess.list2cmdline(args))
                else:
                    processed_segments.append(shlex.join(args))
                
            cmd_to_run = " | ".join(processed_segments)
            result = subprocess.run(cmd_to_run, capture_output=True, text=True, timeout=30, shell=True)
        else:
            args, temp_path = _prepare_kubectl_command(cmd)
            if temp_path: all_temp_paths.append(temp_path)
            
            if is_win:
                cmd_to_run = subprocess.list2cmdline(args)
                result = subprocess.run(cmd_to_run, capture_output=True, text=True, timeout=30, shell=True)
            else:
                result = subprocess.run(args, capture_output=True, text=True, timeout=30, shell=False)
            
        # --- START ACTIVITY LOGGING ---
        # If the command created a resource, record it so we can wipe it later
        if result.returncode == 0 and ("created" in result.stdout.lower() or "applied" in result.stdout.lower()):
            # Try to identify something like configmap/my-fix
            match = re.search(r'([a-z0-9.-]+)\/([a-z0-9.-]+)\s+(?:created|applied)', result.stdout.lower())
            if match:
                res_kind, res_name = match.groups()
                # We don't have scenario_id here easily, so we store in a global 'recent_fixes' file
                # The injector will look at this file to find extra junk to clean.
                fix_log_path = BASE_DIR / "data" / "ai_leavings.json"
                fix_log_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    leavings = {}
                    if fix_log_path.exists():
                        with open(fix_log_path, "r") as f: leavings = json.load(f)
                    
                    # Store as {kind: [names]}
                    if res_kind not in leavings: leavings[res_kind] = []
                    if res_name not in leavings[res_kind]: leavings[res_kind].append(res_name)
                    
                    with open(fix_log_path, "w") as f: json.dump(leavings, f)
                except: pass
        # --- END ACTIVITY LOGGING ---

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Command timed out after 30 seconds.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in all_temp_paths:
            if os.path.exists(p):
                try: os.remove(p)
                except OSError: pass

# ── K8s Resource Routes ──────────────────────────────────────────

@app.get("/namespaces")
def get_namespaces():
    try: return get_namespaces_logic()
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/pods")
def get_pods(namespace: str):
    try: return get_pods_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/deployments")
def get_deployments(namespace: str):
    try: return get_deployments_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/statefulsets")
def get_statefulsets(namespace: str):
    try: return get_statefulsets_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/daemonsets")
def get_daemonsets(namespace: str):
    try: return get_daemonsets_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/events")
def get_events(namespace: str):
    try: return get_events_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/services")
def get_services(namespace: str):
    try: return get_services_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/ingresses")
def get_ingresses(namespace: str):
    try: return get_ingresses_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/networkpolicies")
def get_network_policies(namespace: str):
    try: return get_network_policies_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/topology")
def get_topology(namespace: str):
    try: return get_topology_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
def get_stats(namespace: Optional[str] = None):
    return get_stats_logic(namespace)

# ── Scenario Routes ─────────────────────────────────────────────

@app.get("/scenarios")
def list_scenarios():
    scenarios = []
    if not SCENARIOS_DIR.exists(): return []
    for d in sorted(SCENARIOS_DIR.iterdir()):
        if d.is_dir():
            gt_path = d / "ground_truth.json"
            if gt_path.exists():
                try:
                    with open(gt_path, "r") as f:
                        gt = json.load(f)
                        scenarios.append({
                            "id": d.name,
                            "name": gt.get("name", d.name),
                            "description": gt.get("root_cause", "No description available"),
                            "difficulty": gt.get("difficulty", "medium"),
                            "category": gt.get("category", "general"),
                            "version": gt.get("version", "1.0"),
                        })
                except: pass
    return scenarios

@app.get("/benchmarks")
def get_benchmarks():
    reports_dir = BASE_DIR / "data" / "reports"
    benchmarks = []
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("*.json")):
            try:
                with open(f, "r") as fh:
                    benchmarks.append(json.load(fh))
            except: pass
    return benchmarks

@app.post("/reset-sandbox")
def reset_sandbox():
    """Nuclear reset: Delete entire oncall-bench namespace and recreate it."""
    try:
        namespace = "oncall-bench"
        # Delete namespace and wait for completion
        subprocess.run(["kubectl", "delete", "namespace", namespace, "--ignore-not-found", "--wait=true"], timeout=60)
        
        # Recreate namespace
        subprocess.run(["kubectl", "create", "namespace", namespace], check=True)
        
        # Also clear AI leavings log
        leavings_path = BASE_DIR / "data" / "ai_leavings.json"
        if leavings_path.exists():
             os.remove(leavings_path)

        return {"status": "success", "message": "Sandbox namespace 'oncall-bench' has been fully reset."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")

@app.post("/inject/{scenario_id}")
def inject_failure(scenario_id: str):
    if not injection_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Another injection is already in progress. Please wait.")
    
    try:
        manifest_path = SCENARIOS_DIR / scenario_id / "manifest.yaml"
        if not manifest_path.exists(): 
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        namespace = "oncall-bench"
        
        # 1. CHECK FOR REDUNDANCY: Block if scenario already exists
        labels = []
        try:
            with open(manifest_path, "r") as f:
                manifest_text = f.read()
                for match in re.finditer(r'app:\s*([a-zA-Z0-9_-]+)', manifest_text):
                    labels.append(f"app={match.group(1)}")
        except: pass

        for selector in set(labels):
            # Check if any resources with this label exist
            check_cmd = ["kubectl", "get", "all", "-l", selector, "-n", namespace, "--no-headers"]
            res = subprocess.run(check_cmd, capture_output=True, text=True)
            if res.stdout.strip():
                 return {
                     "status": "warning", 
                     "message": f"Scenario {scenario_id} is already present in the namespace. To re-inject a factory-reset version, please 'Reset Namespace' first."
                 }

        # 2. ENSURE NAMESPACE: Quick idempotent check
        subprocess.run(["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"], capture_output=True)
        subprocess.run(["kubectl", "apply", "-f", "-"], input=f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {namespace}", text=True)

        # 3. PERFORM INJECTION
        cmd = ["kubectl", "apply", "-f", str(manifest_path)]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Give K8s a few seconds to begin the rollout
        import time
        time.sleep(2)
        
        return {"status": "success", "message": f"Scenario {scenario_id} injected successfully into sandbox."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Injection failed: {str(e)}")
    finally:
        injection_lock.release()

# ── Diagnosis Route ──────────────────────────────────────────────

@app.post("/diagnose")
def run_diagnosis(req: DiagnosticRequest):
    try:
        try:
            data = gather_pod_data_for_diagnosis(req.namespace, req.pod_name)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                raise HTTPException(status_code=404, detail=f"Pod '{req.pod_name}' no longer exists.")
            raise e

        # Build context
        context = {
            "metadata": {
                "name": data["pod"].metadata.name,
                "namespace": data["pod"].metadata.namespace,
                "owner": data["owner_info"],
                "labels": data["pod"].metadata.labels,
                "creation_timestamp": str(data["pod"].metadata.creation_timestamp)
            },
            "parent_controller_spec": data["parent_spec"],
            "current_health": {
                "phase": data["pod"].status.phase,
                "is_healthy": data["is_healthy"],
                "containers": data["container_statuses_summary"]
            },
        }

        # General triage hints — guide the AI's investigation, never prescribe a fix
        current_health = context.get("current_health", {})
        phase = current_health.get("phase")
        container_summaries = current_health.get("containers", [])
        
        if phase == "Pending":
            context["triage_hint"] = (
                "Pod is UNSCHEDULED (Pending). Common causes: insufficient node resources, "
                "node affinity/anti-affinity rules, taints without tolerations, unbound PersistentVolumeClaims, "
                "or resource requests exceeding node capacity. Investigate FailedScheduling events and node status."
            )
            # Always include resource and node info for Pending pods — the AI needs this context
            if "resource_requests" in data:
                context["resource_requests"] = data["resource_requests"]
            if "node_capacity" in data:
                context["node_capacity"] = data["node_capacity"]
        elif isinstance(container_summaries, list):
             for cs in container_summaries:
                 if not isinstance(cs, dict): continue
                 state = cs.get("state", {})
                 if not isinstance(state, dict): continue
                 waiting = state.get("waiting", {})
                 terminated = state.get("terminated", {})
                 if not isinstance(waiting, dict): waiting = {}
                 if not isinstance(terminated, dict): terminated = {}
                 reason = waiting.get("reason", "")
                 term_reason = terminated.get("reason", "")
                 if reason in ["CreateContainerConfigError", "InvalidImageName", "ImagePullBackOff"]:
                      context["triage_hint"] = (
                          "Pod is stuck in a pre-start state. Investigate missing ConfigMaps, Secrets, "
                          "invalid image references, or container configuration issues."
                      )
                      break
                 elif reason == "CrashLoopBackOff" or term_reason == "OOMKilled":
                      context["triage_hint"] = (
                          "Container is crash-looping or OOMKilled. Investigate container logs, resource limits, "
                          "startup commands, and health probe configurations."
                      )
                      break
        
        # Ownership guide
        if data["owner_info"] != "Standalone Pod":
            context["patch_target"] = f"You MUST patch the parent controller ({data['owner_info']}), NOT the pod directly."

        # We ALWAYS run the agent, even if K8s thinks it is healthy, because 
        # there might be subtle application-level issues (like DNS) that 
        # readiness probes haven't caught or aren't configured to catch.
        context["status"] = data["pod"].status.to_dict()
        context["events"] = [{
            "type": e.type, "reason": e.reason, "message": e.message, "last_timestamp": str(e.last_timestamp)
        } for e in data["events"].items]
        context["logs_preview"] = data["logs"][-2000:]

        from agent import DebuggerAgent
        agent = DebuggerAgent(provider="google")
        diagnosis_data = agent.diagnose(context)

        # Filter out destructive commands as a safety net (using same blacklist as /execute)
        destructive_blacklist = [
            "delete namespace", "delete clusterrole", "delete node", "delete pv",
            "delete deployment", "delete statefulset", "delete replicaset",
            "delete service", "delete daemonset", "delete all",
        ]
        if "fix_steps" in diagnosis_data and isinstance(diagnosis_data.get("fix_steps"), list):
            sanitized_steps = []
            for s in diagnosis_data["fix_steps"]:
                if isinstance(s, dict):
                    cmd = s.get("command", "").lower()
                    if not any(b in cmd for b in destructive_blacklist):
                        sanitized_steps.append(s)
                elif isinstance(s, str):
                    if not any(b in s.lower() for b in destructive_blacklist):
                        sanitized_steps.append({"label": "Fix", "command": s, "reasoning": "AI suggested fix", "type": "kubectl"})
            diagnosis_data["fix_steps"] = sanitized_steps

        return diagnosis_data
    except Exception as e:
        print(f"Diagnosis Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
def search_resources(q: str):
    from k8s_service import search_resources_logic
    return search_resources_logic(q)

# ── Retry Fix (Self-Correction) ──────────────────────────────────

class RetryFixRequest(BaseModel):
    failed_command: str
    error_message: str
    pod_name: Optional[str] = None
    namespace: str = "oncall-bench"
    diagnosis_context: Optional[dict] = None

@app.post("/retry-fix")
def retry_fix(request: RetryFixRequest):
    """When a fix command fails, send the error back to Gemini to get a corrected command."""
    if not client_genai:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")

    prompt = f"""A kubectl fix command failed. Analyze the error and provide a corrected command.

FAILED COMMAND:
{request.failed_command}

ERROR OUTPUT:
{request.error_message}

CONTEXT:
- Pod: {request.pod_name or 'unknown'}
- Namespace: {request.namespace}

RULES:
- Fix the command so it succeeds. Do NOT just explain the error.
- Commands must be non-interactive and idempotent.
- If the error is "already exists", use --dry-run=client -o yaml | kubectl apply -f - pattern.
- If the error is about missing fields, include all required fields.
- If a resource was created but pods need to pick it up, add a rollout restart.

Return ONLY a JSON object. Do not include markdown or terminal markers like EOF.
{{"corrected_steps": [{{"label": "string", "command": "corrected kubectl command", "reasoning": "why this fixes the error", "type": "kubectl"}}]}}"""

    try:
        response = client_genai.models.generate_content(model=model_name, contents=prompt)
        result = extract_json_from_text(response.text)
        if not result:
             raise ValueError("Could not extract result from AI response")
        return result
    except Exception as e:
        print(f"Retry Fix Error: {e}")
        raise HTTPException(status_code=500, detail=f"Retry error: {str(e)}")

# ── Evaluation (Benchmark Scoring) ───────────────────────────────

@app.post("/evaluate")
def evaluate_diagnosis(request: dict):
    """Score a diagnosis against the ground truth using Gemini as judge."""
    scenario_id = request.get("scenario_id")
    diagnosis = request.get("diagnosis", {})

    if not scenario_id:
        # Try to auto-detect scenario from pod name
        pod_name = request.get("pod_name", "")
        for d in SCENARIOS_DIR.iterdir():
            if d.is_dir() and d.name in pod_name:
                scenario_id = d.name
                break

    if not scenario_id:
        raise HTTPException(status_code=400, detail="Could not determine scenario_id")

    gt_path = SCENARIOS_DIR / scenario_id / "ground_truth.json"
    if not gt_path.exists():
        raise HTTPException(status_code=404, detail=f"No ground truth for scenario '{scenario_id}'")

    with open(gt_path, "r") as f:
        gt = json.load(f)

    if not client_genai:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")

    judge_prompt = f"""You are a fair and strict judge evaluating an AI SRE agent's performance.

Compare the PREDICTION against the GROUND TRUTH.

GROUND TRUTH:
- Root Cause: {gt['root_cause']}
- Fix Steps: {gt['fix_steps']}

PREDICTION:
- Root Cause: {diagnosis.get('root_cause', diagnosis.get('summary', 'N/A'))}
- Fix Commands: {json.dumps(diagnosis.get('fix_steps', []), default=str)}

Score these metrics from 0.0 to 1.0:
1. root_cause_match: Did the agent correctly identify the actual root cause?
2. fix_correctness: Are the suggested fix commands correct and would they resolve the issue?

Output ONLY a JSON object with these two keys and float values. Example: {{"root_cause_match": 0.85, "fix_correctness": 0.9}}"""

    try:
        response = client_genai.models.generate_content(model=model_name, contents=judge_prompt)
        scores = extract_json_from_text(response.text)
        if not scores:
             raise ValueError("Could not extract scores from judge response")

        scores["scenario_id"] = scenario_id
        scores["confidence_score"] = diagnosis.get("confidence_score", 0.8)
        scores["model_used"] = "gemini-2.0-flash"

        # Save the report
        reports_dir = BASE_DIR / "data" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / f"score_{scenario_id}.json"
        with open(report_file, "w") as f:
            json.dump(scores, f, indent=2)

        return scores
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation error: {str(e)}")

# ── AI Chat (Incident Commander) ─────────────────────────────────

class ChatMessage(BaseModel):
    message: str
    namespace: Optional[str] = None

@app.post("/chat")
def chat(request: ChatMessage):
    """AI Incident Commander — natural language interface to the cluster."""
    if not client_genai:
        raise HTTPException(status_code=503, detail="Gemini API key not configured.")

    ns = request.namespace or "oncall-bench"

    # Gather live cluster context for the AI
    cluster_context = ""
    try:
        pods_data = get_pods_logic(ns)
        pod_summary = "\n".join([
            f"  - {p.name}: {p.status} (healthy={p.is_healthy}, restarts={p.restarts})"
            for p in pods_data
        ])
        cluster_context += f"CURRENT PODS in namespace '{ns}':\n{pod_summary}\n\n"
    except Exception:
        cluster_context += f"(Could not fetch pods for namespace '{ns}')\n\n"

    try:
        events_data = get_events_logic(ns)
        warnings = [e for e in events_data if e.get("type") == "Warning"][:10]
        if warnings:
            event_summary = "\n".join([
                f"  - [{e['reason']}] {e['object_kind']}/{e['object_name']}: {e['message']}"
                for e in warnings
            ])
            cluster_context += f"RECENT WARNING EVENTS:\n{event_summary}\n\n"
    except Exception:
        pass

    prompt = f"""You are an expert SRE Incident Commander with access to a live Kubernetes cluster.
The user is asking about their cluster. Use the live context below to give accurate, actionable answers.

LIVE CLUSTER CONTEXT:
{cluster_context}

RULES:
1. Be concise but thorough. Format your response in markdown.
2. If you suggest kubectl commands, wrap each in a separate ```kubectl code block.
3. Explain your reasoning briefly.
4. If the cluster is healthy, say so — don't make up problems.
5. Focus on the namespace '{ns}' unless the user asks about something else.

USER QUESTION: {request.message}"""

    try:
        response = client_genai.models.generate_content(model=model_name, contents=prompt)
        text = response.text

        # Extract kubectl commands from the response for the UI execute buttons
        commands = []
        import re as _re
        # Improved regex to catch multi-line kubectl blocks
        for match in _re.finditer(r'```(?:kubectl|bash|sh)?\s*\n(kubectl .*?)\n```', text, _re.DOTALL):
            cmd = match.group(1).strip()
            # Collapse multiple lines into one for the execution button if it doesn't already have line continuations
            if "\n" in cmd and "\\" not in cmd:
                cmd = " ".join([line.strip() for line in cmd.split("\n")])
            commands.append(cmd)

        return {
            "response": text,
            "commands": commands,
            "namespace": ns
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

