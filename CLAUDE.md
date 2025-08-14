# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code hook that sends Pushbullet notifications when Claude Code tasks complete. It extracts the last N assistant messages from the transcript and includes them in the notification body.

## Development Setup

### Local Development

1. Install dependencies using `uv`:
```bash
uv venv
uv pip install -e .
```

2. Set up configuration:
```bash
# Copy the example config
cp config.toml.example config.toml

# Edit with your settings
nano config.toml
```

3. Set up environment variables:
```bash
# Create .env file with your Pushbullet API token
echo "PUSHBULLET_TOKEN=your_token_here" > .env
```

### DevContainer Development

This project includes a DevContainer configuration for consistent development environments. The DevContainer includes:
- Python 3.12 (managed by mise)
- uv for Python package management
- mise for runtime version management
- Git and GitHub CLI
- Automated environment setup

To use the DevContainer:
1. Open the project in VS Code
2. Install the "Dev Containers" extension if not already installed
3. Click "Reopen in Container" when prompted (or use Command Palette: "Dev Containers: Reopen in Container")
4. The container will automatically:
   - Install mise and uv
   - Set up Python 3.12
   - Create a virtual environment
   - Install project dependencies
   - Configure bash aliases for common tasks

The DevContainer provides these convenient aliases:
- `test` - Run pytest tests
- `test-cov` - Run tests with coverage report
- `notify-test` - Test the notification system

## Architecture

The project is a Python package (`claude_code_pushbullet_notify`) that:
1. Reads JSON hook data from stdin when invoked by Claude Code
2. Parses the transcript file (JSONL format) to extract assistant messages
3. Sends a Pushbullet notification with git repository/branch info and recent messages

Key components:
- `claude_code_pushbullet_notify/__init__.py`: Main module with all functionality
- `scripts/claude-code-pushbullet-notify`: Shell script wrapper that activates venv and runs the Python module
- `config.toml.example`: Example TOML configuration (copy to `config.toml` and customize)
- `config.toml`: User-specific TOML configuration (not committed to git)
- `.env`: Environment variables for API tokens (not committed)

The hook is triggered by Claude Code's stop event and processes the transcript path provided in the JSON payload. Configuration supports setting the number of messages to include, maximum notification body length, and timezone conversion for timestamps.

### Timezone Support

The notification system supports timezone-aware timestamps through the `timezone` configuration option. Timestamps are displayed in the specified timezone using IANA timezone names (e.g., "America/New_York", "Asia/Tokyo", "UTC"). If no timezone is specified or an invalid timezone is provided, the system falls back to the local system timezone.

Available timezone-related template variables:
- `{TIMESTAMP}`: Current timestamp (YYYY-MM-DD HH:MM:SS)
- `{DATE}`: Current date (YYYY-MM-DD) 
- `{TIME}`: Current time (HH:MM:SS)
- `{TIMEZONE}`: Timezone abbreviation (e.g., JST, EST, UTC)
- `{TIMESTAMP_TZ}`: Timestamp with timezone (YYYY-MM-DD HH:MM:SS TZ)

## Testing

The project uses pytest for testing. Tests are organized in the `tests/` directory:
- `tests/test_transcript.py`: Tests for transcript reading and parsing functionality
- `tests/test_notification.py`: Tests for Pushbullet notification sending and main function

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=claude_code_pushbullet_notify
```

Test the notification system manually:
```bash
python -m claude_code_pushbullet_notify
```

## CI/CD

The project uses GitHub Actions for continuous integration:

### Workflows

1. **Test Workflow** (`.github/workflows/test.yml`):
   - Runs pytest in the DevContainer environment
   - Tests against Python 3.9, 3.10, 3.11, and 3.12
   - Generates coverage reports
   - Triggered on push to main and pull requests

2. **Lint Workflow** (`.github/workflows/lint.yml`):
   - Runs ruff for code formatting and linting
   - Performs pyright type checking
   - Ensures code quality standards

### Running CI Locally

You can test the CI workflows locally using the DevContainer:
```bash
# Run tests as CI would
uv run pytest -v --cov=claude_code_pushbullet_notify --cov-report=term-missing

# Run linting as CI would
uv run ruff format --check .
uv run ruff check .
```