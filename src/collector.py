import subprocess
import json
import os
from pathlib import Path
from rich.console import Console

console = Console()

def run_kubectl(args: list):
    cmd = ["kubectl"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def collect_evidence(scenario_id: str, namespace: str = "oncall-bench"):
    bundle = {
        "scenario_id": scenario_id,
        "timestamp": str(os.path.getmtime(__file__)), # Rough timestamp
        "namespace_info": {},
        "pods": [],
        "events": ""
    }
    
    console.print(f"Collecting pods for {scenario_id}...")
    pod_list_raw = run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])
    try:
        pods_data = json.loads(pod_list_raw)
        bundle["pods_raw"] = pods_data
    except:
        bundle["pods_raw"] = pod_list_raw

    # Collect detailed info for each pod
    pods = run_kubectl(["get", "pods", "-n", namespace, "-o", "name"]).splitlines()
    for pod_name in pods:
        pod_name = pod_name.replace("pod/", "")
        console.print(f"  Fetching details for {pod_name}...")
        
        pod_info = {
            "name": pod_name,
            "describe": run_kubectl(["describe", "pod", pod_name, "-n", namespace]),
            "logs_current": run_kubectl(["logs", pod_name, "-n", namespace, "--tail=100"]),
            "logs_previous": run_kubectl(["logs", pod_name, "-n", namespace, "--previous", "--tail=100"])
        }
        bundle["pods"].append(pod_info)
    
    console.print("Collecting events...")
    bundle["events"] = run_kubectl(["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"])
    
    # Optional: metrics-server
    console.print("Checking metrics...")
    bundle["metrics"] = run_kubectl(["top", "pod", "-n", namespace])
    
    output_dir = Path("data/bundles")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"bundle_{scenario_id}.json"
    
    with open(output_file, "w") as f:
        json.dump(bundle, f, indent=2)
    
    console.print(f"[bold green]Evidence bundle saved to {output_file}[/bold green]")
    return output_file
