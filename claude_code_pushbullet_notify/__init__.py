"""
Claude Code hook for sending Pushbullet notifications when tasks complete.
Reads JSON from stdin and processes transcript files.
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import tomllib
from dotenv import load_dotenv

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Default configuration
DEFAULT_NUM_MESSAGES = 3
DEFAULT_MAX_BODY_LENGTH = 500


def merge_configs(default, loaded):
    """Recursively merge two configuration dictionaries."""
    result = default.copy()
    for key, value in loaded.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Load configuration from config.toml file."""
    config_path = Path(__file__).parent.parent / "config.toml"
    config = {
        "notification": {"num_messages": DEFAULT_NUM_MESSAGES, "max_body_length": DEFAULT_MAX_BODY_LENGTH},
        "pushbullet": {},
        "logging": {"debug": True, "log_file": "claude-code-pushbullet-notify.log"},
    }

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                loaded_config = tomllib.load(f)
                # Recursively merge loaded config with defaults
                config = merge_configs(config, loaded_config)
        except Exception as e:
            logging.error(f"Error loading config: {e}")

    return config


# Load configuration on import
CONFIG = load_config()


# Set up logging
def setup_logging():
    """Configure logging based on config settings."""
    log_level = logging.DEBUG if CONFIG["logging"]["debug"] else logging.INFO
    log_file = Path(__file__).parent.parent / CONFIG["logging"]["log_file"]

    # Configure logging to file and stderr
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stderr)],
    )


setup_logging()
logger = logging.getLogger(__name__)


def read_hook_input():
    """Read JSON input from stdin for the hook."""
    try:
        # Read from stdin
        input_data = sys.stdin.read()
        if not input_data:
            return None

        # Parse JSON
        hook_data = json.loads(input_data)
        return hook_data
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error reading hook input: {e}")
        return None


def get_git_info():
    """Get repository name and branch name from git."""
    # First check if the shell script has already captured git info in environment variables
    repo_name = os.environ.get("HOOK_GIT_REPO")
    branch_name = os.environ.get("HOOK_GIT_BRANCH")

    if repo_name and branch_name:
        # Use the git info captured by the shell script from the original directory
        return repo_name, branch_name

    # Fallback to the old method for testing or when not called via the shell script
    try:
        # Get current working directory from environment or fallback
        cwd = os.getcwd()

        # Get repository name
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, cwd=cwd
        )
        repo_path = Path(result.stdout.strip())
        repo_name = repo_path.name.replace(".git", "")

        # Get branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True, cwd=cwd
        )
        branch_name = result.stdout.strip()

        return repo_name, branch_name
    except subprocess.CalledProcessError:
        # If not in a git repo, use the current directory name
        return Path.cwd().name, "main"


def _extract_text_from_list(content_list):
    """Extract text from a list of content items."""
    texts = []
    for item in content_list:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text", "").strip()
        if text:
            texts.append(text)
    return texts


def _extract_message_text(content):
    """Extract text from message content (string or list format)."""
    if isinstance(content, str):
        return [content]

    if isinstance(content, list):
        return _extract_text_from_list(content)

    return []


def _is_assistant_message(data):
    """Check if data represents an assistant message."""
    if data.get("type") != "assistant":
        return False
    if "message" not in data:
        return False
    msg = data["message"]
    return msg.get("role") == "assistant" and "content" in msg


def _process_transcript_line(line, line_number):
    """Process a single transcript line and extract assistant messages."""
    try:
        data = json.loads(line)
        if not _is_assistant_message(data):
            return []
        return _extract_message_text(data["message"]["content"])
    except json.JSONDecodeError as e:
        logger.debug(f"Line {line_number}: Skipping invalid JSON - {e}")
        return []


