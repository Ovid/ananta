#!/usr/bin/env bash
# Launch the Shesha Document Explorer.
# Handles venv creation, dependency installation, frontend build, and startup.
#
# Usage:
#   ./document-explorer/document-explorer.sh                      # defaults
#   ./document-explorer/document-explorer.sh --model gpt-5-mini   # pass args
#   ./document-explorer/document-explorer.sh --port 9000           # custom port
#   ./document-explorer/document-explorer.sh --no-browser          # don't open browser
#   ./document-explorer/document-explorer.sh --rebuild             # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/shared/frontend"
FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/document_explorer/frontend"
FRONTEND_DIST="$FRONTEND_DIR/dist"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[shesha]${NC} $*"; }
warn()  { echo -e "${YELLOW}[shesha]${NC} $*"; }
error() { echo -e "${RED}[shesha]${NC} $*" >&2; }

# --- Parse our own flags (strip --rebuild before passing to shesha-document-explorer) ---
REBUILD=false
SHESHA_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--rebuild" ]; then
        REBUILD=true
    else
        SHESHA_ARGS+=("$arg")
    fi
done

# --- Check prerequisites ---
check_command() {
    if ! command -v "$1" &>/dev/null; then
        error "$1 is required but not found. $2"
        exit 1
    fi
}

check_command python3 "Install from https://www.python.org/downloads/"
check_command node    "Install from https://nodejs.org/"
check_command npm     "Install from https://nodejs.org/"
check_command docker  "Install from https://www.docker.com/get-started/"

# Check Python version >= 3.12
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 12 ]; }; then
    error "Python 3.12+ required, found $PYVER"
    exit 1
fi

# Check for an API key
if [ -z "${SHESHA_API_KEY:-}" ]; then
    warn "No SHESHA_API_KEY detected. Set it before querying documents. Continuing anyway..."
fi

# Check Docker is running
if ! docker info &>/dev/null 2>&1; then
    warn "Docker daemon is not running. Start Docker Desktop before querying documents."
fi

# --- Virtual environment ---
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# --- Python dependencies ---
MARKER="$VENV_DIR/.shesha-document-explorer-installed"
if [ ! -f "$MARKER" ] || [ "$PROJECT_ROOT/pyproject.toml" -nt "$MARKER" ]; then
    info "Installing Python dependencies..."
    pip install -q -e "$PROJECT_ROOT[document-explorer]"
    touch "$MARKER"
else
    info "Python dependencies up to date."
fi

# --- Frontend build ---
if [ "$REBUILD" = true ] || [ ! -d "$FRONTEND_DIST" ]; then
    info "Installing shared UI dependencies..."
    (cd "$SHARED_FRONTEND_DIR" && npm install --silent)
    info "Building frontend..."
    (cd "$FRONTEND_DIR" && npm install --silent && npm run build)
else
    info "Frontend already built. Use --rebuild to force."
fi

# --- Launch ---
info "Starting Shesha Document Explorer..."
exec shesha-document-explorer ${SHESHA_ARGS[@]+"${SHESHA_ARGS[@]}"}
