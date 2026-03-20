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

## API Boundaries

- **No private API access across module boundaries.** Never access `_`-prefixed attributes from outside the owning class. Use or create public properties/methods instead. Private attributes are internal implementation details — accessing them from another module creates tight coupling that breaks when internals change. The experimental layer uses `Shesha.storage`, `Project.rlm_engine`, and `StorageBackend.get_project_dir()` — not `_storage`, `_rlm_engine`, or `_project_path()`.

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
- **Beyond PoC mindset:** The experimental web explorers are moving beyond proof-of-concept. When making design choices in the experimental layer, prefer resilient patterns (graceful degradation, self-healing on restart) over shortcuts that assume single-use or ephemeral state. This is not a mandate to gold-plate everything, but "it's just a PoC" should not be the default justification for fragile design.

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
[unreleased]: https://github.com/Ovid/shesha/compare/vLATEST...HEAD
[X.Y.Z]: https://github.com/Ovid/shesha/compare/vPREVIOUS...vX.Y.Z
```

### git

CRITICAL: git commit messages MUST be plain text. Never do things similar to `git commit -m "$(cat <<'COMMITEOF'`