def _read_transcript_messages(transcript_path):
    """Read all assistant messages from transcript file."""
    messages = []
    with open(transcript_path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            messages.extend(_process_transcript_line(line, line_number))
    return messages


def _format_notification_body(messages, num_lines, max_length):
    """Format messages for notification body."""
    if not messages:
        return "Task completed."

    last_messages = messages[-num_lines:] if len(messages) > num_lines else messages
    result = "\n\n".join(last_messages)

    if len(result) > max_length:
        result = result[: max_length - 3] + "..."

    return result


def get_last_messages_from_transcript(transcript_path, num_lines=None):
    """Get the last N lines from the transcript file."""
    if not transcript_path or not Path(transcript_path).exists():
        return "completed."

    # Use config values if not specified
    if num_lines is None:
        num_lines = CONFIG["notification"]["num_messages"]
    max_length = CONFIG["notification"]["max_body_length"]

    try:
        transcript_path = Path(transcript_path).expanduser()
        messages = _read_transcript_messages(transcript_path)
        return _format_notification_body(messages, num_lines, max_length)
    except Exception as e:
        logger.error(f"Error reading transcript: {e}")
        return "Task completed."


def send_pushbullet_notification(title, body):
    """Send notification via Pushbullet API."""
    # Get token from environment variable or config file
    token = os.environ.get("PUSHBULLET_TOKEN")
    if not token and "token" in CONFIG.get("pushbullet", {}):
        token = CONFIG["pushbullet"]["token"]
    if not token:
        logger.error("PUSHBULLET_TOKEN not set. Please set it in environment variable or config.toml")
        return False

    payload = {"type": "note", "title": title, "body": body}

    try:
        import requests

        response = requests.post(
            "https://api.pushbullet.com/v2/pushes",
            headers={"Access-Token": token, "Content-Type": "application/json"},
            json=payload,
        )
        return response.status_code == 200
    except ImportError:
        # Fallback to curl if requests is not available
        import json

        result = subprocess.run(
            [
                "curl",
                "-s",
                "-u",
                f"{token}:",
                "-X",
                "POST",
                "https://api.pushbullet.com/v2/pushes",
                "-H",
                "Content-Type: application/json",
                "--data-raw",
                json.dumps(payload),
            ],
            capture_output=True,
        )
        return result.returncode == 0


def _handle_test_mode(args):
    """Handle test mode execution."""
    logger.info("Running in test mode")
    repo_name, branch_name = get_git_info()
    logger.info(f"Repository: {repo_name}, Branch: {branch_name}")

    if args.transcript_path:
        notification_body = get_last_messages_from_transcript(args.transcript_path)
        transcript_path = args.transcript_path
    else:
        notification_body = "Test mode - no transcript available"
        transcript_path = None

    _send_notification(repo_name, branch_name, notification_body, transcript_path)


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


def _apply_truncate_function(text, variables):
    """Apply truncate function to template text."""
    import re
    
    truncate_pattern = r"\{truncate\(\s*([^,)]+?)\s*,\s*(\d+)\s*\)\}"

    def truncate_replace(match):
        var_content = match.group(1).strip()
        var_content = _resolve_variable_content(var_content, variables)
        length = int(match.group(2))
        if len(var_content) > length:
            return var_content[: length - 3] + "..."
        return var_content

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


def _apply_complex_substr(text, variables):
    """Handle substr functions with content containing commas."""
    while "{substr(" in text:
        start_idx = text.find("{substr(")
        if start_idx == -1:
            break

        end_idx = text.find(")}", start_idx)
        if end_idx == -1:
            break

        new_text = _process_substr_match(text, start_idx, end_idx, variables)
        if new_text is None:
            break
        text = new_text
    
    return text


def _apply_string_functions(text, variables=None):
    """Apply string functions like truncate and substr to template.

    Args:
        text: The template text with function calls
        variables: Optional dict of template variables to resolve
    """
    text = _apply_truncate_function(text, variables)
    text = _apply_substr_function(text, variables)
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
    
    return hostname, username, cwd, cwd_basename


def _get_time_variables():
    """Get time-related template variables."""
    now = datetime.now()
    return {
        "TIMESTAMP": now.strftime("%Y-%m-%d %H:%M:%S"),
        "DATE": now.strftime("%Y-%m-%d"),
        "TIME": now.strftime("%H:%M:%S"),
    }


def _read_messages_from_transcript(transcript_path):
    """Read messages from transcript file if it exists."""
    if not transcript_path:
        return []
    if not Path(transcript_path).exists():
        return []
    try:
        return _read_transcript_messages(Path(transcript_path).expanduser())
    except Exception:
        return []


def _get_message_variables(transcript_path):
    """Get MSG0, MSG1, MSG2 variables from transcript."""
    messages = _read_messages_from_transcript(transcript_path)
    
    # Reverse so MSG0 is the latest message
    messages = list(reversed(messages))
    
    msg_vars = {}
    for i in range(3):
        msg_vars[f"MSG{i}"] = messages[i] if i < len(messages) else ""
    
    return msg_vars


def _get_template_variables(repo_name, branch_name, transcript_path=None):
    """Get all available template variables."""
    hostname, username, cwd, cwd_basename = _get_system_info()
    
    variables = {
        "GIT_REPO": repo_name,
        "GIT_BRANCH": branch_name,
        "HOSTNAME": hostname,
        "USERNAME": username,
        "CWD": cwd,
        "CWD_BASENAME": cwd_basename,
    }
    
    # Add time variables
    variables.update(_get_time_variables())
    
    # Add message variables
    variables.update(_get_message_variables(transcript_path))

    return variables


def _send_notification(repo_name, branch_name, notification_body, transcript_path=None):
    """Send notification with template-based or standard title format."""
    variables = _get_template_variables(repo_name, branch_name, transcript_path)

    # Use template from config if available, otherwise use default
    title_template = CONFIG.get("notification", {}).get(
        "title_template", "claude code task completed {GIT_REPO} {GIT_BRANCH}"
    )
    title = _format_template(title_template, variables)

    # Check if there's a custom body template
    body_template = CONFIG.get("notification", {}).get("body_template")
    if body_template:
        notification_body = _format_template(body_template, variables)

    logger.info(f"Sending notification: {title}")

    if notification_body and len(notification_body) > 100:
        logger.debug(f"Notification body: {notification_body[:100]}...")
    elif notification_body:
        logger.debug(f"Notification body: {notification_body}")

    result = send_pushbullet_notification(title, notification_body)
    logger.info(f"Notification sent: {result}")
    return result


def _handle_stop_event(hook_data):
    """Handle Stop event from hook."""
    transcript_path = hook_data.get("transcript_path")
    logger.debug(f"Transcript path: {transcript_path}")
    logger.debug(f"Stop hook active: {hook_data.get('stop_hook_active')}")

    if not transcript_path:
        logger.warning("No transcript path provided")
        return

    repo_name, branch_name = get_git_info()
    notification_body = get_last_messages_from_transcript(transcript_path)

    logger.debug(
        f"Config: num_messages={CONFIG['notification']['num_messages']}, "
        f"max_body_length={CONFIG['notification']['max_body_length']}"
    )

    _send_notification(repo_name, branch_name, notification_body, transcript_path)


def _handle_hook_mode(hook_data):
    """Handle hook mode execution."""
    hook_event = hook_data.get("hook_event_name", "")
    logger.info(f"Hook event: {hook_event}")

    if hook_event == "Stop":
        _handle_stop_event(hook_data)
    else:
        logger.info(f"Skipping - Event: {hook_event} (not Stop)")


def _handle_legacy_mode():
    """Handle legacy fallback mode."""
    logger.info("No JSON input received. Running in legacy test mode")
    repo_name, branch_name = get_git_info()
    logger.info(f"Repository: {repo_name}, Branch: {branch_name}")
    notification_body = "Test mode - no transcript available"
    _send_notification(repo_name, branch_name, notification_body, None)


def main():
    """Main function for the Claude Code hook."""
    parser = argparse.ArgumentParser(description="Claude Code Pushbullet notification hook")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument("--transcript-path", help="Path to transcript file for testing")
    args = parser.parse_args()

    if args.test:
        _handle_test_mode(args)
        return

    hook_data = read_hook_input()
    if hook_data:
        _handle_hook_mode(hook_data)
    else:
        _handle_legacy_mode()


if __name__ == "__main__":
    main()
