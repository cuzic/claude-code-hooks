"""
Claude Code hook for sending Pushbullet notifications when tasks complete.
Reads JSON from stdin and processes transcript files.
"""

import os
import sys
import subprocess
import json
from pathlib import Path
import tomllib
from dotenv import load_dotenv

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Default configuration
DEFAULT_NUM_MESSAGES = 3
DEFAULT_MAX_BODY_LENGTH = 500

def load_config():
    """Load configuration from config.toml file."""
    config_path = Path(__file__).parent.parent / "config.toml"
    config = {
        'notification': {
            'num_messages': DEFAULT_NUM_MESSAGES,
            'max_body_length': DEFAULT_MAX_BODY_LENGTH
        },
        'pushbullet': {},
        'logging': {
            'debug': True,
            'log_file': 'claude-code-pushbullet-notify.log'
        }
    }
    
    if config_path.exists():
        try:
            with open(config_path, 'rb') as f:
                loaded_config = tomllib.load(f)
                # Merge loaded config with defaults
                for section, values in loaded_config.items():
                    if section in config:
                        config[section].update(values)
                    else:
                        config[section] = values
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)
    
    return config

# Load configuration on import
CONFIG = load_config()

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
        print(f"Error reading hook input: {e}", file=sys.stderr)
        return None

def get_git_info():
    """Get repository name and branch name from git."""
    try:
        # Get current working directory from environment or fallback
        cwd = os.getcwd()
        
        # Get repository name
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        repo_path = Path(result.stdout.strip())
        repo_name = repo_path.name.replace('.git', '')
        
        # Get branch name
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        branch_name = result.stdout.strip()
        
        return repo_name, branch_name
    except subprocess.CalledProcessError:
        # If not in a git repo, use the current directory name
        return Path.cwd().name, 'main'

def get_last_messages_from_transcript(transcript_path, num_lines=None):
    """Get the last N lines from the transcript file."""
    if not transcript_path or not Path(transcript_path).exists():
        return "completed."
    
    # Use config values if not specified
    if num_lines is None:
        num_lines = CONFIG['notification']['num_messages']
    max_length = CONFIG['notification']['max_body_length']
    
    try:
        # Expand ~ in path
        transcript_path = Path(transcript_path).expanduser()
        
        messages = []
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # Check if this is an assistant message
                    if data.get('type') == 'assistant' and 'message' in data:
                        msg = data['message']
                        # Extract text from assistant messages
                        if msg.get('role') == 'assistant' and 'content' in msg:
                            content = msg['content']
                            # Handle both string and list content formats
                            if isinstance(content, str):
                                messages.append(content)
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        text = item.get('text', '').strip()
                                        if text:  # Only add non-empty messages
                                            messages.append(text)
                except json.JSONDecodeError:
                    continue
        
        # Get last N messages and join them
        if messages:
            last_messages = messages[-num_lines:] if len(messages) > num_lines else messages
            # Truncate long messages for notification
            result = '\n\n'.join(last_messages)
            if len(result) > max_length:  # Limit notification body length
                result = result[:max_length-3] + "..."
            return result
        else:
            return "Task completed."
    except Exception as e:
        print(f"Error reading transcript: {e}", file=sys.stderr)
        return "Task completed."

def send_pushbullet_notification(title, body):
    """Send notification via Pushbullet API."""
    # Get token from environment variable or config file
    token = os.environ.get('PUSHBULLET_TOKEN')
    if not token and 'token' in CONFIG.get('pushbullet', {}):
        token = CONFIG['pushbullet']['token']
    if not token:
        print("Error: PUSHBULLET_TOKEN not set. Please set it in environment variable or config.toml", file=sys.stderr)
        return False
    
    payload = {
        'type': 'note',
        'title': title,
        'body': body
    }
    
    try:
        import requests
        response = requests.post(
            'https://api.pushbullet.com/v2/pushes',
            headers={
                'Access-Token': token,
                'Content-Type': 'application/json'
            },
            json=payload
        )
        return response.status_code == 200
    except ImportError:
        # Fallback to curl if requests is not available
        import json
        result = subprocess.run(
            [
                'curl', '-s',
                '-u', f'{token}:',
                '-X', 'POST',
                'https://api.pushbullet.com/v2/pushes',
                '-H', 'Content-Type: application/json',
                '--data-raw', json.dumps(payload)
            ],
            capture_output=True
        )
        return result.returncode == 0

def main():
    """Main function for the Claude Code hook."""
    # Read JSON input from stdin
    hook_data = read_hook_input()
    
    if hook_data:
        # Hook mode: Process stop event
        hook_event = hook_data.get('hook_event_name', '')
        print(f"Hook event: {hook_event}", file=sys.stderr)
        
        if hook_event == 'Stop':
            # Get transcript path from hook data
            transcript_path = hook_data.get('transcript_path')
            print(f"Transcript path: {transcript_path}", file=sys.stderr)
            print(f"Stop hook active: {hook_data.get('stop_hook_active')}", file=sys.stderr)
            
            if transcript_path:
                repo_name, branch_name = get_git_info()
                notification_body = get_last_messages_from_transcript(transcript_path)
                title = f"claude code task completed {repo_name} {branch_name}"
                
                if CONFIG['logging']['debug']:
                    print(f"Config: num_messages={CONFIG['notification']['num_messages']}, max_body_length={CONFIG['notification']['max_body_length']}", file=sys.stderr)
                    print(f"Sending notification: {title}", file=sys.stderr)
                    print(f"Notification body: {notification_body[:100]}..." if len(notification_body) > 100 else f"Notification body: {notification_body}", file=sys.stderr)
                
                result = send_pushbullet_notification(title, notification_body)
                
                if CONFIG['logging']['debug']:
                    print(f"Notification sent: {result}", file=sys.stderr)
            else:
                print("No transcript path provided", file=sys.stderr)
        else:
            print(f"Skipping - Event: {hook_event} (not Stop)", file=sys.stderr)
    else:
        # Standalone mode (for testing)
        print("No JSON input received. Running in test mode.", file=sys.stderr)
        repo_name, branch_name = get_git_info()
        print(f"Repository: {repo_name}, Branch: {branch_name}", file=sys.stderr)
        # For testing, you would need to provide a transcript path
        notification_body = "Test mode - no transcript available"
        title = f"claude code task completed {repo_name} {branch_name}"
        print(f"Sending test notification: {title}", file=sys.stderr)
        result = send_pushbullet_notification(title, notification_body)
        print(f"Test notification sent: {result}", file=sys.stderr)

if __name__ == "__main__":
    main()