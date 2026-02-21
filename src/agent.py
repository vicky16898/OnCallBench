import json
import os
import subprocess
from pathlib import Path
from rich.console import Console
from openai import OpenAI
import google.generativeai as genai

console = Console()

def run_kubectl_tool(command: str):
    """Executes a kubectl command safely for the agent."""
    allowed = ["get", "describe", "logs", "top"]
    if not any(command.startswith(f"kubectl {a}") for a in allowed):
        return "Error: Command not allowed for security reasons."
    
    cmd = command.split()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout if result.returncode == 0 else result.stderr
    except Exception as e:
        return str(e)

from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

class DebuggerAgent:
    def __init__(self, provider="openai", model=None):
        self.provider = provider.lower()
        if self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.api_key or self.api_key == "your_openai_key_here":
                raise ValueError("Missing or invalid OPENAI_API_KEY. Please set it in your .env file.")
            self.model = model or "gpt-4o"
            self.client = OpenAI(api_key=self.api_key)
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_API_KEY")
            if not self.api_key or self.api_key == "your_google_key_here":
                raise ValueError("Missing or invalid GOOGLE_API_KEY. Please set it in your .env file.")
            self.model = model or "models/gemini-2.0-flash"
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def diagnose(self, bundle_path: Path):
        with open(bundle_path, "r") as f:
            bundle = json.load(f)
        
        console.print(f"[bold blue]Agent ({self.provider}) starting diagnosis for: {bundle.get('scenario_id')}[/bold blue]")
        
        if self.provider == "openai":
            return self._diagnose_openai(bundle)
        elif self.provider == "google":
            return self._diagnose_google(bundle)

    def _diagnose_openai(self, bundle):
        tools = [{
            "type": "function",
            "function": {
                "name": "run_kubectl_tool",
                "description": "Run a kubectl command (get, describe, logs, top) to gather more info.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The full kubectl command"}
                    },
                    "required": ["command"]
                }
            }
        }]
        
        messages = [
            {"role": "system", "content": "You are a senior K8s SRE. Analyze the bundle and run extra checks if needed."},
            {"role": "user", "content": f"Initial Incident Bundle:\n{json.dumps(bundle)[:5000]}"}
        ]
        
        for _ in range(3):
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools)
            msg = response.choices[0].message
            messages.append(msg)
            if not msg.tool_calls: break
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = run_kubectl_tool(args['command'])
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": "run_kubectl_tool", "content": result[:2000]})

        messages.append({"role": "user", "content": "Provide Final Answer as JSON: root_cause, fix_commands (list), confidence_score."})
        final_response = self.client.chat.completions.create(model=self.model, messages=messages, response_format={"type": "json_object"})
        return self._save_prediction(json.loads(final_response.choices[0].message.content), bundle.get('scenario_id'))

    def _diagnose_google(self, bundle):
        # Gemini version with simplified tool-like flow (Gemini supports tools, but let's keep it simple for MVP)
        prompt = f"""
        You are a senior K8s SRE. Analyze this incident bundle:
        {json.dumps(bundle)[:10000]}
        
        Identify the root cause and provide fix commands.
        Output ONLY a JSON object with:
        - root_cause: string
        - fix_commands: list of strings
        - confidence_score: float
        """
        response = self.client.generate_content(prompt)
        # Handle potential markdown in response
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        return self._save_prediction(json.loads(text), bundle.get('scenario_id'))

    def _save_prediction(self, prediction, scenario_id):
        output_file = Path("data/predictions") / f"pred_{scenario_id}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(prediction, f, indent=2)
        console.print(f"[bold green]Diagnosis complete. Saved to {output_file}[/bold green]")
        return prediction, output_file
