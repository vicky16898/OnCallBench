import subprocess
import os
from pathlib import Path
from rich.console import Console

console = Console()

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"

def run_kubectl(args: list):
    cmd = ["kubectl"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[bold red]Error running kubectl:[/bold red] {result.stderr}")
    return result

def inject_scenario(scenario_id: str):
    scenario_path = SCENARIOS_DIR / scenario_id
    manifest_path = scenario_path / "manifest.yaml"
    
    if not manifest_path.exists():
        console.print(f"[bold red]Scenario '{scenario_id}' not found at {manifest_path}[/bold red]")
        return False
    
    console.print(f"Applying manifest for {scenario_id}...")
    run_kubectl(["apply", "-f", str(manifest_path)])
    console.print(f"[bold green]Scenario {scenario_id} injected successfully.[/bold green]")
    return True

def cleanup_namespace(namespace: str = "oncall-bench"):
    console.print(f"Cleaning up namespace {namespace}...")
    run_kubectl(["delete", "all", "--all", "-n", namespace])
