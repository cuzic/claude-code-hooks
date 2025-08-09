#!/bin/bash
set -e

echo "🚀 Setting up development environment..."

# Ensure mise is activated
eval "$(~/.local/bin/mise activate bash)"

# Ensure uv is in PATH
source $HOME/.cargo/env

# Install Python version specified by mise if .mise.toml exists
if [ -f ".mise.toml" ]; then
    echo "📦 Installing mise dependencies..."
    mise install
fi

# Set up Python virtual environment with uv
echo "🐍 Setting up Python environment with uv..."
if [ ! -d ".venv" ]; then
    uv venv
fi

# Install dependencies
echo "📚 Installing Python dependencies..."
uv pip install -e .
uv pip install pytest pytest-cov

# Install pre-commit hooks if .pre-commit-config.yaml exists
if [ -f ".pre-commit-config.yaml" ]; then
    echo "🔧 Installing pre-commit hooks..."
    uv pip install pre-commit
    pre-commit install
fi

# Set up git config if not already set
if [ -z "$(git config --global user.email)" ]; then
    echo "📝 Setting up git config..."
    echo "Please configure git:"
    echo "  git config --global user.email 'you@example.com'"
    echo "  git config --global user.name 'Your Name'"
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "🔐 Creating .env file template..."
    cat > .env << EOF
# Pushbullet API configuration
PUSHBULLET_TOKEN=your_token_here
EOF
    echo "⚠️  Please update .env with your Pushbullet API token"
fi

# Display Python and tool versions
echo ""
echo "✅ Development environment ready!"
echo ""
echo "Tool versions:"
mise --version
uv --version
python --version
echo ""
echo "Python location: $(which python)"
echo "Virtual environment: $(pwd)/.venv"
echo ""
echo "To activate the virtual environment manually:"
echo "  source .venv/bin/activate"
echo ""
echo "To run tests:"
echo "  uv run pytest"
echo ""