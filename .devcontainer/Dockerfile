FROM mcr.microsoft.com/devcontainers/python:3.12-bullseye

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch to vscode user
USER vscode
WORKDIR /home/vscode

# Install mise
RUN curl https://mise.run | sh && \
    echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    echo 'source $HOME/.cargo/env' >> ~/.bashrc

# Set up mise and uv in PATH for subsequent commands
ENV PATH="/home/vscode/.local/bin:/home/vscode/.cargo/bin:${PATH}"

# Pre-install Python with mise
RUN mise use --global python@3.12 && \
    mise install

# Create directory for custom bashrc additions
RUN mkdir -p ~/.bashrc.d && \
    echo 'for f in ~/.bashrc.d/*; do [ -f "$f" ] && source "$f"; done' >> ~/.bashrc

# Set working directory
WORKDIR /workspaces