"""Template processing and system information gathering for Claude Code notifications."""

import os
import socket
import subprocess
from datetime import datetime
from pathlib import Path

# Avoid circular import by defining this locally


# Git information functions

def _get_git_info_from_env():
    """Get git info from environment variables."""
    repo_name = os.environ.get("HOOK_GIT_REPO")
    branch_name = os.environ.get("HOOK_GIT_BRANCH")
    if repo_name and branch_name:
        return repo_name, branch_name
    return None, None


def _get_repo_name_from_git(cwd):
    """Get repository name using git command."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], 
        capture_output=True, text=True, check=True, cwd=cwd
    )
    repo_path = Path(result.stdout.strip())
    return repo_path.name.replace(".git", "")


def _get_branch_name_from_git(cwd):
    """Get branch name using git command."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], 
        capture_output=True, text=True, check=True, cwd=cwd
    )
    return result.stdout.strip()


def get_git_info():
    """Get repository name and branch name from git."""
    # First check environment variables
    repo_name, branch_name = _get_git_info_from_env()
    if repo_name and branch_name:
        return repo_name, branch_name

    # Fallback to git commands
    try:
        cwd = os.getcwd()
        repo_name = _get_repo_name_from_git(cwd)
        branch_name = _get_branch_name_from_git(cwd)
        return repo_name, branch_name
    except subprocess.CalledProcessError:
        # If not in a git repo, use the current directory name
        return Path.cwd().name, "main"


# System information functions

def _get_tty_direct():
    """Get TTY using the direct tty command."""
    try:
        result = subprocess.run(
            ["tty"], capture_output=True, text=True, check=True
        )
        tty_full = result.stdout.strip()
        # Remove /dev/ prefix if present
        return tty_full.replace("/dev/", "") if tty_full.startswith("/dev/") else tty_full
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _get_tty_for_pid(pid):
    """Try to get TTY for a specific PID using ps command."""
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(pid)],
            capture_output=True, text=True, check=True
        )
        tty = result.stdout.strip()
        
        # Check if we got a valid TTY (not ? or ??)
        if tty and tty not in ["?", "??", "-"]:
            # Remove /dev/ prefix if present
            return tty.replace("/dev/", "") if tty.startswith("/dev/") else tty
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def _get_parent_pid_from_proc(pid):
    """Get parent PID from /proc/{pid}/stat file."""
    try:
        stat_path = f"/proc/{pid}/stat"
        if not os.path.exists(stat_path):
            return None
            
        with open(stat_path, 'r') as f:
            stat_content = f.read()
            # Parent PID is the 4th field in stat file
            # Format: pid (comm) state ppid ...
            # We need to handle comm which might contain spaces and parentheses
            close_paren = stat_content.rfind(')')
            if close_paren == -1:
                return None
                
            fields = stat_content[close_paren + 1:].split()
            if len(fields) >= 2:
                parent_pid = int(fields[1])
                if parent_pid != pid and parent_pid > 1:
                    return parent_pid
    except (IOError, ValueError, IndexError):
        pass
    return None


def _get_tty_from_parent_processes():
    """Get TTY by traversing parent processes using /proc filesystem."""
    try:
        pid = os.getpid()
        
        # Traverse up to 10 parent processes to find a TTY
        for _ in range(10):
            # Try to get TTY for current PID
            tty = _get_tty_for_pid(pid)
            if tty:
                return tty
            
            # Get parent PID and continue traversing
            parent_pid = _get_parent_pid_from_proc(pid)
            if parent_pid is None:
                break
            pid = parent_pid
                
        return "unknown"
        
    except Exception:
        return "unknown"


def _get_system_info():
    """Get system information for template variables."""
    # Get hostname
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    # Get username
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    # Get current working directory
    cwd = os.getcwd()
    
    # Get basename of current working directory
    cwd_basename = os.path.basename(cwd.rstrip(os.sep)) if cwd != os.sep else ""
    
    # Get TTY (terminal) information - try direct method first
    tty = _get_tty_direct()
    
    # If direct TTY detection failed, try traversing parent processes
    if tty == "unknown":
        tty = _get_tty_from_parent_processes()
    
    return hostname, username, cwd, cwd_basename, tty


def _get_time_variables():
    """Get time-related template variables."""
    now = datetime.now()
    return {
        "TIMESTAMP": now.strftime("%Y-%m-%d %H:%M:%S"),
        "DATE": now.strftime("%Y-%m-%d"),
        "TIME": now.strftime("%H:%M:%S"),
    }


def _read_messages_from_transcript_for_template(transcript_path):
    """Read messages from transcript file if it exists."""
    if not transcript_path:
        return []
    if not Path(transcript_path).exists():
        return []
    try:
        # Import here to avoid circular imports
        from .transcript import _read_transcript_messages
        return _read_transcript_messages(Path(transcript_path).expanduser())
    except Exception:
        return []


def _get_message_variables(transcript_path):
    """Get MSG0-MSG9 variables from transcript."""
    messages = _read_messages_from_transcript_for_template(transcript_path)
    
    # Reverse so MSG0 is the latest message
    messages = list(reversed(messages))
    
    msg_vars = {}
    for i in range(10):  # MSG0 through MSG9
        msg_vars[f"MSG{i}"] = messages[i] if i < len(messages) else ""
    
    return msg_vars


# Template processing functions

def _resolve_variable_content(var_content, variables):
    """Resolve a variable name to its content if it exists in variables dict."""
    if variables and var_content in variables:
        return str(variables[var_content])
    return var_content


