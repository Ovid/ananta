# Shared Launcher Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract shared launcher logic into `scripts/common.sh`, collect all preflight failures into a single report, and reduce each launcher to ~15 lines of config.

**Architecture:** A shared `scripts/common.sh` defines validation functions that collect errors into a bash array instead of exiting immediately. Each launcher sets config variables (`APP_NAME`, `PIP_EXTRA`, `ENTRY_POINT`, etc.), sources `common.sh`, and calls `launch "$@"`.

**Tech Stack:** Bash, bats-core (for testing)

---

### Task 1: Create `scripts/common.sh` with validation and error collection

**Files:**
- Create: `scripts/common.sh`

**Step 1: Create `scripts/common.sh` with all shared logic**

```bash
#!/usr/bin/env bash
# Shared launcher logic for Shesha explorer scripts.
# Source this file after setting config variables — see individual launchers.

# --- Derived paths ---
VENV_DIR="$PROJECT_ROOT/.venv"
FRONTEND_DIST="$FRONTEND_DIR/dist"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[shesha]${NC} $*"; }
warn()  { echo -e "${YELLOW}[shesha]${NC} $*"; }
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
    if ! docker info &>/dev/null 2>&1; then
        ERRORS+=("  - Start Docker daemon (e.g. open Docker Desktop)")
    fi
}

report_and_exit() {
    if [ ${#ERRORS[@]} -gt 0 ]; then
        error "Cannot start $APP_NAME. Fix the following:"
        for e in "${ERRORS[@]}"; do echo -e "$e"; done
        exit 1
    fi
}

run_preflight() {
    require_command python3 "https://www.python.org/downloads/"
    require_command node    "https://nodejs.org/"
    require_command npm     "https://nodejs.org/"
    require_command docker  "https://www.docker.com/get-started/"
    [ "${REQUIRES_GIT:-false}" = true ] && \
        require_command git "https://git-scm.com/"
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

launch() {
    run_preflight
    setup_venv
    install_python_deps
    build_frontend
    info "Starting $APP_NAME..."
    exec "$ENTRY_POINT" ${SHESHA_ARGS[@]+"${SHESHA_ARGS[@]}"}
}
```

**Step 2: Make it executable**

Run: `chmod +x scripts/common.sh`

**Step 3: Commit**

```bash
git add scripts/common.sh
git commit -m "feat: add shared launcher common.sh with preflight validation"
```

---

### Task 2: Write tests for `scripts/common.sh`

**Files:**
- Create: `tests/scripts/test_common.bats`

**Step 1: Install bats-core if not present**

Run: `brew list bats-core &>/dev/null || brew install bats-core`

**Step 2: Write bats tests for error collection and reporting**

