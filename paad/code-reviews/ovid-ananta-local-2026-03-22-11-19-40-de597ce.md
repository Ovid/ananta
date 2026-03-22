# Agentic Code Review: ovid/ananta-local

**Date:** 2026-03-22 11:19:40
**Branch:** ovid/ananta-local -> main
**Commit:** de597ce4c9e9cfc401fbbb4c2155e020b091bda4
**Files changed:** 27 | **Lines changed:** +1590 / -157
**Diff size category:** Medium

## Executive Summary

This branch adds Docker socket auto-discovery, replaces `--no-browser` with `--open` across explorers, and improves startup error handling. The discovery logic is solid overall but has a real concurrency hazard around `os.environ` mutation and a state management gap where `stop()` doesn't clear the pool reference, leading to silent failures on restart. The lifespan error handler in `app_factory.py` has a gap that lets `DockerException` escape as a raw traceback.

## Critical Issues

None found.

## Important Issues

### [I1] `stop()` leaves stale pool reference; restart after failure silently broken
- **File:** `src/ananta/ananta.py:495-503`
- **Bug:** `stop()` calls `self._pool.stop()` but never sets `self._pool = None`. After a stop+restart cycle where `pool.start()` fails, `self._pool` still points to the old dead pool, `_stopped` is `False` (set at line 478 before the failure), and the next `start()` call hits the guard `if self._pool is not None and not self._stopped` — returns early without creating a working pool.
- **Impact:** After a failed restart, the system silently appears started but all RLM operations use a dead pool with no error surfaced.
- **Suggested fix:** Add `self._pool = None` after `self._pool.stop()` in `stop()`.
- **Confidence:** High
- **Found by:** Logic & Correctness, Concurrency & State, Error Handling & Edge Cases

### [I2] `os.environ["DOCKER_HOST"]` mutated globally during discovery probes; races with pool threads
- **File:** `src/ananta/ananta.py:204, 212, 238, 246`
- **Bug:** During Strategies 2 and 3, `DOCKER_HOST` is tentatively set in `os.environ`, tested with `docker.from_env()`, and then popped on failure. The class-level `_docker_discovery_lock` serialises discovery callers, but `ContainerExecutor.start()` (called during pool warm-up at `executor.py:74`) calls `docker.from_env()` independently without this lock. A concurrent container start sees the transient, potentially wrong `DOCKER_HOST` value.
- **Impact:** Race condition can cause pool containers to connect to the wrong Docker endpoint.
- **Suggested fix:** Use `docker.DockerClient(base_url=socket_url)` for probing instead of mutating `os.environ`. Only set `os.environ["DOCKER_HOST"]` once after confirming a working socket.
- **Confidence:** High
- **Found by:** Concurrency & State, Logic & Correctness, Contract & Integration

### [I3] Non-`RuntimeError`/`ImageNotFound` exceptions from `start()` bypass clean error handler
- **File:** `src/ananta/experimental/shared/app_factory.py:59-72`
- **Bug:** The lifespan handler catches `RuntimeError` and `ImageNotFound`, but `ContainerExecutor.start()` can raise `DockerException` from `docker.from_env()` during pool warm-up, and `PermissionError`/`OSError` can occur when the socket exists but is unreadable. These propagate as unhandled exceptions, producing raw Python tracebacks instead of clean `[ananta] Error:` messages.
- **Impact:** Users see unformatted stack traces instead of actionable error messages for common failure modes (e.g., user not in `docker` group).
- **Suggested fix:** Add `except Exception as e:` after the `ImageNotFound` block that prints `[ananta] Error: {e}` and raises `SystemExit(1)`.
- **Confidence:** High
- **Found by:** Error Handling & Edge Cases, Contract & Integration

### [I4] `stderr_filter` awk suppresses real error lines matching `Type: message` pattern
- **File:** `scripts/common.sh:140`
- **Bug:** The rule `skip && /^[A-Za-z_][A-Za-z0-9_.]*:/ { skip=0; next }` is intended to detect the exception type line ending a GC traceback block. When `skip=1`, a genuine error line like `RuntimeError: configuration invalid` matches this pattern — `skip` is reset to 0 but `next` discards the line without printing it.
- **Impact:** Real error messages from the Python process are silently swallowed when they occur after a GC `Exception ignored` block.
- **Suggested fix:** Change to `skip=0; print; next` or use `skip=0` without `next` so the line is printed.
- **Confidence:** High
- **Found by:** Error Handling & Edge Cases

