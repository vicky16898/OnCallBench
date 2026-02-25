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


def _prepare_kubectl_command(cmd):
    """
    Platform-agnostic kubectl command preparation.
    For patch commands: extracts JSON, repairs, writes to --patch-file.
    For other commands: cleans shell quotes and returns arg list.
    Returns: (args_list, temp_file_path_or_None)
    """
    import tempfile
    import json as _json
    
    temp_path = None
    has_patch_flag = ("-p " in cmd or "-p'" in cmd or '-p"' in cmd
                      or "--patch " in cmd or "--patch=" in cmd)
    is_patch = "patch" in cmd.lower() and has_patch_flag
    
    if is_patch:
        # Strip all single quotes (shell-only, never valid JSON)
        cmd_clean = cmd.replace("'", "")
        
        brace_idx = cmd_clean.find('{')
        bracket_idx = cmd_clean.find('[')
        
        if bracket_idx != -1 and (brace_idx == -1 or bracket_idx < brace_idx):
            start_idx = bracket_idx
        elif brace_idx != -1:
            start_idx = brace_idx
        else:
            start_idx = -1
        
        if start_idx != -1:
            raw_json = cmd_clean[start_idx:].rstrip()
            clean = raw_json.replace('\\"', '"').replace('\\\\', '\\')
            
            repaired = _repair_json(clean) or _repair_json(raw_json)
            
            if repaired:
                if "--type=json" in cmd:
                    parsed = _json.loads(repaired)
                    if isinstance(parsed, dict):
                        repaired = _json.dumps([parsed])
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                                  encoding='utf-8', delete=False) as f:
                    f.write(repaired)
                    temp_path = f.name
                
                # Build args list directly — never pass file paths through shlex
                # (shlex treats backslashes as escape chars, breaking Windows paths)
                patch_match = re.search(r'(-p|--patch)\s*', cmd_clean)
                prefix = (cmd_clean[:patch_match.start()].strip()
                          if patch_match else cmd_clean[:start_idx].strip())
                prefix_args = shlex.split(prefix)  # safe: no file paths here
                args = prefix_args + [f'--patch-file={temp_path}']
                
                print(f"[CMD] Patch rewritten -> {' '.join(args)}")
                return args, temp_path
            else:
                print(f"[CMD] WARN: JSON repair failed, attempting raw execution")
    
    # Non-patch (or patch fallback): clean quotes and split
    try:
        args = shlex.split(cmd)
    except ValueError:
        args = shlex.split(cmd.replace("'", ""))
    
    return args, temp_path