```bash
#!/usr/bin/env bats
# Tests for scripts/common.sh preflight validation.

COMMON="$BATS_TEST_DIRNAME/../../scripts/common.sh"

setup() {
    # Minimal config required by common.sh
    export PROJECT_ROOT="$BATS_TEST_DIRNAME/../.."
    export APP_NAME="Test Explorer"
    export APP_SLUG="test-explorer"
    export PIP_EXTRA="dev"
    export ENTRY_POINT="echo"
    export FRONTEND_DIR="$BATS_TEST_TMPDIR/frontend"
    mkdir -p "$FRONTEND_DIR/dist"
}

# --- require_command ---

@test "require_command adds error for missing command" {
    source "$COMMON"
    ERRORS=()
    require_command "nonexistent_cmd_xyz" "https://example.com"
    [ ${#ERRORS[@]} -eq 1 ]
    [[ "${ERRORS[0]}" == *"Install nonexistent_cmd_xyz"* ]]
}

@test "require_command succeeds for existing command" {
    source "$COMMON"
    ERRORS=()
    require_command "bash" "https://example.com"
    [ ${#ERRORS[@]} -eq 0 ]
}

# --- require_env ---

@test "require_env adds error for unset variable" {
    unset TOTALLY_UNSET_VAR
    source "$COMMON"
    ERRORS=()
    require_env "TOTALLY_UNSET_VAR" "export TOTALLY_UNSET_VAR=value"
    [ ${#ERRORS[@]} -eq 1 ]
    [[ "${ERRORS[0]}" == *"Set TOTALLY_UNSET_VAR"* ]]
}

@test "require_env adds error for empty variable" {
    export EMPTY_VAR=""
    source "$COMMON"
    ERRORS=()
    require_env "EMPTY_VAR" "export EMPTY_VAR=value"
    [ ${#ERRORS[@]} -eq 1 ]
}

@test "require_env passes for set variable" {
    export PRESENT_VAR="hello"
    source "$COMMON"
    ERRORS=()
    require_env "PRESENT_VAR" "export PRESENT_VAR=value"
    [ ${#ERRORS[@]} -eq 0 ]
}

# --- check_python_version ---

@test "check_python_version passes for current python" {
    source "$COMMON"
    ERRORS=()
    check_python_version
    [ ${#ERRORS[@]} -eq 0 ]
}

# --- report_and_exit ---

@test "report_and_exit does nothing when no errors" {
    source "$COMMON"
    ERRORS=()
    run report_and_exit
    [ "$status" -eq 0 ]
}

@test "report_and_exit exits 1 and prints errors" {
    source "$COMMON"
    ERRORS=("  - Error one" "  - Error two")
    run report_and_exit
    [ "$status" -eq 1 ]
    [[ "$output" == *"Cannot start Test Explorer"* ]]
    [[ "$output" == *"Error one"* ]]
    [[ "$output" == *"Error two"* ]]
}

# --- Error collection (multiple failures) ---

@test "multiple failures are all collected" {
    unset SHESHA_API_KEY
    unset SHESHA_MODEL
    source "$COMMON"
    ERRORS=()
    require_command "nonexistent_cmd_xyz" "https://example.com"
    require_env "SHESHA_API_KEY" "export SHESHA_API_KEY=<your-key>"
    require_env "SHESHA_MODEL" "export SHESHA_MODEL=<model-name>"
    [ ${#ERRORS[@]} -eq 3 ]
}

# --- Flag parsing ---

@test "--rebuild flag is stripped from args" {
    export SHESHA_API_KEY="test"
    export SHESHA_MODEL="test"
    set -- --port 9000 --rebuild --no-browser
    source "$COMMON"
    [ "$REBUILD" = true ]
    [ ${#SHESHA_ARGS[@]} -eq 3 ]
    [[ "${SHESHA_ARGS[*]}" == "--port 9000 --no-browser" ]]
}

@test "args without --rebuild are passed through" {
    export SHESHA_API_KEY="test"
    export SHESHA_MODEL="test"
    set -- --port 9000
    source "$COMMON"
    [ "$REBUILD" = false ]
    [ ${#SHESHA_ARGS[@]} -eq 2 ]
}
```

**Step 3: Run tests to verify they pass**

Run: `bats tests/scripts/test_common.bats`
Expected: All tests pass.

**Step 4: Commit**

```bash
git add tests/scripts/test_common.bats
git commit -m "test: add bats tests for shared launcher common.sh"
```

---

### Task 3: Rewrite `code-explorer/code-explorer.sh`

**Files:**
- Modify: `code-explorer/code-explorer.sh` (full rewrite)

**Step 1: Replace contents with config + source**

```bash
#!/usr/bin/env bash
# Launch the Shesha Code Explorer.
# Usage:
#   ./code-explorer/code-explorer.sh                      # defaults
#   ./code-explorer/code-explorer.sh --model gpt-5-mini   # pass args to shesha-code
#   ./code-explorer/code-explorer.sh --port 9000           # custom port
#   ./code-explorer/code-explorer.sh --no-browser          # don't open browser
#   ./code-explorer/code-explorer.sh --rebuild             # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Shesha Code Explorer"
APP_SLUG="shesha-code"
PIP_EXTRA="web"
ENTRY_POINT="shesha-code"
REQUIRES_GIT=true
FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/code_explorer/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/shared/frontend"

source "$PROJECT_ROOT/scripts/common.sh"
launch "$@"
```

