# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code hook that sends Pushbullet notifications when Claude Code tasks complete. It extracts the last N assistant messages from the transcript and includes them in the notification body.

## Development Setup

Install dependencies using `uv`:
```bash
uv venv
uv pip install -e .
```

## Architecture

The project is a Python package (`claude_code_pushbullet_notify`) that:
1. Reads JSON hook data from stdin when invoked by Claude Code
2. Parses the transcript file (JSONL format) to extract assistant messages
3. Sends a Pushbullet notification with git repository/branch info and recent messages

Key components:
- `claude_code_pushbullet_notify/__init__.py`: Main module with all functionality
- `scripts/claude-code-pushbullet-notify`: Shell script wrapper that activates venv and runs the Python module
- `config.toml`: TOML configuration for notification settings
- `.env`: Environment variables for API tokens (not committed)

The hook is triggered by Claude Code's stop event and processes the transcript path provided in the JSON payload. Configuration supports setting the number of messages to include and maximum notification body length.

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