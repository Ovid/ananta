# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 16:11:30
**Branch:** ovid/architecture -> main
**Commit:** ebef6626cd7a8d201a278a24c254a2fcf826f4db
**Files changed:** 46 | **Lines changed:** +3521 / -727
**Diff size category:** Large

## Executive Summary

This branch implements 22 of 26 findings from an architecture report: dependency injection, protocol abstractions, extracted orchestration logic, and numerous bug fixes found through iterative code reviews. The architecture improvements are well-executed with comprehensive tests. However, the review found 7 important issues including a security bypass via `file://` protocol, data loss when updating subdirectory-scoped projects, and a shutdown race in the container pool. No critical (crash/data-corruption-at-scale) issues found.

## Critical Issues

None found.

## Important Issues

### [I1] `path` subdirectory filter lost on updates — silent data expansion
- **File:** `src/shesha/shesha.py:348,444-476` + `src/shesha/experimental/code_explorer/api.py:144`
- **Bug:** When a project is created with `create_project_from_repo(url, path="src/")`, the `path` parameter scopes ingestion to a subdirectory but is never persisted in `_repo_meta.json`. When `check_updates` or `check_repo_for_updates` calls `create_project_from_repo(source_url, name=project_id)` without `path`, it defaults to `None`. Updates silently ingest the entire repository instead of the scoped subdirectory.
- **Impact:** Projects scoped to a subdirectory expand to the full repo on update. Document count changes dramatically and queries return irrelevant results.
- **Suggested fix:** Persist `path` in `_repo_meta.json` alongside `source_url` and `head_sha`. Load it in `_handle_existing_project` when the caller passes `path=None`.
- **Confidence:** High
- **Found by:** Logic & Correctness, Error Handling, Contract & Integration

### [I2] `file://` protocol in `GIT_ALLOW_PROTOCOL` enables local filesystem reads
- **File:** `src/shesha/repo/ingester.py:67`
- **Bug:** `_GIT_SAFE_PROTOCOLS = "https:ssh:git:file"` includes `file`. The `is_local_path()` check (lines 77-84) only matches `/`, `~`, `./`, `../` prefixes — NOT `file://`. A URL like `file:///etc/sensitive-repo` passes `is_local_path()` (returns False), bypasses the local-path branch, and git clones from the local filesystem. Combined with the unauthenticated API, this enables local filesystem reads through the repo ingestion endpoint.
- **Impact:** Any client that can reach the code explorer API can clone arbitrary local git repositories.
- **Suggested fix:** Remove `file` from `_GIT_SAFE_PROTOCOLS`. If local path support is needed, it should go through the `is_local_path()` codepath which can apply authorization checks.
- **Confidence:** High
- **Found by:** Security

### [I3] Both SHAs `None` triggers permanent false "updates available"
- **File:** `src/shesha/shesha.py:460-483`
- **Bug:** When `saved_sha is None AND current_sha is None` (e.g., project without SHA tracking, or SHA resolution failed), the guard `saved_sha is not None and saved_sha == current_sha` evaluates to False. Falls through to return `"updates_available"`. The special-case warning at line 460 only fires when `current_sha is None and saved_sha is not None`. Projects without SHA tracking permanently report false updates.
- **Impact:** Unnecessary re-ingestion on every `apply_updates` call. Users see perpetual "updates available" for projects where SHA tracking isn't available.
- **Suggested fix:** When both `saved_sha is None` and `current_sha is None`, return `"unchanged"` rather than `"updates_available"`.
- **Confidence:** High
- **Found by:** Logic & Correctness, Error Handling

### [I4] `ingest()` bypasses `safe_path` for remote repo path construction
- **File:** `src/shesha/repo/ingester.py:452`
- **Bug:** `ingest()` computes the remote repo path as `self.repos_dir / name` (direct path join), while `clone()` uses `self._repo_path(name)` which calls `safe_path()` for path traversal protection. If `name` contains characters that `safe_path` normalizes, the clone target and ingest source path diverge.
- **Impact:** Currently masked by `_sanitize_project_id()` in the caller, but inconsistent security boundaries. A future caller passing an unsanitized name would have a path mismatch or traversal issue.
- **Suggested fix:** Use `self._repo_path(name)` instead of `self.repos_dir / name` on line 452.
- **Confidence:** High
- **Found by:** Contract & Integration

