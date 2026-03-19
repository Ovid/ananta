# Architecture Report — shesha

**Date:** 2026-03-18
**Commit:** a8543d7c4338b1709f32fb03b0d270535af86ce2
**Languages:** Python 3.11+ (core library, web explorers via FastAPI/WebSocket), JavaScript/HTML (explorer frontends)
**Key directories:** `src/shesha/` (111 source files, ~14K lines), `tests/` (142 test files)
**Scope:** Full repository

## Repo Overview

Shesha is a Python library implementing Recursive Language Models (RLMs) per arXiv:2512.24601v1. Documents are loaded as variables in a sandboxed Python REPL inside Docker containers; an LLM generates code to explore them, observes output, and iterates until producing a `FINAL("answer")`. The codebase consists of a core library (`rlm/`, `llm/`, `sandbox/`, `parser/`, `storage/`, `security/`) and three experimental web explorers (`web/`, `code_explorer/`, `document_explorer/`) built on a shared FastAPI+WebSocket infrastructure. A Textual-based TUI provides a terminal interface. The project uses strict mypy, ruff linting, and has ~142 test files.

## Strengths

### [S-1] Protocol-based interface contracts
- **Category:** S1 (Clear modular boundaries) / S3 (Loose coupling)
- **Impact:** High
- **Explanation:** `StorageBackend` and `DocumentParser` are `typing.Protocol` classes, enabling structural subtyping without inheritance coupling. The `Shesha` constructor accepts these via dependency injection with sensible defaults.
- **Evidence:** `storage/base.py:12` (`class StorageBackend(Protocol)`), `parser/base.py:9` (`class DocumentParser(Protocol)`), `shesha.py:47-49` (DI parameters)
- **Found by:** Structure, Coupling

### [S-2] Container hardening with defense-in-depth
- **Category:** S10 (Security built-in)
- **Impact:** High
- **Explanation:** Every sandbox container is hardened by default: drops ALL capabilities, disables networking, read-only root filesystem, `no-new-privileges`, and size-limited `noexec/nosuid/nodev` tmpfs. No opt-in required.
- **Evidence:** `security/containers.py:7-42` (`cap_drop=["ALL"]`, `network_disabled=True`, `read_only=True`, `security_opt=["no-new-privileges:true"]`)
- **Found by:** Security

### [S-3] Randomized per-query untrusted content boundaries
- **Category:** S10 (Security built-in)
- **Impact:** High
- **Explanation:** Each query generates a 128-bit hex boundary via `secrets.token_hex(16)`. Untrusted content is wrapped in boundary markers, making it cryptographically infeasible for adversarial documents to forge closing tags.
- **Evidence:** `rlm/boundary.py:13` (`generate_boundary()`) used in `engine.py:451`
- **Found by:** Structure, Security

### [S-4] Container executor protocol limits and DoS protection
- **Category:** S10 (Security built-in) / S12 (Resilience patterns)
- **Impact:** High
- **Explanation:** The executor enforces MAX_BUFFER_SIZE (10MB), MAX_MESSAGE_SIZE (10MB), MAX_READ_DURATION (300s), MAX_PAYLOAD_SIZE (50MB), and DEFAULT_SEND_TIMEOUT (30s). Protocol violations trigger container termination, preventing reuse of compromised state.
- **Evidence:** `sandbox/executor.py:30-36` (limits), `:245-288` (fail-closed error handling with `self.stop()`)
- **Found by:** Integration, Security

### [S-5] Path traversal protection
- **Category:** S10 (Security built-in)
- **Impact:** High
- **Explanation:** All filesystem paths incorporating user-supplied data pass through `safe_path()`, which resolves and verifies paths stay under the base directory. Applied consistently across storage and ingestion.
- **Evidence:** `security/paths.py:12-31`, called in `filesystem.py:35,78,95,104,130` and `ingester.py:42`
- **Found by:** Security

### [S-6] LLM retry with exponential backoff, jitter, and error classification
- **Category:** S7 (Robust error handling) / S12 (Resilience patterns)
- **Impact:** High
- **Explanation:** LLM errors are classified into `PermanentError` (fail immediately), `TransientError` (retry), and `RateLimitError` (retry with backoff). Configurable exponential backoff with jitter prevents thundering herd.
- **Evidence:** `llm/retry.py:15-22` (`RetryConfig`), `:34` (`retry_with_backoff` catches only `RateLimitError | TransientError`)
- **Found by:** Integration, Error Handling

### [S-7] Dead executor recovery mid-loop
- **Category:** S7 (Robust error handling) / S12 (Resilience patterns)
- **Impact:** High
- **Explanation:** When a container executor dies mid-query, the engine discards it from the pool, acquires a fresh one, re-initializes context, and continues. Prevents single container crashes from killing entire queries.
- **Evidence:** `rlm/engine.py:857-872` (`self._pool.discard(executor); executor = self._pool.acquire()`)
- **Found by:** Integration, Error Handling

