# Experimental → Explorers Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename `src/ananta/experimental/` to `src/ananta/explorers/` with clearer submodule names and remove the unused `multi_repo/` module.

**Architecture:** Mechanical rename in phases — delete dead code first, then move directories with `git mv`, fix imports/configs, verify with tests. Each phase is independently committable.

**Tech Stack:** Python, bash, git, pytest, mypy, ruff

**Design doc:** `docs/plans/2026-03-22-experimental-to-explorers-design.md`

---

### Task 1: Remove `multi_repo/` and related code

**Files:**
- Delete: `src/ananta/experimental/multi_repo/` (entire directory)
- Delete: `tests/experimental/multi_repo/` (entire directory)
- Delete: `examples/multi_repo.py`
- Delete: `tests/examples/test_multi_repo.py`

**Step 1: Delete multi_repo source, tests, and example**

```bash
git rm -r src/ananta/experimental/multi_repo/
git rm -r tests/experimental/multi_repo/
git rm examples/multi_repo.py
git rm tests/examples/test_multi_repo.py
```

**Step 2: Verify no remaining references**

```bash
grep -r "multi_repo" src/ tests/ examples/ --include="*.py" -l
```

Expected: No results (plan docs in `docs/` are historical and stay).

**Step 3: Run tests**

```bash
pytest tests/ -x -q
```

Expected: All pass (multi_repo had its own tests, nothing else depends on it).

**Step 4: Commit**

```bash
git add -A
git commit -m "remove: delete unused multi_repo module (replaced by code explorer)"
```

---

### Task 2: Rename `experimental/` → `explorers/` (source tree)

This task does all directory moves in one atomic step to avoid broken intermediate states.

**Renames:**
- `src/ananta/experimental/` → `src/ananta/explorers/`
- Then within `explorers/`: `web/` → `arxiv_explorer_tmp/` (temp name to avoid collision with `arxiv/`)
- Then: `arxiv/` → `arxiv_explorer_tmp/papers/`
- Then: `arxiv_explorer_tmp/` → `arxiv/`
- Then: `code_explorer/` → `code/`
- Then: `document_explorer/` → `document/`
- Then: `shared/` → `shared_ui/`

**Step 1: Rename the top-level directory**

```bash
git mv src/ananta/experimental src/ananta/explorers
```

**Step 2: Rename `web/` → temporary name (to free up space for arxiv merge)**

```bash
git mv src/ananta/explorers/web src/ananta/explorers/arxiv_app_tmp
```

**Step 3: Move `arxiv/` library into the app as `papers/`**

```bash
git mv src/ananta/explorers/arxiv src/ananta/explorers/arxiv_app_tmp/papers
```

**Step 4: Rename temp to final name**

```bash
git mv src/ananta/explorers/arxiv_app_tmp src/ananta/explorers/arxiv
```

**Step 5: Rename code_explorer → code, document_explorer → document, shared → shared_ui**

```bash
git mv src/ananta/explorers/code_explorer src/ananta/explorers/code
git mv src/ananta/explorers/document_explorer src/ananta/explorers/document
git mv src/ananta/explorers/shared src/ananta/explorers/shared_ui
```

**Step 6: Update `explorers/__init__.py` docstring**

Change `src/ananta/explorers/__init__.py` from:
```python
"""Experimental features - not part of stable API."""
```
to:
```python
"""Ananta explorer applications."""
```

**Step 7: Update `shared_ui/__init__.py` docstring**

Change `src/ananta/explorers/shared_ui/__init__.py` from:
```python
"""Shared web infrastructure for Ananta experimental tools."""
```
to:
```python
"""Shared web infrastructure for Ananta explorers."""
```

**Step 8: Update `code/__init__.py` docstring**

Change `src/ananta/explorers/code/__init__.py` from:
```python
"""Code explorer experimental module."""
```
to:
```python
"""Code explorer module."""
```

**Step 9: Commit (tests will NOT pass yet — imports are still broken)**

```bash
git add -A
git commit -m "rename: move experimental/ to explorers/ with clearer submodule names"
```

---

### Task 3: Fix all Python imports in source tree

**Scope:** All `.py` files under `src/ananta/explorers/`.

The import renames are (order matters — do the most specific first to avoid partial replacements):

| Find | Replace |
|---|---|
| `ananta.experimental.web` | `ananta.explorers.arxiv` |
| `ananta.experimental.arxiv` | `ananta.explorers.arxiv.papers` |
| `ananta.experimental.code_explorer` | `ananta.explorers.code` |
| `ananta.experimental.document_explorer` | `ananta.explorers.document` |
| `ananta.experimental.shared` | `ananta.explorers.shared_ui` |
| `ananta.experimental.multi_repo` | (should not exist after Task 1) |