### [I5] `pool.stop()` kills in-use executors; query recovery raises uncaught RuntimeError
- **File:** `src/shesha/sandbox/pool.py:48-58` + `src/shesha/rlm/engine.py:1009-1013`
- **Bug:** `pool.stop()` acquires its lock and stops all executors including those in `_in_use`, then sets `_started = False`. An in-flight query that captured the pool locally at engine.py:811 sees its executor die, attempts `pool.acquire()` for recovery, and gets `RuntimeError("Cannot acquire from a stopped pool")`. This error is uncaught and propagates to the caller.
- **Impact:** During shutdown (`atexit`, context manager exit) with an in-flight query, the query fails with an unexpected RuntimeError instead of a graceful abort.
- **Suggested fix:** In the engine's recovery path (lines 1009-1013), catch `RuntimeError` from `pool.acquire()` and fall through to the "no pool" abort path. Alternatively, have `pool.stop()` skip executors in `_in_use` and let the query `finally` block handle them.
- **Confidence:** Medium
- **Found by:** Concurrency & State

### [I6] No upload file size limit — denial of service
- **File:** `src/shesha/experimental/document_explorer/api.py:169`
- **Bug:** `content = await file.read()` reads the entire upload into memory with no size limit. No `MaxSizeMiddleware` or manual size check. An arbitrarily large upload can exhaust server memory.
- **Impact:** Memory exhaustion / OOM on the server from a single large upload.
- **Suggested fix:** Add a size check after `await file.read()` (e.g., 50 MB limit), or use Starlette's `MaxSizeMiddleware`.
- **Confidence:** High
- **Found by:** Security

### [I7] `0.0.0.0` binding + wildcard CORS + no authentication (pre-existing)
- **File:** `src/shesha/experimental/shared/app_factory.py:66-72` + `*/__main__.py`
- **Bug:** All three experimental web servers bind to `0.0.0.0` with `allow_origins=["*"]` and no authentication. Any device on the same network can access the full API. Combined with I2 and I6, this enables remote exploitation.
- **Impact:** Full unauthenticated access to all API operations from the LAN.
- **Suggested fix:** Bind to `127.0.0.1` by default. Add `--bind` flag for users who need network access.
- **Confidence:** High
- **Found by:** Security
- **Note:** Pre-existing issue, not introduced by this branch. Already noted as "Won't fix" in the architecture report (F-3). Included here because I2 (new on this branch) increases the blast radius.

## Suggestions

### [S1] `find_final_answer` Pass 2 returns empty answer for bare `FINAL(`
- **File:** `src/shesha/rlm/engine.py:156-159`
- **Bug:** If the LLM writes just `FINAL(` with no content, Pass 2 captures an empty string. Returns `("final", "")` instead of `None`. Engine returns empty answer instead of retrying.
- **Suggested fix:** After Pass 2, return `None` if `content` is empty after `.strip()`.
- **Found by:** Logic & Correctness, Error Handling

### [S2] `find_final_answer` Pass 2 includes trailing `)` when FINAL(x) is followed by text
- **File:** `src/shesha/rlm/engine.py:148-159`
- **Bug:** For `"FINAL(The answer)\nSome commentary"`, Pass 1 fails (`)` not at end-of-string). Pass 2 captures `"The answer)\nSome commentary"` including the stray `)`.
- **Suggested fix:** Add a middle pass: `r"^\s*FINAL\((.*)\)\s*$"` with `re.MULTILINE` (no DOTALL) before the unclosed-paren Pass 2.
- **Found by:** Logic & Correctness, Error Handling

### [S3] Safety-net trace finalization overwrites successful answer with "[interrupted]"
- **File:** `src/shesha/rlm/engine.py:1095` + `src/shesha/rlm/trace_writer.py:174`
- **Bug:** If `finalize()` fails silently (suppress_errors), `_finalized` stays False. The `finally` block retries with `"[interrupted]"` as the answer. Extremely narrow window (transient I/O error that recovers).
- **Found by:** Logic & Correctness, Contract & Integration