### [S-8] Constructor injection in Shesha facade
- **Category:** S5 (Dependency management hygiene)
- **Impact:** High
- **Explanation:** `Shesha.__init__` accepts optional `storage`, `engine`, `parser_registry`, and `repo_ingester` parameters with sensible defaults. Enables testing without Docker and allows swapping implementations.
- **Evidence:** `shesha.py:47-50`
- **Found by:** Coupling

### [S-9] Filesystem swap_docs with crash recovery
- **Category:** S12 (Resilience patterns)
- **Impact:** High
- **Explanation:** Implements a three-phase crash-recoverable swap: rename target to backup, rename source to target, delete backup. On startup after crash, leftover backups are detected and state is restored.
- **Evidence:** `storage/filesystem.py:237-282`
- **Found by:** Integration

### [S-10] Secret redaction in traces
- **Category:** S10 (Security built-in) / S8 (Observability present)
- **Impact:** High
- **Explanation:** Both trace writers automatically redact API keys, Bearer tokens, AWS keys, Base64 auth, private key blocks, and generic key=value patterns before writing to disk.
- **Evidence:** `security/redaction.py` (7 regex patterns), applied in `trace_writer.py:216` and `trace.py:88`
- **Found by:** Security, Error Handling

### [S-11] Git token handling via GIT_ASKPASS
- **Category:** S10 (Security built-in)
- **Impact:** High
- **Explanation:** Repository tokens are passed via `GIT_ASKPASS` environment variable, never embedded in URLs or CLI args. Temp files are cleaned up in `finally` blocks.
- **Evidence:** `repo/ingester.py:144-163`
- **Found by:** Security

### [S-12] Dedicated adversarial prompt injection test suite
- **Category:** S11 (Testability & coverage)
- **Impact:** High
- **Explanation:** Tests verify boundary escape, instruction override (ChatML, INST, Human/Assistant patterns), null bytes, Unicode line separators, RTL markers, and emoji all remain inside the security boundary.
- **Evidence:** `tests/unit/rlm/test_prompt_injection.py` (4 test classes)
- **Found by:** Security

### [S-13] High-cohesion security module
- **Category:** S2 (High cohesion)
- **Impact:** Medium
- **Explanation:** The `security/` package has three focused files: `containers.py` (container config), `paths.py` (traversal prevention), `redaction.py` (secret scrubbing). Each addresses one concern with minimal cross-coupling.
- **Evidence:** `containers.py` (42 lines), `paths.py` (47 lines), `redaction.py` (53 lines)
- **Found by:** Structure

### [S-14] Domain exception hierarchy
- **Category:** S13 (Domain modeling strength)
- **Impact:** Medium
- **Explanation:** Clean hierarchy rooted at `SheshaError` with typed subclasses carrying domain attributes (`project_id`, `doc_name`, `path`). Separate LLM error hierarchy for infrastructure concerns.
- **Evidence:** `exceptions.py` (9 exception classes), `llm/exceptions.py` (4 exception classes)
- **Found by:** Structure, Error Handling

### [S-15] Callback-based extension in experimental explorers
- **Category:** S14 (Simple, pragmatic abstractions)
- **Impact:** Medium
- **Explanation:** Shared infrastructure uses callbacks (`QueryHandler`, `BuildContext`, `ExtraHandler`) rather than subclassing. Each explorer module is a thin delegation layer (~60 lines).
- **Evidence:** `shared/websockets.py:39-54` (callback parameters), explorer-specific modules
- **Found by:** Structure

### [S-16] Clean LLM abstraction layer
- **Category:** S1 (Clear modular boundaries)
- **Impact:** Medium
- **Explanation:** The `llm/` package cleanly separates client (89 lines), retry logic (72 lines), and exceptions (28 lines). The retry module is generic and LLM-agnostic.
- **Evidence:** `llm/client.py`, `llm/retry.py`, `llm/exceptions.py`
- **Found by:** Structure

### [S-17] Stable dependency direction
- **Category:** S4 (Dependency direction is stable)
- **Impact:** Medium
- **Explanation:** `models.py` and `exceptions.py` depend on nothing. `storage/base.py` depends only on `models`. `shesha.py` (composition root) depends on everything, which is correct.
- **Evidence:** Import analysis of core module files
- **Found by:** Coupling

### [S-18] Shared schema and route infrastructure
- **Category:** S6 (Consistent API contracts)
- **Impact:** Medium
- **Explanation:** All three explorers share Pydantic schemas and `create_shared_router()` for identical REST endpoints. Domain-specific schemas extend without overriding shared ones.
- **Evidence:** `shared/schemas.py`, `shared/routes.py`
- **Found by:** Integration

