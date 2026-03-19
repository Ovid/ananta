# Agentic Code Review: ovid/architecture

**Date:** 2026-03-19 13:47:14
**Branch:** ovid/architecture -> main
**Commit:** b1ec46ea86ff88012ab5c79d2bb1f0e39c772388
**Files changed:** 40 | **Lines changed:** +2824 / -645
**Diff size category:** Large

## Executive Summary

This branch implements 22 of 26 architecture report findings across 40 commits — a substantial and well-tested refactoring effort. The review found **no critical bugs**. There are 8 important issues (1 security, 3 logic/error-handling, 4 CLAUDE.md private-API violations in tests) and 5 suggestions. The most impactful finding is a cluster of private attribute access in the test suite that directly violates the project's own API boundary rules, rooted in a `set_pool()` isinstance check that blocks mock injection. The most user-facing bug is that network failures during SHA resolution are silently misreported as "updates available."

## Critical Issues

None found.

## Important Issues

### [I1] Network timeout misreported as "updates available"
- **File:** `src/shesha/shesha.py:445`
- **Bug:** When `get_remote_sha()` returns `None` (network timeout) but `saved_sha` is a valid SHA, the condition `saved_sha is not None and saved_sha == current_sha` is `False`, causing the method to fall through and return `status="updates_available"`. A network failure is silently reported as available updates.
- **Impact:** Users see "Updates available" and click "Apply Updates", triggering a `pull()` that will likely also fail. Violates CLAUDE.md: "Lookups that can fail need fallbacks."
- **Suggested fix:** When `current_sha is None`, return a status indicating the check was inconclusive rather than claiming updates exist.
- **Confidence:** High
- **Found by:** Logic & Correctness, Error Handling

### [I2] `path` subdirectory filter lost on updates — never persisted
- **File:** `src/shesha/shesha.py:333,455` + `src/shesha/experimental/code_explorer/api.py:143,176`
- **Bug:** `check_repo_for_updates` calls `_handle_existing_project(url, project_id, token, None)` with `path=None`. If the project was originally created with a `path` subdirectory filter (e.g., `create_project_from_repo("https://...", path="src/")`), that filter is lost. The `path` is never persisted in `_repo_meta.json`, so updates ingest the entire repo instead of the scoped subdirectory.
- **Impact:** Projects created from a subdirectory silently expand to the full repo on update. Document count changes dramatically and queries may return results from irrelevant files.
- **Suggested fix:** Persist `path` in `_repo_meta.json` alongside `source_url` and `head_sha`. Load it in `check_repo_for_updates` and pass through to `_handle_existing_project`.
- **Confidence:** High
- **Found by:** Logic & Correctness

### [I3] `response.choices[0].message.content` can be `None`
- **File:** `src/shesha/llm/client.py:90`
- **Bug:** LiteLLM's `Message.content` is `Optional[str]`. When the API returns `content=None` (tool-call responses, content moderation refusals), it propagates to `LLMResponse.content: str` and crashes on downstream `.strip()` calls (e.g., `shortcut.py:111`, `shortcut.py:156`).
- **Impact:** Certain model configurations or API edge cases would crash with `AttributeError: 'NoneType' object has no attribute 'strip'` instead of a meaningful error.
- **Suggested fix:** Guard: `content = raw_content if raw_content is not None else ""`, or raise a descriptive error.
- **Confidence:** Medium
- **Found by:** Error Handling
- **Note:** Pre-existing, but this branch adds new `.strip()`/`.startswith()` call sites.

### [I4] `pool.stop()` kills in-use executors mid-query
- **File:** `src/shesha/sandbox/pool.py:54-55`
- **Bug:** `pool.stop()` iterates `self._in_use` and calls `executor.stop()` on each, including executors actively used by in-flight queries. When `Shesha.stop()` runs (e.g., atexit handler), it kills the container underneath a running query. The query's executor dies mid-execution and sees `is_alive == False` but the recovery path tries to acquire from a stopped pool.
- **Impact:** Concurrent `stop()` during an active query (atexit, context manager exit) causes a graceless shutdown. The executor's container is killed mid-iteration rather than completing or cleanly aborting.
- **Suggested fix:** Only stop `_available` executors in `stop()`. Let in-use executors be stopped when returned via `release()`/`discard()` after the pool is marked stopped.
- **Confidence:** Medium
- **Found by:** Error Handling, Concurrency & State

### [I5] Tests access private attributes across module boundaries (CLAUDE.md violation)
- **File:** `tests/unit/test_shesha_di.py:213,218,230,238,265,271,277,283`
- **Bug:** Multiple test classes access `shesha._rlm_engine`, `shesha._storage`, `shesha._parser_registry`, `shesha._repo_ingester`. CLAUDE.md explicitly states: "No private API access across module boundaries." Only `storage` has a public property; the others do not.
- **Impact:** Tests will break if private attributes are renamed. Creates tight coupling between test code and implementation details.
- **Suggested fix:** Add public read-only properties for the injected components, or restructure tests to verify behavior rather than internal wiring.
- **Confidence:** High
- **Found by:** Contract & Integration

### [I6] Engine tests access `_llm_client_factory` and `_pool` private attributes
- **File:** `tests/unit/rlm/test_engine.py:111,119,132,141` and `tests/unit/rlm/test_engine_cancellation.py:47,74`
- **Bug:** Tests access `engine._llm_client_factory` and `engine._pool` directly. Cancellation tests set `engine._pool = mock_pool` instead of using the public `set_pool()` method.
- **Impact:** Same CLAUDE.md violation as I5. Tests bypass the `isinstance` validation in `set_pool()`.
- **Suggested fix:** Use `engine.set_pool()` for pool injection. For `_llm_client_factory`, add a public property or test the factory's effect behaviorally.
- **Confidence:** High
- **Found by:** Contract & Integration

