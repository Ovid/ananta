# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 07:55:00
**Branch:** ovid/architecture -> main
**Commit:** 51d1e2e1439370a45b2cfaf5fa906a0ed400dac8
**Files changed:** 35 | **Lines changed:** +1752 / -553
**Diff size category:** Large

## Executive Summary

The branch contains 22 architecture fixes (F-1 through F-26) addressing findings from the agentic architecture report. One critical bug was introduced: the atexit cleanup handler became unreachable dead code when the `storage` property was added, meaning Docker containers leak on process exit. Additionally, `save_sha()` can silently overwrite metadata, and a `None == None` comparison masks failed SHA resolution as "unchanged". Overall the architecture improvements are sound, but the dead code bug needs immediate attention.

## Critical Issues

### [C1] Unreachable atexit cleanup handler -- containers leak on exit
- **File:** `src/shesha/shesha.py:111-119`
- **Bug:** The `storage` property returns `self._storage` at line 109. Lines 111-119 (the `atexit.register(_cleanup)` block) follow the `return` statement and are unreachable dead code. The cleanup handler that calls `Shesha.stop()` on process exit is never registered.
- **Impact:** Docker containers from the pool leak on process exit if the user doesn't explicitly call `stop()` or use the context manager. This is the only atexit registration in the class.
- **Suggested fix:** Move the atexit block (lines 111-119) into `__init__` (after line 104) or into `start()` where the pool is created.
- **Confidence:** High
- **Found by:** Logic & Correctness, Contract & Integration, Concurrency & State, Security (all 4 specialists)

## Important Issues

### [I1] `save_sha()` overwrites `_repo_meta.json` without preserving existing keys
- **File:** `src/shesha/repo/ingester.py:183-188`
- **Bug:** `save_sha()` writes `{"head_sha": sha}` unconditionally, discarding any existing data. In contrast, `save_source_url()` (line 196) correctly does read-modify-write. If `save_sha()` is ever called after `save_source_url()`, the source URL is silently lost. Current call order (sha first, url second) happens to work, but the asymmetry is a maintenance trap.
- **Impact:** Future callers reversing the call order will silently lose metadata.
- **Suggested fix:** Make `save_sha()` load-and-merge like `save_source_url()`.
- **Confidence:** High
- **Found by:** Logic & Correctness

### [I2] `None == None` treats failed SHA resolution as "unchanged"
- **File:** `src/shesha/shesha.py:436-449`
- **Bug:** Both `get_saved_sha()` and `get_remote_sha()`/`get_sha_from_path()` can return `None`. When both fail (e.g., network timeout + missing metadata), `saved_sha == current_sha` evaluates to `True` (`None == None`), and the method returns `status="unchanged"` even though no check was performed.
- **Impact:** A transient network failure silently reports "no updates available" instead of flagging the inconclusive result.
- **Suggested fix:** When `current_sha is None`, either raise a warning or return a distinct status.
- **Confidence:** Medium
- **Found by:** Logic & Correctness

### [I3] `set_pool()` isinstance check contradicts SandboxExecutor protocol
- **File:** `src/shesha/rlm/engine.py:223-224`
- **Bug:** `set_pool()` enforces `isinstance(pool, ContainerPool)`, but the `SandboxExecutor` protocol (introduced in F-14) exists specifically to enable executor substitution. The pool's internal collections use `SandboxExecutor` types, but the engine rejects any pool that isn't the concrete `ContainerPool`.
- **Impact:** Blocks the stated design goal of executor substitution for testing or non-Docker backends.
- **Suggested fix:** Remove the isinstance check (rely on static typing), or define a `SandboxPool` protocol.
- **Confidence:** Medium
- **Found by:** Logic & Correctness, Contract & Integration

### [I4] `sandbox/base.py` imports from concrete `executor.py`
- **File:** `src/shesha/sandbox/base.py:5`
- **Bug:** The protocol module imports `ExecutionResult` and `LLMQueryHandler` from the concrete `executor.py`. This creates a dependency from the abstract interface to its concrete implementation, defeating the dependency inversion that protocols are meant to provide. Importing `SandboxExecutor` transitively pulls in `docker` and all of `executor.py`.
- **Impact:** Alternative executor implementations still require the Docker SDK installed; clean layering is broken.
- **Suggested fix:** Move `ExecutionResult` and `LLMQueryHandler` into `base.py` (or a shared types module) and have `executor.py` import from there.
- **Confidence:** High
- **Found by:** Contract & Integration

## Suggestions

- `engine.py:540` — `result.final_value or ""` should use `if result.final_value is not None` for consistency with the `final_answer` path at line 517 (Logic & Correctness, Error Handling)
- `shesha.py:354-360` — `stop()` should call `self._rlm_engine.set_pool(None)` for defensive cleanup (Contract & Integration)
- `pool.py:31-44` — `start()` should acquire `self._lock` for the `_started` check to prevent theoretical double-init race (Concurrency & State)
- `shortcut.py:112,157` — Exact string match on LLM output could use `.upper()` or `.startswith()` for marginally more robust sentinel detection (Error Handling)
- `shortcut.py:17` + `engine.py:45` — Duplicated `LLMClientFactory` type alias should be consolidated into a shared location (Contract & Integration)

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security (5 specialists + 1 verifier)
- **Scope:** 35 changed files + adjacent callers/callees
- **Raw findings:** 28 (before verification)
- **Verified findings:** 10 (after verification)
- **Filtered out:** 18 (false positives, below threshold, or impractical race conditions)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** none (plan doc staleness noted but not actionable)