### [S-19] Shared WebSocket message protocol
- **Category:** S6 (Consistent API contracts)
- **Impact:** Medium
- **Explanation:** Uniform WebSocket message types (`query`, `cancel`, `step`, `complete`, `error`, `status`, `cancelled`) with identical field shapes. Explorer-specific messages injected via `extra_handlers`.
- **Evidence:** `shared/websockets.py`
- **Found by:** Integration

### [S-20] Rate limiter for external APIs
- **Category:** S12 (Resilience patterns)
- **Impact:** Medium
- **Explanation:** Thread-safe rate limiter enforces minimum intervals between arXiv API calls and supports explicit backoff periods after 429 responses.
- **Evidence:** `experimental/arxiv/rate_limit.py:9-38`
- **Found by:** Integration

### [S-21] Atomic file persistence for sessions
- **Category:** S12 (Resilience patterns)
- **Impact:** Medium
- **Explanation:** Session writes use `tempfile.mkstemp` + `os.replace()` for atomic swap, preventing data corruption from interrupted writes.
- **Evidence:** `shared/session.py:36-44`
- **Found by:** Integration

### [S-22] Configuration with clear precedence hierarchy
- **Category:** S9 (Configuration discipline)
- **Impact:** Medium
- **Explanation:** Four-layer config: dataclass defaults < YAML/JSON file < environment variables < explicit kwargs. Boolean env vars validated with `_parse_bool_env`.
- **Evidence:** `config.py:92-133`
- **Found by:** Error Handling

### [S-23] Trace recording system
- **Category:** S8 (Observability present)
- **Impact:** Medium
- **Explanation:** Every RLM query produces JSONL traces with header, per-step records, and summary. `IncrementalTraceWriter` writes as steps occur so partial traces survive crashes.
- **Evidence:** `rlm/trace.py`, `rlm/trace_writer.py`
- **Found by:** Error Handling

### [S-24] TYPE_CHECKING guards prevent circular imports
- **Category:** S3 (Loose coupling)
- **Impact:** Low
- **Explanation:** Several files use `if TYPE_CHECKING:` guards to import types needed only for annotations, preventing runtime circular dependencies.
- **Evidence:** `models.py:8-9`, `analysis/generator.py:17-18`, `shesha.py:32-34`, `tui/app.py:33-35`
- **Found by:** Coupling

### [S-25] Comprehensive test suite for security and core paths
- **Category:** S11 (Testability & coverage)
- **Impact:** Medium
- **Explanation:** Test suite covers container security, path traversal, secret redaction, prompt injection boundaries, engine behavior, sandbox executor protocol, and runner behavior with mocked I/O.
- **Evidence:** `tests/unit/security/`, `tests/unit/rlm/`, `tests/unit/sandbox/`
- **Found by:** Security

## Flaws/Risks

### [F-1] RLMEngine.query() god method
- **Category:** 2 (God object)
- **Impact:** High
- **Explanation:** The `query()` method spans ~515 lines and manages LLM interaction, code extraction, FINAL parsing, variable resolution, code execution, verification, semantic verification, trace writing, cancellation, executor lifecycle, and fallback answers. Deeply nested with 7+ levels and many interleaved responsibilities.
- **Evidence:** `rlm/engine.py:436-951` — handles `LLMClient`, `ContainerExecutor`, `Trace`, `TokenUsage`, `IncrementalTraceWriter`, `VerificationResult`, `SemanticVerificationReport` all in one method
- **Found by:** Structure
- **Status:** Fixed
- **Status reason:** Extracted _execute_code_blocks(), _resolve_final_var(), _run_verifications(), and _CodeBlockResult dataclass. query() reduced from ~515 to ~310 lines.
- **Status date:** 2026-03-18 18:38 UTC
- **Status commit:** dc4edca

### [F-2] Pervasive private API access from experimental layer
- **Category:** 6 (Leaky abstractions) / 13 (Inconsistent boundaries)
- **Impact:** High
- **Explanation:** The shared WebSocket handlers and routes access `state.topic_mgr._storage`, `project._rlm_engine`, `state.shesha._storage`, and even double-private `_storage._project_path()`. This tightly couples the experimental modules to internal structure of `Project`, `Shesha`, and topic managers, making any refactoring of these internals break the web layer.
- **Evidence:** `shared/websockets.py:167,197,208,256,263,288,363,462`; `shared/routes.py:223` (`_storage._project_path`)
- **Found by:** Structure, Coupling, Integration (3 specialists agreed)
- **Status:** Fixed
- **Status reason:** Added Shesha.storage, Project.rlm_engine, StorageBackend.get_project_dir() public APIs. Updated all 8 experimental source files to use public APIs exclusively.
- **Status date:** 2026-03-18 19:42 UTC
- **Status commit:** efe0d0a

