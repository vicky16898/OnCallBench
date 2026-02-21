import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from openai import OpenAI
import os

console = Console()

class Evaluator:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)

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
        
        # LLM-as-a-Judge for root cause and fix match
        judge_prompt = f"""
        Compare the Predicted diagnosis and fix against the Ground Truth.
        
        GROUND TRUTH:
        Root Cause: {gt['root_cause']}
        Fix: {gt['fix_steps']}
        
        PREDICTION:
        Root Cause: {pred.get('root_cause')}
        Fix Commands: {pred.get('fix_commands')}
        
        Evaluate the following metrics (scale 0 to 1):
        1. root_cause_match: Did the agent find the actual root cause?
        2. fix_correctness: Are the fix commands correct and would they resolve the issue?
        
        Output ONLY a JSON object with these two keys and float values.
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a fair judge of SRE skills."},
                      {"role": "user", "content": judge_prompt}],
            response_format={"type": "json_object"}
        )
        
        scores = json.loads(response.choices[0].message.content)
        scores["scenario_id"] = scenario_id
        scores["confidence_score"] = pred.get("confidence_score", 0)
        
        report_file = Path("data/reports") / f"score_{scenario_id}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(scores, f, indent=2)
            
        return scores

    def generate_summary(self):
        reports_dir = Path("data/reports")
        if not reports_dir.exists():
            console.print("No reports found.")
            return

        table = Table(title="OnCallBench Performance Report")
        table.add_column("Scenario", style="cyan")
        table.add_column("Root Cause Match", style="magenta")
        table.add_column("Fix Correctness", style="green")
        table.add_column("Agent Confidence", style="yellow")
        
        for report_file in reports_dir.glob("score_*.json"):
            with open(report_file, "r") as f:
                data = json.load(f)
                table.add_row(
                    data["scenario_id"],
                    str(data["root_cause_match"]),
                    str(data["fix_correctness"]),
                    str(data["confidence_score"])
                )
        
        console.print(table)
