#!/usr/bin/env bash
# Launch the Ananta arXiv Web Explorer.
# Usage:
#   ./arxiv-explorer/arxiv-explorer.sh                      # defaults
#   ./arxiv-explorer/arxiv-explorer.sh --model gpt-5-mini   # pass args to ananta-web
#   ./arxiv-explorer/arxiv-explorer.sh --port 8080          # custom port
#   ./arxiv-explorer/arxiv-explorer.sh --no-browser         # don't open browser
#   ./arxiv-explorer/arxiv-explorer.sh --rebuild            # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Ananta arXiv Web Explorer"
APP_SLUG="ananta-web"
PIP_EXTRA="web"
ENTRY_POINT="ananta-web"
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/web/frontend"

source "$PROJECT_ROOT/scripts/common.sh"
launch "$@"