### [F-3] No authentication on web API endpoints
- **Category:** 30 (Security as an afterthought)
- **Impact:** High
- **Explanation:** The FastAPI app factory configures `allow_origins=["*"]` with `allow_credentials=True` and adds no authentication middleware. All REST and WebSocket endpoints are accessible to any network client. The comment says "during development" but there is no production auth path. These endpoints trigger LLM queries (consuming API credits) and execute code in Docker containers.
- **Evidence:** `shared/app_factory.py:66-72` (`CORSMiddleware(allow_origins=["*"], allow_credentials=True)`), no auth checks anywhere in shared or explorer modules
- **Found by:** Security
- **Status:** Won't fix
- **Status reason:** Acceptable for local-only PoC. Web explorers bind to localhost and are single-user. Auth middleware would be premature — the real mitigation is the bind address.
- **Status date:** 2026-03-18 19:45 UTC

### [F-4] Shesha.start() directly mutates RLMEngine._pool
- **Category:** 27 (Temporal coupling) / 13 (Inconsistent boundaries)
- **Impact:** Medium
- **Explanation:** The pool is assigned to the engine via direct private attribute mutation (`self._rlm_engine._pool = self._pool`) inside `start()`. The engine's behavior depends on whether this external method was called. Without `start()`, the engine silently creates standalone executors instead of using the pool.
- **Evidence:** `shesha.py:342`, read in `engine.py:546-553`
- **Found by:** Structure, Coupling
- **Status:** Fixed
- **Status reason:** Added RLMEngine.set_pool() with isinstance validation. Shesha.start() now uses the public API instead of mutating _pool directly.
- **Status date:** 2026-03-18 23:30 UTC
- **Status commit:** 909d354

### [F-5] Repo ingestion logic misplaced in Shesha facade
- **Category:** 10 (Feature envy / anemic domain model)
- **Impact:** Medium
- **Explanation:** The 115-line `_ingest_repo()` method in `Shesha` orchestrates file parsing, staging, atomic swap, error cleanup, and SHA persistence. This logic belongs in `RepoIngester` or a dedicated service, not the main API facade. `Shesha` has intimate knowledge of parser behavior and storage staging internals.
- **Evidence:** `shesha.py:470-584` — calls `_repo_ingester.list_files_from_path()`, `_parser_registry.find_parser()`, `_storage.create_project()`, `_storage.store_document()`, `_storage.swap_docs()`, `_storage.delete_project()`
- **Found by:** Structure
- **Status:** Fixed
- **Status reason:** Moved ingestion orchestration into RepoIngester.ingest(). Shesha._ingest_repo is now a thin wrapper that delegates and wraps IngestResult into RepoProjectResult.
- **Status date:** 2026-03-18 22:40 UTC
- **Status commit:** 3aa3f7f

### [F-6] Shotgun surgery: dual WebSocket response construction
- **Category:** 9 (Shotgun surgery)
- **Impact:** Medium
- **Explanation:** The WebSocket `complete` response is built as inline dict construction at two separate locations for single-project and multi-project handlers. Adding a new field (like `allow_background_knowledge` in commit `56fd993`) requires updating both. No shared schema enforces consistency.
- **Evidence:** `shared/websockets.py:310-325` (single-project) and `:521-535` (multi-project) — structurally identical but separately maintained
- **Found by:** Structure
- **Status:** Fixed
- **Status reason:** Extracted build_complete_response() helper used by both single-project and multi-project handlers
- **Status date:** 2026-03-18 18:16 UTC

### [F-7] RLMEngine creates LLMClient instances directly
- **Category:** 3 (Tight coupling)
- **Impact:** Medium
- **Explanation:** `RLMEngine` instantiates `LLMClient` at four points throughout the engine (subcall handler, two semantic verification layers, main query loop). There is no way to inject a custom LLM client for testing without API calls or for using a different LLM abstraction.
- **Evidence:** `engine.py:261` (subcall), `:344` (verification L1), `:408` (verification L2), `:516` (main loop)
- **Found by:** Coupling
- **Status:** Fixed
- **Status reason:** Added llm_client_factory parameter to RLMEngine.__init__() defaulting to LLMClient. All 4 creation sites use self._llm_client_factory() enabling test injection without import-level patching.
- **Status date:** 2026-03-18 22:47 UTC
- **Status commit:** b7b3122