### [I7] `set_pool()` isinstance check blocks mock injection, contradicts protocol design
- **File:** `src/shesha/rlm/engine.py:224`
- **Bug:** `set_pool()` enforces `isinstance(pool, ContainerPool)`, rejecting any object that isn't the concrete class — including mocks without `spec=ContainerPool`. This is why tests bypass `set_pool()` and set `_pool` directly (I6). The check contradicts the protocol-based design where `SandboxExecutor` is the abstraction.
- **Impact:** Blocks the stated design goal of executor/pool substitution for testing or non-Docker backends. Forces tests to violate the private API boundary rule.
- **Suggested fix:** Remove the isinstance check (rely on static typing), or define a `SandboxPool` protocol. The comment at lines 221-223 acknowledges this tension.
- **Confidence:** Medium
- **Found by:** Contract & Integration

### [I8] CORS `allow_origins=["*"]` + `allow_credentials=True` + `0.0.0.0` binding
- **File:** `src/shesha/experimental/shared/app_factory.py:66-72` + `src/shesha/experimental/code_explorer/__main__.py:37`
- **Bug:** The server binds to `0.0.0.0` (all interfaces) with `allow_origins=["*"]` and `allow_credentials=True`. Any webpage on the same network can make cross-origin requests to the API, enabling CSRF against the unauthenticated endpoints (`add_repo`, `delete_repo`, etc.).
- **Impact:** A malicious webpage visited by a user on the same network could add/delete repos or trigger queries.
- **Suggested fix:** Bind to `127.0.0.1` by default. Remove `allow_credentials=True` when using wildcard origins.
- **Confidence:** Medium
- **Found by:** Security
- **Note:** Pre-existing. Already noted as "Won't fix" in the architecture report for local-only use, but the `0.0.0.0` binding broadens the exposure beyond localhost.

## Suggestions

### [S1] `classify_query` catches `PermanentError` (auth failures), delaying error signal
- **File:** `src/shesha/analysis/shortcut.py:104`
- `classify_query`'s bare `except Exception` catches `PermanentError` (auth failure) and returns a graceful fallback. This delays the error through 2 extra LLM calls before it surfaces in the full RLM query.
- **Found by:** Error Handling

### [S2] Post-ingestion metadata save failure leaves project without SHA/URL
- **File:** `src/shesha/repo/ingester.py:506-514`
- After successful ingestion, `save_sha` and `save_source_url` run outside the main try/except. If either fails (disk full), the project exists with documents but no metadata, breaking update-checking.
- **Found by:** Error Handling

### [S3] `ExecutionResult` imported from concrete `executor.py` instead of `base.py`
- **File:** `src/shesha/rlm/engine.py:38`
- The engine imports `ExecutionResult` from the concrete `executor.py` (which re-exports it from `base.py`). This creates an unnecessary transitive dependency on Docker, partially defeating the dependency inversion goal of F-14.
- **Found by:** Contract & Integration

### [S4] Mock sets `mock._pool = None` bypassing public API
- **File:** `tests/unit/test_shesha_di.py:25`
- `_make_mock_engine()` sets `mock._pool = None` directly on a mock RLMEngine. Minor private API boundary violation.
- **Found by:** Contract & Integration

### [S5] `_finalized` not set on write failure allows repeated finalize attempts
- **File:** `src/shesha/rlm/trace_writer.py:169-172`
- If `finalize()` fails under `suppress_errors=True`, `_finalized` stays `False`. The safety-net in `engine.py`'s `finally` block retries finalization with `"[interrupted]"` as the answer, which could overwrite the intended answer/status if the retry succeeds.
- **Found by:** Security, Contract & Integration

## Plan Alignment

- **Implemented:** F-1, F-2, F-4, F-5, F-6, F-7, F-8, F-9, F-11, F-13, F-14, F-15, F-16, F-17, F-20, F-21, F-22, F-23, F-24, F-25, F-26
- **Not yet implemented:** F-12 (sync-only LLM client) — no status annotation
- **Won't fix (reasonable):** F-3, F-10, F-19
- **Skipped (reasonable):** F-18
- **Deviations:**
  - F-1: Status claims `query()` reduced to ~310 lines; actual is ~400 lines. Decomposition is real (3 extracted methods) but metric overstated.
  - F-14: `ExecutionResult` and `LLMQueryHandler` correctly defined in `base.py` (not imported from `executor.py` as a prior review claimed). Dependency direction is correct.
  - F-15: `_finalized = True` correctly set after write (line 172), not before — contradicts a prior code review's claim (I5 in 3rd review).
  - F-4: `set_pool()` uses `isinstance(ContainerPool)` check rather than protocol-based typing. Acknowledged in code comments but creates tension with F-14's protocol goals.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Plan Alignment (6 specialists + 1 verifier)
- **Scope:** 40 changed files + adjacent callers/callees one level deep
- **Raw findings:** 29 (before verification)
- **Verified findings:** 13 (after verification)
- **Filtered out:** 16 (false positives, below confidence threshold, or theoretical races with benign fallbacks)
- **Steering files consulted:** CLAUDE.md
- **Plan/design docs consulted:** paad/architecture-reviews/2026-03-18-shesha-architecture-report.md
