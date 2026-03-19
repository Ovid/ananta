# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 17:56:31
**Branch:** ovid/architecture -> main
**Commit:** f9f7d83630d0c591476339e1bcfed6435fbfe09a
**Files changed:** 58 | **Lines changed:** +4751 / -822
**Diff size category:** Large

## Executive Summary

This branch implements a comprehensive architecture improvement campaign driven by the PAAD architecture report. The changes are substantial (58 files, ~5500 lines) and well-structured — extracting protocols, moving logic to proper modules, adding DI, and fixing numerous bugs from prior reviews. No critical issues were found. Three important issues exist: a SHA comparison gap causing false update-available reports, a subdirectory scope loss when re-ingesting through `create_project_from_repo`, and unconstrained local path access in the repo ingester. The remaining 19 findings are suggestions for hardening edge cases.

## Critical Issues

None found.

## Important Issues

### [I1] False `updates_available` when saved SHA is missing
- **File:** `src/shesha/shesha.py:480`
- **Bug:** In `_handle_existing_project()`, the SHA comparison cascade has three guards: both-None → unchanged, current=None → check_failed, equal → unchanged. When `saved_sha` is None but `current_sha` is a valid SHA (e.g., SHA save failed during initial ingest, or project predates SHA tracking), none of the guards fire. The code falls through to returning `status='updates_available'` with an apply_updates closure, causing a full re-ingest every time.
- **Impact:** Projects with a missing saved SHA permanently and falsely report updates available, triggering unnecessary re-ingestion on every check. Wastes network, storage, and compute.
- **Suggested fix:** Add a guard after line 478: `if saved_sha is None: return RepoProjectResult(project=project, status='unchanged', files_ingested=len(self._storage.list_documents(name)))`.
- **Confidence:** High
- **Found by:** Logic & Correctness, Error Handling

### [I2] Subdirectory scope lost on `create_project_from_repo` update
- **File:** `src/shesha/shesha.py:412`
- **Bug:** `create_project_from_repo` passes the caller-supplied `path` directly to `_handle_existing_project`. When `path=None` (the common case for re-checking an existing project), but the project was originally created with a subdirectory scope (e.g., `path='src/'`), the apply_updates closure captures `path=None` and re-ingests the full repository. `check_repo_for_updates` at line 348 correctly loads `get_saved_path()` first, but `create_project_from_repo` does not.
- **Impact:** Updates to subdirectory-scoped projects silently expand to the full repository. Document count changes dramatically and queries return results from irrelevant files.
- **Suggested fix:** In `_handle_existing_project`, when `path` is None, fall back to `self._repo_ingester.get_saved_path(name)` to preserve the original scope.
- **Confidence:** High
- **Found by:** Logic & Correctness

### [I3] Unconstrained local path access in repo ingester
- **File:** `src/shesha/repo/ingester.py:462`
- **Bug:** Local-path ingestion reads from `Path(url).expanduser()` without constraining to a safe base directory. `is_local_path()` permits any path starting with `/`, `~`, `./`, `../`. Via the unauthenticated API, any caller can supply an arbitrary local filesystem path to ingest files from any git repository accessible to the server process.
- **Impact:** Unauthorized local filesystem read. Mitigated by default 127.0.0.1 bind address, but exploitable if bind changes or via SSRF.
- **Suggested fix:** Add a configurable `allow_local_paths` flag (default False) to `RepoIngester` and reject local-path URLs when False. If local paths are needed, validate against a configurable allowlist of permitted base directories.
- **Confidence:** Medium
- **Found by:** Security

## Suggestions

### [S1] Missing FINAL_ANSWER trace step on post-loop FINAL_VAR retry
- **File:** `src/shesha/rlm/engine.py:601`
- Post-loop retry in `_execute_code_blocks()` sets `final_answer` without emitting a trace step, calling `on_step`, or calling `on_progress`. Trace is missing a FINAL_ANSWER step for this code path.
- **Found by:** Logic & Correctness

### [S2] CORS allow_credentials=True with wildcard origin
- **File:** `src/shesha/experimental/shared/app_factory.py:68`
- `allow_origins=['*']` with `allow_credentials=True` causes Starlette to reflect the request Origin, enabling any webpage to make credentialed cross-origin requests. Remove `allow_credentials=True` since no cookies/auth headers are used.
- **Found by:** Security

### [S3] `start()` assigns pool before `pool.start()` succeeds
- **File:** `src/shesha/shesha.py:362`
- `self._pool` is set before `pool.start()`. If `pool.start()` raises, the early-return guard prevents retry. Move assignment after `pool.start()` succeeds.
- **Found by:** Logic & Correctness, Contract & Integration

### [S4] Static tag fallback in `try_answer_from_analysis` when boundary=None
- **File:** `src/shesha/analysis/shortcut.py:149`
- Falls back to predictable static XML tags when `boundary=None`. Current primary caller always provides a boundary. Make boundary internally mandatory: `boundary = boundary or generate_boundary()`.
- **Found by:** Security

### [S5] `get_analysis_status` returns 'current' when SHA unknown
- **File:** `src/shesha/shesha.py:263`
- Returns `'current'` when `get_saved_sha()` is None but analysis exists. Analysis may be arbitrarily stale. Should return `'stale'` as the conservative choice.
- **Found by:** Logic & Correctness

### [S6] Outer except in `ingest()` can mask original error
- **File:** `src/shesha/repo/ingester.py:507`
- For `is_update=True`, the outer `except` calls `storage.delete_project(staging_name)` without a nested try/except. If cleanup also raises, the original error is replaced. Wrap in try/except: pass.
- **Found by:** Error Handling