**Step 1: Replace imports — `web` → `arxiv` (must come BEFORE arxiv → arxiv.papers)**

```bash
find src/ananta/explorers/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.web/ananta.explorers.arxiv/g' {} +
```

**Step 2: Replace imports — `arxiv` → `arxiv.papers`**

Note: After step 1, the string `ananta.experimental.arxiv` only appears in files that reference the arxiv *library*, not the web app. But we must be careful not to match `ananta.explorers.arxiv` (already replaced). So we target the remaining `ananta.experimental.arxiv` strings:

```bash
find src/ananta/explorers/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.arxiv/ananta.explorers.arxiv.papers/g' {} +
```

**Step 3: Replace imports — `code_explorer` → `code`**

```bash
find src/ananta/explorers/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.code_explorer/ananta.explorers.code/g' {} +
```

**Step 4: Replace imports — `document_explorer` → `document`**

```bash
find src/ananta/explorers/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.document_explorer/ananta.explorers.document/g' {} +
```

**Step 5: Replace imports — `shared` → `shared_ui`**

```bash
find src/ananta/explorers/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.shared/ananta.explorers.shared_ui/g' {} +
```

**Step 6: Verify no remaining `ananta.experimental` references in source**

```bash
grep -r "ananta\.experimental" src/ --include="*.py"
```

Expected: No results.

**Step 7: Run ruff to check for import issues**

```bash
ruff check src/ananta/explorers/
```

Expected: Clean (or only pre-existing issues).

**Step 8: Commit**

```bash
git add -A
git commit -m "fix: update all source imports from experimental to explorers"
```

---

### Task 4: Rename test directories and fix test imports

**Renames:**

Unit tests:
- `tests/unit/experimental/` → `tests/unit/explorers/`
- Then within: `web/` → `arxiv/`, `arxiv/` → `arxiv/papers/` (same merge pattern as source)
- `code_explorer/` → `code/`, `document_explorer/` → `document/`, `shared/` → `shared_ui/`

Integration tests:
- `tests/experimental/` → `tests/explorers/`
- Same subdir renames (minus multi_repo, already deleted)

**Step 1: Rename unit test directories**

```bash
git mv tests/unit/experimental tests/unit/explorers
git mv tests/unit/explorers/web tests/unit/explorers/arxiv_app_tmp
git mv tests/unit/explorers/arxiv tests/unit/explorers/arxiv_app_tmp/papers
git mv tests/unit/explorers/arxiv_app_tmp tests/unit/explorers/arxiv
git mv tests/unit/explorers/code_explorer tests/unit/explorers/code
git mv tests/unit/explorers/document_explorer tests/unit/explorers/document
git mv tests/unit/explorers/shared tests/unit/explorers/shared_ui
```

**Step 2: Rename integration test directories**

```bash
git mv tests/experimental tests/explorers
git mv tests/explorers/web tests/explorers/arxiv_app_tmp
git mv tests/explorers/arxiv tests/explorers/arxiv_app_tmp/papers
git mv tests/explorers/arxiv_app_tmp tests/explorers/arxiv
git mv tests/explorers/code_explorer tests/explorers/code
git mv tests/explorers/shared tests/explorers/shared_ui
```

Note: `tests/explorers/document_explorer/` does not exist (no integration tests for document explorer).

**Step 3: Fix imports in ALL test files (same replacements as Task 3, same order)**

```bash
find tests/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.web/ananta.explorers.arxiv/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.arxiv/ananta.explorers.arxiv.papers/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.code_explorer/ananta.explorers.code/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.document_explorer/ananta.explorers.document/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/ananta\.experimental\.shared/ananta.explorers.shared_ui/g' {} +
```

**Step 4: Verify no remaining references**

```bash
grep -r "ananta\.experimental" tests/ --include="*.py"
```

Expected: No results.

**Step 5: Commit**

```bash
git add -A
git commit -m "fix: rename test directories and update test imports"
```

---

### Task 5: Update pyproject.toml entry points

**Files:**
- Modify: `pyproject.toml` (lines 74-76)

**Step 1: Update entry points**

Change:
```toml
ananta-web = "ananta.experimental.web.__main__:main"
ananta-code = "ananta.experimental.code_explorer.__main__:main"
ananta-document-explorer = "ananta.experimental.document_explorer.__main__:main"
```
to:
```toml
ananta-web = "ananta.explorers.arxiv.__main__:main"
ananta-code = "ananta.explorers.code.__main__:main"
ananta-document-explorer = "ananta.explorers.document.__main__:main"
```

**Step 2: Reinstall editable package**

```bash
pip install -e ".[dev]"
```

**Step 3: Verify entry points resolve**

