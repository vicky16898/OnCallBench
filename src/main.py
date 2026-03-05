import typer
import json
from pathlib import Path
from rich.console import Console
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from injector import inject_scenario, cleanup_namespace, run_kubectl
from collector import collect_evidence
from agent import DebuggerAgent
from evaluator import Evaluator

app = typer.Typer(help="OnCallBench: K8s Incident Simulator + AI Debugger")
console = Console()

@app.command()
def init():
    """Initialize cluster and namespace."""
    console.print("[bold blue]Initializing OnCallBench...[/bold blue]")
    # Check if namespace exists, create if not
    run_kubectl(["create", "namespace", "oncall-bench"])
    console.print("Namespace 'oncall-bench' initialized.")

@app.command()
def inject(scenario: str = typer.Option(..., help="Scenario ID to inject")):
    """Inject a specific failure scenario."""
    console.print(f"[bold red]Injecting scenario: {scenario}[/bold red]")
    inject_scenario(scenario)

@app.command()
def collect(scenario: str = typer.Option(..., help="Scenario ID to collect evidence for")):
    """Collect evidence for the incident."""
    console.print(f"[bold yellow]Collecting evidence for: {scenario}[/bold yellow]")
    collect_evidence(scenario)

@app.command()
def diagnose(
    bundle: Path = typer.Option(..., help="Path to incident bundle JSON"),
    provider: str = typer.Option("openai", help="AI provider: 'openai' or 'google'"),
    model: str = typer.Option(None, help="Specific model name (e.g. 'gpt-4o' or 'gemini-1.5-flash')")
):
    """Run the AI debugger on the collected bundle."""
    console.print(f"[bold magenta]Diagnosing bundle: {bundle} using {provider}[/bold magenta]")
    agent = DebuggerAgent(provider=provider, model=model)
    agent.diagnose(bundle)

@app.command()
def score(scenario: str, prediction: Path):
    """Score the agent output vs ground truth."""
    console.print(f"[bold cyan]Scoring prediction for {scenario}...[/bold cyan]")
    evaluator = Evaluator()
    evaluator.score(scenario, prediction)

@app.command()
def report():
    """Generate a summary report."""
    console.print("[bold green]Generating report...[/bold green]")
    evaluator = Evaluator()
    evaluator.generate_summary()

@app.command()
def cleanupReady():
    """Clean up the oncall-bench namespace."""
    cleanup_namespace()

if __name__ == "__main__":
    app()
