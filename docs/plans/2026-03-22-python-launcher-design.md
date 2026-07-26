# Python Launcher Scripts Design

**Date:** 2026-03-22
**Status:** Approved (post-pushback)

## Motivation

The three explorer launcher scripts (`arxiv-explorer.sh`, `code-explorer.sh`,
`document-explorer.sh`) and their shared logic (`scripts/common.sh`) are bash.
This causes three problems:

1. **Testability** — the launcher logic (preflight checks, build steps) can't be unit tested
2. **Consolidation** — shared logic deserves a proper Python module, not a sourced shell file
3. **Maintainability** — the bash has grown complex enough (staleness markers, shared UI logic, stderr filter) that Python would be clearer

Note: Cross-platform (Windows) support is a future goal but not achieved by this
design alone — the bash shims are still Unix-only. However, the Python logic
(`launch.py` + `launcher.py`) is fully portable, so users who install via pip
can run explorers on Windows without the shims.

## Design

### Architecture

Each explorer keeps a bash shim (`*-explorer.sh`) that handles only the
bootstrapping problem: ensuring a venv exists and dependencies are installed.
All real logic moves to Python.

```
*-explorer/*-explorer.sh    (bash shim: venv + pip install)
    └── *-explorer/launch.py (thin config + call shared launcher)
            └── src/ananta/explorers/launcher.py (all shared logic)
```

### Bash Shim (~20 lines each)

The shim's only responsibilities:
- Determine `PROJECT_ROOT` and `VENV_DIR`
- Create venv if missing
- Activate venv
- Install pip dependencies if stale (marker file vs pyproject.toml mtime)
- `exec python launch.py "$@"`

Each shim differs only in `PIP_EXTRA` and `APP_SLUG` variables.

Example (arxiv):

```bash
#!/usr/bin/env bash
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
```

### Python `launch.py` (thin, per-explorer)

Each explorer gets a `launch.py` that defines config and calls the shared launcher:

```python
#!/usr/bin/env python3
"""Launch the Ananta arXiv Web Explorer."""

from ananta.explorers.launcher import LauncherConfig, launch

config = LauncherConfig(
    app_name="Ananta arXiv Web Explorer",
    entry_point="ananta-web",
    frontend_dir="src/ananta/explorers/arxiv/frontend",
    requires_git=False,
    shared_frontend_dir=None,
)

if __name__ == "__main__":
    launch(config)
```

### Shared Launcher (`src/ananta/explorers/launcher.py`)

Responsibilities, in order:

1. **Parse args** — strip `--rebuild`, pass the rest through to the entry point
2. **Preflight checks** — collect all errors, report at once:
   - Python version >= 3.11
   - `node`, `npm`, `docker` on PATH
   - `git` on PATH (if `requires_git`)
   - `ANANTA_API_KEY` and `ANANTA_MODEL` env vars set
   - Docker daemon running
   - Sandbox image exists — attempt to build if missing, only error if build fails
3. **Build frontend** — `npm install` + `npm run build` for shared UI (if configured) and explorer frontend, skipped if `dist/` exists unless `--rebuild`
4. **Launch** — `subprocess.run()` + `sys.exit()` the entry point with remaining args (not `os.execvp()`, for Windows compatibility)

Key design points:
- `LauncherConfig` is a dataclass
- Each preflight check is a small method returning an optional error string (testable)
- No stderr filter (dropped — fix root causes instead of filtering symptoms)
- `--rebuild` is the only flag consumed by the launcher; all others pass through unchanged

## Files Changed

### Created
- `src/ananta/explorers/launcher.py` — shared launcher logic
- `arxiv-explorer/launch.py` — arxiv config
- `code-explorer/launch.py` — code config
- `document-explorer/launch.py` — document config

### Rewritten
- `arxiv-explorer/arxiv-explorer.sh` — bash shim
- `code-explorer/code-explorer.sh` — bash shim
- `document-explorer/document-explorer.sh` — bash shim

### Deleted
- `scripts/common.sh` — replaced by `launcher.py`
- `examples/arxiv-explorer.sh` — stale, points at old paths

### Updated
- `README.md` — update Document Explorer section: drop "(Experimental)" label, replace `python -m` invocation with launcher script reference
- `CHANGELOG.md` — entry under Unreleased/Changed

## Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Invocation style | Same paths, `.sh` preserved | Preserves existing UX |
| Shared logic location | `src/ananta/explorers/launcher.py` | Importable, testable, scoped to explorers |
| Venv bootstrap | Stays in bash shim | Avoids chicken-and-egg (launcher can't import before pip install) |
| Pip install | Stays in bash shim | Same bootstrap reason |
| Stderr filter | Dropped | Fix root causes, not symptoms |
| Frontend build | Python (`subprocess.run`) | Maximizes testability |
| `--rebuild` handling | Python (only flag consumed by launcher) | Same reason |
| Process launch | `subprocess.run()` + `sys.exit()` | `os.execvp()` is Unix-only; Python logic should be portable |
| Sandbox image build | Auto-build during preflight, error only on failure | Matches current behavior; good UX |
| Per-explorer configs | Separate `launch.py` files (not a registry) | Simpler now; trivial to consolidate into a dict later for unified launcher |
| Cross-platform | Bash shims Unix-only; Python logic portable | Windows users can `pip install` and run `launch.py` directly |
