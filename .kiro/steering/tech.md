---
inclusion: always
---

# Tech Stack

- Language: Python 3.11+ (strict mypy, ruff linting)
- Build system: Hatchling with hatch-vcs (version from git tags)
- Package config: `pyproject.toml` (no setup.py/setup.cfg)
- Virtual env: `python -m venv .venv` or uv
- Dependency lock: `uv.lock`

## Key Dependencies

- litellm: LLM provider abstraction (100+ providers)
- docker: Container management for sandboxed code execution
- pdfplumber, python-docx, beautifulsoup4: Document parsing
- pyyaml: Configuration
- chardet: Encoding detection
- textual: TUI framework (optional, `[tui]`)
- fastapi + uvicorn: Web UI backend (optional, `[web]`)
- httpx: HTTP client for API calls (optional, `[web]`)
- websockets: Real-time WebSocket communication (optional, `[web]`)
- python-multipart: File upload handling (optional, `[document-explorer]`)
- python-pptx, openpyxl, striprtf: Office format parsing (optional, `[document-explorer]`)
- arxiv, bibtexparser: arXiv paper retrieval (optional, `[arxiv]`)
- datasets, pandas, tqdm, matplotlib: Benchmarking/evaluation (dev only)
- pytest, pytest-asyncio, pytest-cov: Testing
- ruff: Linting and formatting
- mypy: Static type checking (strict mode)

## Entry Points

```bash
shesha-web                       # arXiv paper explorer web UI
shesha-code                      # Code explorer
shesha-document-explorer         # Document explorer
```

## Optional Dependency Groups

- `[tui]` — Terminal UI
- `[arxiv]` — arXiv paper retrieval
- `[web]` — Web UI (includes arxiv)
- `[document-explorer]` — Document explorer (includes web)
- `[dev]` — All of the above plus testing/linting tools

## Common Commands

```bash
source .venv/bin/activate        # Always activate venv first
pip install -e ".[dev]"          # Install with dev deps
make all                         # Format + lint + typecheck + test + test-frontend
pytest                           # Run all tests
pytest tests/path::test_name -v  # Single test
pytest --cov=src/shesha          # Tests with coverage
mypy src/shesha                  # Type check (strict)
ruff check src tests             # Lint
ruff format src tests            # Format
make cover                       # Coverage with HTML report
```

## Ruff Config

- Line length: 100
- Target: py311
- Rules: E, F, I, N, W, UP
- `src/shesha/rlm/prompts.py` is exempt from E501 (long prompt strings)
- `src/shesha/_version.py` is excluded (auto-generated)

## Mypy Config

- Strict mode enabled
- `warn_return_any` and `warn_unused_ignores` enabled
- Some third-party modules have `ignore_missing_imports` (arxiv, uvicorn, openpyxl, striprtf)

## Pytest Config

- Test paths: `tests/`
- Python path includes project root
- asyncio_mode: auto
- litellm deprecation warnings are filtered

## Docker

The sandbox container (`shesha-sandbox`) is required for code execution:
```bash
docker build -t shesha-sandbox -f src/shesha/sandbox/Dockerfile src/shesha/sandbox/
```

## Versioning

Versions are derived from git tags via `hatch-vcs`. No manual version bumps. Tag format: `vX.Y.Z`.
