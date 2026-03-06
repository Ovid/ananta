# Shared Launcher Validation Design

## Problem

The three explorer launcher scripts (`code-explorer.sh`, `arxiv-explorer.sh`,
`document-explorer.sh`) duplicate ~80 lines of identical shell code. They also
have weak validation: Docker-not-running and missing `SHESHA_API_KEY` are
non-blocking warnings, `SHESHA_MODEL` is not checked at all, and failures
abort on the first error rather than reporting everything at once.

## Goals

1. Collect all validation failures and print a single actionable report before
   exiting.
2. Add `SHESHA_MODEL` as a mandatory environment variable.
3. Promote Docker-daemon and `SHESHA_API_KEY` checks from warnings to hard
   failures.
4. Extract all shared logic into `scripts/common.sh` so each launcher is pure
   config (~15 lines).

## Validation Checks

| Check | Applies to | Action on failure |
|---|---|---|
| `python3` installed | All | Report install URL |
| Python >= 3.11 | All | Report required version |
| `node` installed | All | Report install URL |
| `npm` installed | All | Report install URL |
| `docker` installed | All | Report install URL |
| Docker daemon running | All | Report "start Docker Desktop" |
| `git` installed | code-explorer only | Report install URL |
| `SHESHA_API_KEY` set | All | Report export command |
| `SHESHA_MODEL` set | All | Report export command |

## Architecture

### `scripts/common.sh`

Contains all shared logic:

- Color helpers (`info`, `warn`, `error`)
- `--rebuild` flag parsing
- Error collection (`ERRORS` array)
- Check functions: `require_command`, `check_python_version`, `require_env`,
  `check_docker_running`
- `report_and_exit` — prints all collected errors and exits non-zero if any
- `run_preflight` — orchestrates all checks, then calls `report_and_exit`
- Lifecycle functions: `setup_venv`, `install_python_deps`, `build_frontend`
- `launch` — single entry point: preflight, venv, deps, build, exec

### Launcher scripts

Each launcher sets config variables then sources `common.sh`:

```bash
APP_NAME="Shesha Code Explorer"   # Display name
APP_SLUG="shesha-code"            # Used for pip marker file
PIP_EXTRA="web"                   # pyproject.toml extra
ENTRY_POINT="shesha-code"         # CLI command to exec
REQUIRES_GIT=true                 # Optional, default false
FRONTEND_DIR="..."                # Path to frontend source
SHARED_FRONTEND_DIR="..."        # Optional, for shared UI deps
```

Then: `source "$PROJECT_ROOT/scripts/common.sh"` and `launch "$@"`.

### Config per explorer

| Variable | code-explorer | arxiv-explorer | document-explorer |
|---|---|---|---|
| `APP_NAME` | Shesha Code Explorer | Shesha arXiv Web Explorer | Shesha Document Explorer |
| `APP_SLUG` | shesha-code | shesha-web | shesha-document-explorer |
| `PIP_EXTRA` | web | web | document-explorer |
| `ENTRY_POINT` | shesha-code | shesha-web | shesha-document-explorer |
| `REQUIRES_GIT` | true | (unset) | (unset) |
| `SHARED_FRONTEND_DIR` | set | (unset) | set |

## Example error report

```
[shesha] Cannot start Shesha Code Explorer. Fix the following:
  - Install docker: https://www.docker.com/get-started/
  - Start Docker daemon (e.g. open Docker Desktop)
  - Set SHESHA_API_KEY: export SHESHA_API_KEY=<your-key>
  - Set SHESHA_MODEL: export SHESHA_MODEL=<model-name>
```

## Key design decisions

- Downstream checks skip if the prerequisite command is missing (e.g., don't
  check Docker daemon if `docker` isn't installed). Avoids cascading errors.
- `require_env` uses bash indirect expansion (`${!var}`) for generic env
  checking.
- `SHARED_FRONTEND_DIR` is optional; `build_frontend` only installs shared
  deps when it's set.
- Flag parsing for `--rebuild` lives in `common.sh` since all scripts use it.
