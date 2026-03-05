import os
import json
import shlex
import sys
import subprocess
import re
import tempfile

def _repair_json(s):
    """Repair common AI-generated JSON errors (mismatched braces/brackets, extra closers)."""
    import json as _json
    # Try as-is first
    try:
        return _json.dumps(_json.loads(s))
    except (ValueError, _json.JSONDecodeError):
        pass
    
    # Strategy 1: Stack-based brace/bracket rebalancing
    stack = []
    result = []
    in_string = False
    escape_next = False
    
    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            result.append(ch)
            continue
        if ch in '{[':
            stack.append(ch)
            result.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
                result.append(ch)
            elif stack and stack[-1] == '[':
                stack.pop()
                result.append(']')
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()
                result.append(ch)
            elif stack and stack[-1] == '{':
                stack.pop()
                result.append('}')
        else:
            result.append(ch)
    
    while stack:
        opener = stack.pop()
        result.append('}' if opener == '{' else ']')
    
    repaired = ''.join(result)
    
    # Clean up common AI artifacts in JSON
    repaired = repaired.replace(": True", ": true").replace(": False", ": false").replace(": None", ": null")
    
    try:
        return _json.dumps(_json.loads(repaired))
    except (ValueError, _json.JSONDecodeError):
        pass
    
    # Strategy 2: Trim trailing junk
    for trim in range(1, min(8, len(s))):
        try:
            return _json.dumps(_json.loads(s[:-trim]))
        except (ValueError, _json.JSONDecodeError):
            continue
    
    return None


def extract_json_from_text(text):
    """Robustly extracts and parses JSON from a string, handles markdown and malformed content."""
    if not text:
        return None
        
    # 1. Try simple json.loads
    try:
        return json.loads(text.strip())
    except:
        pass
        
    # 2. Try to find JSON block via markdown tags
    import re
    json_block = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if json_block:
        candidate = json_block.group(1).strip()
        repaired = _repair_json(candidate)
        if repaired:
            try: return json.loads(repaired)
            except: pass
            
    # 3. Try any backtick block
    any_block = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
    if any_block:
        candidate = any_block.group(1).strip()
        repaired = _repair_json(candidate)
        if repaired:
            try: return json.loads(repaired)
            except: pass
            
    # 4. Find first { or [ and last } or ]
    brace_match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(1).strip()
        repaired = _repair_json(candidate)
        if repaired:
            try: return json.loads(repaired)
            except: pass
            
    return None