### [F-8] hasattr check breaks storage protocol abstraction
- **Category:** 6 (Leaky abstractions)
- **Impact:** Medium
- **Explanation:** `Shesha._ingest_repo` uses `hasattr(self._storage, "swap_docs")` to decide between an atomic swap path and manual copy-then-delete. `swap_docs` is not part of the `StorageBackend` protocol, creating an implicit dependency on `FilesystemStorage`.
- **Evidence:** `shesha.py:535`
- **Found by:** Coupling
- **Status:** Fixed
- **Status reason:** Added swap_docs to StorageBackend protocol with default_swap_docs fallback function. hasattr check eliminated — ingestion now calls storage.swap_docs() unconditionally.
- **Status date:** 2026-03-18 22:40 UTC
- **Status commit:** 3aa3f7f

### [F-9] No logging in core library modules
- **Category:** 21 (No observability plan) / 34 (Inconsistent error/logging)
- **Impact:** Medium
- **Explanation:** The entire core library (RLM engine, LLM client, sandbox executor, container pool, Shesha facade, Project) has zero `logging` module usage. Only `trace_writer.py` and the `experimental/` subsystem use loggers. Operator-facing diagnostics (container lifecycle, LLM call timing, pool exhaustion, executor restarts) are invisible.
- **Evidence:** Zero `logger` instances in `engine.py`, `client.py`, `executor.py`, `pool.py`, `shesha.py`, `project.py`
- **Found by:** Error Handling
- **Status:** Fixed
- **Status reason:** Added logging.getLogger(__name__) to all 6 core modules. Key log points: query start/end with timing, pool lifecycle, pool exhaustion, executor recovery, LLM errors.
- **Status date:** 2026-03-19 00:20 UTC
- **Status commit:** ccf6025

### [F-10] Broad exception swallowing in analysis shortcut
- **Category:** 20 (Weak error handling strategy)
- **Impact:** Medium
- **Explanation:** Both `classify_query` and `try_answer_from_analysis` catch bare `except Exception` and return fallback values with zero logging. Persistent auth errors, configuration issues, or unexpected failures produce no diagnostic signal.
- **Evidence:** `analysis/shortcut.py:78` (`except Exception: return (True, 0, 0)`), `:120` (`except Exception: return None`)
- **Found by:** Error Handling
- **Status:** Won't fix
- **Status reason:** False positive — both exception handlers have explanatory comments per codebase style guide. The fallback behavior is intentional: shortcut failure degrades gracefully to the full RLM query path.
- **Status date:** 2026-03-18 18:22 UTC

### [F-11] Business logic in TUI layer
- **Category:** 25 (Business logic in the UI)
- **Impact:** Medium
- **Explanation:** The TUI's `_make_query_runner` contains analysis shortcut decision logic (try shortcut, check result, branch on success/failure). This same logic would need to be duplicated for any other frontend.
- **Evidence:** `tui/app.py:384-423`
- **Found by:** Error Handling
- **Status:** Fixed
- **Status reason:** Extracted query_with_shortcut() and ShortcutResult dataclass into analysis/shortcut.py. TUI now calls the domain function instead of inlining the shortcut decision logic.
- **Status date:** 2026-03-19 00:00 UTC
- **Status commit:** 809e32b

### [F-12] Synchronous-only LLM client
- **Category:** 16 (Synchronous-only integration)
- **Impact:** Medium
- **Explanation:** `LLMClient.complete()` calls blocking `litellm.completion()`. The web layer works around this via `loop.run_in_executor()`, meaning every concurrent query occupies a thread. Adequate for single-user explorers but limits concurrency scaling.
- **Evidence:** `llm/client.py:69` (`litellm.completion()`), `shared/websockets.py:265` (`run_in_executor`)
- **Found by:** Integration

### [F-13] Multi-step document upload lacks atomicity
- **Category:** 26 (Poor transactional boundaries)
- **Impact:** Medium
- **Explanation:** Document upload performs 6 sequential side effects (write file, extract text, write metadata, create project, store document, add to topic). Only text extraction failure triggers cleanup. Failures at later steps leave orphaned upload directories and unattached projects.
- **Evidence:** `document_explorer/api.py:155-213`
- **Found by:** Integration
- **Status:** Fixed
- **Status reason:** Wrapped post-extraction steps in try/except with cleanup: deletes project (if created) and upload dir on failure at any step.
- **Status date:** 2026-03-19 00:10 UTC
- **Status commit:** acd713c

### [F-14] ContainerPool returns concrete ContainerExecutor
- **Category:** 6 (Leaky abstractions)
- **Impact:** Low
- **Explanation:** `ContainerPool.acquire()` returns the concrete `ContainerExecutor` class. There is no executor protocol/interface, preventing substitution of mock executors for testing or non-Docker backends.
- **Evidence:** `sandbox/pool.py:51` (`def acquire(self) -> ContainerExecutor`)
- **Found by:** Coupling

