# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Code Explorer web application for exploring git repositories via RLM
- Shared web infrastructure module (`shesha.experimental.shared`) for building experimental tools
- Developer guide for extending the web tool ecosystem (`docs/extending-web-tools.md`)
- **Code Explorer CLI entry point** — `shesha-code` command launches the code explorer web server with `--port`, `--data-dir`, `--model`, and `--no-browser` options
- **Code Explorer module skeleton** — new `shesha.experimental.code_explorer` module with `CodeExplorerTopicManager` for lightweight repo grouping, `CodeExplorerState` dataclass and `create_app_state()` factory, and `__main__.py` CLI entry point stub
- **Code Explorer WebSocket handler** — cross-project query handler that loads documents from multiple repos, merges per-project analysis as context, and records consulted project_ids in the global session
- **Multi-source citation verification** — citations are now verified against CrossRef, OpenAlex, and Semantic Scholar in addition to arXiv, dramatically reducing false "unresolved" results for non-arXiv sources
- **Fuzzy title matching** — Jaccard similarity with LLM fallback for ambiguous cases (0.50-0.85 range) reduces false positives from title changes between paper versions
- **Topical relevance checking** — LLM-based batch check flags citations that exist but are clearly unrelated to the citing paper
- **Source badges** — citation report shows where each citation was verified (arXiv, CrossRef, OpenAlex, S2)
- **Email modal for polite-pool access** — optional email stored in browser localStorage gives faster API access to CrossRef and OpenAlex
- **Inline paper citations** — LLM responses in arXiv Explorer now cite papers by arxiv ID with clickable links that open the paper detail view
- **Shared ChatArea and ChatMessage components** — extracted parameterized versions to shared-ui package with `selectedDocuments`/`document_ids` naming, optional `renderAnswer` and `renderAnswerFooter` props for domain-specific customization
- **Shared TopicSidebar component** — extracted parameterized TopicSidebar to shared-ui package with `loadDocuments`/`DocumentItem` abstraction, cross-topic selection scoping (All/None buttons only affect current topic), optional uncategorized docs section, and configurable add button
- **Repo-to-topic context menu** — document rows in the Code Explorer sidebar now have an ellipsis menu to add repos to topics or remove them, enabling multi-topic assignment without re-adding
- **Boundary marker rendering** — UNTRUSTED_CONTENT boundary markers that leak into RLM answers are now displayed as labeled blockquotes instead of raw tokens
- **RLM context metadata** — document names are now included in context metadata so the RLM can reference files by name
- **FallbackTextParser file headers** — non-code documents now include `=== FILE: name ===` headers matching CodeParser format, helping the RLM identify document boundaries

### Changed

- Code Explorer API routes for traces, model, history, and context-budget now use shared router with callbacks
- arXiv Explorer refactored to use shared web infrastructure module
- "unresolved" citations now labeled "not found in databases" to clarify external sources were tried
- LLM-tell phrases displayed in purple (was amber) for better visual distinction
- Papers default to selected when clicking a topic name

### Fixed

- Papers not auto-selected when clicking a topic (required expanding the paper list first)

---

_Previous entries:_

### Added

- **Web citation checking** — citation verification now works in the web interface (Check Citations toolbar button), reusing the same extraction and arXiv verification logic as the TUI `/check` command
- **Consulted papers display** — query answers now show which papers were used, with clickable links to paper detail view
- **Document-only constraint** — system prompt now explicitly forbids the LLM from using training data, requiring answers based solely on provided documents
- **Trace document IDs** — trace viewer summary shows which documents were included in each query
- **Experimental web interface** for arXiv Explorer (`shesha-web` command)
  - React frontend with dark/light theme
  - FastAPI backend with REST API and WebSocket
  - Topic management (create, rename, delete, switch)
  - arXiv search with multi-topic paper picker
  - Local paper search across all topics
  - Query execution with live progress streaming
  - Trace viewer with expandable step timeline
  - Citation checking with streamed progress
  - Context budget indicator (warns at 50% and 80%)
  - Conversation history persisted per topic
  - Markdown transcript export
  - In-app help system
- Real query cancellation via `threading.Event` in RLM engine
- `ARXIV.md` setup guide for researchers

### Changed

- **Web interface: paper sidebar redesign** — papers moved from top chip bar into collapsible lists under each topic in the sidebar, showing titles instead of arXiv IDs
- Web interface: clicking a paper title opens full detail view (abstract, authors, metadata) in the main content area
- Web interface: paper selection checkboxes with All/None toggle to scope queries to specific papers
- TUI cancellation now uses real `cancel_event` instead of cosmetic query-ID bump

### Added

