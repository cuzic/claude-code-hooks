# Claude Code Stop Notification Hook

[![Test](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/test.yml/badge.svg)](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/test.yml)
[![Lint](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/lint.yml/badge.svg)](https://github.com/cuzic/claude-code-pushbullet-notify/actions/workflows/lint.yml)

A notification system for Claude Code that sends Pushbullet notifications when Claude Code tasks complete, including the last conversation messages in the notification.

## Features

- 🔔 Sends Pushbullet notifications when Claude Code tasks complete
- 💬 Includes the last N assistant messages in the notification body
- 📧 Automatically splits long messages into multiple notifications
- 🔧 Configurable via TOML configuration file
- 📝 Debug logging for troubleshooting
- 🌳 Shows Git repository and branch information in notifications
- 🎨 Customizable notification templates with variables
- 🌍 Timezone support for notification timestamps

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
# Each notification chunk will be limited to this size
max_body_length = 1000

# Split long messages into multiple notifications (default: true)
# When enabled, messages exceeding max_body_length will be split into multiple parts
# Each part will be numbered (e.g., [1/3], [2/3], [3/3])
split_long_messages = true

# Optional: Delay between sending split messages (milliseconds)
# split_delay_ms = 500

# Timezone for timestamps (IANA timezone name, e.g., "America/New_York", "Asia/Tokyo")
# If not specified or invalid, falls back to system timezone
# timezone = "Asia/Tokyo"

# Custom notification title template (optional)
# Available variables: {GIT_REPO}, {GIT_BRANCH}, {HOSTNAME}, {USERNAME}, {CWD}, {CWD_BASENAME}, 
#                     {TIMESTAMP}, {DATE}, {TIME}, {TIMEZONE}, {TIMESTAMP_TZ}, {MSG0}-{MSG9}
title_template = "[{GIT_REPO}] ({GIT_BRANCH}) - Claude Code Task completed"

[pushbullet]
# Pushbullet API token (can also be set via PUSHBULLET_TOKEN environment variable)
# token = "your_token_here"

[logging]
# Enable debug logging
debug = true

# Log file path (relative to project directory)
log_file = "claude-code-stop-notify.log"
```

### Timezone Configuration

Configure timezone for notification timestamps:

- **IANA timezone names**: Use standard timezone names like "America/New_York", "Asia/Tokyo", "Europe/London"
- **Automatic DST handling**: Daylight saving time is handled automatically
- **Fallback behavior**: Falls back to system timezone if not specified or invalid
- **Template variables**: Use `{TIMEZONE}` for timezone abbreviation, `{TIMESTAMP_TZ}` for full timestamp with timezone

Example configuration:
```toml
[notification]
timezone = "Asia/Tokyo"
title_template = "[{TIMESTAMP_TZ}] Task completed in {TIMEZONE}"
```

### Message Splitting

When messages exceed `max_body_length`, they are automatically split into multiple notifications:

- **Smart word-boundary splitting**: Messages are split at word boundaries to avoid breaking words
- **Automatic numbering**: Multi-part messages are numbered (e.g., "[1/3] Title", "[2/3] Title")
- **Configurable behavior**: Can be disabled by setting `split_long_messages = false`
- **Optional delay**: Add delay between notifications with `split_delay_ms`

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