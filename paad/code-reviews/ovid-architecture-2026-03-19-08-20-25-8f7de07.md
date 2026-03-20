# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 08:20:25
**Branch:** ovid/architecture -> main
**Commit:** 8f7de0735b10a0c8a45debd5a90cf366c3e4904b
**Files changed:** 37 | **Lines changed:** +1889 / -584
**Diff size category:** Large

## Executive Summary

This branch fixes 21 of 26 architecture report findings across 30 commits — a substantial refactoring effort with strong test coverage. The review found **4 important issues** and **7 suggestions**. The most critical finding is a behavioral regression where analysis context is silently dropped from the RLM fallback path after extracting the shortcut logic from the TUI. A staging project leak on every successful repo update is the second most impactful finding.

## Critical Issues

None found.

## Important Issues

### [I1] Analysis context dropped on RLM fallback path — behavioral regression
- **File:** `src/shesha/tui/app.py:387`, `src/shesha/analysis/shortcut.py:200`
- **Bug:** `query_with_shortcut` is called with `question=question_with_history or full_question`. Since `question_with_history` is always truthy, `full_question` (which prepends analysis context) is never used. When the shortcut declines and falls through to `project.query()`, the analysis context that was previously included in the question is lost. The `full_question` parameter to `_make_query_runner` is effectively dead code.
- **Impact:** Users with codebase analysis enabled get degraded RLM responses because the engine no longer sees the analysis context that previously guided its exploration. Silent quality regression — no crash, no error.
- **Suggested fix:** Pass the analysis context through to the RLM fallback path. Either have `query_with_shortcut` prepend analysis context to the question before calling `project.query()`, or pass `full_question` directly instead of `question_with_history or full_question`.
- **Confidence:** High
- **Found by:** Logic & Correctness, Contract & Integration, Plan Alignment

### [I2] Staging project leaked after successful `swap_docs`
- **File:** `src/shesha/repo/ingester.py:480-481`
- **Bug:** After a successful update ingestion, `storage.swap_docs(staging_name, name)` is called but the staging project (`_staging_{name}_{uuid}`) is never deleted. `FilesystemStorage.swap_docs()` only moves the `docs/` directory — it does NOT delete the source project directory. The empty staging project remains visible in `list_projects()`. In contrast, `default_swap_docs()` in `base.py` does delete the source.
- **Impact:** Every successful repo update leaks a `_staging_*` project directory that appears in project listings and wastes storage. Accumulates over time.
- **Suggested fix:** Add `storage.delete_project(staging_name)` after the successful `swap_docs` call on line 481 for the `is_update` path.
- **Confidence:** High
- **Found by:** Error Handling, Contract & Integration

### [I3] `final_value or ""` silently produces empty answer on failed variable lookup
- **File:** `src/shesha/rlm/engine.py:542`
- **Bug:** When `result.final_var` is set but `result.final_value` is `None` (sandbox variable not found), the code sets `final_answer = result.final_value or ""` and breaks out of the loop, returning an empty string to the user. The bare-text `FINAL_VAR` handler (lines 846-862) correctly retries when variable resolution fails, but this code-block path does not.
- **Impact:** Users see an empty answer with no indication that a variable resolution failed. Violates CLAUDE.md: "Never let a failed lookup silently produce an empty answer."
- **Suggested fix:** When `result.final_value is None` and `result.final_var is not None`, don't treat it as a final answer — continue the loop and prompt the model to retry, similar to the bare-text FINAL_VAR handler.
- **Confidence:** High
- **Found by:** Error Handling

