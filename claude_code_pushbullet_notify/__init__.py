"""
Claude Code hook for sending Pushbullet notifications when tasks complete.
Reads JSON from stdin and processes transcript files.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
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


def get_last_messages_from_transcript(transcript_path, num_lines=None):
    """Get the last N lines from the transcript file."""
    if not transcript_path or not Path(transcript_path).exists():
        return "completed."

    # Use config values if not specified
    if num_lines is None:
        num_lines = CONFIG["notification"]["num_messages"]
    max_length = CONFIG["notification"]["max_body_length"]

    try:
        # Expand ~ in path
        transcript_path = Path(transcript_path).expanduser()

        messages = []
        with open(transcript_path, encoding="utf-8") as f:
            for line_number, line in enumerate(f, 1):
                try:
                    data = json.loads(line)
                    # Check if this is an assistant message
                    if data.get("type") == "assistant" and "message" in data:
                        msg = data["message"]
                        # Extract text from assistant messages
                        if msg.get("role") == "assistant" and "content" in msg:
                            content = msg["content"]
                            # Handle both string and list content formats
                            if isinstance(content, str):
                                messages.append(content)
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text = item.get("text", "").strip()
                                        if text:  # Only add non-empty messages
                                            messages.append(text)
                except json.JSONDecodeError as e:
                    logger.debug(f"Line {line_number}: Skipping invalid JSON - {e}")
                    continue

        # Get last N messages and join them
        if messages:
            last_messages = messages[-num_lines:] if len(messages) > num_lines else messages
            # Truncate long messages for notification
            result = "\n\n".join(last_messages)
            if len(result) > max_length:  # Limit notification body length
                result = result[: max_length - 3] + "..."
            return result
        else:
            return "Task completed."
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


def main():
    """Main function for the Claude Code hook."""
    parser = argparse.ArgumentParser(description="Claude Code Pushbullet notification hook")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument("--transcript-path", help="Path to transcript file for testing")
    args = parser.parse_args()

    if args.test:
        # Test mode
        logger.info("Running in test mode")
        repo_name, branch_name = get_git_info()
        logger.info(f"Repository: {repo_name}, Branch: {branch_name}")

        if args.transcript_path:
            notification_body = get_last_messages_from_transcript(args.transcript_path)
        else:
            notification_body = "Test mode - no transcript available"

        title = f"claude code task completed {repo_name} {branch_name}"
        logger.info(f"Sending test notification: {title}")
        result = send_pushbullet_notification(title, notification_body)
        logger.info(f"Test notification sent: {result}")
        return

    # Read JSON input from stdin
    hook_data = read_hook_input()

    if hook_data:
        # Hook mode: Process stop event
        hook_event = hook_data.get("hook_event_name", "")
        logger.info(f"Hook event: {hook_event}")

        if hook_event == "Stop":
            # Get transcript path from hook data
            transcript_path = hook_data.get("transcript_path")
            logger.debug(f"Transcript path: {transcript_path}")
            logger.debug(f"Stop hook active: {hook_data.get('stop_hook_active')}")

            if transcript_path:
                repo_name, branch_name = get_git_info()
                notification_body = get_last_messages_from_transcript(transcript_path)
                title = f"claude code task completed {repo_name} {branch_name}"

                logger.debug(
                    f"Config: num_messages={CONFIG['notification']['num_messages']}, max_body_length={CONFIG['notification']['max_body_length']}"
                )
                logger.info(f"Sending notification: {title}")
                logger.debug(
                    f"Notification body: {notification_body[:100]}..."
                    if len(notification_body) > 100
                    else f"Notification body: {notification_body}"
                )

                result = send_pushbullet_notification(title, notification_body)
                logger.info(f"Notification sent: {result}")
            else:
                logger.warning("No transcript path provided")
        else:
            logger.info(f"Skipping - Event: {hook_event} (not Stop)")
    else:
        # Legacy fallback mode (no arguments and no stdin)
        logger.info("No JSON input received. Running in legacy test mode")
        repo_name, branch_name = get_git_info()
        logger.info(f"Repository: {repo_name}, Branch: {branch_name}")
        notification_body = "Test mode - no transcript available"
        title = f"claude code task completed {repo_name} {branch_name}"
        logger.info(f"Sending test notification: {title}")
        result = send_pushbullet_notification(title, notification_body)
        logger.info(f"Test notification sent: {result}")


if __name__ == "__main__":
    main()
