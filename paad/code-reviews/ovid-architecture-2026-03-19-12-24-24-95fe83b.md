# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 12:24:24
**Branch:** ovid/architecture -> main
**Commit:** 95fe83bb707494266f674bd9f207ce3b5ed0294e
**Files changed:** 39 | **Lines changed:** +2435 / -641
**Diff size category:** Large

## Executive Summary

This branch implements 22 of 26 architecture report findings across 38 commits. The refactoring is thorough with strong test coverage. The review found **6 important issues** and **7 suggestions**. No critical bugs. The most impactful finding is a pre-existing git URL injection vulnerability (`ext::` protocol) that enables RCE via the `add_repo` API. Among bugs introduced by this branch, the most actionable are: an unhandled exception in the code explorer self-heal path (returns 500 instead of 422), a trace writer finalization flag ordering bug (prevents retry on write failure), and a staging cleanup failure that masks successful repo updates.

## Critical Issues

None found.

## Important Issues

### [I1] Git URL injection via `ext::` protocol allows RCE
- **File:** `src/shesha/repo/ingester.py:131`
- **Bug:** `cmd = ["git", "clone", "--depth=1", url, str(repo_path)]` passes the user-supplied `url` directly to `git clone` without restricting the protocol. Git's `ext::` transport handler allows arbitrary command execution (e.g., `ext::sh -c evil%`). No `GIT_ALLOW_PROTOCOL` environment variable is set in `_no_prompt_env()` or `clone()`.
- **Impact:** An attacker who can call the `add_repo` API endpoint with a crafted URL can achieve remote code execution on the server.
- **Suggested fix:** Set `GIT_ALLOW_PROTOCOL=https,ssh,git,file` in the subprocess environment for all `git` calls, or validate URLs against a protocol allowlist before invoking git.
- **Confidence:** High
- **Found by:** Security
- **Note:** Pre-existing issue, not introduced by this branch.

### [I2] Unhandled `RepoIngestError` in `apply_updates` self-heal path
- **File:** `src/shesha/experimental/code_explorer/api.py:170`
- **Bug:** The self-heal fallback calls `state.shesha.create_project_from_repo(source_url, name=project_id)` which can raise `RepoIngestError` (network error, disk full, clone failure). The exception is not caught, so FastAPI returns HTTP 500. By contrast, `add_repo` (line 98) correctly catches `RepoIngestError` and returns 422 with the error message.
- **Impact:** Users who click "Apply Updates" after a server restart get an unhelpful 500 error if the remote repo is temporarily unreachable.
- **Suggested fix:** Wrap in `try/except RepoIngestError` returning `HTTPException(422, detail=str(exc))`.
- **Confidence:** High
- **Found by:** Error Handling

### [I3] Race condition: check-then-pop on `pending_updates` dict
- **File:** `src/shesha/experimental/code_explorer/api.py:156-157`
- **Bug:** `if project_id in pending_updates: repo_result = pending_updates.pop(project_id)` is a classic TOCTOU race. FastAPI runs sync handlers in a thread pool. Two concurrent `apply_updates` calls for the same project can both pass the `in` check; the second `.pop()` raises `KeyError`, returning 500.
- **Impact:** Double-click on "Apply Updates" or concurrent API calls produce unhandled 500 errors.
- **Suggested fix:** Use `pending_updates.pop(project_id, None)` and fall through to the self-heal path if None.
- **Confidence:** High
- **Found by:** Concurrency & State

### [I4] Post-swap staging cleanup failure treated as ingestion failure
- **File:** `src/shesha/repo/ingester.py:480-496`
- **Bug:** After `swap_docs(staging_name, name)` succeeds at line 481, the staging cleanup at lines 484-485 can throw. The bare `except Exception` handler at line 487 re-raises, making the caller think ingestion failed. Lines 498-506 (saving SHA and source URL) are never reached, so the project's metadata becomes stale. The exception handler also tries to delete the staging project again (lines 489-490), which will likely fail the same way.
- **Impact:** A successful document update is reported as a failure. The next `check-updates` reports "updates available" again because SHA was never saved.
- **Suggested fix:** Isolate the staging cleanup in its own `try/except` so it cannot prevent SHA/URL saving:
  ```python
  if is_update:
      storage.swap_docs(staging_name, name)
      try:
          if storage.project_exists(staging_name):
              storage.delete_project(staging_name)
      except Exception:
          pass  # Swap succeeded; orphaned staging shell is harmless
  ```
