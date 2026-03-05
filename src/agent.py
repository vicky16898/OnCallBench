import json
import os
import subprocess
import shlex
from pathlib import Path
from rich.console import Console
from openai import OpenAI
from google import genai
from typing import Dict, Any, List
from utils import extract_json_from_text
from dotenv import load_dotenv

load_dotenv()
console = Console()

def load_system_prompt() -> str:
    """Load the SRE system prompt from an external template file.
    Returns a fallback prompt if the file is missing.
    """
    template_path = Path(__file__).parent / "prompt_templates" / "k8s_system_prompt.txt"
    if template_path.is_file():
        return template_path.read_text(encoding="utf-8")
    return "You are a Principal SRE. Diagnose Kubernetes incidents using the provided bundle and available tools."

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
            # Reconstruct string for Windows shell resolution using official tool
            cmd_to_run = subprocess.list2cmdline(parts)
            result = subprocess.run(cmd_to_run, capture_output=True, text=True, timeout=15, shell=True)
        else:
            result = subprocess.run(parts, capture_output=True, text=True, timeout=15, shell=False)
            
        output = result.stdout if result.returncode == 0 else result.stderr
        return output[:5000] # Cap output to avoid context overflow
    except Exception as e:
        return str(e)

def cluster_wide_health_tool():
    """Returns cluster nodes status and resource usage to check for global issues."""
    try:
        import sys
        is_win = sys.platform == 'win32'
        
        # Get nodes and their resource usage
        cmds = [
            "kubectl get nodes -o wide",
            "kubectl top nodes"
        ]
        results = []
        for cmd in cmds:
            if is_win:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
            else:
                res = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=10, shell=False)
            results.append(f"--- {cmd} ---\n{res.stdout if res.returncode == 0 else res.stderr}")
            
        return "\n".join(results)
    except Exception as e:
        return f"Error fetching cluster health: {str(e)}"

def investigate_resource(kind: str, name: str, namespace: str):
    """Fetches full YAML for any K8s resource for deep inspection."""
    try:
        cmd = f"kubectl get {kind} {name} -n {namespace} -o yaml"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
        return res.stdout if res.returncode == 0 else res.stderr
    except Exception as e:
        return str(e)

def search_logs(pod_name: str, namespace: str, query: str = None):
    """Retrieves logs with optional search filtering."""
    try:
        cmd = f"kubectl logs {pod_name} -n {namespace} --tail=200"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
        logs = res.stdout if res.returncode == 0 else res.stderr
        
        if query and res.returncode == 0:
            lines = [l for l in logs.splitlines() if query.lower() in l.lower()]
            return "\n".join(lines) if lines else f"No log lines found matching: {query}"
        return logs
    except Exception as e:
        return str(e)

def check_metrics(target: str, namespace: str = None):
    """Retrieves resource usage (CPU/Mem)."""
    try:
        if target == "nodes":
            cmd = "kubectl top nodes"
        else:
            cmd = f"kubectl top pods -n {namespace}" if namespace else "kubectl top pods --all-namespaces"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
        return res.stdout if res.returncode == 0 else "Metrics API may not be available: " + res.stderr
    except Exception as e:
        return str(e)

