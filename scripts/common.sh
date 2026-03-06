#!/usr/bin/env bash
# Shared launcher logic for Shesha explorer scripts.
# Source this file after setting config variables — see individual launchers.

# --- Derived paths ---
VENV_DIR="$PROJECT_ROOT/.venv"
FRONTEND_DIST="$FRONTEND_DIR/dist"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info()  { echo -e "${GREEN}[shesha]${NC} $*"; }
error() { echo -e "${RED}[shesha]${NC} $*" >&2; }

# --- Parse flags (strip --rebuild before passing to the explorer) ---
REBUILD=false
SHESHA_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--rebuild" ]; then
        REBUILD=true
    else
        SHESHA_ARGS+=("$arg")
    fi
done

# --- Preflight validation ---
ERRORS=()

require_command() {
    local cmd="$1" install_hint="$2"
    if ! command -v "$cmd" &>/dev/null; then
        ERRORS+=("  - Install $cmd: $install_hint")
    fi
}

check_python_version() {
    if ! command -v python3 &>/dev/null; then return; fi
    local ver major minor
    ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=${ver%%.*}; minor=${ver##*.}
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 12 ]; }; then
        ERRORS+=("  - Upgrade Python: 3.12+ required, found $ver")
    fi
}

require_env() {
    local var="$1" hint="$2"
    if [ -z "${!var:-}" ]; then
        ERRORS+=("  - Set $var: $hint")
    fi
}

check_docker_running() {
    if ! command -v docker &>/dev/null; then return; fi
    if ! docker info &>/dev/null; then
        ERRORS+=("  - Start Docker daemon (e.g. open Docker Desktop)")
    fi
}

report_and_exit() {
    if [ ${#ERRORS[@]} -gt 0 ]; then
        error "Cannot start $APP_NAME. Fix the following:"
        for e in "${ERRORS[@]}"; do echo -e "$e" >&2; done
        exit 1
    fi
}

run_preflight() {
    require_command python3 "https://www.python.org/downloads/"
    require_command node    "https://nodejs.org/"
    require_command npm     "https://nodejs.org/"
    require_command docker  "https://www.docker.com/get-started/"
    if [ "${REQUIRES_GIT:-false}" = true ]; then
        require_command git "https://git-scm.com/"
    fi
    check_python_version
    require_env SHESHA_API_KEY "export SHESHA_API_KEY=<your-key>"
    require_env SHESHA_MODEL   "export SHESHA_MODEL=<model-name>"
    check_docker_running
    report_and_exit
}

# --- Lifecycle ---
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
}

install_python_deps() {
    local marker="$VENV_DIR/.${APP_SLUG}-installed"
    if [ ! -f "$marker" ] || [ "$PROJECT_ROOT/pyproject.toml" -nt "$marker" ]; then
        info "Installing Python dependencies..."
        pip install -q -e "$PROJECT_ROOT[$PIP_EXTRA]"
        touch "$marker"
    else
        info "Python dependencies up to date."
    fi
}

build_frontend() {
    if [ -n "${SHARED_FRONTEND_DIR:-}" ]; then
        if [ "$REBUILD" = true ] || [ ! -d "$FRONTEND_DIST" ]; then
            info "Installing shared UI dependencies..."
            (cd "$SHARED_FRONTEND_DIR" && npm install --silent)
        fi
    fi
    if [ "$REBUILD" = true ] || [ ! -d "$FRONTEND_DIST" ]; then
        info "Building frontend..."
        (cd "$FRONTEND_DIR" && npm install --silent && npm run build)
    else
        info "Frontend already built. Use --rebuild to force."
    fi
}

stderr_filter() {
    # Suppress Python GC "Exception ignored" traceback blocks that appear
    # during shutdown (harmless but scary-looking to users).
    awk '
        /^Exception ignored/ { skip=1; next }
        skip && /^[A-Z][a-zA-Z]*Error:/ { skip=0; next }
        skip { next }
        { print }
    '
}

launch() {
    run_preflight
    setup_venv
    install_python_deps
    build_frontend
    info "Starting $APP_NAME..."
    "$ENTRY_POINT" ${SHESHA_ARGS[@]+"${SHESHA_ARGS[@]}"} 2> >(stderr_filter >&2)
}
