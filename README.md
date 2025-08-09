# Claude Code Stop Notification Hook

[![Test](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/test.yml/badge.svg)](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/test.yml)
[![Lint](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/lint.yml/badge.svg)](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/lint.yml)

A notification system for Claude Code that sends Pushbullet notifications when Claude Code tasks complete, including the last conversation messages in the notification.

## Features

- 🔔 Sends Pushbullet notifications when Claude Code tasks complete
- 💬 Includes the last N assistant messages in the notification body
- 🔧 Configurable via TOML configuration file
- 📝 Debug logging for troubleshooting
- 🌳 Shows Git repository and branch information in notifications

## Installation

1. Clone the repository:
```bash
git clone https://github.com/cuzic/claude-code-pushbullet-notify.git
cd claude-code-pushbullet-notify
```

2. Set up Python environment (requires Python 3.11+):
```bash
uv venv
uv pip install -e .
```

3. Create a symlink to the hook script in your ~/bin directory:
```bash
mkdir -p ~/bin
ln -s $(pwd)/scripts/claude-code-pushbullet-notify ~/bin/claude-code-pushbullet-notify
```

4. Configure Claude Code to use the hook by adding to your Claude Code settings:
```json
{
  "hooks": {
    "stop": "$HOME/bin/claude-code-pushbullet-notify"
  }
}
```

## Configuration

Edit `config.toml` to customize the behavior:

```toml
[notification]
# Number of last assistant messages to include in the notification
num_messages = 3

# Maximum length of notification body (characters)
max_body_length = 500

[pushbullet]
# Pushbullet API token (can also be set via PUSHBULLET_TOKEN environment variable)
# token = "your_token_here"

[logging]
# Enable debug logging
debug = true

# Log file path (relative to project directory)
log_file = "claude-code-stop-notify.log"
```

### Pushbullet Token

You can set your Pushbullet API token in three ways (in order of priority):

1. `.env` file in the project root (recommended):
   ```bash
   cp .env.example .env
   # Edit .env and add your token
   ```

2. Environment variable: `export PUSHBULLET_TOKEN="your_token"`

3. In `config.toml` under `[pushbullet]` section:
   ```toml
   [pushbullet]
   token = "your_token_here"
   ```

Get your Pushbullet API token from: https://www.pushbullet.com/#settings/account

## Debugging

Check the log file for troubleshooting:
```bash
tail -f claude-code-pushbullet-notify.log
```

Test the notification system:
```bash
# Basic test
python -m claude_code_pushbullet_notify --test

# Test with specific transcript file
python -m claude_code_pushbullet_notify --test --transcript-path /path/to/transcript.jsonl

# Legacy test script
python test_transcript.py
```

## How It Works

1. When Claude Code stops, it sends a JSON payload to the hook via stdin
2. The hook extracts the transcript path from the payload
3. It reads the last N assistant messages from the transcript
4. Sends a Pushbullet notification with the repository info and message content

## Requirements

- Python 3.11+
- `requests` library (optional, falls back to curl)
- Pushbullet account and API token

## License

MIT