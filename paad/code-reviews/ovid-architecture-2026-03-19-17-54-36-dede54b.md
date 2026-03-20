# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 17:54:36
**Branch:** ovid/architecture -> main
**Commit:** dede54b60db9bb053631bf68c7e3a64d337a500a
**Files changed:** 62 | **Lines changed:** +5375 / -850
**Diff size category:** Large

## Executive Summary

This branch implements fixes for 20 of 26 findings from the architecture report, with strong verification across all claimed fixes. The core DI refactoring, protocol abstractions, and ingestion extraction are well-executed. Six verified issues remain: an inconsistent empty-string handling pattern across FINAL_VAR resolution paths, an incorrect conversation role in the max-iterations fallback, a missing error handler in batch LLM subcalls, missing input validation on code explorer endpoints, the `git://` protocol enabling potential SSRF, and a latent interface contract violation in the shared websocket/routes layer.

## Critical Issues

None found.

## Important Issues

### [I1] Inconsistent empty-string handling across FINAL_VAR resolution paths
- **File:** `src/shesha/rlm/engine.py:576, 603, 915, 987`
- **Bug:** Four different check patterns for `_resolve_final_var` return values: `if resolved is None:` (line 576, accepts empty string), `if resolved is not None and resolved != ""` (line 603, rejects empty string), `if not bare_answer:` (line 915, rejects empty string), `if resolved:` (line 987, rejects empty string). The code-block initial path accepts `""` as a final answer while the post-loop retry and bare-text paths reject it.
- **Impact:** `FINAL_VAR(x)` where `x=""` produces different behavior depending on which code path resolves it. In the code-block path, empty string is accepted; in other paths, it triggers a retry. The comment at line 546 explicitly says `use is not None to catch falsy values like FINAL(0), FINAL(""), FINAL(False)`, but the variable-resolution paths don't follow this principle.
- **Suggested fix:** Decide on one policy. If empty-string values are valid final answers (matching the `is not None` approach for `FINAL("")`), use `if resolved is None:` consistently. If invalid, use `if not resolved:` consistently.
- **Confidence:** High
- **Found by:** Logic & Correctness, Error Handling & Edge Cases

### [I2] Max-iterations fallback uses `assistant` role instead of `user` role
- **File:** `src/shesha/rlm/engine.py:1119-1126`
- **Bug:** The fallback message appended at max iterations uses `"role": "assistant"`. The prior message appended in the loop body (line 1083) is also `"role": "assistant"`, creating two consecutive assistant messages before requesting a new LLM completion. Some LLM APIs enforce alternating roles and may reject or behave unexpectedly.
- **Impact:** Degraded response quality or API errors when hitting the max-iterations limit with strict LLM providers.
- **Suggested fix:** Change the fallback message role to `"user"`.
- **Confidence:** High
- **Found by:** Logic & Correctness

### [I3] `_execute_batch` only catches `SubcallContentError`, crashes query on other exceptions
- **File:** `src/shesha/sandbox/executor.py:310-314`
- **Bug:** `_call_one` in `_execute_batch` catches only `SubcallContentError`. If the LLM handler raises `PermanentError` (auth failure), `TransientError` (timeout), or any other exception, it propagates through `pool.map()` uncaught. The single llm_query path (lines 192-203) catches `Exception` broadly and sends an error back to the sandbox. The batch path lacks this safety net.
- **Impact:** A single LLM call failure in a batch crashes the entire query instead of gracefully degrading.
- **Suggested fix:** Broaden the `except` in `_call_one` to catch `Exception` and return an error string, matching the single-call path.
- **Confidence:** High
- **Found by:** Error Handling & Edge Cases

### [I4] Code explorer API endpoints lack `project_id` input validation
- **File:** `src/shesha/experimental/code_explorer/api.py:130-236`
- **Bug:** All `{project_id}` route handlers (`get_repo`, `delete_repo`, `check_updates`, `apply_updates`, `generate_analysis`, `get_analysis`) accept raw path parameters without validation. The document explorer consistently validates with `_SAFE_ID_RE = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"`. Defense-in-depth mandates validation at the API boundary.
- **Impact:** Inconsistent input validation across explorers. While `safe_path()` protects at the storage layer, unsanitized IDs flow through error messages, topic managers, and metadata operations.
- **Suggested fix:** Add a `_validate_project_id()` function (reuse the `_SAFE_ID_RE` pattern) and call it at the top of each `{project_id}` route handler.
- **Confidence:** High
- **Found by:** Security

