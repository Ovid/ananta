---
inclusion: always
---

# Project Structure

```
src/ananta/                      # Main package
├── ananta.py                    # Main Ananta class (entry point)
├── project.py                   # Project class (document collections)
├── config.py                    # AnantaConfig
├── models.py                    # ParsedDocument and data models
├── exceptions.py                # Exception hierarchy
├── __init__.py                  # Public API exports
├── rlm/                         # RLM engine (core loop)
│   ├── engine.py                # Core iteration loop
│   ├── prompts.py               # Hardened system prompts
│   ├── trace.py                 # Execution tracing
│   ├── trace_writer.py          # Trace output
│   ├── boundary.py              # Security boundaries
│   ├── verification.py          # Answer verification
│   └── semantic_verification.py # Semantic answer checks
├── sandbox/                     # Docker-based code execution
│   ├── executor.py              # Host-side container management
│   ├── pool.py                  # Container pool (3 warm containers)
│   ├── runner.py                # Runs inside container
│   └── Dockerfile
├── storage/                     # Document storage backends
│   ├── base.py                  # Abstract storage interface
│   └── filesystem.py            # Filesystem implementation
├── parser/                      # Document parsers
│   ├── registry.py              # Parser registry (by extension)
│   ├── base.py                  # Abstract parser
│   ├── text.py, pdf.py, html.py # Format-specific parsers
│   ├── code.py                  # Code file parser
│   ├── office.py                # DOCX/PPTX/XLSX
│   └── fallback.py              # Fallback parser
├── llm/                         # LLM client layer
│   ├── client.py                # LiteLLM wrapper
│   ├── retry.py                 # Retry logic
│   └── exceptions.py            # LLM-specific exceptions
├── repo/                        # Git repository ingestion
│   └── ingester.py              # Clone, parse, ingest repos
├── security/                    # Security utilities
│   ├── containers.py            # Container security
│   ├── paths.py                 # Path validation
│   └── redaction.py             # Content redaction
├── analysis/                    # Analysis shortcuts
│   ├── generator.py             # Analysis generation
│   └── shortcut.py              # Quick analysis paths
├── prompts/                     # Prompt management
│   ├── __main__.py              # CLI entry point
│   ├── loader.py                # Load prompt templates
│   └── validator.py             # Prompt validation
├── tui/                         # Terminal UI (Textual)
│   ├── app.py                   # Main TUI app
│   ├── commands.py              # Command handling
│   ├── session.py, history.py   # Session management
│   ├── progress.py              # Progress display
│   └── widgets/                 # Custom widgets
│       ├── completion_popup.py  # Autocomplete popup
│       ├── info_bar.py          # Status/info bar
│       ├── input_area.py        # Query input
│       └── output_area.py       # Response display
└── explorers/                   # Web explorer applications
    ├── shared_ui/               # Common explorer framework
    │   ├── app_factory.py       # FastAPI app builder
    │   ├── dependencies.py      # Shared DI
    │   ├── routes.py            # Shared API routes
    │   ├── schemas.py           # Shared request/response models
    │   ├── session.py           # Session management
    │   ├── topics.py            # Topic management
    │   └── websockets.py        # WebSocket infrastructure
    ├── arxiv/                   # arXiv paper explorer
    │   ├── cache.py, download.py, search.py  # Paper retrieval
    │   ├── citations.py         # Citation handling
    │   ├── models.py            # Data models
    │   ├── rate_limit.py        # API rate limiting
    │   ├── relevance.py         # Relevance scoring
    │   ├── topics.py            # Topic management
    │   └── verifiers.py         # Result verification
    ├── arxiv_web/               # arXiv web UI (FastAPI backend)
    │   ├── api.py, dependencies.py, schemas.py
    │   ├── session.py, websockets.py
    │   └── frontend/            # React frontend
    ├── code_explorer/           # Code exploration tool
    │   ├── api.py, dependencies.py, schemas.py
    │   ├── topics.py, websockets.py
    │   └── frontend/            # React frontend
    └── document_explorer/       # Document exploration tool
        ├── api.py, dependencies.py, schemas.py
        ├── extractors.py        # Document content extraction
        ├── topics.py, websockets.py
        └── frontend/            # React frontend

tests/                           # Test suite
├── unit/                        # Unit tests (mirrors src/ananta/ structure)
├── integration/                 # Integration tests
├── examples/                    # Example script tests
├── explorers/                   # Explorer feature tests
├── scripts/                     # Script tests
└── fixtures/                    # Test data files

examples/                        # Example scripts (barsoom.py, repo.py)
prompts/                         # Prompt template files
docs/                            # Documentation
```

## Conventions

- Source code lives in `src/ananta/` (src layout)
- Unit tests mirror the source structure under `tests/unit/`
- Explorer applications go in `src/ananta/explorers/` — they have their own optional dependency groups
- All imports at top of file (comment if exception needed)
- Public API is exported from `src/ananta/__init__.py`
