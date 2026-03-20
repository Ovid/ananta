#!/usr/bin/env bash
# Launch the Ananta Code Explorer.
# Usage:
#   ./code-explorer/code-explorer.sh                      # defaults
#   ./code-explorer/code-explorer.sh --model gpt-5-mini   # pass args to ananta-code
#   ./code-explorer/code-explorer.sh --port 9000           # custom port
#   ./code-explorer/code-explorer.sh --no-browser          # don't open browser
#   ./code-explorer/code-explorer.sh --rebuild             # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Ananta Code Explorer"
APP_SLUG="ananta-code"
PIP_EXTRA="web"
ENTRY_POINT="ananta-code"
REQUIRES_GIT=true
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/code_explorer/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/shared/frontend"

source "$PROJECT_ROOT/scripts/common.sh"
launch "$@"
