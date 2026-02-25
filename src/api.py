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
import google.generativeai as genai
from dotenv import load_dotenv
from kubernetes import client

# Local imports
from schemas import DiagnosticRequest, CommandExecutionRequest, PodStatus
from utils import _repair_json, _prepare_kubectl_command
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

app = FastAPI(title="OnCallBench AI Debugger API")

# Enable CORS for the GUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gemini Config
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    model = None

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = BASE_DIR / "scenarios"

@app.get("/info")
async def get_info():
    return {
        "mode": K8S_MODE,
        "api_ready": GOOGLE_API_KEY is not None,
        "version": "1.0.0"
    }

@app.post("/execute")
async def execute_command(request: CommandExecutionRequest):
    cmd = request.command.strip()
    if not cmd.startswith("kubectl"):
        raise HTTPException(status_code=400, detail="Only 'kubectl' commands are allowed for security.")
    
    blacklist = [
        "delete namespace", "delete clusterrole", "delete node", "delete pv",
        "delete deployment", "delete statefulset", "delete replicaset",
        "delete service", "delete daemonset", "delete all",
    ]
    if any(b in cmd.lower() for b in blacklist):
        raise HTTPException(status_code=400, detail="Destructive resource-level deletes are blocked.")

    temp_path = None
    try:
        args, temp_path = _prepare_kubectl_command(cmd)
        is_win = sys.platform == 'win32'
        if is_win:
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
        raise HTTPException(status_code=504, detail="Command timed out after 30 seconds.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except OSError: pass

# ── K8s Resource Routes ──────────────────────────────────────────

@app.get("/namespaces")
async def get_namespaces():
    try: return get_namespaces_logic()
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/pods")
async def get_pods(namespace: str):
    try: return get_pods_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/deployments")
async def get_deployments(namespace: str):
    try: return get_deployments_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/statefulsets")
async def get_statefulsets(namespace: str):
    try: return get_statefulsets_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/daemonsets")
async def get_daemonsets(namespace: str):
    try: return get_daemonsets_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/events")
async def get_events(namespace: str):
    try: return get_events_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/services")
async def get_services(namespace: str):
    try: return get_services_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/ingresses")
async def get_ingresses(namespace: str):
    try: return get_ingresses_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/networkpolicies")
async def get_network_policies(namespace: str):
    try: return get_network_policies_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/topology")
async def get_topology(namespace: str):
    try: return get_topology_logic(namespace)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats(namespace: Optional[str] = None):
    return get_stats_logic(namespace)

# ── Scenario Routes ─────────────────────────────────────────────

@app.get("/scenarios")
async def list_scenarios():
    scenarios = []
    if not SCENARIOS_DIR.exists(): return []
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
                except: pass
    return scenarios

@app.get("/benchmarks")
async def get_benchmarks():
    reports_dir = BASE_DIR / "data" / "reports"
    benchmarks = []
    if not reports_dir.exists(): return []
    for report_file in reports_dir.glob("score_*.json"):
        try:
            with open(report_file, "r") as f:
                benchmarks.append(json.load(f))
        except: pass
    return benchmarks

@app.post("/inject/{scenario_id}")
async def inject_failure(scenario_id: str):
    manifest_path = SCENARIOS_DIR / scenario_id / "manifest.yaml"
    if not manifest_path.exists(): raise HTTPException(status_code=404, detail="Scenario not found")
    try:
        cmd = ["kubectl", "apply", "-f", str(manifest_path)]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"status": "success", "message": f"Scenario {scenario_id} injected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Diagnosis Route ──────────────────────────────────────────────

@app.post("/diagnose")
async def diagnose(request: DiagnosticRequest):
    try:
        try:
            data = gather_pod_data_for_diagnosis(request.namespace, request.pod_name)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                raise HTTPException(status_code=404, detail=f"Pod '{request.pod_name}' no longer exists.")
            raise e

        # Build context
        context = {
            "metadata": {
                "name": data["pod"].metadata.name,
                "namespace": data["pod"].metadata.namespace,
                "owner": data["owner_info"],
                "creation_timestamp": str(data["pod"].metadata.creation_timestamp)
            },
            "parent_controller_spec": data["parent_spec"],
            "current_health": {
                "phase": data["pod"].status.phase,
                "is_healthy": data["is_healthy"],
                "containers": data["container_statuses_summary"]
            },
        }

        if data["is_healthy"]:
            context["summary"] = "Pod is Running with all containers Ready."
            prompt = f"VERDICT: HEALTHY. Respond with JSON health report: {json.dumps(context, default=str)}"
            response = model.generate_content(prompt)
            text = response.text
            if "```json" in text: text = text.split("```json")[1].split("```")[0]
            diagnosis_data = json.loads(text.strip())
            diagnosis_data["investigation_steps"] = [{"command": "Health Check", "findings": "All containers are Running and Ready. No anomalies found."}]
        else:
            context["status"] = data["pod"].status.to_dict()
            context["events"] = [{
                "type": e.type, "reason": e.reason, "message": e.message, "last_timestamp": str(e.last_timestamp)
            } for e in data["events"].items]
            context["logs_preview"] = data["logs"][-2000:]

            from agent import DebuggerAgent
            agent = DebuggerAgent(provider="google")
            diagnosis_data = agent.diagnose(context)

        # Post-process fixes
        if "fix_steps" in diagnosis_data:
            for step in diagnosis_data["fix_steps"]:
                cmd = step.get("command", "")
                if "patch" in cmd and ("-p " in cmd or "-p'" in cmd):
                    try:
                        cmd_clean = cmd.replace("'", "")
                        start = max(cmd_clean.find('{'), cmd_clean.find('['))
                        if start != -1:
                            raw = cmd_clean[start:]
                            clean = raw.replace('\\"', '"').replace('\\\\', '\\')
                            repaired = _repair_json(clean) or _repair_json(raw)
                            if repaired:
                                prefix_match = re.search(r'(-p|--patch)\s*', cmd_clean)
                                prefix = cmd_clean[:prefix_match.start()].strip() if prefix_match else cmd_clean[:start].strip()
                                step["command"] = f"{prefix} -p '{repaired}'"
                    except: pass
            
            diagnosis_data["fix_steps"] = [s for s in diagnosis_data["fix_steps"] if "delete" not in s.get("command", "").lower()]

        return diagnosis_data
    except Exception as e:
        print(f"Diagnosis Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