def list_namespace_resources(namespace: str):
    """Lists all common resources in a namespace."""
    try:
        cmd = f"kubectl get all,configmap,secret,ingress,netpol -n {namespace}"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
        return res.stdout if res.returncode == 0 else res.stderr
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
            self.client = genai.Client(api_key=self.api_key)
            # For Gemini 2.0 via google-genai, tools are passed during generation
            self.tools = [run_kubectl_tool, cluster_wide_health_tool, investigate_resource, search_logs, check_metrics, list_namespace_resources]
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def diagnose(self, bundle: Dict[str, Any]):
        """Main entry point for diagnosis. Takes a dictionary bundle directly."""
        console.print(f"[bold blue]Agent ({self.provider}) starting multi-step diagnosis...[/bold blue]")
        self.investigation_steps = [{"command": "Initial Triage", "findings": "Analyzing pod metadata, logs, and events bundle..."}]
        
        try:
            if self.provider == "openai":
                return self._diagnose_openai(bundle)
            elif self.provider == "google":
                return self._diagnose_google(bundle)
        except Exception as e:
            console.print(f"[bold red]AI Diagnosis Failed: {str(e)}[/bold red]")
            return {
                "root_cause": f"AI Analysis Failed: {str(e)}",
                "symptoms": ["System error during diagnosis"],
                "fix_summary": "Please check your API keys and network connection.",
                "fix_steps": [{"label": "Troubleshoot Agent", "command": "echo Check logs", "reasoning": "AI provider returned an error", "type": "manual"}],
                "confidence_score": 0.0,
                "risk_level": "High"
            }

    def _diagnose_openai(self, bundle):
        # OpenAI implementation with tool-calling
        tools = [
            {
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
            },
            {
                "type": "function",
                "function": {
                    "name": "cluster_wide_health_tool",
                    "description": "Check cluster nodes and resource usage to see if the issue is global (e.g. Node Pressure).",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "investigate_resource",
                    "description": "Get full details of any K8s resource (Deployment, Service, Secret, etc.) if you suspect it is related to the issue.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "description": "e.g., Service, Secret, ConfigMap, RoleBinding"},
                            "name": {"type": "string", "description": "The name of the resource"},
                            "namespace": {"type": "string", "description": "The namespace of the resource"}
                        },
                        "required": ["kind", "name", "namespace"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_logs",
                    "description": "Retrieve logs for a pod with optional filtering to find specific error strings.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pod_name": {"type": "string"},
                            "namespace": {"type": "string"},
                            "query": {"type": "string", "description": "Optional search term to filter logs (e.g., 'Error', 'Timeout', 'Connection refused')"}
                        },
                        "required": ["pod_name", "namespace"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_metrics",
                    "description": "Get real-time CPU/Memory usage for nodes or pods.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "enum": ["nodes", "pods"]},
                            "namespace": {"type": "string", "description": "Required if target is 'pods'"}
                        },
                        "required": ["target"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_namespace_resources",
                    "description": "List all resources (Deployments, Services, Ingresses, etc.) in a namespace to understand the environment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"}
                        },
                        "required": ["namespace"]
                    }
                }
            }
        ]

        # triage_hint is already set by the caller (api.py run_diagnosis) based on pod state.
        # No need to duplicate that logic here — it arrives in the bundle.
        
        # Load dynamic system prompt from external template
        system_prompt = load_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Initial Incident Bundle:\n{json.dumps(bundle, default=str)[:10000]}"}
        ]
        
        for _ in range(5):
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools)
            msg = response.choices[0].message
            messages.append(msg)
            if not msg.tool_calls: break
            
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                if name == "run_kubectl_tool":
                    cmd = args['command']
                    console.print(f"[dim]Running: {cmd}[/dim]")
                    result = run_kubectl_tool(cmd)
                elif name == "investigate_resource":
                    cmd = f"kubectl get {args['kind']} {args['name']} -n {args['namespace']}"
                    console.print(f"[dim]Investigating: {cmd}[/dim]")
                    result = investigate_resource(args['kind'], args['name'], args['namespace'])
                elif name == "search_logs":
                    cmd = f"kubectl logs {args['pod_name']} (search: {args.get('query', 'N/A')})"
                    console.print(f"[dim]Searching Logs: {cmd}[/dim]")
                    result = search_logs(args['pod_name'], args['namespace'], args.get('query'))
                elif name == "check_metrics":
                    cmd = f"kubectl top {args['target']}"
                    console.print(f"[dim]Checking Metrics: {cmd}[/dim]")
                    result = check_metrics(args['target'], args.get('namespace'))
                elif name == "list_namespace_resources":
                    cmd = f"kubectl get all -n {args['namespace']}"
                    console.print(f"[dim]Listing Resources in {args['namespace']}[/dim]")
                    result = list_namespace_resources(args['namespace'])
                else: # cluster_wide_health_tool
                    cmd = "kubectl top nodes/nodes info"
                    console.print(f"[dim]Cluster Health Check[/dim]")
                    result = cluster_wide_health_tool()
                
                self.investigation_steps.append({
                    "command": cmd,
                    "findings": result[:500] + "..." if len(result) > 500 else result
                })
                
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": name, "content": result})

        messages.append({"role": "user", "content": "Provide Final Diagnosis as JSON. Return valid JSON only."})
        final_response = self.client.chat.completions.create(model=self.model, messages=messages, response_format={"type": "json_object"})
        diagnosis = json.loads(final_response.choices[0].message.content)
        diagnosis["investigation_steps"] = self.investigation_steps
        return diagnosis

    def _diagnose_google(self, bundle):
        # Gemini implementation with native tool-calling via google-genai
        # Load dynamic system prompt from external template (same as OpenAI path)
        system_prompt = load_system_prompt()
        
        chat = self.client.chats.create(
            model=self.model,
            config={
                "tools": self.tools,
                "system_instruction": system_prompt
            }
        )
        
        prompt = f"""INVESTIGATION: Every tool you call will be recorded. Use them to prove your theories.
        
        - For kubectl patch: -p value MUST be a JSON object with the FULL path starting at {{"spec":{{"template":{{"spec":...}}}}}}. NEVER a bare array.
        - K8s Structure: Containers go under spec.template.spec.containers. Volumes go under spec.template.spec.volumes.
        - Be an expert: diagnose → verify → provide minimal but sufficient fix steps.
        
        OUTPUT FORMAT (JSON):
        {{
          "root_cause": "string",
          "symptoms": ["string"],
          "fix_summary": "string",
          "fix_steps": [{{"label": "string", "command": "string", "reasoning": "string", "type": "kubectl|manual|investigation"}}],
          "confidence_score": 0.9,
          "risk_level": "Low"
        }}
        
        Respond only with the valid JSON object. Do not add markdown backticks, EOF, or any other explanations.
        Incident Bundle:
        {json.dumps(bundle, default=str)[:50000]}"""
        
        try:
            response = chat.send_message(prompt)
            text = response.text
            
            # Extract investigation steps from history
            # In google-genai, history is accessed via get_history()
            calls = {}
            for msg in chat.get_history():
                if msg.role == "model":
                    for part in msg.parts:
                        if part.function_call:
                            # Map function call to its arguments
                            fn = part.function_call
                            args = fn.args
                            # Some SDK versions might return args as a string
                            if isinstance(args, str):
                                try:
                                     args = json.loads(args)
                                except:
                                     args = {}
                            
                            cmd = args.get("command", fn.name) if isinstance(args, dict) else fn.name
                            calls[fn.name] = cmd
                elif msg.role == "user" or msg.role == "tool":
                    for part in msg.parts:
                        if part.function_response:
                            fn_resp = part.function_response
                            cmd = calls.get(fn_resp.name, fn_resp.name)
                            # Handle different response types (result vs content)
                            res_obj = fn_resp.response
                            # Robust extraction: res_obj might be a dict or an object depending on version
                            if isinstance(res_obj, dict):
                                resp_text = str(res_obj.get("result", res_obj))
                            else:
                                try:
                                    resp_text = str(getattr(res_obj, 'result', res_obj))
                                except:
                                    resp_text = str(res_obj)
                            
                            self.investigation_steps.append({
                                "command": cmd,
                                "findings": resp_text[:500] + "..." if len(resp_text) > 500 else resp_text
                            })
        except Exception as e:
            print(f"Agent Error: {e}")
            text = str(e)

        diagnosis = extract_json_from_text(text)
        if diagnosis:
            diagnosis["investigation_steps"] = self.investigation_steps
            return diagnosis
            
        return {
            "root_cause": text[:500],
            "symptoms": ["Analysis completed"],
            "fix_summary": "Manual review needed",
            "fix_steps": [{"label": "Review pods", "command": "kubectl get pods", "reasoning": "Fallback", "type": "manual"}],
            "investigation_steps": self.investigation_steps,
            "confidence_score": 0.5,
            "risk_level": "Medium"
        }
