# CLAUDE.md

## Project Overview

Ananta: Python library for Recursive Language Models (RLMs) per arXiv:2512.24601v1. Documents load as variables in a sandboxed Python REPL; LLM generates code to explore them, sees output, repeats until `FINAL("answer")`.

## Architecture

```
User Query → RLM Core Loop → Docker Sandbox
                ↓                  ↓
           LiteLLM Client    llm_query() sub-calls
                ↓
           Trace Recorder
```

**Core engine** (`src/ananta/`):
- `rlm/` — RLM engine (core loop, prompts, trace, semantic verification, boundary handling)
- `sandbox/` — Docker executor, container pool, in-container runner
- `storage/` — Pluggable storage backends (filesystem default)
- `parser/` — Document parsers (PDF, DOCX, HTML, code, text)
- `llm/` — LiteLLM wrapper
- `analysis/` — Analysis shortcut classifier
- `security/` — Path traversal, redaction, boundary tokens
- `repo/` — Git repository ingestion for code analysis
- `prompts/` — External prompt templates (packaged into the wheel)
- `tui/` — Terminal UI

**Explorers** (`src/ananta/explorers/`) — user-facing apps built on the engine:
- `arxiv/`, `code/`, `document/` — three web explorers (FastAPI + React frontends)
- `shared_ui/` — shared backend (app factory, routes, websockets, session) and frontend package (`@ananta/shared-ui`) consumed by all three. **When extending or adding an explorer, read `docs/extending-web-tools.md` first.**
- `launcher.py` — Python launcher that replaced the old shell scripts (see current branch)

**Security:** Two untrusted content tag patterns:
- `llm_query(instruction, content)` — instruction trusted, content wrapped in `<untrusted_document_content>` tags
- REPL output shown to LLM wrapped in `<repl_output type="untrusted_document_content">` tags

Per-query boundary tokens (`secrets.token_hex(16)`) prevent forged closing tags. Containers are network-isolated with no egress; LLM sub-calls are made from the host.

## Commands

Python 3.11+ required (per `pyproject.toml`; mypy/ruff target py311).

```bash
python -m venv .venv             # Create virtual environment
source .venv/bin/activate        # Activate venv (use .venv first!)
pip install -e ".[dev]"          # Install with dev extras

# Sandbox container — required before running anything end-to-end
docker build -t ananta-sandbox -f src/ananta/sandbox/Dockerfile src/ananta/sandbox/

# Make targets (preferred over raw tool invocations)
make all                         # Format + lint + typecheck (py & ts) + test (py & frontend)
make test                        # Python tests only
make test-frontend               # Vitest (src/ananta/explorers/arxiv/frontend)
make typecheck                   # mypy src/ananta
make typecheck-frontend          # tsc on shared_ui frontend
make lint                        # ruff check
make format                      # ruff format + ruff check --fix
make cover                       # pytest with coverage
make loc                         # cloc summary

# Single test
pytest tests/path/test_file.py::test_name -v
```

**Test layout:** `tests/{unit,integration,explorers,examples,fixtures}/`. Frontend tests live next to their source under `src/ananta/explorers/*/frontend/`.

**Console scripts** (installed by `pip install -e .`):

| Script | Launches |
|---|---|
| `ananta-web` | arXiv Explorer |
| `ananta-code` | Code Explorer |
| `ananta-document-explorer` | Document Explorer |

## MANDATORY TDD

**ALL CODE MUST USE TEST-DRIVEN DEVELOPMENT. NO EXCEPTIONS (unless config/docs).**

### Red → Green → Refactor

1. **RED:** Write failing test FIRST. Run it. Confirm failure.
2. **GREEN:** Write MINIMAL code to pass. Nothing extra.
3. **REFACTOR:** Clean up if needed, keeping tests green.
4. **COMMIT:** After each green state.

### Refactor scope for bug fixes

A bug-fix commit MAY include refactoring as part of the same red/green/refactor cycle, **as long as the refactor is the direct result of the changes made to fix the bug.** Example: if the fix introduces a second copy of an existing pattern, extracting the shared helper in the REFACTOR step is appropriate and encouraged — it eliminates duplication the fix itself created and prevents the same bug class from regressing in the future.

