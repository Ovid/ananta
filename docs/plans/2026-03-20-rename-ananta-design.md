# Rename Shesha → Ananta — Design

## Motivation

"Shesha" sounds like "shisha" (hookah/waterpipe), which some interpret as a drug reference. Renaming to "Ananta" — an alternate name for the same Hindu serpent deity — eliminates this confusion while preserving the mythological connection.

This is a clean break with no backwards-compatibility shims. Version becomes 1.0.0.

## Scope

### Python Package

- Directory: `src/shesha/` → `src/ananta/`
- Main class: `Shesha` → `Ananta`
- Config class: `SheshaConfig` → `AnantaConfig`
- TUI class: `SheshaTUI` → `AnantaTUI`
- Module file: `shesha.py` → `ananta.py`
- Exceptions: `SheshaError` → `AnantaError`
- Constants: `SHESHA_TEAL` → `ANANTA_TEAL`
- App state attribute: `state.shesha` → `state.ananta`
- All imports throughout `src/` and `tests/`
- Test files: `test_shesha.py` → `test_ananta.py`, `test_shesha_di.py` → `test_ananta_di.py`

### Configuration

- `pyproject.toml`: package name, entry points, build paths
- `.env` file: update variable names
- `Makefile`: update `src/shesha/` paths
- All `SHESHA_*` environment variables → `ANANTA_*` (14 total: `API_KEY`, `MODEL`, `STORAGE_PATH`, `POOL_SIZE`, `CONTAINER_MEMORY_MB`, `EXECUTION_TIMEOUT_SEC`, `SANDBOX_IMAGE`, `MAX_ITERATIONS`, `MAX_OUTPUT_CHARS`, `VERIFY_CITATIONS`, `VERIFY`, `MAX_TRACES_PER_PROJECT`, `KEEP_RAW_FILES`, `PROMPTS_DIR`)

### CLI Entry Points

- `shesha-web` → `ananta-web`
- `shesha-code` → `ananta-code`
- `shesha-document-explorer` → `ananta-document-explorer`

### Data & User Home Directories

- `shesha_data/` → `ananta_data/`
- `~/.shesha-arxiv/` → `~/.ananta-arxiv/`
- `~/.shesha/<app_name>/` → `~/.ananta/<app_name>/`
- Startup check for each: detect old directory and print migration message telling users to rename it

### Shell Scripts & Docker

- Launcher scripts: APP_NAME, APP_SLUG, marker files, log prefixes
- Dockerfiles: ENTRYPOINT commands
- docker-compose.yml: service names, environment variables
- Sandbox Docker image: `shesha-sandbox` → `ananta-sandbox`

### Frontend

- `@shesha/` scoped packages → `@ananta/`
- package.json files updated
- localStorage keys: `shesha-*` → `ananta-*` (`theme`, `welcome-dismissed`, `polite-email`, `email-skipped`)
- Static asset path: `/static/shesha.png` → `/static/ananta.png`
- UI copy/text mentioning "Shesha" (e.g., FAQ in App.tsx)

### Examples

- All files in `examples/` updated: imports, class references, env var references

### Documentation

- README.md: title, logo (`images/ananta.png`), examples, "Who is Ananta?" section
- CHANGELOG.md: new `[1.0.0]` section documenting the rename (fold [Unreleased] content into it)
- CLAUDE.md: project description, paths
- SECURITY.md: project name, class references
- HANDOFF.md: delete (should never have been committed)
- docs/ENVIRONMENT.md, DEVELOPMENT.md, OVERVIEW.md, extending-web-tools.md: references
- arxiv-explorer/README.md, code-explorer/README.md: explorer documentation
- prompts/README.md: env var references, `python -m shesha.prompts` → `python -m ananta.prompts`
- .github/copilot-instructions.md: references

### oolong (research)

- Python imports and env var references in runnable scripts: updated so they work
- Research prose and analysis notes: left as-is (historical)

### NOT Renamed

- Git history (commits referencing "shesha" are historical)
- Historical plan doc filenames in `docs/plans/`
- Architecture report filenames in `paad/`
- Build artifacts (`.venv/`, `.mypy_cache/`, `htmlcov/` — regenerated)
- Research prose in `oolong/` (only runnable code updated)
- The repo directory itself on disk
- GitHub repository URL (to be handled separately later)

## Version

1.0.0, set via git tag. hatch-vcs derives the version from tags.