```bash
python -c "from ananta.explorers.arxiv.__main__ import main; print('arxiv OK')"
python -c "from ananta.explorers.code.__main__ import main; print('code OK')"
python -c "from ananta.explorers.document.__main__ import main; print('document OK')"
```

Expected: All three print OK.

**Step 4: Run full test suite**

```bash
pytest tests/ -x -q
```

Expected: All pass.

**Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "fix: update pyproject.toml entry points for explorers paths"
```

---

### Task 6: Update shell scripts

**Files:**
- Modify: `arxiv-explorer/arxiv-explorer.sh` (line 19)
- Modify: `code-explorer/code-explorer.sh` (lines 20-21)
- Modify: `document-explorer/document-explorer.sh` (lines 19-20)

**Step 1: Update arxiv-explorer.sh**

Change line 19:
```bash
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/web/frontend"
```
to:
```bash
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/explorers/arxiv/frontend"
```

**Step 2: Update code-explorer.sh**

Change lines 20-21:
```bash
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/code_explorer/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/shared/frontend"
```
to:
```bash
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/explorers/code/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/ananta/explorers/shared_ui/frontend"
```

**Step 3: Update document-explorer.sh**

Change lines 19-20:
```bash
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/document_explorer/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/ananta/experimental/shared/frontend"
```
to:
```bash
FRONTEND_DIR="$PROJECT_ROOT/src/ananta/explorers/document/frontend"
SHARED_FRONTEND_DIR="$PROJECT_ROOT/src/ananta/explorers/shared_ui/frontend"
```

**Step 4: Commit**

```bash
git add arxiv-explorer/arxiv-explorer.sh code-explorer/code-explorer.sh document-explorer/document-explorer.sh
git commit -m "fix: update shell script paths for explorers directory structure"
```

---

### Task 7: Update Dockerfiles

**Files:**
- Modify: `arxiv-explorer/Dockerfile`
- Modify: `code-explorer/Dockerfile`
- Modify: `document-explorer/Dockerfile`

**Step 1: Update arxiv-explorer/Dockerfile**

Replace all `experimental` path references:
- Line 12: `COPY src/ananta/experimental/shared/frontend/` → `COPY src/ananta/explorers/shared_ui/frontend/`
- Line 16: `COPY src/ananta/experimental/web/frontend/package.json` → `COPY src/ananta/explorers/arxiv/frontend/package.json`
- Line 19: `sed` command — `file:../../shared/frontend` → `file:../../shared_ui/frontend`
- Line 22: `COPY src/ananta/experimental/web/frontend/` → `COPY src/ananta/explorers/arxiv/frontend/`
- Line 32: `COPY --from=frontend /build/dist src/ananta/experimental/web/frontend/dist` → `COPY --from=frontend /build/dist src/ananta/explorers/arxiv/frontend/dist`

**Step 2: Update code-explorer/Dockerfile**

Replace all `experimental` path references:
- Line 12: `COPY src/ananta/experimental/shared/frontend/` → `COPY src/ananta/explorers/shared_ui/frontend/`
- Line 16: `COPY src/ananta/experimental/code_explorer/frontend/package.json` → `COPY src/ananta/explorers/code/frontend/package.json`
- Line 19: `sed` command — `file:../../shared/frontend` → `file:../../shared_ui/frontend`
- Line 22: `COPY src/ananta/experimental/code_explorer/frontend/` → `COPY src/ananta/explorers/code/frontend/`
- Line 35: `COPY --from=frontend /build/dist src/ananta/experimental/code_explorer/frontend/dist` → `COPY --from=frontend /build/dist src/ananta/explorers/code/frontend/dist`

**Step 3: Update document-explorer/Dockerfile**

Replace all `experimental` path references:
- Line 12: `COPY src/ananta/experimental/shared/frontend/` → `COPY src/ananta/explorers/shared_ui/frontend/`
- Line 16: `COPY src/ananta/experimental/document_explorer/frontend/package.json` → `COPY src/ananta/explorers/document/frontend/package.json`
- Line 19: `sed` command — `file:../../shared/frontend` → `file:../../shared_ui/frontend`
- Line 22: `COPY src/ananta/experimental/document_explorer/frontend/` → `COPY src/ananta/explorers/document/frontend/`
- Line 32: `COPY --from=frontend /build/dist src/ananta/experimental/document_explorer/frontend/dist` → `COPY --from=frontend /build/dist src/ananta/explorers/document/frontend/dist`

**Step 4: Commit**

```bash
git add arxiv-explorer/Dockerfile code-explorer/Dockerfile document-explorer/Dockerfile
git commit -m "fix: update Dockerfile paths for explorers directory structure"
```

---

### Task 8: Update frontend package.json files

**Files:**
- Modify: `src/ananta/explorers/arxiv/frontend/package.json`
- Modify: `src/ananta/explorers/code/frontend/package.json`
- Modify: `src/ananta/explorers/document/frontend/package.json`

**Step 1: Update shared-ui dependency path in all three**

In each `package.json`, change:
```json
"@ananta/shared-ui": "file:../../shared/frontend"
```
to:
```json
"@ananta/shared-ui": "file:../../shared_ui/frontend"
```

**Step 2: Commit**

```bash
git add src/ananta/explorers/*/frontend/package.json
git commit -m "fix: update frontend shared-ui dependency paths"
```

---

### Task 9: Update documentation and config files

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/extending-web-tools.md`
- Modify: `.kiro/steering/structure.md`
- Modify: `.kiro/specs/explorer-more-button/design.md`
- Modify: `.kiro/specs/explorer-more-button/requirements.md`
- Modify: `.kiro/specs/explorer-more-button/tasks.md`

**Step 1: Update CLAUDE.md**

In the Architecture section, change references from `src/ananta/{rlm,sandbox,storage,parser,llm}/` and the experimental mention to reflect the new `explorers/` path.

Also update the "Beyond PoC mindset" bullet and the API Boundaries section if they reference `experimental`.

**Step 2: Update docs/extending-web-tools.md**

This file has ~20 occurrences. Apply these replacements throughout:

| Find | Replace |
|---|---|
| `experimental web tool` | `explorer` |
| `src/ananta/experimental/shared/` | `src/ananta/explorers/shared_ui/` |
| `ananta.experimental.web` | `ananta.explorers.arxiv` |
| `ananta.experimental.code_explorer` | `ananta.explorers.code` |
| `src/ananta/experimental/your_tool/` | `src/ananta/explorers/your_tool/` |
| `ananta.experimental.your_tool` | `ananta.explorers.your_tool` |
| `ananta.experimental.shared` | `ananta.explorers.shared_ui` |
| `src/ananta/experimental/` | `src/ananta/explorers/` |

**Step 3: Update .kiro/steering/structure.md**

Replace directory tree references:
- `experimental/` → `explorers/`
- `src/shesha/experimental/` → `src/ananta/explorers/` (also fix the stale `shesha` reference)

**Step 4: Update .kiro/specs/explorer-more-button/ files**

In all three files, replace:
- `src/shesha/experimental/shared/` → `src/ananta/explorers/shared_ui/`
- `tests/experimental/shared/` → `tests/explorers/shared_ui/`

**Step 5: Commit**

```bash
git add CLAUDE.md docs/extending-web-tools.md .kiro/
git commit -m "docs: update all documentation for explorers directory structure"
```

---

### Task 10: Final verification

**Step 1: Check for any remaining `experimental` references (excluding plan docs and changelog)**

```bash
grep -r "experimental" src/ tests/ *.toml arxiv-explorer/ code-explorer/ document-explorer/ .kiro/ docs/extending-web-tools.md CLAUDE.md --include="*.py" --include="*.toml" --include="*.sh" --include="*.md" --include="*.json" --include="Dockerfile" --include="*.yml" | grep -v "docs/plans/" | grep -v "CHANGELOG" | grep -v "node_modules" | grep -v "__pycache__"
```

Expected: No results (or only false positives like "ExperimentalWarning" in test config).

**Step 2: Run full lint + typecheck + test suite**

```bash
make all
```

Expected: All pass.

**Step 3: Verify editable install works**

```bash
pip install -e ".[dev]"
python -c "import ananta.explorers; print('OK')"
```

**Step 4: Final commit if any fixups needed, otherwise done**

---

## Execution Notes

- **Task ordering is strict.** Tasks 1-2 must be sequential. Tasks 3-4 must follow 2. Task 5 must follow 3-4. Tasks 6-9 can run in parallel after Task 5. Task 10 is last.
- **The arxiv merge (steps 2-4 in Tasks 2 and 4)** uses a temp directory to avoid `git mv` collision between `arxiv/` (library) and the target name `arxiv/` (app). This is the trickiest part.
- **Import replacement order matters** in Tasks 3 and 4: `web` → `arxiv` must happen before `arxiv` → `arxiv.papers`, otherwise `web` replacements would match the already-replaced `arxiv` string.
- **No TDD for this task** — this is a pure rename refactor. The existing test suite is the specification. The TDD cycle maps naturally: rename breaks imports (RED), fix imports/paths (GREEN), no new code to refactor. Each task follows this pattern: structural change → verify with tests → commit.

## Alignment Review (2026-03-22)

- All 10 design requirements map to plan tasks. No gaps found.
- No scope creep — Task 10 (final verification) is the only item not in the design, and it's standard practice.
- README files in explorer directories say "experimental" as a description ("experimental software"), not as a path. No update needed.
- Docker-compose files and remaining examples are clean of `experimental` path references.
