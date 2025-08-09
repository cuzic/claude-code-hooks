#!/bin/bash
# Project-specific bash configuration

# Activate mise
eval "$(~/.local/bin/mise activate bash)"

# Activate uv
source $HOME/.cargo/env

# Auto-activate Python virtual environment if it exists
if [ -f "/workspaces/claude-code-pushbullet-notify/.venv/bin/activate" ]; then
    source /workspaces/claude-code-pushbullet-notify/.venv/bin/activate
fi

# Aliases for common commands
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Project-specific aliases
alias test='uv run pytest'
alias test-cov='uv run pytest --cov=claude_code_pushbullet_notify --cov-report=term-missing'
alias test-watch='uv run pytest-watch'
alias notify-test='uv run python -m claude_code_pushbullet_notify --test'

# Show project info on terminal start
echo "🚀 Claude Code Pushbullet Notify Development Environment"
echo "📂 Project: $(pwd)"
echo "🐍 Python: $(python --version 2>&1)"
echo ""
echo "Useful aliases:"
echo "  test       - Run tests with pytest"
echo "  test-cov   - Run tests with coverage"
echo "  notify-test - Test notification sending"
echo ""