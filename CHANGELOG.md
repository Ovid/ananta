# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Document Explorer: folder upload. Drop a folder onto the explorer (or use the new "Upload folder" button) to recursively upload its supported files into the currently selected topic. Pre-flight modal previews counts, byte totals, and skipped reasons; progress modal shows per-batch upload; summary modal reports ingested / failed / skipped per file. Drop is disabled when no topic is selected. (See `docs/plans/2026-05-05-folder-upload-design.md`.)
- Document Explorer: documents now expose a `relative_path` field (in API responses, UI subtitle, and `ParsedDocument.metadata`) so the LLM can filter or group by folder structure.

### Changed

- Document Explorer: multi-file upload now returns per-file partial-success rows instead of failing the whole request on one bad file. Each `DocumentUploadResponse` row carries `status` (`"created"` or `"failed"`) and an optional `reason`. Single-file uploads are observably unchanged.
- Document Explorer: upload limits centralized in `src/ananta/explorers/document/config.py`. No behavior change.

### Fixed

- Codebase analysis no longer crashes with `AttributeError` when the LLM returns a bare string in the `components` or `external_dependencies` arrays — strings are now promoted to `{"name": <string>}` to match the expected element shape
- Code Explorer now shows an "Analysis in progress…" status on the repo detail page while an analysis is running — the action buttons are hidden so the in-progress state is unambiguous, and the state is preserved when the user navigates away and returns (previously the page reverted to "Generate Analysis", letting users start a duplicate run)
- Code Explorer repo "analysis status" badge now refreshes from "not analyzed" to "current" as soon as analysis completes (previously the badge stayed stale until the page was reloaded)
- Document Explorer: single/multi-file upload via the picker now reports per-file failures in the toast — previously it always toasted "uploaded" even when the server flagged unsupported extensions or oversize files
- Document Explorer: folder upload modal recovers from server errors (e.g., 413) — previously a non-OK response left the modal stuck on "progress" with no error info
- Document Explorer: folder upload sidebar refreshes after a mid-upload cancel — committed batches no longer remain hidden until manual reload
- Document Explorer: project-id collisions can no longer destroy unrelated documents (suffix is now cryptographically random; rollback skips destructive cleanup unless this upload created the project)
- Document Explorer: Continue button on the folder-upload preflight modal disables on click, preventing double-click double-uploads
- Document Explorer: a folder containing many unsupported files but few accepted ones no longer trips the 500-file cap (the cap now counts accepted files only)
- Document Explorer: re-picking the same folder via the folder-input button now works (the input value is reset after each selection)
- Document Explorer: a folder upload that trips the 200 MB aggregate cap now returns 200 with per-file failed rows for the over-the-line files instead of a hard 413 that abandoned earlier files already committed server-side
- Document Explorer: when a later batch of a folder upload fails, the summary now reflects the rows committed by earlier batches instead of showing "0 ingested" alongside an upload-failure row
- Document Explorer: a network drop, DNS failure, or malformed JSON response mid-folder-upload no longer strands the rows from earlier successful batches — every error path through `uploadFolderInBatches` now wraps as `BatchUploadError` so the summary always reflects the durably-committed work (the previous fix only covered HTTP non-OK responses)
- Document Explorer: dropping a folder with zero supported files no longer enables the Continue button on the preflight modal (which used to flash a nonsensical "batch 1 of 0" progress modal and trigger a needless sidebar refetch)
- Document Explorer: folder-upload summary now disambiguates skipped and failed rows for files with the same bare name in different subfolders (e.g., two `README.md` files under `pkg-a/` and `pkg-b/`) by prefixing the relative path. The server's `DocumentUploadResponse` now echoes `relative_path` to support this
- Document Explorer: cancelling an upload and starting a new one no longer leaves the new upload's Cancel button unresponsive (the previous upload's promise no longer clobbers the new abort controller)
- Document Explorer: the folder-upload progress modal no longer briefly displays "batch 0 of N" before the first batch completes
- Document Explorer: corrupt PDFs / DOCX / PPTX / XLSX files now report "text extraction failed: …" instead of a generic "unexpected upload error"
- Document Explorer: a get_page_count failure no longer rejects the entire upload — page count falls back to None and the file still ingests
- Document Explorer: dropping multiple folders at once now strips each top-level folder's own name from its files' relative paths (previously only the first folder's prefix was stripped)
- Document Explorer: a single unreadable file in a dropped folder no longer abandons the whole walk — readable files still reach the summary
- Document Explorer: dropping a second folder while an upload is in flight is now a no-op (previously it churned the modal); cancel the first upload to start a new one
- Document Explorer: rename now refreshes all DocumentInfo fields from disk instead of reconstructing them inline (no observable change today, but new metadata fields surface immediately)
- Shared explorer factory: chunked / no-Content-Length requests above the 256 MiB body cap now return a real 413 instead of failing with a 5xx ClientDisconnect — the body-size middleware was rewritten as a pure ASGI middleware so it can synthesise the 413 from inside the streaming branch
- Document Explorer: folder-upload paths with apostrophes, parens, brackets, commas, ampersands, plus signs, hash, and other common filename punctuation no longer fail with "invalid relative_path" — the validator switched from a tight allowlist to a denylist of control bytes, backslash, leading slash, and `..`-as-segment. Filenames like `John's docs/notes (final).md`, `C++/file.cpp`, and `Q&A/answers.md` now ingest cleanly. `..` inside a single segment (e.g., `v1.0..final.txt`) is also accepted; only `..` as a complete segment is treated as path traversal

### Security

- Document Explorer: `/api/documents/upload` rejects requests with more than 500 files (denial-of-service guard); previously only the per-file 50 MB and per-batch 200 MB caps were enforced server-side
- Document Explorer: per-file upload errors no longer include raw exception text in the API response (which could leak filesystem paths or dependency error details); the original exception is logged server-side
- Document Explorer: `relative_path` form input is now validated against an allowlist regex (max 512 chars, no `..`, no leading `/`, ASCII-friendly character set). Previously the value was persisted verbatim, allowing disk-fill DoS via giant strings and a path-traversal / prompt-injection surface. The array length is also required to match `files` length
- Shared explorer factory now rejects requests with bodies above 256 MiB at the middleware layer before any data is spooled to disk. Previously the application's per-route caps fired only after Starlette had finished spooling, leaving a disk-fill DoS reachable
- Shared explorer factory now refuses mutating HTTP requests (POST/PUT/PATCH/DELETE) whose `Origin` header does not match `Host`. Defends against drive-by uploads from arbitrary webpages: with `allow_origins=["*"]` and no auth on `/api/documents/upload`, any page the user visited could previously inject attacker-chosen documents into the local RLM corpus. Direct API callers (curl, scripts) typically omit `Origin` and remain unaffected

## [0.24.0] - 2026-03-22

### Changed

- Explorers no longer auto-open the browser on startup — pass `--open` to open it (replaces `--no-browser`)
- Explorers print their URL on startup so users know where to connect

### Fixed

- Docker socket auto-discovery — finds Docker Desktop, Colima, and Podman sockets automatically instead of failing with a stacktrace when `/var/run/docker.sock` is missing ([#8](https://github.com/Ovid/ananta/issues/8))
- Clean error message when `ananta-sandbox` Docker image is missing, with build command hint

## [0.23.0] - 2026-03-20

### Added

- Startup migration warnings when legacy `shesha_data/`, `~/.shesha/`, or `~/.shesha-arxiv/` directories are detected
- **`/release` skill** — Claude Code skill for merging feature branches with automatic semantic versioning, changelog finalization, `git done -y`, and git tagging

### Changed

- **BREAKING:** Renamed project from "Shesha" to "Ananta" to avoid confusion
  with "shisha" (hookah). Ananta is an alternate name for the same Hindu serpent
  deity. All public APIs, environment variables, CLI commands, and data
  directories have been renamed:
  - Package: `shesha` → `ananta`
  - Classes: `Shesha` → `Ananta`, `SheshaConfig` → `AnantaConfig`, `SheshaError` → `AnantaError`
  - CLI: `shesha-web` → `ananta-web`, `shesha-code` → `ananta-code`, `shesha-document-explorer` → `ananta-document-explorer`
  - Environment variables: `SHESHA_*` → `ANANTA_*`
  - Data directories: `shesha_data` → `ananta_data`, `~/.shesha/` → `~/.ananta/`, `~/.shesha-arxiv/` → `~/.ananta-arxiv/`
  - Docker image: `shesha-sandbox` → `ananta-sandbox` — rebuild required: `docker build -t ananta-sandbox src/ananta/sandbox/`
- Changelog rewritten with versioned sections for all 13 previously unversioned branch merges (v0.10.0–v0.21.1), with keepachangelog 1.1.0 comparison links
- CLAUDE.md versioning section updated: `/release` is now the only sanctioned merge path, keepachangelog 1.1.0 format enforced, auto-increment version rules documented

## [0.21.1] - 2026-03-20

### Fixed

- Pending question and thinking indicator now scoped to their originating topic — switching topics no longer shows the previous topic's in-flight query state (question bubble, spinner, phase text) in the new topic's chat area

## [0.21.0] - 2026-03-20

### Added

- **`PARTIAL()` callable** — RLM can now call `PARTIAL("partial answer")` when it exhausts iterations without reaching `FINAL()`, reporting partial evidence instead of giving up silently
  - Registered in sandbox runtime alongside `FINAL()`
  - `gave_up` flag propagated through `QueryResult`, `ExchangeSchema`, session, and WebSocket responses
  - More button becomes context-sensitive: shows a retry prompt when the previous answer was partial
  - System prompts updated to instruct the RLM to use `PARTIAL()` on give-up
- **Sidebar rename and reorder UI** — rename repos, documents, and papers via new API endpoints; drag-and-drop document reordering with backend support
- **Consulted documents footer** shown in chat responses
- `final_source` metadata in trace steps for answer provenance debugging
- `SandboxExecutor` protocol in `sandbox/base.py` for executor abstraction (enables mock executors and non-Docker backends)
- `resolve()` method on `BaseTopicManager` for shared routes/websockets
- `allow_local_paths` flag on `RepoIngester` to explicitly control local path access
- `--bind` CLI flag for experimental servers (default changed to `127.0.0.1`)
- Logging added to core library modules (`rlm`, `sandbox`, `llm`, `storage`)

### Changed

- `RLMEngine` accepts an `LLMClient` factory instead of a concrete client — dependency injection for analysis/shortcut and engine
- `AnalysisGenerator` narrowed to accept callables instead of concrete types
- Shortcut decision logic extracted from TUI into `query_with_shortcut()` in the domain layer, making it reusable by other frontends
- Repo ingestion extracted from the `Shesha` facade into dedicated methods
- `LLMError` now inherits from `SheshaError` for consistent exception hierarchy
- `IncrementalTraceWriter` enforces temporal coupling (steps must be added before finalization)
- `save_sha()` now preserves existing metadata keys instead of overwriting

### Fixed

- `FINAL_VAR` on `None`-valued variable now returns `None` instead of the string `'None'`
- `FINAL_VAR` for missing variables returns `None` instead of empty string
- `print(None)` output treated as unresolved in `_resolve_final_var`
- Bare-text `FINAL()` regex no longer truncates answers at nested parentheses on end-of-line
- Empty `FINAL()` and `FINAL(x)` followed by trailing commentary now handled correctly
- Code-block loop continues on failed `FINAL_VAR` lookup (with retry guidance) instead of returning empty answer
- `PermanentError` from `try_answer_from_analysis` and `classify_query` now propagated instead of swallowed
- Analysis context wrapped in untrusted boundary on RLM fallback path
- Guard against `None` `message.content` from LiteLLM API responses
- `RuntimeError` from `pool.stop()` during active query now caught in executor
- `RuntimeError` from `pool.acquire()` caught in executor recovery path
- Pool lock released during overflow container creation to prevent deadlock
- Pool assigned only after `pool.start()` succeeds; safe lifecycle ordering
- Thread-safety: `_meta_lock` added to metadata reads; `start_lock` added to `Shesha` to prevent duplicate pools
- Thread-safety: lock added to `_repo_meta.json` read-modify-write; bounded cache for `pending_updates`
- Trace marked as finalized even on suppressed write failure; `_finalized` flag set after successful write to allow retry
- Trace `metadata` field preserved in `Trace.redacted()` steps
- Subdirectory scope preserved when re-checking existing projects and during code explorer check/apply updates
- Subdirectory path persisted in `_repo_meta.json` to prevent data expansion on update
- `get_analysis_status` returns `stale` when SHA is unknown (instead of crashing)
- Return `unchanged` when `saved_sha` is `None` but `current_sha` is valid
- Return `check_failed` instead of `updates_available` on network failure
- Self-healing `apply-updates` when in-memory `pending_updates` cache is empty (e.g., after server restart)
- Staging project deleted after successful `swap_docs` to prevent orphan leak
- TOCTOU race eliminated in apply-updates self-heal path
- `RepoIngestError` caught in `check_updates` and `apply_updates` API endpoints
- Corrupt `_repo_meta.json` handled gracefully in metadata read/write
- Topic associations removed during batch upload rollback; batch upload rolls back all projects on partial failure
- Upload cleanup on document upload failure
- `NEED_DEEPER` sentinel detection uses `startswith` to handle trailing punctuation
- Emit trace step and callbacks on post-loop `FINAL_VAR` retry
- Preserve code-block `var_lookup_failed` over bare-text overwrite
- CORS credentials, static boundary fallback, and empty-string final var fixes
- `project_id` validated on code explorer API endpoints
- Forward slashes allowed in `_SAFE_ID_RE` for old-style arXiv IDs (e.g., `hep-ph/9901234`)
- Use `'user'` role in max-iterations fallback message
- Textarea and buttons aligned to same height (36px / h-9) with bottom alignment

### Security

- Restrict git transport protocols to `https` and `ssh` only — block `ext::` (RCE vector), `git://` (SSRF), and `file://` (local filesystem reads)
- Experimental servers bind to `127.0.0.1` by default instead of `0.0.0.0`
- 50 MB per-file and 200 MB aggregate upload size limits
- File extension validated before reading upload body and before writing to disk
- Internal filesystem paths sanitized from API error responses
- All exceptions caught in batch LLM subcalls to prevent information leakage
- `allow_local_paths` flag on `RepoIngester` defaults to `False`

## [0.20.0] - 2026-03-18

### Changed

- **RLMEngine.query() decomposed** — the ~515-line god method was split into four focused methods: `_execute_code_blocks()`, `_resolve_final_var()`, `_run_verifications()`, and a `_CodeBlockResult` dataclass
- Replaced private API access (`_storage`, `_rlm_engine`, etc.) with public properties across module boundaries; added API boundary rule to CLAUDE.md
- Extracted shared WebSocket `complete` response builder to reduce duplication across handlers
- Context budget magic numbers extracted to named constants
- All config fields now have environment variable mappings (`SHESHA_KEEP_RAW_FILES`, `SHESHA_CONTAINER_MEMORY_MB`, `SHESHA_EXECUTION_TIMEOUT_SEC`, `SHESHA_SANDBOX_IMAGE`, `SHESHA_MAX_OUTPUT_CHARS`, `SHESHA_VERIFY`)

### Removed

- Dead `TraceWriter.write_trace()` method
- Unused `sanitize_filename` utility

### Fixed

- LLM API calls now have a default timeout (300s initially, then reduced to 120s) — previously could hang indefinitely
- LLM call failures in executor subcall dispatch are now handled gracefully instead of crashing

## [0.19.0] - 2026-03-18

### Added

- **Background Knowledge Toggle** — "Allow background knowledge" checkbox in the TopicSidebar lets users opt-in to LLM answers that draw on training data beyond the loaded documents
  - New `system_augmented.md` prompt variant instructs the LLM to use background knowledge when enabled
  - Background knowledge sections in responses are rendered with a visually distinct tinted block and ARIA role
  - `splitAugmentedSections` utility parses background-knowledge markers from LLM output
  - `bottomControls` slot added to TopicSidebar for explorer-specific controls
  - Hint displayed below More button when background knowledge checkbox is off
- **Documents-only Notice** — when background knowledge was allowed but the LLM answered purely from documents, a notice is shown
- **Trace Download** — download button in TraceViewer downloads the raw JSONL trace file
  - New `/topics/{name}/traces/{id}/download` endpoint returns JSONL with `Content-Disposition` header
  - `downloadTrace()` method added to the shared API client
- `allow_background_knowledge` field persisted per exchange in session history

### Fixed

- WebSocket `drain_queue` now guards against a closed WebSocket and uses `finally` for cleanup

## [0.18.0] - 2026-03-18

### Added

- **More Button** for deeper analysis — a one-click "More" button in the shared ChatArea sends a predefined deeper-analysis prompt, with full accessibility support (ARIA attributes, keyboard activation, focus ring)
- Property-based tests for More button using fast-check
- Integration tests for More button across all three explorers
- Frontend TypeScript type-checking as a dedicated Makefile target

### Changed

- `useWebSocket.send()` now returns a boolean indicating success
- More button requires at least one prior exchange before becoming active
- Textarea draft is preserved when More button is used

### Fixed

- Redundant `onKeyDown` handler on More button that could cause double-fire
- Timestamp regex in tests now accepts both 12-hour and 24-hour locale formats

### Security

- Validate `document_ids` in WebSocket `_handle_query` using `_SAFE_ID_RE` and mask raw exception details in error messages

## [0.17.0] - 2026-03-16

### Added

- **`BaseTopicManager`** — generic base class for topic management with `add_item`, `remove_item`, `list_items`, `get_topic_dir` methods; document and code explorer topic managers are now thin subclasses

### Changed

- **Shared explorer dependencies** — `BaseExplorerState` dataclass and `create_app_state()` factory extracted into `shared/dependencies.py`
- **Shared item router** — `create_item_router()` factory generates unified topic CRUD and item-reference routes (`/api/topics/{name}/items`); URL paths changed from `/documents` and `/repos` to `/items`
- **Shared multi-project WebSocket handler** — `handle_multi_project_query()` extracted; explorer WS handlers are now thin wrappers
- Topic manager tests consolidated into a shared test module
- Dead `GET /topics/{name}/items` route removed from shared item router

### Fixed

- Slug collisions in topic creation now return 422 instead of 409
- Expanded topic documents reload when `refreshKey` changes, fixing stale sidebar after adding items
- `GET /topics/{name}/items` returns full objects (DocumentInfo/RepoInfo) instead of bare project ID strings

## [0.16.0] - 2026-03-06

### Added

- **Document Explorer** web application — upload documents (PDF, DOCX, PPTX, XLSX, RTF, and 30+ plain-text formats) into topics, then query them with the RLM engine via a chat interface
  - Text extraction pipeline with format-specific extractors (pdfplumber, python-docx, python-pptx, openpyxl, striprtf)
  - Multi-document cross-project queries via WebSocket
  - Document detail modal with metadata display
  - Consulted documents shown in answer footer
  - Upload drag-and-drop area with keyboard accessibility
  - Document context menu with View, Add to Topic, Remove from Topic, and Delete actions
  - Docker container and launch script
- **Shared HelpPanel component** — configurable slide-out panel with Quick Start, FAQ, and Keyboard Shortcuts sections; adopted by all three explorers
  - Help button added to the shared `Header` component
  - Close button has `aria-label` for accessibility
- **Shared launcher script** (`scripts/common.sh`) — preflight validation shared across all explorer launch scripts; includes `--rebuild` flag
  - BATS test suite for the shared launcher logic
- Bug report link icon added to shared header
- `/documents/{id}/topics` endpoint to list which topics contain a given document

### Changed

- Launcher scripts now validate Python >= 3.11 before proceeding
- `Shesha._extract_repo_name()` sanitizes output to match `_SAFE_ID_RE` pattern
- `project_id` hash suffix increased from 4 to 8 hex characters
- `TopicSidebar` shows document actions button whenever any action callback is provided
- Duplicate-named documents are prevented from being added to the same topic

### Fixed

- `stderr_filter` now handles `Traceback` lines and all exception types
- Corrupt `topic.json` files are recovered on `create()` instead of silently returning
- `_slugify` output normalized to ASCII
- Topic names containing path separators rejected to prevent directory traversal
- Upload endpoint returns 422 for invalid topic names before creating upload artifacts
- Topic rename endpoints return 422 for validation errors instead of 500
- `openpyxl` workbooks are explicitly closed to prevent file handle leaks
- Python GC traceback noise on Ctrl-C shutdown is suppressed
- Sidebar refreshes after document deletion
- `UploadArea` event handlers properly `await` `handleFiles`
- WebSocket handlers try all project IDs when resolving the RLM engine
- `get_topic_dir()` exposed as public API instead of using private `_resolve()`
- Context metadata built from actually loaded project IDs

### Security

- Document IDs validated against path traversal in REST and WebSocket handlers
- `dangerouslySetInnerHTML` removed from `HelpPanel` in the arxiv explorer (XSS risk)
- `aria-label` added to close buttons for accessibility

## [0.15.0] - 2026-03-05

### Added

- **Auto-growing textarea** in chat input — expands as users type up to ~4 lines, then scrolls internally
- **Per-topic chat history** for the code explorer — each topic now maintains its own conversation history and transcript
- User messages now render as Markdown in the shared `ChatMessage` component

### Changed

- Code explorer frontend loads history from per-topic endpoints instead of the global route
- Global `/api/history`, `/api/history` (DELETE), and `/api/export` routes removed from code explorer
- Header logo now has rounded corners

### Fixed

- Textarea auto-resize uses standard `scrollHeight` pattern instead of a brittle custom implementation

## [0.14.0] - 2026-02-28

### Added

- **Inline paper citations rendered as Markdown** — LLM answers in the arXiv explorer now render citation tags as clickable citation buttons via `react-markdown`
- Shared `citations.tsx` utility extracted from duplicated logic

### Fixed

- Citation buttons no longer trigger form submission

### Security

- Disallow `<img>` elements in Markdown rendering to prevent IP exfiltration via attacker-influenced image URLs

## [0.13.0] - 2026-02-18

### Added

- **`useAppState` hook** — extracted shared React state management into reusable hook for both arXiv and code explorers
- **Repo-to-topic assignment context menu** in code explorer sidebar — right-click documents to add/remove from topics
- **Boundary marker rendering** — leaked `UNTRUSTED_CONTENT` markers in LLM answers now rendered as labeled Markdown blockquotes instead of raw tokens
- File headers added to `FallbackTextParser` output and document names injected into RLM context metadata
- Callback parameters on `create_shared_router()` for tool-specific customization
- `include_topic_crud` flag on shared router

### Changed

- arXiv Explorer frontend and WebSocket adapter refactored to use standardized field names
- Both explorers refactored to use shared `useAppState` hook
- arXiv and code explorer wired to use shared router with callbacks
- Topic submenu rendered inline instead of as flyout

### Fixed

- Boundary marker regex uses backreference to ensure BEGIN and END tokens match
- urllib3 connection pools closed in Docker client
- Chat messages render as Markdown instead of plain text
- Check-for-updates now detects and applies repo changes correctly
- `document_ids` mapped to `paper_ids` in arXiv history endpoint

## [0.12.0] - 2026-02-17

### Added

- **Code Explorer** — web application for exploring code repositories with RLM-powered analysis
  - `shesha-code` CLI entry point (`--port`, `--data-dir`, `--no-browser`, `--model`)
  - REST API: repo management, topic-repo references, analysis generation, global history
  - WebSocket handler for cross-project queries with project ID scoping
  - `CodeExplorerTopicManager` — topics as lightweight reference containers
  - Repo detail component with inline analysis display
  - Add-repo modal for importing repositories
  - Docker deployment with Dockerfile, docker-compose.yml, and launch script
- **Shared experimental infrastructure** (`src/shesha/experimental/shared/`)
  - Generic FastAPI app factory with CORS, static files, WebSocket, and container pool lifespan
  - Shared Pydantic schemas, REST routes, WebSocket query handler, conversation session
  - Shared React frontend package with parameterized components (TopicSidebar, ChatArea, ChatMessage, Header, etc.)
  - Generic API client, TypeScript types, hooks
- Developer guide for extending web tools (`docs/extending-web-tools.md`)

### Changed

- arXiv Explorer backend and frontend refactored to use shared base classes and components
- `FINAL()` system prompt expanded with explicit formatting guidance
- Trace viewer renders step content as Markdown

### Fixed

- Stale project IDs handled gracefully in code explorer WebSocket handler
- Wildcard `*` query treated as empty
- Shared `AppShell` layout fixes arXiv horizontal scrollbar
- WebSocket dispatch loop consolidated, fixing query task race condition
- `FINAL()` arguments stripped of quotes and unescaped for proper Markdown rendering
- Session factory injected into shared WebSocket handler to fix history split-brain bug

## [0.11.0] - 2026-02-13

### Added

- **arXiv Explorer web interface** — React + TypeScript + Tailwind frontend with FastAPI backend
  - REST API for topics, papers, search, traces, history, export, model info, and context budget
  - WebSocket endpoint with async progress streaming for RLM queries
  - Persistent `WebConversationSession` with JSON file storage
  - Paper sidebar with collapsible lists, selection checkboxes, All/None toggle, paper detail view
  - Resizable sidebar with drag handle
  - KaTeX math rendering in paper abstracts and chat messages
  - Search panel with arXiv and local search
  - Trace viewer for inspecting RLM execution steps
  - Dark/light theme toggle; connection loss banner with auto-reconnect
  - `shesha-web` CLI command and `run-web.sh` launch script
- **Cascading citation verification** — multi-source verification pipeline
  - CrossRef, OpenAlex, and Semantic Scholar verifiers with rate limiting
  - Jaccard-based fuzzy title matching; LLM-based topical relevance checker
  - `CascadingVerifier` with per-citation WebSocket progress
  - Email modal for CrossRef polite pool
  - Citation report with source badges and severity levels
- **Inline paper citations** — chat answers render references as clickable links to paper detail views
- **Query cancellation** — `cancel_event` parameter on `RLMEngine.query()` allows mid-iteration interruption
- **Docker deployment** — Dockerfile, docker-compose.yml, and launch script
- `RateLimiter` utility, download progress modal, `consulted_papers` in query responses

### Changed

- Citation report redesigned with structured JSON, strict regex parsing, severity levels, and source badges
- `RLMEngine.query()` accepts optional `cancel_event: threading.Event` parameter
- TUI cancel button now triggers real query cancellation via `cancel_event`

### Fixed

- WebSocket handler catches query engine exceptions without leaking drain tasks
- `get_event_loop()` replaced with `get_running_loop()` (deprecation fix)
- HTML escaped in paper abstract/title before LaTeX rendering
- Local search reports all topics for multi-topic papers
- Cancel messages allowed during in-flight WebSocket queries
- Old-style arXiv IDs supported in citation rendering
- Papers persist across Docker container restarts

## [0.10.0] - 2026-02-12

### Added

- **arXiv Explorer** — experimental tool for searching, downloading, and analyzing arXiv papers organized into topics
  - Paper search with pagination and `--sort` flag
  - Paper download with LaTeX source-first strategy, falling back to PDF
  - Citation extraction from LaTeX/PDF sources with BibTeX parsing
  - Citation verification against arXiv API with per-citation progress indicator
  - LLM-tell detection — flags citations the LLM may have fabricated
  - Topic management backed by Shesha projects
  - Conversational queries against loaded papers using the RLM engine
- **arXiv Explorer TUI** — full Textual-based terminal interface
  - Commands: `/search`, `/more`, `/load`, `/papers`, `/topic`, `/history`, `/check-citations`
  - Command group system with subcommand dispatch and auto-generated help
  - Threaded command execution for long-running operations
- **Randomized untrusted content boundaries** — per-query 128-bit hex boundary tokens replace static XML tags for prompt injection defense
- Paper cache for local storage, `InfoBar.update_project_name()`, `TopicManager.rename()`, `shesha[arxiv]` optional dependency group

### Changed

- TUI `CommandRegistry` supports command groups with subcommand registration
- RLM engine boundary is now per-query instead of shared engine state

### Fixed

- `FINAL(variable_name)` now retries with variable lookup instead of returning the raw variable name
- LLM instructed to return natural-language/Markdown answers, not dicts or JSON
- `TopicManager` wrote `_topic.json` to the wrong directory
- `ArxivSearcher.close()` explicitly closes urllib3 connection pools
- Timeout added to `urlopen` calls in paper download
- Threading lock used for threaded command guard (race condition fix)
- eprint field normalized to strip `arXiv:` prefix in BibTeX extraction
- Topic delete uses equality check instead of substring match

### Security

- Randomized content boundaries replace static XML tags — papers cannot forge closing tags
- Directory traversal prevented in `store_source_files`

## [0.9.0] - 2026-02-10

### Changed

- Analysis shortcut classifier now includes few-shot examples and a "when in doubt, NEED_DEEPER" bias, reducing false ANALYSIS_OK classifications on terse or ambiguous queries (e.g. "SECURITY.md?", "I think that's out of date").
- Analysis shortcut LLM now responds NEED_DEEPER when the analysis lacks information instead of answering with "the analysis does not mention X". Absence from the analysis no longer produces misleading non-answers.

### Removed

- Fast/deep execution mode toggle (`/fast`, `/deep` commands, `execution_mode` parameter, `--fast` CLI flag). Batch sub-LLM calls now always run concurrently. The sequential "deep" mode offered no quality benefit over concurrent execution.

### Fixed

- Analysis shortcut answers now display token usage in the TUI info bar. Previously, the shortcut discarded token counts from the LLM response, leaving the info bar showing `Tokens: 0 (prompt: 0, comp: 0)`.
- Analysis shortcut answers now display `[Thought for N seconds]` above the response, matching the normal query route. Previously, shortcut answers skipped the thought-time indicator entirely.
- Bare `FINAL(variable_name)` in LLM response now correctly resolves the variable from the sandbox instead of returning the variable name as a literal string. Previously, if the LLM wrote `FINAL(final_answer)` as bare text (outside a code block) intending to return a variable's value, the answer displayed was the literal string "final_answer" instead of the variable's content.
- `FINAL(identifier)` variable resolution now falls back to the literal identifier when the variable is undefined in the sandbox, instead of returning an empty answer.
- Bare `FINAL(variable)` in the same response as code blocks that define the variable now works correctly. Previously, the bare FINAL check fired before code blocks executed, so the variable didn't exist yet and the user saw the literal variable name (e.g. "my_answer") instead of the actual answer.
- Analysis shortcut session transcript now includes token counts, matching the normal query path. Previously, `/write` transcripts omitted token usage for shortcut-answered questions.
- `/write` command now warns before overwriting existing files (including case-insensitive collisions on macOS). Use `/write filename!` to force overwrite.

## [0.8.0] - 2026-02-10

### Added

- Analysis shortcut: questions answerable from the pre-computed codebase analysis are now answered directly via a single LLM call, skipping the full RLM pipeline (Docker sandbox, code execution, sub-LLM calls). Falls through to the full query automatically when deeper investigation is needed.
- Fast/deep execution modes for `llm_query_batched`: fast (default) runs concurrent via thread pool, deep runs sequential for cross-chunk knowledge building
- `execution_mode` parameter on `ContainerExecutor`, `RLMEngine`, and `Project`
- `/fast`, `/deep`, and `/clear` TUI commands in repo explorer
- `--model` CLI flag for example scripts (`repo.py`, `barsoom.py`); overrides `SHESHA_MODEL` env var
- Model name display in TUI info bar (date suffix stripped for readability)
- `OutputArea.clear()` method for resetting conversation display
- Mode indicator (`Mode: Fast` / `Mode: Deep`) in TUI info bar

### Changed

- Switched container-host protocol from newline-delimited JSON to 4-byte length-prefix framing; removes 1MB message size limit that caused executor crashes on large `llm_query()` payloads
- Iteration feedback now sends per-code-block messages with code echo (matching reference RLM)
- Per-iteration continuation prompt re-instructs model to use sub-LLMs via `iteration_continue.md`
- Replaced inline reminder string with external prompt template

## [0.7.0] - 2026-02-09

### Added

- Strict type validation (`__post_init__`) on `AnalysisComponent`, `AnalysisExternalDep`, and `RepoAnalysis` dataclasses — bad-typed fields now raise `TypeError` at construction time
- `coerce_to_str()` and `coerce_to_str_list()` helpers in `models.py` for safe type coercion at storage/generation boundaries

### Fixed

- `load_analysis()` and `AnalysisGenerator.generate()` now coerce all validated string fields (scalars via `coerce_to_str()`, lists via `coerce_to_str_list()`) before constructing analysis models, preventing `TypeError` crashes from LLM-generated or stored data
- `_send_raw()` now wraps `OSError`/`TimeoutError` from socket `sendall()` as `ProtocolError` and restores the previous socket timeout after each send
- Fixed mutable closure in RLM engine where `llm_query` callback captured loop variable by reference
- Repo ingestion is now atomic: updates use stage-then-swap to prevent mixed state on failure, new project creation cleans up on failure
- Successful repo updates now remove orphaned documents that no longer exist in the repository

### Security

- Added tmpfs mounts to container security config (default `/tmp` with 64MB limit, noexec)
- Added send timeout and payload size limit (50 MB) to container executor protocol
- Tied read deadline to execution timeout to prevent slow-drip DoS via long MAX_READ_DURATION gap
- Sandbox runner now exits on invalid JSON input (fail-closed) instead of continuing
- Added timeouts to all git subprocess calls to prevent indefinite hangs
- Added `GIT_TERMINAL_PROMPT=0` to non-token git operations to prevent interactive prompts
- Fixed `get_remote_sha()` to use authentication token when provided

## [0.6.0] - 2026-02-08

### Added

- Interactive TUI (Text User Interface) for `barsoom.py` and `repo.py` examples, inspired by Claude Code's interface. Features: 3-pane layout (scrolling output, live info bar, input area), markdown rendering toggle, slash commands with auto-complete, input history, dark/light theme toggle, real-time progress display replacing `--verbose` flag. Install with `pip install shesha[tui]`.

### Changed

- Renamed `/analysis` command to `/summary` in `repo.py` to avoid confusion with `/analyze`
- `/summary` output now renders as markdown when markdown mode is enabled
- Tab key toggles focus between output area and input area, with border highlight showing active pane
- Example commands now require `/` prefix (e.g., `/help`, `/write`, `/quit`) instead of bare words
- `--verbose` flag removed from `barsoom.py` and `repo.py` (info bar shows progress by default)

### Removed

- Interactive loop helper functions from `script_utils.py` (history formatting, command parsing, session writing -- absorbed into TUI modules)

## [0.5.0] - 2026-02-08

### Added

- Semantic verification (`--verify` flag): opt-in post-analysis adversarial review that checks whether findings are supported by evidence. For code projects, adds code-specific checks for comment-mining, test/production conflation, and language idiom misidentification. Output reformatted into verified summary + appendix. Note: significantly increases analysis time and token cost (1-2 additional LLM calls)
- Post-FINAL citation verification: after `FINAL()`, the engine mechanically checks that cited doc IDs exist in the corpus and that quoted strings actually appear in the cited documents. Results are available via `QueryResult.verification`. Zero LLM cost, fail-safe (verification errors don't affect answer delivery)
- `verify_citations` config option (default `True`, env var `SHESHA_VERIFY_CITATIONS`) to enable/disable citation verification
- `ContainerExecutor.is_alive` property to check whether executor has an active socket connection

### Changed

- `llm_query()` in sandbox now raises `ValueError` when content exceeds the sub-LLM size limit, preventing error messages from being silently captured as return values and passed to `FINAL()`

### Fixed

- RLM engine now recovers from dead executors mid-loop when a container pool is available, acquiring a fresh executor instead of wasting remaining iterations
- RLM engine exits early with a clear error when executor dies and no pool is available, instead of running all remaining iterations against a dead executor
- Oversized `llm_query()` calls no longer produce error strings that get passed to `FINAL()` as the answer; they now raise exceptions so the LLM can retry with chunked content

## [0.4.0] - 2026-02-06

### Added

- `TraceWriteError` and `EngineNotConfiguredError` exception classes
- `suppress_errors` parameter on `TraceWriter` and `IncrementalTraceWriter` for opt-in error suppression
- Sandbox namespace `reset` action to clear state between queries
- Experimental multi-repo PRD analysis (`shesha.experimental.multi_repo`)
  - `MultiRepoAnalyzer` for analyzing how PRDs impact multiple codebases
  - Four-phase workflow: recon, impact, synthesize, align
  - Example script `examples/multi_repo.py`
- `examples/multi_repo.py`: `--prd <path>` argument to read PRD from file
- `examples/multi_repo.py`: interactive repo picker with all-then-deselect across both storage locations
- External prompt files in `prompts/` directory for easier customization
- `python -m shesha.prompts` CLI tool for validating prompt files
- Support for alternate prompt directories via `SHESHA_PROMPTS_DIR` environment variable
- `prompts/README.md` documenting prompt customization
- Session write command (`write` or `write <filename>`) in example scripts (`repo.py`, `barsoom.py`) to save conversation transcripts as markdown files

### Changed

- `Shesha.__init__` now accepts optional DI parameters (`storage`, `engine`, `parser_registry`, `repo_ingester`) for testability and extensibility; defaults are backward-compatible
- `Shesha()` no longer requires Docker at construction time; Docker check and container pool creation are deferred to `start()`, enabling ingest-only workflows without a Docker daemon
- `Shesha.get_project`, `get_project_info`, `get_analysis_status`, `get_analysis`, `generate_analysis`, `check_repo_for_updates` now raise `ProjectNotFoundError` instead of `ValueError`
- `Shesha.check_repo_for_updates` raises `RepoError` instead of `ValueError` when no repo URL is stored
- `Shesha._ingest_repo` now catches only `ParseError`/`NoParserError` (expected) and propagates unexpected errors as `RepoIngestError`
- `Project.query()` raises `EngineNotConfiguredError` instead of `RuntimeError`
- `TraceWriter` and `IncrementalTraceWriter` raise `TraceWriteError` by default on failure instead of silently returning `None`
- Engine passes `suppress_errors=True` to trace writers for best-effort tracing during queries
- `TraceWriter` and `IncrementalTraceWriter` now accept `StorageBackend` protocol instead of `FilesystemStorage`
- `RLMEngine.query()` accepts `StorageBackend` protocol instead of `FilesystemStorage`
- `Project.query()` always passes storage to engine (removed `FilesystemStorage` special-casing)
- `Shesha.__init__` now uses `SheshaConfig.load()` by default, honoring env vars and config files
- `RLMEngine` now respects `max_traces_per_project` config setting for trace cleanup (previously hardcoded to 50)

### Fixed

- `Project.upload()` with directories now uses relative paths for document names, preventing silent overwrites when files in different subdirectories share the same basename (e.g., `src/foo/main.py` and `src/bar/main.py`)
- RLM engine now uses the container pool for queries instead of creating throwaway containers, eliminating cold-start overhead and idle resource waste
- Pool-backed executor cleanup no longer masks query results or leaks executors when `reset_namespace()` fails (e.g., after a protocol error closes the socket)
- `ContainerPool.acquire()` now raises `RuntimeError` when pool is stopped, preventing container creation after shutdown
- `Shesha.start()` is now idempotent — calling it twice no longer leaks orphaned container pools
- Local repo paths (`./foo`, `../bar`) are now resolved to absolute paths before saving, preventing breakage when working directory changes between sessions

### Removed

- Removed unused `allowed_hosts` config field (containers have networking disabled; all LLM calls go through the host)

### Security

- `is_local_path` no longer uses `Path(url).exists()`; uses prefix-only matching to prevent misclassification
- Git clone tokens are now passed via `GIT_ASKPASS` instead of being embedded in the clone URL, preventing exposure in process argument lists
- Enforce `<untrusted_document_content>` wrapping in code (`wrap_subcall_content()`), not just in prompt template files, closing a prompt injection defense gap for sub-LLM calls
- Validate that `subcall.md` template contains required security tags at load time

## [0.3.0] - 2026-02-04

### Fixed

- Host memory exhaustion via unbounded container output buffering
- Execution hanging indefinitely when container drips output without newlines
- Oversized JSON messages from container causing memory/CPU spike
- Path traversal in repository ingestion when project_id contains path separators
- Path traversal in raw file storage when document name contains path separators

### Security

- Added protocol limits for container communication (max buffer 10MB, max line 1MB, deadline 5min)
- Applied `safe_path()` consistently to all filesystem operations in repo ingestion and storage

## [0.2.0] - 2026-02-04

### Added

- `Shesha.check_repo_for_updates()` method to check if a cloned repository has updates available
- `RepoIngester.get_repo_url()` method to retrieve the remote origin URL from a cloned repo
- `ProjectInfo` dataclass for project metadata (source URL, is_local, source_exists)
- `Shesha.get_project_info()` method to retrieve project source information
- Repo picker now shows "(missing - /path)" for local repos that no longer exist
- Repo picker supports `d<N>` command to delete projects with confirmation

### Changed

- `Shesha.delete_project()` now accepts `cleanup_repo` parameter (default `True`) to also remove cloned repository data for remote repos

### Fixed

- `--update` flag in `examples/repo.py` now works when selecting an existing project from the picker

## [0.1.0] - 2026-02-03

### Added

- Initial release of Shesha RLM library
- Core RLM loop with configurable max iterations
- Docker sandbox for secure code execution
- Document loading for PDF, DOCX, HTML, and text files
- Sub-LLM queries via `llm_query()` function
- Project-based document organization
- LiteLLM integration for multiple LLM providers
- Trace recording for debugging and analysis
- Security hardening with untrusted content tagging
- Network isolation with egress whitelist for LLM APIs

[unreleased]: https://github.com/Ovid/ananta/compare/v0.24.0...HEAD
[0.24.0]: https://github.com/Ovid/ananta/compare/v0.23.0...v0.24.0
[0.23.0]: https://github.com/Ovid/ananta/compare/v0.22.0...v0.23.0
[0.21.1]: https://github.com/Ovid/ananta/compare/v0.21.0...v0.21.1
[0.21.0]: https://github.com/Ovid/ananta/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/Ovid/ananta/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/Ovid/ananta/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/Ovid/ananta/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/Ovid/ananta/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/Ovid/ananta/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/Ovid/ananta/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/Ovid/ananta/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/Ovid/ananta/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/Ovid/ananta/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/Ovid/ananta/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/Ovid/ananta/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/Ovid/ananta/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Ovid/ananta/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Ovid/ananta/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Ovid/ananta/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Ovid/ananta/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Ovid/ananta/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Ovid/ananta/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Ovid/ananta/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Ovid/ananta/releases/tag/v0.1.0