- **Confidence:** Medium
- **Found by:** Logic & Correctness, Error Handling, Contract & Integration (3 specialists)

### [I5] `_finalized` flag set before write attempt, preventing retry on failure
- **File:** `src/shesha/rlm/trace_writer.py:155-157`
- **Bug:** `finalize()` sets `self._finalized = True` at line 157 before the file write at line 171. If the write fails under `suppress_errors=True`, the flag is permanently True. The safety-net call in `engine.py:1073` checks `inc_writer.finalized` and returns early, so the trace file is left without a summary line.
- **Impact:** A transient disk-full condition results in an incomplete trace file with no summary, even if disk space becomes available before the `finally` block runs.
- **Suggested fix:** Move `self._finalized = True` after the successful write (after line 172).
- **Confidence:** Medium
- **Found by:** Logic & Correctness

### [I6] Code-block FINAL_VAR failure gives no feedback to model
- **File:** `src/shesha/rlm/engine.py:547-549`
- **Bug:** When `result.final_var is not None` but `_resolve_final_var` returns `None`, the code `break`s out of the code-block loop with `final_answer=None`. The main query loop continues to the next iteration without telling the model why its FINAL_VAR failed. In contrast, the bare-text FINAL_VAR failure path (lines 857-873) sends explicit "Variable not found" guidance. This violates CLAUDE.md: "Match all user-facing behavior when adding alternate code paths."
- **Impact:** The model gets different error feedback depending on whether FINAL_VAR is inside or outside a code block. The code-block path is less likely to self-correct, potentially wasting iterations.
- **Suggested fix:** Add a `failed_final_var` field to `_CodeBlockResult`, set it when the break happens, and use it in the main loop to append the same retry hint.
- **Confidence:** Medium
- **Found by:** Logic & Correctness, Error Handling (2 specialists)

## Suggestions

- `src/shesha/experimental/document_explorer/api.py:215-223` — Batch upload rollback does not call `topic_mgr.remove_item_from_all(pid)` to undo topic associations for cleaned-up projects. Orphaned topic entries remain referencing non-existent projects. (Error Handling)
- `src/shesha/shesha.py:437-450` — When `current_sha` is None (remote unreachable) but `saved_sha` is not None, falls through to "updates_available" instead of flagging inconclusive result. Pre-existing, but this branch improved the `None==None` case. (Logic & Correctness)
- `src/shesha/llm/client.py:90` — `response.choices[0].message.content` can be `None` from LiteLLM (tool-call responses, content moderation). Pre-existing. (Error Handling)
- `src/shesha/experimental/code_explorer/api.py:61,147` — `pending_updates` dict grows unboundedly when `check-updates` is called without `apply-updates`. Mitigated by per-project keying. (Concurrency & State)
- `tests/unit/test_shesha_di.py:105,143,158` — DI tests access private attributes (`_rlm_engine`, `_parser_registry`, `_parsers`) when public properties exist. Violates CLAUDE.md private API rule. (Contract & Integration)
- `tests/unit/analysis/test_generator.py:53-54` — Tests assert on private `_get_project` / `_get_project_sha` attributes. (Contract & Integration)
- `src/shesha/analysis/shortcut.py:104` — `classify_query` catches all exceptions including `PermanentError` (auth failures), delaying the error signal through 3 sequential LLM calls before it surfaces. (Error Handling)

## Plan Alignment

- **Implemented:** F-1, F-2, F-4, F-5, F-6, F-7, F-8, F-9, F-11, F-13, F-14, F-15, F-16, F-17, F-20, F-21, F-22, F-23, F-24, F-25, F-26
- **Not yet implemented:** F-12 (sync-only LLM client) -- no status annotation
- **Won't fix (reasonable):** F-3 (no web auth), F-10 (broad exception swallowing), F-19 (naming mismatch)
- **Skipped (reasonable):** F-18 (non-idempotent upload)
- **Deviations:** F-1 status claims query() reduced to ~310 lines but actual count is ~414 lines. The decomposition is real (3 extracted methods) but the metric overstates the reduction. F-2 has a minor residual: `code_explorer/api.py:67` calls `storage.list_documents()` directly with a TODO comment.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment (6 specialists + 1 verifier)
- **Scope:** 39 changed files + adjacent callers/callees one level deep
- **Raw findings:** 25 (before verification)
- **Verified findings:** 13 (after verification)
- **Filtered out:** 12 (false positives, pre-existing design choices, framework-mitigated, below threshold)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** paad/architecture-reviews/2026-03-18-shesha-architecture-report.md