### [F-15] IncrementalTraceWriter temporal coupling
- **Category:** 27 (Temporal coupling)
- **Impact:** Low
- **Explanation:** Requires calling `start()` before `write_step()` before `finalize()`. Skipping `start()` causes silent no-ops. The no-op behavior is intentional fault tolerance but the call sequence has no type-level enforcement.
- **Evidence:** `rlm/trace_writer.py:204` (`if self.path is None: return`), `:243` (same guard)
- **Found by:** Coupling
- **Status:** Fixed
- **Status reason:** Added _finalized state flag to IncrementalTraceWriter with public `finalized` property. write_step() and finalize() are no-ops after finalization. Removed redundant `trace_finalized` guard from RLMEngine.query() — writer now owns its own state invariant.
- **Status date:** 2026-03-19 06:12 UTC
- **Status commit:** cfad664

### [F-16] analysis/shortcut.py creates LLMClient directly
- **Category:** 3 (Tight coupling)
- **Impact:** Low
- **Explanation:** Both functions create `LLMClient` inline, making them impossible to test without mocking at the import level. Less impactful than engine coupling since these are standalone utility functions.
- **Evidence:** `analysis/shortcut.py:74`, `:110`
- **Found by:** Coupling
- **Status:** Fixed
- **Status reason:** Added llm_client_factory parameter to classify_query() and try_answer_from_analysis(), defaulting to LLMClient. Same pattern as F-7 fix.
- **Status date:** 2026-03-18 22:50 UTC
- **Status commit:** a33371a

### [F-17] AnalysisGenerator takes full Shesha instance
- **Category:** 3 (Tight coupling)
- **Impact:** Low
- **Explanation:** `AnalysisGenerator.__init__` takes a `Shesha` instance but only uses `get_project()` and `get_project_sha()`. Wider dependency surface than necessary.
- **Evidence:** `analysis/generator.py:24`
- **Found by:** Coupling
- **Status:** Fixed
- **Status reason:** Changed constructor to accept two callables (get_project, get_project_sha) instead of full Shesha instance
- **Status date:** 2026-03-18 22:02 UTC
- **Status commit:** 699ea3d

### [F-18] Non-idempotent document upload
- **Category:** 19 (Lack of idempotency)
- **Impact:** Low
- **Explanation:** `_make_project_id` includes `datetime.now(UTC).isoformat()` in its hash, so uploading the same file twice creates different project IDs. Repeated uploads waste storage.
- **Evidence:** `document_explorer/api.py:47`
- **Found by:** Integration
- **Status:** Skipped
- **Status reason:** Requires content-based hashing and duplicate detection in the upload endpoint — broader change than a simple hash fix. Deferred to a dedicated task.
- **Status date:** 2026-03-19 06:15 UTC

### [F-19] WebSocket vs REST field naming mismatch
- **Category:** 24 (Inconsistent API contracts)
- **Impact:** Low
- **Explanation:** WebSocket `complete` message uses `duration_ms` (int) while `ExchangeSchema` uses `execution_time` (float seconds). Different field names for the same concept across channels.
- **Evidence:** `shared/websockets.py:320` vs `shared/schemas.py:65`
- **Found by:** Integration
- **Status:** Won't fix
- **Status reason:** False positive — the naming split is intentional. execution_time (float seconds) is the internal representation used in QueryResult, ExchangeSchema, and session storage. duration_ms (int milliseconds) is the WebSocket wire format for client convenience, produced by build_complete_response() at the API boundary. Different units at different layers, not inconsistent naming.
- **Status date:** 2026-03-18 22:05 UTC

### [F-20] Code explorer pending_updates in memory
- **Category:** 26 (Poor transactional boundaries)
- **Impact:** Low
- **Explanation:** The check-updates/apply-updates two-phase operation stores state in an in-memory dict. Server restart between check and apply loses the pending update.
- **Evidence:** `code_explorer/api.py:61` (`pending_updates: dict[str, RepoProjectResult] = {}`)
- **Found by:** Integration
- **Status:** Fixed
- **Status reason:** apply-updates now self-heals when cache is empty: re-derives update state via create_project_from_repo, returns 409 only if genuinely no updates available. Server restarts no longer lose pending updates.
- **Status date:** 2026-03-19 06:30 UTC
- **Status commit:** 0733dac

### [F-21] LLMError doesn't inherit SheshaError
- **Category:** 20 (Weak error handling strategy)
- **Impact:** Low
- **Explanation:** `LLMError` inherits from `Exception`, not `SheshaError`. A caller catching `SheshaError` will miss LLM errors. May be intentional (infrastructure vs domain separation) but creates a gap.
- **Evidence:** `llm/exceptions.py:4` (`class LLMError(Exception)`)
- **Status:** Fixed
- **Status reason:** Changed LLMError to inherit from SheshaError, unifying the exception hierarchy
- **Status date:** 2026-03-18 21:55 UTC
- **Status commit:** 789f6a4
- **Found by:** Error Handling