def _remove_quotes(text):
    """Remove surrounding quotes from text if present."""
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _truncate_text(text, length):
    """Truncate text to specified length with ellipsis."""
    if len(text) > length:
        return text[: length - 3] + "..."
    return text


def _apply_truncate_function(text, variables):
    """Apply truncate function to template text."""
    import re
    
    truncate_pattern = r"\{truncate\(\s*([^,)]+?)\s*,\s*(\d+)\s*\)\}"

    def truncate_replace(match):
        var_content = match.group(1).strip()
        var_content = _resolve_variable_content(var_content, variables)
        length = int(match.group(2))
        return _truncate_text(var_content, length)

    return re.sub(truncate_pattern, truncate_replace, text)


def _apply_substr_function(text, variables):
    """Apply substr function to template text."""
    import re
    
    # Handle simple cases with regex
    substr_pattern = r"\{substr\(\s*([^,)]+|\w+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\}"

    def substr_replace(match):
        var_content = match.group(1).strip()
        var_content = _resolve_variable_content(var_content, variables)
        var_content = _remove_quotes(var_content)
        start = int(match.group(2))
        length = int(match.group(3))
        return var_content[start : start + length]

    text = re.sub(substr_pattern, substr_replace, text)
    
    # Handle complex cases with commas
    text = _apply_complex_substr(text, variables)
    return text


def _extract_substr_params(func_content):
    """Extract parameters from substr function content."""
    parts = func_content.rsplit(",", 2)
    if len(parts) != 3:
        return None, None, None
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def _process_substr_match(text, start_idx, end_idx, variables):
    """Process a single substr function match."""
    func_content = text[start_idx + 8 : end_idx]
    var_content, start_str, length_str = _extract_substr_params(func_content)
    
    if var_content is None:
        return None
        
    var_content = _resolve_variable_content(var_content, variables)
    var_content = _remove_quotes(var_content)
    
    try:
        start_pos = int(start_str)
        length_val = int(length_str)
        replacement = var_content[start_pos : start_pos + length_val]
        return text[:start_idx] + replacement + text[end_idx + 2 :]
    except (ValueError, IndexError):
        return None


def _find_function_bounds(text, func_name):
    """Find the start and end indices of a function call."""
    pattern = f"{{{func_name}("
    start_idx = text.find(pattern)
    if start_idx == -1:
        return None, None
    
    end_idx = text.find(")}", start_idx)
    if end_idx == -1:
        return None, None
    
    return start_idx, end_idx


def _apply_complex_substr(text, variables):
    """Handle substr functions with content containing commas."""
    while True:
        start_idx, end_idx = _find_function_bounds(text, "substr")
        if start_idx is None:
            break

        new_text = _process_substr_match(text, start_idx, end_idx, variables)
        if new_text is None:
            break
        text = new_text
    
    return text


def _extract_regex_params(func_content):
    """Extract parameters from regex function content."""
    parts = func_content.rsplit(",", 1)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()


def _apply_regex_pattern(var_content, pattern):
    """Apply regex pattern to variable content."""
    import re
    
    var_content = _remove_quotes(var_content)
    pattern = _remove_quotes(pattern)
    
    try:
        regex_match = re.search(pattern, var_content)
        return regex_match.group(0) if regex_match else ""
    except re.error:
        return ""


def _process_regex_match(text, start_idx, end_idx, variables):
    """Process a single regex function match."""
    func_content = text[start_idx + 7 : end_idx]  # Skip '{regex('
    
    var_content, pattern = _extract_regex_params(func_content)
    if var_content is None:
        return text[:start_idx] + "" + text[end_idx + 2:]
    
    var_content = _resolve_variable_content(var_content, variables)
    replacement = _apply_regex_pattern(var_content, pattern)
    
    return text[:start_idx] + replacement + text[end_idx + 2:]


def _apply_regex_function(text, variables):
    """Apply regex function to extract text matching a pattern.
    
    Usage: {regex(text, pattern)}
    Example: {regex(MSG0, [0-9]+)} - extracts numbers from MSG0
    """
    while True:
        start_idx, end_idx = _find_function_bounds(text, "regex")
        if start_idx is None:
            break

        text = _process_regex_match(text, start_idx, end_idx, variables)
    
    return text


def _apply_string_functions(text, variables=None):
    """Apply string functions like truncate, substr, and regex to template.

    Args:
        text: The template text with function calls
        variables: Optional dict of template variables to resolve
    """
    text = _apply_truncate_function(text, variables)
    text = _apply_substr_function(text, variables)
    text = _apply_regex_function(text, variables)
    return text


def _format_template(template, variables):
    """Format a template string with provided variables and string functions."""
    if template is None:
        return None
    if not template:
        return ""

    result = template

    # Apply string functions first (they can use variable names)
    # Pass variables so functions can resolve variable names
    result = _apply_string_functions(result, variables)

    # Then replace any remaining variables
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))

    return result


def _get_template_variables(repo_name, branch_name, transcript_path=None):
    """Get all available template variables."""
    hostname, username, cwd, cwd_basename, tty = _get_system_info()
    
    variables = {
        "GIT_REPO": repo_name,
        "GIT_BRANCH": branch_name,
        "HOSTNAME": hostname,
        "USERNAME": username,
        "CWD": cwd,
        "CWD_BASENAME": cwd_basename,
        "TTY": tty,
    }
    
    # Add time variables
    variables.update(_get_time_variables())
    
    # Add message variables
    variables.update(_get_message_variables(transcript_path))

    return variables