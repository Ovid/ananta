#!/usr/bin/env bash
# Launch the Ananta arXiv Web Explorer.
# Usage:
#   ./arxiv-explorer/arxiv-explorer.sh                      # defaults
#   ./arxiv-explorer/arxiv-explorer.sh --model gpt-5-mini   # pass args to ananta-web
#   ./arxiv-explorer/arxiv-explorer.sh --port 8080          # custom port
#   ./arxiv-explorer/arxiv-explorer.sh --open               # open browser on startup
#   ./arxiv-explorer/arxiv-explorer.sh --rebuild            # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PIP_EXTRA="web"
APP_SLUG="ananta-web"

if [ ! -d "$VENV_DIR" ]; then
    echo "[ananta] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

MARKER="$VENV_DIR/.${APP_SLUG}-installed"
if [ ! -f "$MARKER" ] || [ "$PROJECT_ROOT/pyproject.toml" -nt "$MARKER" ]; then
    echo "[ananta] Installing Python dependencies..."
    pip install -q -e "$PROJECT_ROOT[$PIP_EXTRA]"
    touch "$MARKER"
fi

exec python "$SCRIPT_DIR/launch.py" "$@"