def _prepare_kubectl_command(cmd):
    """
    Platform-agnostic kubectl command preparation.
    Now correctly handles flags that appear AFTER the JSON patch.
    """
    import tempfile
    import json as _json
    import re
    
    temp_path = None
    cmd_lower = cmd.lower()
    has_patch_flag = ("-p " in cmd_lower or "-p'" in cmd_lower or '-p"' in cmd_lower
                      or "--patch " in cmd_lower or "--patch=" in cmd_lower)
    is_patch = "patch" in cmd_lower and has_patch_flag
    
    # 1. Identify Heredocs (<<EOF pattern)
    # This is a common AI pattern for multi-line YAML files that fails on Windows.
    heredoc_pattern = re.compile(r'<<-?\s*([\'"]?)([a-zA-Z0-9_-]+)\1\s*\n(.*?)\n\s*\2', re.DOTALL | re.IGNORECASE)
    hd_match = heredoc_pattern.search(cmd)
    
    if hd_match:
        content = hd_match.group(3)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', encoding='utf-8', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        # Replace the heredoc with the temp file path in the command
        # If it was 'cat <<EOF ... EOF | kubectl apply -f -', we can simplify to 'kubectl apply -f temp_path'
        # or more robustly: replace 'cat <<EOF...EOF' with 'type temp_path' on Windows or 'cat temp_path' elsewhere.
        
        hd_full = hd_match.group(0)
        new_cmd = cmd.replace(hd_full, "").strip()
        
        # If the command had 'cat |', clean it up
        new_cmd = re.sub(r'^cat\s*\|\s*', '', new_cmd)
        
        # If it uses -f -, change to -f temp_path
        if "-f -" in new_cmd:
            new_cmd = new_cmd.replace("-f -", f"-f {temp_path}")
        elif "--filename -" in new_cmd:
            new_cmd = new_cmd.replace("--filename -", f"--filename {temp_path}")
        else:
            # If not using -f -, maybe it was just a pipe?
            # Reconstruct cleverly
            new_cmd = f"{new_cmd} -f {temp_path}" if "apply" in new_cmd else f"{new_cmd} {temp_path}"
        
        try:
            args = shlex.split(new_cmd)
        except ValueError:
            args = new_cmd.split()
            
        print(f"[HEREDOC REWRITE] {cmd[:50]}... -> {new_cmd}")
        return args, temp_path

    # 2. Existing patch logic
    if is_patch:
        # 1. Identify JSON start
        brace_idx = cmd.find('{')
        bracket_idx = cmd.find('[')
        start_idx = -1
        if brace_idx != -1 and (bracket_idx == -1 or brace_idx < bracket_idx):
            start_idx = brace_idx
        elif bracket_idx != -1:
            start_idx = bracket_idx

        if start_idx != -1:
            # 2. Extract JSON by balancing braces/brackets
            stack = []
            end_idx = -1
            in_str = False
            for i in range(start_idx, len(cmd)):
                char = cmd[i]
                if char == '"' and (i == 0 or cmd[i-1] != '\\'):
                    in_str = not in_str
                if in_str: continue
                
                if char in '{[': stack.append(char)
                elif char in '}]':
                    if stack: stack.pop()
                    if not stack:
                        end_idx = i + 1
                        break
            
            if end_idx == -1:
                # Fallback: Extraction failed to balance. Try to find the next boundary (-- flag, | pipe, or ending quote)
                # This happens if the AI misses closing braces.
                boundary_match = re.search(r'\s+(-[a-zA-Z]|--|\|)', cmd[start_idx:])
                if boundary_match:
                    end_idx = start_idx + boundary_match.start()
                else:
                    # If we find a trailing quote, use that as the boundary
                    trailing_quote = re.search(r"['\"](?:\s*|$)", cmd[start_idx:])
                    if trailing_quote:
                        end_idx = start_idx + trailing_quote.start()
                    else:
                        end_idx = len(cmd)

            raw_json = cmd[start_idx:end_idx].strip()
            # If the raw_json still has a trailing quote, trim it
            if raw_json.endswith("'") or raw_json.endswith('"'):
                raw_json = raw_json[:-1].strip()
                
            prefix = cmd[:start_idx].strip()
            suffix = cmd[end_idx:].strip()
            
            # Clean quotes from prefix/suffix
            if prefix.endswith("'") or prefix.endswith('"'): prefix = prefix[:-1].rstrip()
            if suffix.startswith("'") or suffix.startswith('"'): suffix = suffix[1:].lstrip()

            prefix = re.sub(r'(-p|--patch)$', '', prefix).strip()
            
            # Aggressively repair
            clean_json = raw_json.replace("'", '"')
            repaired = _repair_json(clean_json) or _repair_json(raw_json)
            
            if repaired:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', encoding='utf-8', delete=False) as f:
                    f.write(repaired)
                    temp_path = f.name
                
                # Using separate args for flag and path is much safer for list2cmdline
                args = shlex.split(prefix) + ['--patch-file', temp_path] + shlex.split(suffix)
                print(f"[REWRITE] {cmd} -> {args}")
                return args, temp_path

    # Non-patch (or fix failed): standard split
    try:
        args = shlex.split(cmd)
    except ValueError:
        args = shlex.split(cmd.replace("'", ""))
    
    return args, temp_path


def clean_k8s_object(obj):
    """Recursively removes 'managedFields', 'status', and other noise from K8s dictionaries."""
    if not isinstance(obj, dict):
        if isinstance(obj, list):
            return [clean_k8s_object(i) for i in obj]
        return obj

    # Fields to drop
    to_drop = {
        'managedFields', 'status', 'ownerReferences', 'uid', 
        'resourceVersion', 'generation', 'selfLink', 
        'creationTimestamp', 'deletionTimestamp', 'progressDeadlineSeconds'
    }
    
    cleaned = {}
    for k, v in obj.items():
        if k in to_drop:
            continue
        
        # Recurse
        cleaned_v = clean_k8s_object(v)
        if cleaned_v is not None:
            cleaned[k] = cleaned_v
            
    return cleaned