### [F-22] Magic numbers in context budget estimation
- **Category:** 28 (Magic numbers/strings everywhere)
- **Impact:** Low
- **Explanation:** Context budget endpoint uses `2000` (base prompt tokens), `// 4` (chars-per-token ratio), and `128000` (default max tokens) as inline literals without named constants.
- **Evidence:** `shared/routes.py:430,436,439`
- **Found by:** Error Handling
- **Status:** Fixed
- **Status reason:** Extracted BASE_PROMPT_TOKENS, CHARS_PER_TOKEN, DEFAULT_MAX_CONTEXT_TOKENS as module-level constants
- **Status date:** 2026-03-18 18:08 UTC

### [F-23] Hidden side effect in _finalize_trace
- **Category:** 12 (Hidden side effects)
- **Impact:** Low
- **Explanation:** The `_finalize_trace` inner function not only writes the summary but also calls `cleanup_old_traces` which deletes old trace files. The function name doesn't suggest data deletion.
- **Evidence:** `rlm/engine.py:499-513`
- **Found by:** Error Handling
- **Status:** Fixed
- **Status reason:** Renamed to _finalize_trace_and_cleanup to make the cleanup side effect visible in the name
- **Status date:** 2026-03-18 21:58 UTC
- **Status commit:** f2aa232

### [F-24] Config env_map incomplete
- **Category:** 22 (Configuration sprawl)
- **Impact:** Low
- **Explanation:** 5 of 12 config fields (`container_memory_mb`, `execution_timeout_sec`, `sandbox_image`, `max_output_chars`, `keep_raw_files`) lack environment variable mappings, requiring config files for those settings.
- **Evidence:** `config.py:110-118` (env_map has 7 entries)
- **Found by:** Error Handling
- **Status:** Fixed
- **Status reason:** Added env var mappings for all 6 missing fields (keep_raw_files, container_memory_mb, execution_timeout_sec, sandbox_image, max_output_chars, verify) with proper int/bool parsing
- **Status date:** 2026-03-18 18:12 UTC

### [F-25] sanitize_filename defined but never used
- **Category:** 31 (Dead code / unused dependencies)
- **Impact:** Low
- **Explanation:** `sanitize_filename()` is defined in `security/paths.py`, exported from `security/__init__.py`, and tested, but never called in application code.
- **Evidence:** `security/paths.py:34-47`
- **Found by:** Security
- **Status:** Fixed
- **Status reason:** Removed function from paths.py, export from __init__.py, and associated tests
- **Status date:** 2026-03-18 18:05 UTC

### [F-26] TraceWriter.write_trace() replaced but not removed
- **Category:** 31 (Dead code / unused dependencies)
- **Impact:** Low
- **Explanation:** The batch `write_trace()` method has been replaced by `IncrementalTraceWriter` for production use. `TraceWriter` is only instantiated for `cleanup_old_traces()`. The `write_trace()` method is tested but never called in production.
- **Evidence:** `rlm/trace_writer.py:25-117`, `engine.py:480` (uses `IncrementalTraceWriter`), `engine.py:511` (uses `TraceWriter` only for cleanup)
- **Found by:** Security
- **Status:** Fixed
- **Status reason:** Removed write_trace() method (~93 lines) and associated tests. TraceWriter class retained for cleanup_old_traces().
- **Status date:** 2026-03-18 18:20 UTC

## Coverage Checklist

