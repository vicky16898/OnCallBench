import json
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from google import genai
from utils import extract_json_from_text
from dotenv import load_dotenv

load_dotenv()

console = Console()

class Evaluator:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Missing GOOGLE_API_KEY in .env")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-2.0-flash"

    def score(self, scenario_id: str, prediction_path: Path):
        scenario_dir = Path(__file__).parent.parent / "scenarios" / scenario_id
        gt_path = scenario_dir / "ground_truth.json"

        if not gt_path.exists() or not prediction_path.exists():
            console.print("[red]Ground truth or prediction missing.[/red]")
            return None

        with open(gt_path, "r") as f:
            gt = json.load(f)
        with open(prediction_path, "r") as f:
            pred = json.load(f)

        console.print(f"Scoring prediction for {scenario_id}...")

        judge_prompt = f"""You are a fair and strict judge evaluating an AI SRE agent's performance.

Compare the PREDICTION against the GROUND TRUTH.

GROUND TRUTH:
- Root Cause: {gt['root_cause']}
- Fix Steps: {gt['fix_steps']}

PREDICTION:
- Root Cause: {pred.get('root_cause', 'N/A')}
- Fix Commands: {pred.get('fix_commands', pred.get('fix_steps', 'N/A'))}

Score these metrics from 0.0 to 1.0:
1. root_cause_match: Did the agent correctly identify the actual root cause?
2. fix_correctness: Are the fix commands correct and would they resolve the issue?

Output ONLY a JSON object with these two keys and float values."""

        response = self.client.models.generate_content(model=self.model_name, contents=judge_prompt)
        scores = extract_json_from_text(response.text)
        if not scores:
             raise ValueError("Could not extract scores from judge response")
        scores["scenario_id"] = scenario_id
        scores["confidence_score"] = pred.get("confidence_score", 0)
        scores["model_used"] = "gemini-2.0-flash"

        report_file = Path(__file__).parent.parent / "data" / "reports" / f"score_{scenario_id}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(scores, f, indent=2)

        console.print(f"[bold green]Score saved: root_cause={scores['root_cause_match']}, fix={scores['fix_correctness']}[/bold green]")
        return scores

    def generate_summary(self):
        reports_dir = Path(__file__).parent.parent / "data" / "reports"
        if not reports_dir.exists():
            console.print("No reports found.")
            return

        table = Table(title="OnCallBench Performance Report")
        table.add_column("Scenario", style="cyan")
        table.add_column("Root Cause Match", style="magenta")
        table.add_column("Fix Correctness", style="green")
        table.add_column("Agent Confidence", style="yellow")
        table.add_column("Model", style="dim")

        for report_file in sorted(reports_dir.glob("score_*.json")):
            with open(report_file, "r") as f:
                data = json.load(f)
                table.add_row(
                    data["scenario_id"],
                    f"{data['root_cause_match']:.0%}",
                    f"{data['fix_correctness']:.0%}",
                    f"{data.get('confidence_score', 0):.0%}",
                    data.get("model_used", "unknown")
                )

        console.print(table)
