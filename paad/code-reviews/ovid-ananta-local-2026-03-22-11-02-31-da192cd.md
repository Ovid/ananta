# Agentic Code Review: ovid/ananta-local

**Date:** 2026-03-22 11:02:31
**Branch:** ovid/ananta-local -> main
**Commit:** da192cd082ad51c84448cf81329c4109a89974ad
**Files changed:** 25 | **Lines changed:** +1576 / -149
**Diff size category:** Large

## Executive Summary

This branch adds Docker socket auto-discovery with clean error messages, replaces `--no-browser` with `--open` across all explorers, extracts `parse_args()` in the web explorer, and adds `ensure_sandbox_image` to the shell launcher preflight. The core discovery logic is well-structured with proper diagnostic accumulation, thread safety via a class-level lock, and DOCKER_HOST restoration on failure. Four important issues were found: exception masking during pool cleanup, a narrow exception catch in Strategy 1, and two documentation files that still reference the removed `--no-browser` flag.

## Critical Issues

None found.

## Important Issues

### [I1] `pool.stop()` can mask the original exception from `pool.start()`
- **File:** `src/ananta/ananta.py:485-489`
- **Bug:** If `pool.start()` raises (e.g., `ImageNotFound`), the cleanup calls `pool.stop()` before re-raising. If `pool.stop()` also raises, the original exception is lost -- the user sees the cleanup error instead of the root cause. The `app_factory.py` lifespan specifically catches `ImageNotFound` to display a helpful "build it with:" message; if `pool.stop()` masks it with a different exception type, the user gets an unhelpful traceback.
- **Impact:** Users see confusing cleanup errors instead of the actual Docker startup failure message.
- **Suggested fix:** Wrap `pool.stop()` in a try/except:
  ```python
  except BaseException:
      try:
          pool.stop()
      except Exception:
          logger.debug("pool.stop() failed during cleanup", exc_info=True)
      raise
  ```
- **Confidence:** High
- **Found by:** Error Handling & Edge Cases

### [I2] Strategy 1 catches only `DockerException`, not broader exceptions
- **File:** `src/ananta/ananta.py:179`
- **Bug:** Strategy 1 catches only `DockerException`, while Strategies 2 and 3 catch broad `Exception`. The docker SDK can raise exceptions outside the `DockerException` hierarchy (e.g., `requests.exceptions.ConnectionError`, `OSError`) depending on the failure mode. If `DOCKER_HOST` is set to a syntactically valid but unreachable endpoint, these non-`DockerException` errors propagate uncaught, bypassing all remaining strategies and producing a raw traceback instead of the clean diagnostic message.
- **Impact:** Users who set DOCKER_HOST but have a transient connection error get a raw Python traceback instead of the helpful "Could not connect to Docker" remediation steps.
- **Suggested fix:** Change `except DockerException as e:` to `except Exception as e:` to match Strategies 2 and 3.
- **Confidence:** High
- **Found by:** Logic & Correctness, Error Handling & Edge Cases

### [I3] README.md documents obsolete `--no-browser` flag
- **File:** `README.md:326`
- **Bug:** The README shows `--no-browser` as a valid CLI option. The actual CLI now uses `--open` (opt-in). Running the documented command produces `error: unrecognized arguments: --no-browser`.
- **Impact:** Users following the README hit an immediate error.
- **Suggested fix:** Remove `--no-browser` from the example command.
- **Confidence:** High
- **Found by:** Logic & Correctness

### [I4] `docs/extending-web-tools.md` documents obsolete `--no-browser` pattern
- **File:** `docs/extending-web-tools.md:271,279,468`
- **Bug:** The developer guide shows the old `--no-browser` argument pattern in example code. Developers following this guide to build new explorer tools will implement the wrong CLI interface.
- **Impact:** Incorrect patterns propagate to new tools built from this guide.
- **Suggested fix:** Update to use `--open` pattern.
- **Confidence:** High
- **Found by:** Logic & Correctness

## Suggestions

- `pool.stop()` iterates executors without per-executor try/except -- if a future change to `executor.stop()` introduces a new exception path, remaining executors could leak. Wrap each call defensively. (`pool.py:51-57`)
- `app_factory.py` lifespan catches `RuntimeError` and `ImageNotFound` but not other `DockerException` subclasses from `pool.start()`. The gap is narrow (Docker must fail between availability check and pool startup) but adding a `DockerException` catch would be comprehensive. (`app_factory.py:59-72`)
- Overflow container creation in `pool.acquire()` can raise raw `DockerException` now that `executor.start()` no longer wraps Docker errors. Callers in `engine.py` don't catch this. (`pool.py:79-83`)
- `test_parse_args.py` for the web explorer is at `tests/experimental/web/` while equivalent tests are under `tests/unit/experimental/`. Move to `tests/unit/experimental/web/` for consistency.
- Web explorer `main()` has no test coverage (code explorer has 6 `TestMain` methods, document explorer has 2, web explorer has 0).

## Plan Alignment

- **Implemented:** All design goals are met -- 4-strategy socket discovery, clean diagnostic error messages, `_KNOWN_SOCKET_PATHS` class attribute, `@classmethod`, lifespan error handling, executor simplification, scheme validation (improvement beyond design), class-level threading lock.
- **Not yet implemented:** The distinct error message for "socket found but not responding" uses the generic diagnostic list format rather than the design's two-line format ("Found Docker socket at X but Docker is not responding. Is Docker Desktop running?"). Functionally equivalent but differs in phrasing.
- **Additions beyond design:** `ImageNotFound` handling in `app_factory.py`, `--open` flag replacing `--no-browser`, `ensure_sandbox_image` in shell preflight, scheme validation on `docker context inspect` output. All are positive additions.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment
- **Scope:** 25 changed files + callers/callees in pool.py, executor.py, app_factory.py, engine.py
- **Raw findings:** 21 (before verification)
- **Verified findings:** 9 (after verification)
- **Filtered out:** 12
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** docs/plans/2026-03-21-docker-socket-discovery-design.md, docs/plans/2026-03-21-docker-socket-discovery-implementation.md