### [S7] Metadata read methods lack `_meta_lock`
- **File:** `src/shesha/repo/ingester.py:223`
- `get_source_url()`, `get_saved_sha()`, `get_saved_path()` read `_repo_meta.json` without holding `_meta_lock`. Non-atomic `write_text()` can produce partial JSON visible to concurrent readers.
- **Found by:** Concurrency & State

### [S8] `check_failed` not handled in apply-updates self-heal
- **File:** `src/shesha/experimental/code_explorer/api.py:205`
- The self-heal path returns HTTP 409 for `check_failed` (network error) instead of 503. Add a `check_failed` branch before the 409 guard.
- **Found by:** Contract & Integration

### [S9] No aggregate upload size limit
- **File:** `src/shesha/experimental/document_explorer/api.py:179`
- Per-file 50 MB cap exists but no aggregate limit across all files in a multi-file upload request. Add a running total_bytes counter.
- **Found by:** Security

### [S10] `_resolve_final_var` returns None for empty string values
- **File:** `src/shesha/rlm/engine.py:627`
- `return value if value else None` treats `""` as missing. A variable legitimately holding an empty string is never returned as a valid answer. Three specialists agreed. Change to `return value` (return empty string as valid when status is 'ok').
- **Found by:** Logic & Correctness, Error Handling, Contract & Integration

### [S11] FINAL_VAR on None-valued variable returns string "None"
- **File:** `src/shesha/sandbox/runner.py:215`
- `str(NAMESPACE[rv.var_name])` when the variable holds Python None → string `"None"` returned as the answer. Check for None value before string conversion.
- **Found by:** Error Handling

### [S12] Error sanitization regex misses short paths
- **File:** `src/shesha/experimental/code_explorer/api.py:43`
- Regex requires 2+ directory separators. Short paths like `/tmp/repo` leak in 422 responses. Broaden the pattern or return fixed-format error messages.
- **Found by:** Security

### [S13] `pool.stop()` can crash in-flight queries
- **File:** `src/shesha/sandbox/pool.py:54`
- `stop()` calls `executor.stop()` on in-use executors. Concurrent `_read_message()` raises RuntimeError not caught by `execute()`'s handlers. Add RuntimeError to execute()'s exception handling.
- **Found by:** Error Handling

### [S14] `var_lookup_failed` overwritten by bare-text path
- **File:** `src/shesha/rlm/engine.py:978`
- When both `cb_result.failed_final_var` and a bare-text FINAL_VAR fail with different names, the code-block failure is silently lost. Check `if var_lookup_failed is None` before overwriting.
- **Found by:** Logic & Correctness

### [S15] `swap_docs` protocol docstring inconsistent with `default_swap_docs`
- **File:** `src/shesha/storage/base.py:83`
- Protocol says source "may or may not be deleted"; `default_swap_docs` always deletes source; `FilesystemStorage` does not. Align docstring and implementations.
- **Found by:** Logic & Correctness, Contract & Integration

### [S16] `llm_client_factory` not forwarded to RLM fallback
- **File:** `src/shesha/analysis/shortcut.py:215`
- `query_with_shortcut()` accepts `llm_client_factory` for shortcut calls but the RLM fallback uses the engine's factory. Document the split or accept as a known test-isolation limitation.
- **Found by:** Contract & Integration

### [S17] Content-Disposition filename injection
- **File:** `src/shesha/experimental/document_explorer/api.py:294`
- Filename from stored metadata passed to FileResponse without sanitizing quotes, semicolons, or CRLFs. Strip unsafe characters before passing to FileResponse.
- **Found by:** Security

### [S18] `start()` not thread-safe
- **File:** `src/shesha/shesha.py:357`
- Reads `self._pool` and `self._stopped` without a lock. Concurrent calls can both pass the guard and create duplicate pools. Add a lock or document single-caller requirement.
- **Found by:** Concurrency & State

### [S19] `pool.start()` _started check without lock
- **File:** `src/shesha/sandbox/pool.py:35`
- `_started` read without `_lock`. Code comment acknowledges and justifies with "single-threaded call site". Consider locking or strengthening the contract.
- **Found by:** Concurrency & State

## Plan Alignment

The architecture report (`paad/architecture-reviews/2026-03-18-shesha-architecture-report.md`) identified 26 flaws. This branch addresses most of them:

- **Implemented:** F-1 (god method decomposition), F-2 (private API access), F-4 (pool mutation), F-5/F-8 (repo ingestion extraction), F-7 (LLM client factory), F-9 (logging), F-11 (TUI business logic), F-13 (upload atomicity), F-14 (executor protocol), F-15 (trace writer coupling), F-16 (shortcut factory), F-17 (generator coupling), F-20 (self-heal), F-21 (exception hierarchy), F-22 (magic numbers), F-23 (hidden side effect), F-24 (config env map), F-25 (dead code), F-26 (dead trace writer)
- **Not yet implemented:** F-1 further decomposition (query still ~310 lines), F-6 (dual WebSocket construction — marked fixed), F-12 (sync-only LLM), F-18 (non-idempotent upload)
- **Deviations:** None observed. Fixes align with report recommendations.

## Review Metadata

- **Agents dispatched:** Logic & Correctness (A), Logic & Correctness (B), Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security (6 specialists + 1 verifier)
- **Scope:** 58 changed files + adjacent callers/callees one level deep
- **Raw findings:** 26 (before verification)
- **Verified findings:** 22 (after verification)
- **Filtered out:** 4 (false positives: F8 Pass-2 FINAL trailing paren is acceptable degradation for malformed output; F13 pool acquire race window too narrow; F18 suppress_errors=True hardcoded at only call site makes double-finalize unreachable; F23 case-insensitive NEED_DEEPER — wasted LLM call but not a wrong answer)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** paad/architecture-reviews/2026-03-18-shesha-architecture-report.md