### [I4] `self._pool` can be `None` in query `finally` block after concurrent `stop()`
- **File:** `src/shesha/rlm/engine.py:1073-1075`
- **Bug:** The `finally` block calls `self._pool.discard(executor)` and `self._pool.release(executor)` without guarding against `self._pool` being `None`. If `Shesha.stop()` is called concurrently (atexit handler, context manager exit), `set_pool(None)` clears `self._pool`, causing `AttributeError`. The `# type: ignore[union-attr]` comments suppress the mypy warning but don't prevent the runtime error.
- **Impact:** During application shutdown with in-flight queries, the executor is leaked (never stopped/returned to pool) and an `AttributeError` masks the query result.
- **Suggested fix:** Capture `self._pool` into a local variable at the start of `query()` and use the local in the `finally` block. Add a `pool is not None` guard.
- **Confidence:** High
- **Found by:** Error Handling, Concurrency & State

## Suggestions

### [S1] `swap_docs` protocol contract ambiguous about source cleanup
- **File:** `src/shesha/storage/base.py:83-90`
- The docstring says "Replace target project's docs" but doesn't specify whether the source is deleted. `default_swap_docs` deletes source; `FilesystemStorage.swap_docs` does not. Root cause of I2.
- **Found by:** Contract & Integration

### [S2] Pool published to engine before `pool.start()` completes
- **File:** `src/shesha/shesha.py:351-352`
- `set_pool()` is called before `pool.start()`. If `start()` fails (e.g., Docker image not found), the engine holds a reference to a broken pool. Swap the order: start first, then set on engine.
- **Found by:** Concurrency & State

### [S3] `pool.stop()` before `engine.set_pool(None)` enables stopped-pool access
- **File:** `src/shesha/shesha.py:359-361`
- `stop()` stops the pool before clearing the engine's reference. An in-flight query between these lines would attempt `acquire()` from a stopped pool, raising `RuntimeError`. Clear the reference first, then stop.
- **Found by:** Concurrency & State

### [S4] NEED_DEEPER sentinel can leak as user answer
- **File:** `src/shesha/analysis/shortcut.py:156-158`
- The `answer == _SENTINEL` exact match fails if the LLM appends trailing punctuation (e.g., "NEED_DEEPER."). The system prompt mitigates this but LLMs occasionally deviate. A `startswith` check would be safer.
- **Found by:** Error Handling

### [S5] Multi-file upload leaves orphaned projects on partial failure
- **File:** `src/shesha/experimental/document_explorer/api.py:155-225`
- If file 3 of 5 fails, the cleanup only handles the current file. Successfully created projects from files 1-2 are orphaned.
- **Found by:** Error Handling

### [S6] Upload cleanup comment too terse
- **File:** `src/shesha/experimental/document_explorer/api.py:214`
- `pass  # Best-effort cleanup` satisfies the letter of CLAUDE.md but not the spirit. Expand to explain why failure is acceptable (original exception takes priority and is re-raised).
- **Found by:** Logic & Correctness

### [S7] CORS `allow_origins=["*"]` + `allow_credentials=True`
- **File:** `src/shesha/experimental/shared/app_factory.py:66-72`
- Already addressed as "Won't fix" in the architecture report for local-only use. Noting here for completeness since the combination is a known CORS anti-pattern.
- **Found by:** Security

## Plan Alignment

- **Implemented:** F-1, F-2, F-4, F-5, F-6, F-7, F-8, F-9, F-11, F-13, F-14, F-15, F-16, F-17, F-20, F-21, F-22, F-23, F-24, F-25, F-26
- **Not yet implemented:** F-12 (sync-only LLM client) — no status annotation in report
- **Deviations:** F-11 fix introduces behavioral regression (I1 above) — analysis context dropped from RLM fallback path. F-1 status claims "~310 lines" but actual `query()` is ~400 lines (minor documentation inaccuracy).
- **Won't fix (reasonable):** F-3, F-10, F-19
- **Skipped (reasonable):** F-18

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment (6 specialists + 1 verifier)
- **Scope:** 37 changed files + adjacent callers/callees one level deep
- **Raw findings:** 28 (before verification)
- **Verified findings:** 11 (after verification)
- **Filtered out:** 17 (false positives, out of scope, or below confidence threshold)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** paad/architecture-reviews/2026-03-18-shesha-architecture-report.md
