import json
import os
import subprocess
import shlex
from pathlib import Path
from rich.console import Console
from openai import OpenAI
import google.generativeai as genai
from typing import Dict, Any, List

console = Console()

def run_kubectl_tool(command: str):
    """Executes a kubectl command safely for the agent."""
    allowed = ["get", "describe", "logs", "top", "events"]
    # Be more flexible: allow 'kubectl get pods' or 'kubectl describe node'
    parts = shlex.split(command)
    if not parts or parts[0] != "kubectl":
        return "Error: Command must start with 'kubectl'."
    
    if len(parts) < 2 or parts[1] not in allowed:
        return f"Error: Only {', '.join(allowed)} commands are allowed for security."
    
    try:
        # Avoid destructive flags
        if any(flag in command.lower() for flag in ["delete", "purge", "force", "replace"]):
             return "Error: Destructive flags are not allowed."
             
        import sys
        is_win = sys.platform == 'win32'
        
        if is_win:
            # Reconstruct string for Windows shell resolution
            cmd_to_run = " ".join(f'"{a}"' if " " in a or "\\" in a else a for a in parts)
            result = subprocess.run(cmd_to_run, capture_output=True, text=True, timeout=15, shell=True)
        else:
            result = subprocess.run(parts, capture_output=True, text=True, timeout=15, shell=False)
            
        output = result.stdout if result.returncode == 0 else result.stderr
        return output[:5000] # Cap output to avoid context overflow
    except Exception as e:
        return str(e)

from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

class DebuggerAgent:
    def __init__(self, provider="google", model=None):
        self.provider = provider.lower()
        if self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.model = model or "gpt-4o"
            self.client = OpenAI(api_key=self.api_key)
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_API_KEY")
            if not self.api_key:
                 raise ValueError("Missing GOOGLE_API_KEY in .env")
            self.model = model or "gemini-2.0-flash"
            genai.configure(api_key=self.api_key)
            # Define tools for Gemini
            self.tools = [run_kubectl_tool]
            self.client = genai.GenerativeModel(
                model_name=self.model,
                tools=self.tools
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def diagnose(self, bundle: Dict[str, Any]):
        """Main entry point for diagnosis. Takes a dictionary bundle directly."""
        console.print(f"[bold blue]Agent ({self.provider}) starting multi-step diagnosis...[/bold blue]")
        
        if self.provider == "openai":
            return self._diagnose_openai(bundle)
        elif self.provider == "google":
            return self._diagnose_google(bundle)

    def _diagnose_openai(self, bundle):
        # OpenAI implementation with tool-calling
        tools = [{
            "type": "function",
            "function": {
                "name": "run_kubectl_tool",
                "description": "Run a kubectl command (get, describe, logs, top, events) to gather more info.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The full kubectl command, e.g. 'kubectl describe pod mypod'"}
                    },
                    "required": ["command"]
                }
            }
        }]
        
        messages = [
            {"role": "system", "content": """You are a Principal SRE. Your goal is to find the technical root cause of a K8s incident.
            
            STRATEGY:
            1. Analyze the initial bundle.
            2. Run extra kubectl commands to verify your theory (describe failing resources, check events).
            3. If you find a clear fix, provide it.
            4. If you CANNOT find a clear fix, provide a detailed "Manual Investigation Guide" to help a human SRE finish the job.
            
            OUTPUT FORMAT (JSON):
            - root_cause: string
            - symptoms: list of strings
            - fix_summary: string
            - fix_steps: list of {label, command, reasoning, type: "kubectl"|"manual"|"investigation"}
            - confidence_score: float
            - risk_level: High|Medium|Low
            """},
            {"role": "user", "content": f"Initial Incident Bundle:\n{json.dumps(bundle, default=str)[:10000]}"}
        ]
        
        for _ in range(5): # Up to 5 turns of investigation
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools)
            msg = response.choices[0].message
            messages.append(msg)
            if not msg.tool_calls: break
            
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                console.print(f"[dim]Running: {args['command']}[/dim]")
                result = run_kubectl_tool(args['command'])
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": "run_kubectl_tool", "content": result})

        messages.append({"role": "user", "content": "Provide Final Diagnosis as JSON. If no fix is found, use 'fix_steps' to provide investigation pointers with type 'investigation'."})
        final_response = self.client.chat.completions.create(model=self.model, messages=messages, response_format={"type": "json_object"})
        return json.loads(final_response.choices[0].message.content)

    def _diagnose_google(self, bundle):
        # Gemini implementation with native tool-calling
        chat = self.client.start_chat(enable_automatic_function_calling=True)
        
        system_instructions = """You are a Principal SRE. Find the technical root cause of this K8s incident.
        Analyze the bundle, run extra commands if needed, and provide the fix.
        
        CRITICAL RULES FOR FIXES:
        1. NEVER suggest interactive commands like 'kubectl edit' or 'kubectl exec -it'. These cannot be automated.
        2. ALWAYS prioritize 'kubectl set image' for image issues.
        3. ALWAYS prioritize 'kubectl patch' for configuration/env/resource issues.
        4. If the command can be run non-interactively, use type: "kubectl". This enables the 'Execute' button.
        5. Only use type: "manual" for things that truly require a human (e.g., "Check the external firewall").
        
        OUTPUT FORMAT (JSON):
        Respond with ONLY a JSON object:
        {
          "root_cause": "string",
          "symptoms": ["string"],
          "fix_summary": "string",
          "fix_steps": [{"label": "string", "command": "string", "reasoning": "string", "type": "kubectl|manual|investigation"}],
          "confidence_score": 0.9,
          "risk_level": "Low"
        }"""
        
        prompt = f"{system_instructions}\n\nIncident Bundle:\n{json.dumps(bundle, default=str)[:10000]}"
        
        response = chat.send_message(prompt)
        text = response.text
        
        # Extract JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        try:
            return json.loads(text.strip())
        except Exception:
            # Fallback if AI didn't return valid JSON
            return {
                "root_cause": text[:500],
                "symptoms": ["Analysis completed"],
                "fix_summary": "Manual review needed",
                "fix_steps": [{"label": "Review logs", "command": "kubectl logs ...", "reasoning": "AI returned text response", "type": "manual"}],
                "confidence_score": 0.5,
                "risk_level": "Medium"
            }