### Flaw/Risk Types 1-34
| # | Type | Status | Finding |
|---|------|--------|---------|
| 1 | Global mutable state | Not observed | Sandbox NAMESPACE is intentional per-container design |
| 2 | God object | Observed | #F-1 |
| 3 | Tight coupling | Observed | #F-7, #F-16, #F-17 |
| 4 | High/unstable dependencies | Not observed | Subsumed by F-2 |
| 5 | Circular dependencies | Not observed | TYPE_CHECKING guards prevent these |
| 6 | Leaky abstractions | Observed | #F-2, #F-8, #F-14 |
| 7 | Over-abstraction | Not observed | -- |
| 8 | Premature optimization | Not observed | -- |
| 9 | Shotgun surgery | Observed | #F-6 |
| 10 | Feature envy / anemic domain model | Observed | #F-5 |
| 11 | Low cohesion | Not observed | -- |
| 12 | Hidden side effects | Observed | #F-23 |
| 13 | Inconsistent boundaries | Observed | #F-2, #F-4 |
| 14 | Distributed monolith | Not applicable | Single-process library |
| 15 | Chatty service calls | Not applicable | No inter-service calls |
| 16 | Synchronous-only integration | Observed | #F-12 |
| 17 | No clear ownership of data | Not observed | Subsumed by F-2 |
| 18 | Shared database across services | Not applicable | Single process |
| 19 | Lack of idempotency | Observed | #F-18 |
| 20 | Weak error handling strategy | Observed | #F-10, #F-21 |
| 21 | No observability plan | Observed | #F-9 |
| 22 | Configuration sprawl | Observed | #F-24 |
| 23 | Dependency injection misuse | Not observed | -- |
| 24 | Inconsistent API contracts | Observed | #F-19 |
| 25 | Business logic in the UI | Observed | #F-11 |
| 26 | Poor transactional boundaries | Observed | #F-13, #F-20 |
| 27 | Temporal coupling | Observed | #F-4, #F-15 |
| 28 | Magic numbers/strings everywhere | Observed | #F-22 |
| 29 | "Utility" dumping ground | Not observed | -- |
| 30 | Security as an afterthought | Observed | #F-3 |
| 31 | Dead code / unused dependencies | Observed | #F-25, #F-26 |
| 32 | Missing or inadequate test coverage | Not assessed | Insufficient data to confirm |
| 33 | Hard-coded credentials or secrets | Not observed | .env gitignored, not in source |
| 34 | Inconsistent error/logging conventions | Observed | #F-9 |

### Strength Categories S1-S14
| # | Category | Status | Finding |
|---|----------|--------|---------|
| S1 | Clear modular boundaries | Observed | #S-1, #S-16 |
| S2 | High cohesion | Observed | #S-13 |
| S3 | Loose coupling | Observed | #S-1, #S-24 |
| S4 | Dependency direction is stable | Observed | #S-17 |
| S5 | Dependency management hygiene | Observed | #S-8 |
| S6 | Consistent API contracts | Observed | #S-18, #S-19 |
| S7 | Robust error handling | Observed | #S-6, #S-7 |
| S8 | Observability present | Observed | #S-10, #S-23 |
| S9 | Configuration discipline | Observed | #S-22 |
| S10 | Security built-in | Observed | #S-2, #S-3, #S-4, #S-5, #S-10, #S-11 |
| S11 | Testability & coverage | Observed | #S-12, #S-25 |
| S12 | Resilience patterns | Observed | #S-4, #S-6, #S-7, #S-9, #S-20, #S-21 |
| S13 | Domain modeling strength | Observed | #S-14 |
| S14 | Simple, pragmatic abstractions | Observed | #S-15 |

## Hotspots

1. **`src/shesha/rlm/engine.py`** — The 515-line `query()` method is the highest-complexity, highest-fan-out point in the codebase. It concentrates the most architectural risk (god method, direct LLM client creation, executor lifecycle management) and would benefit from decomposition.

2. **`src/shesha/experimental/shared/websockets.py`** — The primary gateway between the web layer and core library. Contains pervasive private API access (8+ sites), dual response construction, and is the most change-sensitive file in the experimental layer. Three specialists independently flagged this file.

3. **`src/shesha/shesha.py`** — The composition root that also hosts repo ingestion logic (115 lines of feature envy), direct private attribute mutation of the engine, and hasattr checks for non-protocol methods. Boundary between facade responsibility and implementation leakage.

## Next Questions

1. Is the experimental web layer's private API access a deliberate trade-off for development speed, or should `Project`/`Shesha`/`TopicManager` expose richer public APIs?
2. What is the deployment model for the web explorers — are they intended to remain local/single-user, or could they be exposed to a network? This determines the urgency of the auth gap.
3. Has `RLMEngine.query()` been intentionally kept as one method for debuggability/traceability, or would the team welcome decomposition?
4. Should `LLMError` inherit from `SheshaError`, or is the infrastructure/domain exception separation intentional?
5. Is `TraceWriter.write_trace()` kept as a fallback/utility, or can it be safely removed now that `IncrementalTraceWriter` has replaced it?

## Analysis Metadata

- **Agents dispatched:** Structure & Boundaries, Coupling & Dependencies, Integration & Data, Error Handling & Observability, Security & Code Quality (5 specialists + 1 verifier)
- **Scope:** All 111 source files in `src/shesha/` and 142 test files in `tests/`
- **Raw findings:** 61 (26 strengths + 35 flaws)
- **Verified findings:** 51 (25 strengths + 26 flaws)
- **Filtered out:** 10 (6 false positives/intentional design, 4 duplicates)
- **By impact:** 3 high flaws, 10 medium flaws, 13 low flaws; 12 high strengths, 11 medium strengths, 2 low strengths
- **Steering files consulted:** CLAUDE.md