### [I5] `git://` protocol in `_GIT_SAFE_PROTOCOLS` enables potential SSRF
- **File:** `src/shesha/repo/ingester.py:82`
- **Bug:** `_GIT_SAFE_PROTOCOLS = "https:ssh:git"` includes the unauthenticated, unencrypted `git://` protocol (port 9418). An attacker providing a `git://internal-host/repo` URL could probe or clone from internal git daemons accessible from the server's network. GitHub disabled `git://` in 2022.
- **Impact:** SSRF to internal services via git daemon. Relevant for web-facing deployments.
- **Suggested fix:** Remove `git` from `_GIT_SAFE_PROTOCOLS`, restricting to `https:ssh` only.
- **Confidence:** High
- **Found by:** Security

### [I6] `_handle_query` and shared routes call `topic_mgr.resolve()` not defined on `BaseTopicManager`
- **File:** `src/shesha/experimental/shared/websockets.py:193`, `src/shesha/experimental/shared/routes.py:119, 264`
- **Bug:** `BaseTopicManager` does not define a `resolve()` method. Only `ArxivTopicManager` has it. The shared module's `_handle_query` function and `resolve_topic_or_404` / `create_topic` routes call `resolve()`. Currently safe because code_explorer and document_explorer bypass these paths via custom callbacks, but the contract violation means any new explorer using `BaseTopicManager` with the default handler would crash with `AttributeError`.
- **Impact:** Latent `AttributeError` for any non-arxiv explorer using the default shared handler.
- **Suggested fix:** Add `resolve()` to `BaseTopicManager`, or move the dependent functions out of `shared/` into the arxiv-specific layer.
- **Confidence:** Medium
- **Found by:** Contract & Integration

## Suggestions

- `src/shesha/rlm/engine.py:639-642` — `_resolve_final_var` executes `print(var_name)` in sandbox. If variable is `None`, `print(None)` returns `"None"` string accepted as final answer instead of triggering retry. (Logic & Correctness)
- `src/shesha/shesha.py:375-383` — `_pool` not set to `None` in `stop()`, retaining a reference to the stopped pool that prevents GC. (Logic & Correctness)
- `src/shesha/sandbox/pool.py:100-107` — `discard()` permanently reduces pool capacity with no replenishment. Overflow containers still work but lose warm-pool benefit. (Logic & Correctness)
- `src/shesha/rlm/trace_writer.py:41` — `trace_path.unlink()` without `missing_ok=True` can raise `FileNotFoundError` under concurrent cleanup. (Error Handling)
- `src/shesha/sandbox/executor.py:335` — `sock.settimeout()` in `finally` block can raise `OSError` if socket closed by concurrent `stop()`, bypassing `execute()`'s error handlers. (Concurrency & State)
- `src/shesha/analysis/shortcut.py:161` — `startswith` sentinel check could discard valid answers that happen to start with `"NEED_DEEPER"` text. (Error Handling)
- `src/shesha/shesha.py:90-99` — `Shesha.__init__` doesn't forward `llm_client_factory` to `RLMEngine`. DI is incomplete at the facade level; requires injecting a pre-built engine. (Contract & Integration)

## Plan Alignment

**Implemented:** All 20 findings marked "Fixed" in the architecture report are verified present in the code. The DI pattern (F-7, F-16, F-17), protocol abstractions (F-8, F-14), ingestion extraction (F-5), logging addition (F-9), shortcut extraction (F-11), temporal coupling fix (F-15), and all other fixes are correctly implemented.

**Not yet implemented:** F-12 (synchronous-only LLM client) has no status in the report and remains unchanged. F-18 (non-idempotent upload) was deliberately skipped.

**Deviations:**
- F-4's claimed commit hash `909d354` doesn't exist in the repo; the actual fix is in commit `8e225e0`.
- F-4's status claims "isinstance validation" in `set_pool()` but the code uses only static type annotations, no runtime validation.
- F-1 claims `query()` reduced to ~310 lines; actual non-blank count is ~352 (additional logic added in subsequent commits).
- The `allow_credentials=True` CORS fix (commit `cfd052d`) is a meaningful security improvement not tracked in the architecture report.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment (6 specialists + 1 verifier)
- **Scope:** 62 changed files + adjacent callers/callees
- **Raw findings:** 33 (before verification)
- **Verified findings:** 13 (6 important + 7 suggestions)
- **Filtered out:** 20 (false positives, below threshold, duplicates, or design choices)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** paad/architecture-reviews/2026-03-18-shesha-architecture-report.md
