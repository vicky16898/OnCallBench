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

load_dotenv()

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
try:
    config.load_kube_config()
except Exception:
    try:
        config.load_incluster_config()
    except Exception:
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

class PodStatus(BaseModel):
    name: str
    status: str
    restarts: int
    age: str
    is_healthy: bool

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
            # Check health: pod must be Running and all containers must be ready.
            # Note: restart_count > 0 alone does NOT mean unhealthy — pods
            # accumulate restarts over their lifetime (e.g. node reboots).
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

# Handle paths relative to the project root
BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = BASE_DIR / "scenarios"

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
        pod = v1.read_namespaced_pod(request.pod_name, request.namespace)
        events = v1.list_namespaced_event(request.namespace, field_selector=f"involvedObject.name={request.pod_name}")
        
        # Get related resources (Deployment/ReplicaSet)
        owner_info = "Standalone Pod"
        if pod.metadata.owner_references:
            owner = pod.metadata.owner_references[0]
            owner_info = f"{owner.kind}/{owner.name}"

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
            "current_health": {
                "phase": pod.status.phase,
                "is_healthy": is_healthy,
                "containers": container_statuses_summary
            },
        }

        if is_healthy:
            # For healthy pods: minimal context, clear healthy framing
            # Don't send raw logs/events that contain old errors — they confuse the AI
            context["summary"] = "Pod is Running with all containers Ready. No current issues detected."
            prompt = f"""
            You are a Kubernetes Expert (Lens-style assistant).
            
            VERDICT: THIS POD IS CONFIRMED HEALTHY.
            - Phase: Running
            - All containers: Ready
            - The pod is functioning normally.
            
            Any errors in historical logs are from PAST restarts (e.g. node reboots) and are
            NOT current issues. Do NOT report old log errors as current problems.
            
            DATA:
            {json.dumps(context, default=str)}
            
            Respond with a JSON health report confirming the pod is healthy:
            - root_cause: state that the pod is healthy and operating normally
            - symptoms: empty list or list with "No issues detected"
            - fix_summary: state no action needed, pod is running as expected
            - fix_steps: list 1-2 optional best-practice suggestions (e.g. monitoring, resource review) with type "manual"
            - confidence_score: 0.95 or higher
            - risk_level: "Low"
            
            Output MUST be valid JSON only.
            """
        else:
            # For unhealthy pods: full diagnostic with logs and events
            context["status"] = pod.status.to_dict()
            context["events"] = [{
                "type": e.type, "reason": e.reason, 
                "message": e.message, 
                "last_timestamp": str(e.last_timestamp)
            } for e in events.items]
            context["logs_preview"] = logs[-2000:]

            prompt = f"""
            You are a Kubernetes Expert (Lens-style assistant). Analyze this pod incident.
            This pod is currently UNHEALTHY and needs diagnosis.
            
            DATA:
            {json.dumps(context, default=str)}
            
            Output MUST be a valid JSON with:
            - root_cause: string
            - symptoms: list of strings
            - fix_summary: string
            - fix_steps: list of objects with {{ "label": string, "command": string, "type": "kubectl|manual|edit" }}
            - confidence_score: float
            - risk_level: High|Medium|Low
            """

        response = model.generate_content(prompt)
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            # Gemini returned unparseable output — return a structured fallback
            return {
                "root_cause": text.strip()[:500] if text.strip() else "AI returned an unparseable response.",
                "symptoms": ["Could not parse AI response as structured JSON"],
                "fix_summary": "Please retry the diagnosis.",
                "fix_steps": [],
                "confidence_score": 0.0,
                "risk_level": "Low"
            }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
