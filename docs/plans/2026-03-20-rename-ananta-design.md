# Rename Shesha → Ananta — Design

## Motivation

"Shesha" sounds like "shisha" (hookah/waterpipe), which some interpret as a drug reference. Renaming to "Ananta" — an alternate name for the same Hindu serpent deity — eliminates this confusion while preserving the mythological connection.

This is a clean break with no backwards-compatibility shims. Version becomes 1.0.0.

## Scope

### Python Package

- Directory: `src/shesha/` → `src/ananta/`
- Main class: `Shesha` → `Ananta`
- Module file: `shesha.py` → `ananta.py`
- Exceptions: `SheshaError` → `AnantaError`
- All imports throughout `src/` and `tests/`
- Test files: `test_shesha.py` → `test_ananta.py`, `test_shesha_di.py` → `test_ananta_di.py`

### Configuration

- `pyproject.toml`: package name, entry points, build paths
- Environment variables: `SHESHA_API_KEY` → `ANANTA_API_KEY`, `SHESHA_MODEL` → `ANANTA_MODEL`

### CLI Entry Points

- `shesha-web` → `ananta-web`
- `shesha-code` → `ananta-code`
- `shesha-document-explorer` → `ananta-document-explorer`

### Data Directory

- `shesha_data/` → `ananta_data/`
- Startup check: detect old `shesha_data/` directory and print migration message telling users to rename it

### Shell Scripts & Docker

- Launcher scripts: APP_NAME, APP_SLUG, marker files, log prefixes
- Dockerfiles: ENTRYPOINT commands
- docker-compose.yml: service names, environment variables

### Frontend

- `@shesha/` scoped packages → `@ananta/`
- package.json files updated

### Documentation

- README.md: title, logo (`images/ananta.png`), examples, "Who is Ananta?" section
- CHANGELOG.md: new `[1.0.0]` section documenting the rename
- CLAUDE.md: project description, paths
- docs/ENVIRONMENT.md, DEVELOPMENT.md, OVERVIEW.md: references
- .github/copilot-instructions.md: references

### NOT Renamed

- Git history (commits referencing "shesha" are historical)
- Historical plan doc filenames in `docs/plans/`
- Architecture report filenames in `paad/`
- Build artifacts (`.venv/`, `.mypy_cache/`, `htmlcov/` — regenerated)
- `oolong/` research directory
- The repo directory itself on disk

## Version

1.0.0, set via git tag. hatch-vcs derives the version from tags.