- arXiv Explorer example (`examples/arxiv_explorer.py`) — interactive CLI for searching arXiv,
  loading papers into topics, and querying them with Shesha. Features:
  - `/search` with author, category, and keyword filtering
  - `/load` papers by search result number or arXiv ID (source first, PDF fallback)
  - `/check-citations` for automated citation verification against arXiv API with
    LLM-tell phrase detection (always shown with AI disclaimer)
  - `/history` for persistent topic management with creation dates and size on disk
  - Central paper cache to avoid redundant downloads

### Security

- Replace static `<untrusted_document_content>` XML tags with per-query randomized boundary tokens (128-bit entropy) to prevent tag-escape prompt injection attacks
- Restore REPL output wrapping removed in 937c183
- Add wrapping to initial document context shown to the LLM
- All five document-to-LLM paths now have untrusted content boundaries

### Changed

- arXiv Explorer now uses a Textual TUI instead of a readline-based REPL. All
  commands (`/search`, `/load`, `/papers`, `/topic`, `/history`, `/check-citations`,
  `/more`) are registered as TUI commands with auto-complete, markdown rendering,
  and threaded execution for network operations. Topic management updates the
  InfoBar in real time. Conversational queries are guarded against missing
  topic/papers.

## [0.9.0] - 2026-02-10

### Changed

- Analysis shortcut classifier now includes few-shot examples and a "when in doubt, NEED_DEEPER" bias, reducing false ANALYSIS_OK classifications on terse or ambiguous queries (e.g. "SECURITY.md?", "I think that's out of date").
- Analysis shortcut LLM now responds NEED_DEEPER when the analysis lacks information instead of answering with "the analysis does not mention X". Absence from the analysis no longer produces misleading non-answers.

### Fixed

- Analysis shortcut answers now display token usage in the TUI info bar. Previously, the shortcut discarded token counts from the LLM response, leaving the info bar showing `Tokens: 0 (prompt: 0, comp: 0)`.
- Analysis shortcut answers now display `[Thought for N seconds]` above the response, matching the normal query route. Previously, shortcut answers skipped the thought-time indicator entirely.
- Bare `FINAL(variable_name)` in LLM response now correctly resolves the variable from the sandbox instead of returning the variable name as a literal string. Previously, if the LLM wrote `FINAL(final_answer)` as bare text (outside a code block) intending to return a variable's value, the answer displayed was the literal string "final_answer" instead of the variable's content.
- `FINAL(identifier)` variable resolution now falls back to the literal identifier when the variable is undefined in the sandbox, instead of returning an empty answer.
- Bare `FINAL(variable)` in the same response as code blocks that define the variable now works correctly. Previously, the bare FINAL check fired before code blocks executed, so the variable didn't exist yet and the user saw the literal variable name (e.g. "my_answer") instead of the actual answer.
- Analysis shortcut session transcript now includes token counts, matching the normal query path. Previously, `/write` transcripts omitted token usage for shortcut-answered questions.
- `/write` command now warns before overwriting existing files (including case-insensitive collisions on macOS). Use `/write filename!` to force overwrite.

### Removed

- Fast/deep execution mode toggle (`/fast`, `/deep` commands, `execution_mode` parameter, `--fast` CLI flag). Batch sub-LLM calls now always run concurrently. The sequential "deep" mode offered no quality benefit over concurrent execution.

## [0.8.0] - 2026-02-10

### Changed

- Switched container-host protocol from newline-delimited JSON to 4-byte length-prefix framing; removes 1MB message size limit that caused executor crashes on large `llm_query()` payloads
- Iteration feedback now sends per-code-block messages with code echo (matching reference RLM)
- Per-iteration continuation prompt re-instructs model to use sub-LLMs via `iteration_continue.md`
- Replaced inline reminder string with external prompt template

### Added

- Analysis shortcut: questions answerable from the pre-computed codebase analysis are now answered directly via a single LLM call, skipping the full RLM pipeline (Docker sandbox, code execution, sub-LLM calls). Falls through to the full query automatically when deeper investigation is needed.
- Fast/deep execution modes for `llm_query_batched`: fast (default) runs concurrent via thread pool, deep runs sequential for cross-chunk knowledge building
- `execution_mode` parameter on `ContainerExecutor`, `RLMEngine`, and `Project`
- `/fast`, `/deep`, and `/clear` TUI commands in repo explorer
- `--model` CLI flag for example scripts (`repo.py`, `barsoom.py`); overrides `SHESHA_MODEL` env var
- Model name display in TUI info bar (date suffix stripped for readability)
- `OutputArea.clear()` method for resetting conversation display
- Mode indicator (`Mode: Fast` / `Mode: Deep`) in TUI info bar

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

## [0.3.0] 2026-02-04

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
