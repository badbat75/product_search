#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

echo "Setting up virtual environment in $VENV_DIR"

# Create venv if it doesn't exist
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists. Delete .venv and re-run to recreate."
    exit 1
fi

python -m venv "$VENV_DIR"

# Activate
if [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"
else
    source "$VENV_DIR/bin/activate"
fi

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
python -m pip install selenium anthropic pandas

# Copy config template if config doesn't exist
if [ ! -f "$PROJECT_DIR/conf/search.cfg" ]; then
    cp "$PROJECT_DIR/conf/search.cfg.template" "$PROJECT_DIR/conf/search.cfg"
    echo ""
    echo "Created conf/search.cfg from template — edit it to set your CLAUDE_API_KEY."
fi

echo ""
echo "Done. Activate the environment with:"
echo "  source .venv/Scripts/activate   # Windows (Git Bash)"
echo "  source .venv/bin/activate       # Linux/macOS"