### [S4] `swap_docs` protocol contract ambiguous about source project cleanup
- **File:** `src/shesha/storage/base.py:83-90`
- **Bug:** `default_swap_docs` deletes the source; `FilesystemStorage.swap_docs` does not. The caller at ingester.py:488-492 compensates, but the protocol docstring doesn't specify expected behavior.
- **Found by:** Error Handling, Contract & Integration

### [S5] `pending_updates` dict: concurrent mutation + unbounded growth
- **File:** `src/shesha/experimental/code_explorer/api.py:61,149-159`
- **Bug:** Plain dict mutated by sync FastAPI handlers running in thread pool. Also grows unboundedly if `check-updates` is called without `apply-updates` for many distinct projects.
- **Found by:** Concurrency & State, Security

### [S6] `query_with_shortcut` not receiving `llm_client_factory` from TUI
- **File:** `src/shesha/tui/app.py:379-386`
- **Bug:** TUI calls `query_with_shortcut()` without `llm_client_factory`. Shortcut always uses `LLMClient` directly, bypassing any factory injected into the engine.
- **Found by:** Contract & Integration

### [S7] Classifier exact match vs `startswith` inconsistency for NEED_DEEPER
- **File:** `src/shesha/analysis/shortcut.py:115` vs `shortcut.py:162`
- **Bug:** `classify_query` uses `label == _SENTINEL` (exact match). `try_answer_from_analysis` uses `answer.startswith(_SENTINEL)`. LLM response `"NEED_DEEPER."` is misclassified by the classifier.
- **Found by:** Error Handling

### [S8] Failed FINAL_VAR `break`s out of code block loop, skipping later blocks
- **File:** `src/shesha/rlm/engine.py:563-566`
- **Bug:** When FINAL_VAR fails to resolve, `break` exits the code block loop. Later code blocks in the same response that might define the variable are never executed. The outer loop does retry via `failed_final_var` guidance.
- **Found by:** Error Handling

### [S9] `_on_progress` writes shared state from worker thread without synchronization
- **File:** `src/shesha/tui/app.py:419-444`
- **Bug:** Worker thread writes `_last_iteration`, `_last_step_name`, etc. Main thread reads them in `_tick_timer`. Atomic under CPython GIL, but cosmetically inconsistent progress display is possible.
- **Found by:** Concurrency & State

### [S10] `_repo_meta.json` read-modify-write not atomic
- **File:** `src/shesha/repo/ingester.py:201-219`
- **Bug:** `save_sha()` and `save_source_url()` do read-modify-write without locking. Concurrent calls for the same project could lose data.
- **Found by:** Concurrency & State

### [S11] Internal path leakage in API error responses
- **File:** `src/shesha/experimental/code_explorer/api.py:99,146,177,185`
- **Bug:** `RepoIngestError` propagated as HTTP 422 detail may contain git stderr with internal filesystem paths.
- **Found by:** Security

### [S12] `_resolve_final_var` returns "" for variables with empty value
- **File:** `src/shesha/rlm/engine.py:602-605`
- **Bug:** `result.stdout.strip()` returns `""` for empty variables. Caller checks `is None` but empty string passes, producing an empty answer.
- **Found by:** Error Handling

### [S13] No file type validation on upload — arbitrary files written to disk
- **File:** `src/shesha/experimental/document_explorer/api.py:171-173`
- **Bug:** File bytes written to disk before `extract_text()` validation. Cleanup handles failures, but file exists on disk briefly.
- **Found by:** Security

## Plan Alignment

- **Implemented:** 22 of 26 architecture report findings (F-1 through F-26), plus ~15 additional bug fixes discovered through iterative code reviews
- **Not yet implemented:** F-12 (async LLM client) — no status annotation, deferred as Medium priority
- **Deviations:** F-1 status overstates line reduction (~400 actual vs ~310 claimed); F-4 removed isinstance check entirely (better than planned). 3 findings "Won't fix" with documented justifications (F-3, F-10, F-19). 1 finding explicitly deferred (F-18).

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment
- **Scope:** 46 changed files + adjacent callers/callees one level deep
- **Raw findings:** 31 (before verification)
- **Verified findings:** 20 (after verification) — 7 Important, 13 Suggestions
- **Filtered out:** 11 (4 dropped below confidence threshold, 7 merged as duplicates)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** paad/architecture-reviews/2026-03-18-shesha-architecture-report.md
