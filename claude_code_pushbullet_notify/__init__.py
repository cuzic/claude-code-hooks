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


def _extract_message_text(content):
    """Extract text from message content (string or list format)."""
    if isinstance(content, str):
        return [content]
    
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "").strip()
                if text:
                    texts.append(text)
        return texts
    
    return []


def _process_transcript_line(line, line_number):
    """Process a single transcript line and extract assistant messages."""
    try:
        data = json.loads(line)
        if data.get("type") != "assistant" or "message" not in data:
            return []
        
        msg = data["message"]
        if msg.get("role") != "assistant" or "content" not in msg:
            return []
        
        return _extract_message_text(msg["content"])
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
    else:
        notification_body = "Test mode - no transcript available"

    _send_notification(repo_name, branch_name, notification_body)


def _format_template(template, variables):
    """Format a template string with provided variables."""
    if template is None:
        return None
    if not template:
        return ""
    
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    
    return result


def _get_template_variables(repo_name, branch_name):
    """Get all available template variables."""
    now = datetime.now()
    
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
    # Handle edge case where path ends with slash
    cwd_basename = os.path.basename(cwd.rstrip(os.sep)) if cwd != os.sep else ""
    
    return {
        "GIT_REPO": repo_name,
        "GIT_BRANCH": branch_name,
        "TIMESTAMP": now.strftime("%Y-%m-%d %H:%M:%S"),
        "DATE": now.strftime("%Y-%m-%d"),
        "TIME": now.strftime("%H:%M:%S"),
        "HOSTNAME": hostname,
        "USERNAME": username,
        "CWD": cwd,
        "CWD_BASENAME": cwd_basename,
    }


def _send_notification(repo_name, branch_name, notification_body):
    """Send notification with template-based or standard title format."""
    variables = _get_template_variables(repo_name, branch_name)
    
    # Use template from config if available, otherwise use default
    title_template = CONFIG.get("notification", {}).get(
        "title_template", 
        "claude code task completed {GIT_REPO} {GIT_BRANCH}"
    )
    title = _format_template(title_template, variables)
    
    # Check if there's a custom body template
    body_template = CONFIG.get("notification", {}).get("body_template")
    if body_template:
        notification_body = _format_template(body_template, variables)
    
    logger.info(f"Sending notification: {title}")
    
    if len(notification_body) > 100:
        logger.debug(f"Notification body: {notification_body[:100]}...")
    else:
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
    
    _send_notification(repo_name, branch_name, notification_body)


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
    _send_notification(repo_name, branch_name, notification_body)


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