### [I5] Web explorer allows local repo paths; code/document explorers restrict them
- **File:** `src/ananta/experimental/web/dependencies.py:48`
- **Bug:** The code and document explorers use `shared/dependencies.py:create_app_state()` which injects `RepoIngester(allow_local_paths=False)`. The web explorer constructs `Ananta(config=config, storage=storage)` directly, getting the default `RepoIngester` which allows local paths.
- **Impact:** Security inconsistency — the web explorer can be used to ingest local filesystem paths that the sibling explorers explicitly forbid.
- **Suggested fix:** Inject `RepoIngester(storage_path=..., allow_local_paths=False)` in `web/dependencies.py`, or migrate it to use the shared factory.
- **Confidence:** High
- **Found by:** Contract & Integration

## Suggestions

### [S1] Strategy 2 failure clears user's DOCKER_HOST instead of restoring original
- **File:** `src/ananta/ananta.py:212`
- **Bug:** When Strategy 2 fails, `os.environ.pop("DOCKER_HOST", None)` removes DOCKER_HOST entirely rather than restoring `original_docker_host`. Between line 212 and Strategy 4's restoration at line 249, DOCKER_HOST is absent even if the user had it explicitly set.
- **Suggested fix:** Restore `original_docker_host` on failure instead of popping: `os.environ["DOCKER_HOST"] = original_docker_host` if set, else pop.
- **Found by:** Logic & Correctness

### [S2] `docker context inspect` output may contain embedded newlines
- **File:** `src/ananta/ananta.py:198-204`
- **Bug:** `result.stdout.strip()` doesn't reject embedded newlines. If the Docker CLI emits multi-line output, the full blob (matching the scheme prefix) is written to DOCKER_HOST.
- **Suggested fix:** Add `if "\n" in socket_url: reject`.
- **Found by:** Error Handling & Edge Cases, Security

### [S3] Browser timer fires before server confirms bind; non-daemon thread delays exit
- **File:** `src/ananta/experimental/web/__main__.py:39` (identical in all 3 explorers)
- **Bug:** `threading.Timer(1.5, ...)` starts before `uvicorn.run()`. If startup fails, browser opens to a dead URL. The timer thread is non-daemon, so the process hangs for up to 1.5s after uvicorn exits.
- **Suggested fix:** Set `t.daemon = True` before `t.start()`.
- **Found by:** Logic & Correctness, Concurrency & State

### [S4] `check_repo_for_updates` docstring omits `check_failed` return status
- **File:** `src/ananta/ananta.py:441`
- **Bug:** Docstring says status is `'unchanged'` or `'updates_available'`, but `_handle_existing_project` can also return `'check_failed'`.
- **Suggested fix:** Update the docstring to list all three possible statuses.
- **Found by:** Contract & Integration

### [S5] ImageNotFound hint hardcodes `ananta-sandbox` image name
- **File:** `src/ananta/experimental/shared/app_factory.py:69`
- **Bug:** The build hint always says `docker build -t ananta-sandbox ...` regardless of `ANANTA_SANDBOX_IMAGE` env var.
- **Suggested fix:** Read the configured image name and interpolate it into the error message.
- **Found by:** Contract & Integration

## Plan Alignment

- **Implemented:** All four discovery strategies, diagnostic listing, lifespan error handling, executor cleanup, `--no-browser` → `--open` migration, shell script `ensure_sandbox_image`.
- **Not yet implemented:** Distinct "Found socket but not responding" error message format (design shows a separate message shape for Strategy 1 failure vs. total failure).
- **Deviations:** Strategy 2 fallthrough adds diagnostic entries visible in the "Tried:" list; the design specified "silent fallthrough — no warning emitted." The `[ananta] Error:` prefix is injected by `app_factory.py` rather than being part of the `RuntimeError` message itself.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment
- **Scope:** 27 changed files + callers/callees one level deep
- **Raw findings:** 22 (before verification)
- **Verified findings:** 10 (after verification)
- **Filtered out:** 12
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** docs/plans/2026-03-21-docker-socket-discovery-design.md