**Step 2: Verify syntax**

Run: `bash -n code-explorer/code-explorer.sh`
Expected: No output (syntax OK).

**Step 3: Commit**

```bash
git add code-explorer/code-explorer.sh
git commit -m "refactor(code-explorer): use shared scripts/common.sh"
```

---

### Task 4: Rewrite `arxiv-explorer/arxiv-explorer.sh`

**Files:**
- Modify: `arxiv-explorer/arxiv-explorer.sh` (full rewrite)

**Step 1: Replace contents with config + source**

```bash
#!/usr/bin/env bash
# Launch the Shesha arXiv Web Explorer.
# Usage:
#   ./arxiv-explorer/arxiv-explorer.sh                      # defaults
#   ./arxiv-explorer/arxiv-explorer.sh --model gpt-5-mini   # pass args to shesha-web
#   ./arxiv-explorer/arxiv-explorer.sh --port 8080          # custom port
#   ./arxiv-explorer/arxiv-explorer.sh --no-browser         # don't open browser
#   ./arxiv-explorer/arxiv-explorer.sh --rebuild            # force frontend rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Shesha arXiv Web Explorer"
APP_SLUG="shesha-web"
PIP_EXTRA="web"
ENTRY_POINT="shesha-web"
FRONTEND_DIR="$PROJECT_ROOT/src/shesha/experimental/web/frontend"

source "$PROJECT_ROOT/scripts/common.sh"
launch "$@"
```

**Step 2: Verify syntax**

Run: `bash -n arxiv-explorer/arxiv-explorer.sh`
Expected: No output (syntax OK).

**Step 3: Commit**

```bash
git add arxiv-explorer/arxiv-explorer.sh
git commit -m "refactor(arxiv-explorer): use shared scripts/common.sh"
```

---

### Task 5: Rewrite `document-explorer/document-explorer.sh`

**Files:**
- Modify: `document-explorer/document-explorer.sh` (full rewrite)

**Step 1: Replace contents with config + source**

```bash
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
```

**Step 2: Verify syntax**

Run: `bash -n document-explorer/document-explorer.sh`
Expected: No output (syntax OK).

**Step 3: Commit**

```bash
git add document-explorer/document-explorer.sh
git commit -m "refactor(document-explorer): use shared scripts/common.sh"
```

---

### Task 6: End-to-end verification

**Step 1: Run bats tests**

Run: `bats tests/scripts/test_common.bats`
Expected: All tests pass.

**Step 2: Verify error report with unset env vars**

Run: `unset SHESHA_API_KEY SHESHA_MODEL && bash code-explorer/code-explorer.sh 2>&1 || true`
Expected: Output contains "Cannot start Shesha Code Explorer" followed by lines for each missing item (at minimum `SHESHA_API_KEY` and `SHESHA_MODEL`).

**Step 3: Verify each launcher has valid syntax**

Run: `bash -n code-explorer/code-explorer.sh && bash -n arxiv-explorer/arxiv-explorer.sh && bash -n document-explorer/document-explorer.sh && echo "All OK"`
Expected: "All OK"

**Step 4: Update CHANGELOG.md**

Add under `[Unreleased]` → `Changed`:
```
- Launcher scripts (`code-explorer.sh`, `arxiv-explorer.sh`, `document-explorer.sh`) now
  validate all prerequisites and print a single actionable error report instead of failing
  on the first missing dependency. `SHESHA_MODEL` is now required. Shared logic extracted
  to `scripts/common.sh`.
```

**Step 5: Commit changelog**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for shared launcher validation"
```
