# Design: Rename `experimental/` → `explorers/`

**Date:** 2026-03-22
**Branch:** ovid/experimental-to-explorer

## Goal

Rename `src/ananta/experimental/` to `src/ananta/explorers/` with clearer
submodule names. Remove the unused `multi_repo/` module.

## Directory Structure

### Before

```
src/ananta/experimental/
├── arxiv/              # arXiv paper library
├── web/                # arXiv Explorer app
├── code_explorer/      # Code Explorer app
├── document_explorer/  # Document Explorer app
├── shared/             # Shared base classes + frontend
└── multi_repo/         # CLI PRD analyzer (unused)
```

### After

```
src/ananta/explorers/
├── arxiv/              # arXiv Explorer app (absorbs the library)
│   ├── papers/         # Paper fetching, search, cache, citations
│   ├── frontend/
│   ├── api.py
│   ├── websockets.py
│   └── ...
├── code/               # Code Explorer app
├── document/           # Document Explorer app
└── shared_ui/          # Shared base classes + frontend
```

## Changes

### 1. Remove `multi_repo/`

Delete entirely:

- `src/ananta/experimental/multi_repo/`
- `tests/experimental/multi_repo/`
- `examples/multi_repo.py`
- `tests/examples/test_multi_repo.py`

Historical plan docs stay as-is.

### 2. Directory renames

| Old | New |
|---|---|
| `src/ananta/experimental/` | `src/ananta/explorers/` |
| `explorers/web/` | `explorers/arxiv/` (the app) |
| `explorers/arxiv/` (the library) | `explorers/arxiv/papers/` (subpackage of the app) |
| `explorers/code_explorer/` | `explorers/code/` |
| `explorers/document_explorer/` | `explorers/document/` |
| `explorers/shared/` | `explorers/shared_ui/` |

### 3. Import renames

| Old | New |
|---|---|
| `ananta.experimental.web` | `ananta.explorers.arxiv` |
| `ananta.experimental.arxiv` | `ananta.explorers.arxiv.papers` |
| `ananta.experimental.code_explorer` | `ananta.explorers.code` |
| `ananta.experimental.document_explorer` | `ananta.explorers.document` |
| `ananta.experimental.shared` | `ananta.explorers.shared_ui` |

### 4. pyproject.toml

Entry points:

```toml
ananta-web = "ananta.explorers.arxiv.__main__:main"
ananta-code = "ananta.explorers.code.__main__:main"
ananta-document-explorer = "ananta.explorers.document.__main__:main"
```

### 5. Shell scripts

Update `FRONTEND_DIR` and `SHARED_FRONTEND_DIR` paths only:

| Script | Field | New value |
|---|---|---|
| `arxiv-explorer.sh` | `FRONTEND_DIR` | `$PROJECT_ROOT/src/ananta/explorers/arxiv/frontend` |
| `code-explorer.sh` | `FRONTEND_DIR` | `$PROJECT_ROOT/src/ananta/explorers/code/frontend` |
| `code-explorer.sh` | `SHARED_FRONTEND_DIR` | `$PROJECT_ROOT/src/ananta/explorers/shared_ui/frontend` |
| `document-explorer.sh` | `FRONTEND_DIR` | `$PROJECT_ROOT/src/ananta/explorers/document/frontend` |
| `document-explorer.sh` | `SHARED_FRONTEND_DIR` | `$PROJECT_ROOT/src/ananta/explorers/shared_ui/frontend` |

### 6. Dockerfiles

Update `COPY` source paths from `experimental/` to `explorers/` with matching
subdir renames.

### 7. Frontend `package.json` files

Each explorer's `package.json` references the shared frontend via `file:` protocol
(e.g., `"@ananta/shared-ui": "file:../../shared/frontend"`). Update these to
`file:../../shared_ui/frontend`.

The Dockerfiles also contain `sed` commands that rewrite these `file:` paths for
the Docker build context. Those `sed` commands must be updated to match the new
path names.

### 8. Tests

Both test directory trees need renaming:

**Unit tests** (`tests/unit/experimental/` → `tests/unit/explorers/`):

| Old | New |
|---|---|
| `tests/unit/experimental/web/` | `tests/unit/explorers/arxiv/` |
| `tests/unit/experimental/arxiv/` | `tests/unit/explorers/arxiv/papers/` |
| `tests/unit/experimental/code_explorer/` | `tests/unit/explorers/code/` |
| `tests/unit/experimental/document_explorer/` | `tests/unit/explorers/document/` |
| `tests/unit/experimental/shared/` | `tests/unit/explorers/shared_ui/` |

**Integration tests** (`tests/experimental/` → `tests/explorers/`):

| Old | New |
|---|---|
| `tests/experimental/web/` | `tests/explorers/arxiv/` |
| `tests/experimental/arxiv/` | `tests/explorers/arxiv/papers/` |
| `tests/experimental/code_explorer/` | `tests/explorers/code/` |
| `tests/experimental/document_explorer/` | `tests/explorers/document/` |
| `tests/experimental/shared/` | `tests/explorers/shared_ui/` |

### 9. Documentation and config files

Update `experimental` references in:

- `CLAUDE.md` — architecture section
- `docs/extending-web-tools.md` — 5 import path references
- `.kiro/steering/structure.md` — directory layout description
- `.kiro/specs/explorer-more-button/{design,requirements,tasks}.md` — path references

### 10. Post-rename: reinstall editable package

After the rename, run `pip install -e ".[dev]"` to update the editable install.
Old `ananta.experimental` paths will remain importable from stale `.egg-link` /
`.pth` files until reinstalled. Note this in the changelog entry.

## Out of scope

- Rewriting shell scripts in Python
- Consolidating launcher scripts into a single directory
- Renaming CLI entry point commands (e.g., `ananta-web` stays `ananta-web`)
