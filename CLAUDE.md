# CLAUDE.md

## Project Overview

Shesha: Python library for Recursive Language Models (RLMs) per arXiv:2512.24601v1. Documents load as variables in a sandboxed Python REPL; LLM generates code to explore them, sees output, repeats until `FINAL("answer")`.

## Architecture

```
User Query → RLM Core Loop → Docker Sandbox
                ↓                  ↓
           LiteLLM Client    llm_query() sub-calls
                ↓
           Trace Recorder
```

**Components:** `src/shesha/{rlm,sandbox,storage,parser,llm}/`

**Security:** Two untrusted content tag patterns:
- `llm_query(instruction, content)` - instruction trusted, content wrapped in `<untrusted_document_content>` tags
- REPL output shown to LLM wrapped in `<repl_output type="untrusted_document_content">` tags

Containers network-isolated (egress whitelist for LLM APIs only).

## Commands

```bash
python -m venv .venv             # Create virtual environment
source .venv/bin/activate        # Activate venv (use .venv first!)
pip install -e ".[dev]"          # Install
make all                         # All tests
pytest tests/path::test_name -v  # Single test
mypy src/shesha                  # Type check
ruff check src tests             # Lint
ruff format src tests            # Format
make all                         # Format + lint + typecheck + test
```

## MANDATORY TDD

**ALL CODE MUST USE TEST-DRIVEN DEVELOPMENT. NO EXCEPTIONS (unless config/docs).**

### Red → Green → Refactor

1. **RED:** Write failing test FIRST. Run it. Confirm failure.
2. **GREEN:** Write MINIMAL code to pass. Nothing extra.
3. **REFACTOR:** Clean up if needed, keeping tests green.
4. **COMMIT:** After each green state.

### Violations

- Implementation before tests
- Tests after implementation
- Skipping red phase
- More code than needed to pass
- Untested code "because it's simple"
- Tests which emit warnings — fix the root cause (e.g., wrap async state updates in `act()`). Only suppress if the warning originates outside this codebase and cannot be fixed here; add a comment explaining why.

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

## Changelog & Versioning

**CHANGELOG.md must be updated with every user-visible change.**

### Adding Changelog Entries

Add entries under `[Unreleased]` using these categories:
- **Added** - New features
- **Changed** - Changes to existing functionality
- **Deprecated** - Features to be removed in future
- **Removed** - Removed features
- **Fixed** - Bug fixes
- **Security** - Security-related changes

### git

CRITICAL: git commit messages MUST be plain text. Never do things similar to `git commit -m "$(cat <<'COMMITEOF'`

### Release Workflow

Version numbers are derived from git tags via `hatch-vcs`. To release:

1. Move `[Unreleased]` entries to new version section: `[X.Y.Z] - YYYY-MM-DD`
2. Add fresh `## [Unreleased]` section at top
3. Commit the changelog update
4. Create git tag: `git tag vX.Y.Z`
5. Push with tags: `git push && git push --tags`