This explicitly overrides the general "a bug fix doesn't need surrounding cleanup" guideline: cleanup that is the *consequence* of the fix is part of the fix. Unrelated cleanup (touching files the fix didn't change, fixing other bugs noticed in passing, stylistic rewrites) still belongs in its own commit.

### Violations

- Implementation before tests
- Tests after implementation
- Skipping red phase
- More code than needed to pass
- Untested code "because it's simple"
- Tests which emit warnings — fix the root cause (e.g., wrap async state updates in `act()`). Only suppress if the warning originates outside this codebase and cannot be fixed here; add a comment explaining why.

## API Boundaries

- **No private API access across module boundaries.** Never access `_`-prefixed attributes from outside the owning class. Use or create public properties/methods instead. Private attributes are internal implementation details — accessing them from another module creates tight coupling that breaks when internals change. The explorer layer uses `Ananta.storage`, `Project.rlm_engine`, and `StorageBackend.get_project_dir()` — not `_storage`, `_rlm_engine`, or `_project_path()`.

## Code Style

- **Imports at top of file:** All imports must be at the top of the file, not inside functions or methods. If an import cannot be at the top (e.g., circular import, optional dependency), add a comment explaining why.

- **Exception handling:** Never silently swallow exceptions with bare `except: pass` or `except Exception: pass`. If ignoring an exception is intentional (e.g., cleanup code where failure is acceptable), add a comment explaining why. Example:
  ```python
  try:
      container.stop()
  except Exception:
      pass  # Container may already be stopped
  ```

## Common Pitfalls

- **Match all user-facing behavior when adding alternate code paths.** When a new route (e.g., analysis shortcut) produces the same kind of output as an existing route (e.g., normal query), it must call the same display methods. Check: thought time, token counts, history recording, info bar updates.

- **Lookups that can fail need fallbacks.** When resolving a value from an external source (sandbox variable, API call, file read), handle the empty/error case explicitly. Never let a failed lookup silently produce an empty answer — fall back to a sensible default.

- **In Textual tests, await worker handles instead of fixed sleeps.** Use `await pilot.app._worker_handle.wait()` then `await pilot.pause()` — not `await pilot.pause(delay=N)`. Fixed sleeps are flaky on slow CI.

## Design Decisions

- Sub-LLM depth = 1 (plain LLM, not recursive) for predictable cost
- Max iterations = 20 (configurable)
- Container pool with 3 warm containers
- Documents organized into projects
- **Beyond PoC mindset:** The web explorers are moving beyond proof-of-concept. When making design choices in the explorer layer, prefer resilient patterns (graceful degradation, self-healing on restart) over shortcuts that assume single-use or ephemeral state. This is not a mandate to gold-plate everything, but "it's just a PoC" should not be the default justification for fragile design.

## Changelog & Versioning

**CHANGELOG.md must be updated with every user-visible change.** Format: [keepachangelog 1.1.0](https://keepachangelog.com/en/1.1.0/).

### Adding Changelog Entries

Add entries under `[Unreleased]` using these categories (in this order):
- **Added** — New features
- **Changed** — Changes to existing functionality
- **Deprecated** — Features to be removed in future
- **Removed** — Removed features
- **Fixed** — Bug fixes
- **Security** — Security-related changes

Omit empty categories. Entries should describe user-visible behavior changes, not implementation details.

### Merging Feature Branches

**Use `/release` to merge feature branches. Never use bare `git done`.**

`/release` handles: changelog finalization, semantic version suggestion, `git done -y`, tagging, and push. It is the only sanctioned merge path for feature branches.

### Version Auto-Increment Rules

Version numbers are derived from git tags via `hatch-vcs`. The `/release` skill suggests versions based on changelog categories:

**Pre-1.0 (current):**

| Highest category present | Bump |
|---|---|
| Removed, or explicit breaking change | minor |
| Added, Changed, Deprecated | minor |
| Fixed, Security only | patch |

**Post-1.0:** Removed/breaking → major. Otherwise same as above.

Comparison links at the bottom of CHANGELOG.md are mandatory. Format:
```
[unreleased]: https://github.com/Ovid/ananta/compare/vLATEST...HEAD
[X.Y.Z]: https://github.com/Ovid/ananta/compare/vPREVIOUS...vX.Y.Z
```
