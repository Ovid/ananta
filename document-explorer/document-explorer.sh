#!/usr/bin/env bash
# Launch the Shesha Document Explorer.
# Usage:
#   ./document-explorer/document-explorer.sh                      # defaults
#   ./document-explorer/document-explorer.sh --model gpt-5-mini   # pass args
#   ./document-explorer/document-explorer.sh --port 9000           # custom port
#   ./document-explorer/document-explorer.sh --no-browser          # don't open browser
#   ./document-explorer/document-explorer.sh --rebuild             # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Shesha Document Explorer"
APP_SLUG="shesha-document-explorer"
PIP_EXTRA="document-explorer"
ENTRY_POINT="shesha-document-explorer"
FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/document_explorer/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/shared/frontend"

source "$PROJECT_ROOT/scripts/common.sh"
launch "$@"
