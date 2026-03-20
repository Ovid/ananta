# Rename Shesha → Ananta — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename the project from "Shesha" to "Ananta" across all code, config, docs, and infra — clean break, version 1.0.0.

**Architecture:** This is a mechanical rename with a few pieces of new logic (data directory migration checks). The existing test suite serves as the regression safety net. New tests are written only for new behavior (migration warnings).

**Tech Stack:** Python, TypeScript/React, Docker, shell scripts, Markdown

**Design doc:** `docs/plans/2026-03-20-rename-ananta-design.md`

**TDD note:** Most tasks are mechanical renames where the existing test suite IS the test — run `make all` after each rename phase to verify. Only Task 4 (migration checks) is new code that follows full RED/GREEN/REFACTOR.

---

### Task 1: Directory and File Renames

**Requirement:** Design §Python Package — directory, module file, test file renames

Move the package directory and renamed files using `git mv` to preserve history.

#### Steps

**Step 1: Rename the package directory**

```bash
git mv src/shesha src/ananta
```

**Step 2: Rename the main module file**

```bash
git mv src/ananta/shesha.py src/ananta/ananta.py
```

**Step 3: Rename test files**

```bash
git mv tests/unit/test_shesha.py tests/unit/test_ananta.py
git mv tests/unit/test_shesha_di.py tests/unit/test_ananta_di.py
```

**Step 4: Commit the renames**

```bash
git add -A
git commit -m "rename: git mv src/shesha → src/ananta and renamed files"
```

> **Note:** The project will NOT build or pass tests until Task 2 and 3 are complete. That's expected — this commit preserves git rename tracking.

---

### Task 2: Update pyproject.toml

**Requirement:** Design §Configuration — pyproject.toml package name, entry points, build paths

**Files:**
- Modify: `pyproject.toml`

#### Steps

**Step 1: Apply all replacements in pyproject.toml**

| Line | Old | New |
|------|-----|-----|
| 6 | `name = "shesha"` | `name = "ananta"` |
| 12 | `name = "Shesha Authors"` | `name = "Ananta Authors"` |
| 59 | `"shesha[arxiv]"` | `"ananta[arxiv]"` |
| 66 | `"shesha[web]"` | `"ananta[web]"` |
| 74 | `shesha-web = "shesha.experimental...` | `ananta-web = "ananta.experimental...` |
| 75 | `shesha-code = "shesha.experimental...` | `ananta-code = "ananta.experimental...` |
| 76 | `shesha-document-explorer = "shesha.experimental...` | `ananta-document-explorer = "ananta.experimental...` |
| 79 | `packages = ["src/shesha"]` | `packages = ["src/ananta"]` |
| 82 | `"prompts" = "src/shesha/prompts/prompts"` | `"prompts" = "src/ananta/prompts/prompts"` |
| 88 | `version-file = "src/shesha/_version.py"` | `version-file = "src/ananta/_version.py"` |
| 93 | `exclude = ["src/shesha/_version.py"]` | `exclude = ["src/ananta/_version.py"]` |
| 99 | `"src/shesha/rlm/prompts.py"` | `"src/ananta/rlm/prompts.py"` |

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "rename: update pyproject.toml package name and paths"
```

---

### Task 3: Bulk Python Rename

**Requirement:** Design §Python Package — all classes, imports, env vars, constants, state attributes

Perform find-and-replace across all Python files in `src/ananta/` and `tests/`. Order matters — do longer/more specific patterns first to avoid partial replacements.

**Files:**
- Modify: All `.py` files in `src/ananta/` and `tests/`

#### RED

Run `make all` — expected: mass failures due to broken imports (package moved but references still say `shesha`).

#### GREEN

**Step 1: Run replacements in this exact order**

Apply these replacements across all `.py` files in `src/ananta/` and `tests/`:

```
SheshaConfig  → AnantaConfig
SheshaTUI     → AnantaTUI
SheshaError   → AnantaError
SHESHA_TEAL   → ANANTA_TEAL
SHESHA_       → ANANTA_          (env var prefixes)
shesha-sandbox → ananta-sandbox  (Docker image name)
state.shesha  → state.ananta    (app state attribute)
shesha_data   → ananta_data     (data directory name)
.shesha-arxiv → .ananta-arxiv   (home dot-directory)
from shesha.shesha import → from ananta.ananta import
from shesha.  → from ananta.    (import paths)
from shesha import → from ananta import
import shesha → import ananta
"shesha"      → "ananta"        (quoted package name in strings)
'shesha'      → 'ananta'        (single-quoted)
shesha.       → ananta.         (dotted module refs in strings/comments)
.shesha/      → .ananta/        (home dot-directory in path strings)
.shesha"      → .ananta"        (home dot-directory at end of string)
Shesha        → Ananta          (remaining title-case: docstrings, comments, class refs)
```

**Important exclusions:**
- Do NOT modify files in `oolong/` (handled separately in Task 9)
- Do NOT modify files in `docs/plans/` (historical documents)
- Do NOT modify files in `paad/` (architecture reports)
- Do NOT modify `CHANGELOG.md` (handled separately in Task 12)
- Do NOT modify `README.md` (handled separately in Task 10)

**Step 2: Verify the build resolves**

```bash
pip install -e ".[dev]"
```

**Step 3: Run the full test suite**

```bash
make all
```

Expected: All tests pass. If failures, fix them before proceeding.

#### REFACTOR

Scan for any awkward patterns the bulk rename may have introduced (e.g., double-renamed strings, broken comments). Fix and re-run `make all`.

**Step 4: Commit**

```bash
git add -A
git commit -m "rename: bulk Python rename shesha → ananta across src/ and tests/"
```

---

### Task 4: Data Directory Migration Checks (TDD)

**Requirement:** Design §Data & User Home Directories — startup check for each legacy directory

Add startup checks that detect old `shesha_data/`, `~/.shesha-arxiv/`, and `~/.shesha/<app>/` directories and print migration messages.

**Files:**
- Create: `src/ananta/migration.py`
- Create: `tests/unit/test_migration.py`
- Modify: `src/ananta/ananta.py` (call migration check in `Ananta.start()`)
- Modify: `src/ananta/experimental/shared/dependencies.py` (call migration check)
- Modify: `src/ananta/experimental/web/dependencies.py` (call migration check)

#### RED

**Step 1: Write the failing test**

```python
# tests/unit/test_migration.py
import logging
from pathlib import Path

import pytest

from ananta.migration import check_legacy_directory


def test_warns_when_legacy_dir_exists(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Migration check warns when old shesha directory exists."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    new = tmp_path / "ananta_data"

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, "shesha_data", "ananta_data")

    assert "shesha_data" in caplog.text
    assert "ananta_data" in caplog.text
    assert "rename" in caplog.text.lower() or "mv" in caplog.text.lower()


def test_silent_when_no_legacy_dir(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Migration check is silent when no legacy directory exists."""
    legacy = tmp_path / "shesha_data"
    new = tmp_path / "ananta_data"

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, "shesha_data", "ananta_data")

    assert caplog.text == ""


def test_silent_when_new_dir_already_exists(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Migration check is silent when user has already migrated."""
    legacy = tmp_path / "shesha_data"
    legacy.mkdir()
    new = tmp_path / "ananta_data"
    new.mkdir()

    with caplog.at_level(logging.WARNING):
        check_legacy_directory(legacy, new, "shesha_data", "ananta_data")

    assert caplog.text == ""
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_migration.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ananta.migration'`

If it passes unexpectedly: the module already exists from a prior attempt — check its contents match what we need.

#### GREEN

**Step 3: Write minimal implementation**

```python
# src/ananta/migration.py
"""Legacy directory migration checks for the Shesha → Ananta rename."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def check_legacy_directory(
    legacy_path: Path,
    new_path: Path,
    legacy_name: str,
    new_name: str,
) -> None:
    """Warn if a legacy Shesha directory exists and the new one does not."""
    if legacy_path.exists() and not new_path.exists():
        logger.warning(
            "Found legacy directory '%s' at %s. "
            "Ananta now uses '%s'. Please rename it:\n"
            "  mv %s %s",
            legacy_name,
            legacy_path,
            new_name,
            legacy_path,
            legacy_path.parent / new_name,
        )
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_migration.py -v
```

Expected: PASS

**Step 5: Wire up migration checks**

In `src/ananta/ananta.py`, in the `Ananta.start()` method, add a call to check the configured storage path's parent for `shesha_data`:

```python
from ananta.migration import check_legacy_directory

# In Ananta.start(), before other startup logic:
storage_path = Path(self._config.storage_path)
if storage_path.name == "ananta_data":
    legacy = storage_path.parent / "shesha_data"
    check_legacy_directory(legacy, storage_path, "shesha_data", "ananta_data")
```

In `src/ananta/experimental/web/dependencies.py`, add checks for `~/.shesha-arxiv`:

```python
from ananta.migration import check_legacy_directory

# Before creating data_dir:
legacy_arxiv = Path.home() / ".shesha-arxiv"
check_legacy_directory(legacy_arxiv, data_dir, ".shesha-arxiv", ".ananta-arxiv")
```

In `src/ananta/experimental/shared/dependencies.py`, add checks for `~/.shesha/<app>`:

```python
from ananta.migration import check_legacy_directory

# Before creating data_dir:
legacy_shared = Path.home() / ".shesha" / app_name
check_legacy_directory(legacy_shared, data_dir, f".shesha/{app_name}", f".ananta/{app_name}")
```

#### REFACTOR

Look for:
- Duplicated migration-check call patterns that could be extracted
- Whether the import belongs at file top or needs a comment explaining placement

**Step 6: Run full suite**

```bash
make all
```

Expected: All tests pass.

**Step 7: Commit**

```bash
git add src/ananta/migration.py tests/unit/test_migration.py src/ananta/ananta.py src/ananta/experimental/shared/dependencies.py src/ananta/experimental/web/dependencies.py
git commit -m "feat: add legacy directory migration warnings for shesha → ananta"
```

---

### Task 5: Makefile and .env

**Requirement:** Design §Configuration — Makefile paths, .env variable names

**Files:**
- Modify: `Makefile`
- Modify: `.env`

#### RED

Run `make all` — expected: already passing from Task 3. But after Task 3, the Makefile still references `src/shesha/` paths for mypy, vitest, tsc, and coverage. These commands would fail if run directly (the `make all` in Task 3 may have worked because `pip install -e` set up the paths, but mypy and coverage point to wrong dirs).

#### GREEN

**Step 1: Update Makefile**

Replace all `src/shesha` → `src/ananta` in the Makefile (~4 occurrences).

**Step 2: Update .env**

Replace `SHESHA_API_KEY` → `ANANTA_API_KEY` and `SHESHA_MODEL` → `ANANTA_MODEL` (and any other `SHESHA_*` vars present).

**Step 3: Verify**

```bash
make all
```

#### REFACTOR

N/A — mechanical rename.

**Step 4: Commit**

```bash
git add Makefile .env
git commit -m "rename: update Makefile paths and .env variable names"
```

---

### Task 6: Frontend Rename

**Requirement:** Design §Frontend — packages, localStorage keys, static assets, UI text

Update all frontend projects: package names, imports, localStorage keys, static assets, UI text.

**Files:**
- Modify: `src/ananta/experimental/shared/frontend/package.json`
- Modify: `src/ananta/experimental/web/frontend/package.json`
- Modify: `src/ananta/experimental/code_explorer/frontend/package.json`
- Modify: `src/ananta/experimental/document_explorer/frontend/package.json`
- Modify: All `.tsx`, `.ts` files in these frontend directories
- Modify: All frontend test files

#### RED

Run frontend tests — expected: passing (they don't depend on Python package name). After rename, they should still pass. The "red" here is functional: if `@shesha/shared-ui` is renamed in package.json but not in imports, tests fail.

#### GREEN

**Step 1: Update package.json files**

In each `package.json`:
- `"name": "@shesha/shared-ui"` → `"name": "@ananta/shared-ui"`
- `"@shesha/shared-ui": "file:..."` → `"@ananta/shared-ui": "file:..."`

**Step 2: Bulk rename across all frontend source files**

Apply these replacements to all `.tsx`, `.ts`, `.json` files in frontend directories:

```
@shesha/          → @ananta/
shesha-polite-email → ananta-polite-email
shesha-email-skipped → ananta-email-skipped
shesha-welcome-dismissed → ananta-welcome-dismissed
shesha-theme      → ananta-theme
/static/shesha.png → /static/ananta.png
Shesha            → Ananta          (UI text in components)
shesha            → ananta          (remaining lowercase in test assertions, URLs)
```

**Step 3: Regenerate lock files**

```bash
cd src/ananta/experimental/shared/frontend && npm install
cd src/ananta/experimental/web/frontend && npm install
cd src/ananta/experimental/code_explorer/frontend && npm install
cd src/ananta/experimental/document_explorer/frontend && npm install
```

**Step 4: Run frontend tests**

```bash
cd src/ananta/experimental/web/frontend && npx vitest run
cd src/ananta/experimental/shared/frontend && npx tsc --noEmit
```

Expected: All pass.

#### REFACTOR

N/A — mechanical rename.

**Step 5: Commit**

```bash
git add -A
git commit -m "rename: update frontend packages, localStorage keys, static assets, UI text"
```

---

### Task 7: Shell Scripts, Docker, and Explorer READMEs

**Requirement:** Design §Shell Scripts & Docker — launcher scripts, Dockerfiles, compose configs, sandbox image

**Files:**
- Modify: `scripts/common.sh`
- Modify: `arxiv-explorer/arxiv-explorer.sh`
- Modify: `arxiv-explorer/Dockerfile`
- Modify: `arxiv-explorer/docker-compose.yml`
- Modify: `arxiv-explorer/README.md`
- Modify: `code-explorer/code-explorer.sh`
- Modify: `code-explorer/Dockerfile`
- Modify: `code-explorer/docker-compose.yml`
- Modify: `code-explorer/README.md`
- Modify: `document-explorer/document-explorer.sh`
- Modify: `document-explorer/Dockerfile`
- Modify: `document-explorer/docker-compose.yml`
- Modify: `src/ananta/sandbox/Dockerfile`
- Modify: `examples/arxiv-explorer.sh` (if it exists as a launcher)

#### Steps

**Step 1: Apply replacements across all shell, Docker, and README files**

```
[shesha]                  → [ananta]            (log prefix in common.sh)
shesha-web                → ananta-web          (APP_SLUG, service names, entrypoints)
shesha-code               → ananta-code
shesha-document-explorer  → ananta-document-explorer
Shesha arXiv Web Explorer → Ananta arXiv Web Explorer  (APP_NAME)
Shesha Code Explorer      → Ananta Code Explorer
Shesha Document Explorer  → Ananta Document Explorer
SHESHA_                   → ANANTA_             (env vars in compose files)
shesha-sandbox            → ananta-sandbox      (sandbox Dockerfile/image)
.shesha-web-installed     → .ananta-web-installed
.shesha-code-installed    → .ananta-code-installed
.shesha-document-explorer-installed → .ananta-document-explorer-installed
src/shesha                → src/ananta          (paths in Dockerfiles)
Shesha                    → Ananta              (remaining title-case in READMEs)
shesha                    → ananta              (remaining lowercase in READMEs)
```

**Step 2: Commit**

```bash
git add scripts/ arxiv-explorer/ code-explorer/ document-explorer/ src/ananta/sandbox/Dockerfile examples/arxiv-explorer.sh
git commit -m "rename: update shell scripts, Dockerfiles, docker-compose, and explorer READMEs"
```

---

### Task 8: Examples

**Requirement:** Design §Examples — imports, class references, env var references

**Files:**
- Modify: All `.py` files in `examples/`

#### Steps

**Step 1: Apply replacements**

Same patterns as Task 3:
```
from shesha     → from ananta
import shesha   → import ananta
SheshaConfig    → AnantaConfig
SheshaTUI       → AnantaTUI
SheshaError     → AnantaError
Shesha          → Ananta
SHESHA_         → ANANTA_
shesha_data     → ananta_data
```

**Step 2: Commit**

```bash
git add examples/
git commit -m "rename: update examples to use ananta imports and references"
```

---

### Task 9: Oolong (runnable code only)

**Requirement:** Design §oolong — Python imports and env var references in runnable scripts

**Files:**
- Modify: `oolong/run_oolong_and_pairs.py`
- Modify: `oolong/alt-glitch-rlm-oolong.py`
- Modify: `oolong/run_reference_implementation.py`

#### Steps

**Step 1: Update Python imports in oolong scripts**

In `oolong/run_oolong_and_pairs.py`:
```python
# Line 112-113
from ananta import Ananta, AnantaConfig
from ananta.exceptions import ProjectExistsError
```

Update all references in the file: `Shesha` → `Ananta`, `SheshaConfig` → `AnantaConfig`, `SHESHA_*` → `ANANTA_*`.

In `oolong/alt-glitch-rlm-oolong.py` and `oolong/run_reference_implementation.py`:
Update `SHESHA_*` env var references → `ANANTA_*`.

**Step 2: Do NOT modify oolong/*.md files** — these are research prose and stay as historical records.

**Step 3: Commit**

```bash
git add oolong/run_oolong_and_pairs.py oolong/alt-glitch-rlm-oolong.py oolong/run_reference_implementation.py
git commit -m "rename: update oolong benchmark scripts to use ananta imports"
```

---

### Task 10: Documentation — README.md

**Requirement:** Design §Documentation — title, logo, "Who is Ananta?" section

**Files:**
- Modify: `README.md`

#### Steps

**Step 1: Update title and logo**

Change the title from "Shesha" to "Ananta" and update the logo reference from `images/shesha.png` to `images/ananta.png`.

**Step 2: Rewrite the "Who is Shesha?" section**

Replace with:

```markdown
## Who is Ananta?

In Hindu mythology, **Ananta** (अनन्त, "the infinite one") is an alternate name
for Shesha — the cosmic serpent who coils beneath the god Vishnu. The name was
chosen because a Recursive Language Model can loop indefinitely, exploring a
document until it finds the answer. The project was originally called "Shesha"
but was renamed to avoid confusion with "shisha" (hookah).

Learn more: https://en.wikipedia.org/wiki/Ananta_(infinite)
```

**Step 3: Update all other references**

```
Shesha          → Ananta          (title, headings, prose)
shesha          → ananta          (package name, import examples)
SheshaConfig    → AnantaConfig    (code examples)
SHESHA_         → ANANTA_         (env var examples)
shesha-web      → ananta-web      (CLI examples)
shesha-code     → ananta-code
shesha-document-explorer → ananta-document-explorer
shesha_data     → ananta_data
images/shesha.png → images/ananta.png
```

**Step 4: Commit**

```bash
git add README.md
git commit -m "rename: update README — new name, logo, and 'Who is Ananta?' section"
```

---

### Task 11: Documentation — Other Files

**Requirement:** Design §Documentation — CLAUDE.md, docs/, prompts/README.md, copilot instructions

**Files:**
- Modify: `CLAUDE.md`
- Modify: `SECURITY.md`
- Delete: `HANDOFF.md` (should never have been committed)
- Modify: `docs/ENVIRONMENT.md`
- Modify: `docs/DEVELOPMENT.md`
- Modify: `docs/OVERVIEW.md`
- Modify: `docs/extending-web-tools.md`
- Modify: `docs/RELEASE-WORKFLOW.md` (if it references shesha)
- Modify: `prompts/README.md`
- Modify: `.github/copilot-instructions.md`

#### Steps

**Step 1: Delete HANDOFF.md**

```bash
git rm HANDOFF.md
```

**Step 2: Apply replacements across all doc files**

Same pattern set:
```
Shesha          → Ananta
shesha          → ananta
SheshaConfig    → AnantaConfig
SHESHA_         → ANANTA_
src/shesha      → src/ananta
shesha_data     → ananta_data
.shesha         → .ananta
shesha-web      → ananta-web
shesha-code     → ananta-code
shesha-document-explorer → ananta-document-explorer
shesha-sandbox  → ananta-sandbox
python -m shesha → python -m ananta
```

**Step 3: Commit**

```bash
git add CLAUDE.md SECURITY.md docs/ prompts/README.md .github/copilot-instructions.md
git commit -m "rename: update docs, delete HANDOFF.md, update SECURITY.md and copilot instructions"
```

---

### Task 12: CHANGELOG and Version

**Requirement:** Design §Documentation — CHANGELOG 1.0.0 section; Design §Version — 1.0.0

**Files:**
- Modify: `CHANGELOG.md`

#### Steps

**Step 1: Move [Unreleased] content into [1.0.0] and reset [Unreleased]**

The `[Unreleased]` section may have entries from this branch or prior work. Move all its content into a new `[1.0.0]` section dated today, then leave `[Unreleased]` empty. Add the rename entry to the `[1.0.0]` section:

```markdown
## [Unreleased]

## [1.0.0] - 2026-03-20

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
  - Docker image: `shesha-sandbox` → `ananta-sandbox`

### Added

- Startup migration warnings when legacy `shesha_data/`, `~/.shesha/`, or `~/.shesha-arxiv/` directories are detected

(Plus any entries that were previously under [Unreleased])
```

**Step 2: Update comparison links at bottom**

Add/update the comparison links:
```markdown
[unreleased]: https://github.com/Ovid/shesha/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Ovid/shesha/compare/v0.X.Y...v1.0.0
```

(Replace `v0.X.Y` with the actual previous version tag — check `git tag --sort=-v:refname | head -1`.)

**Step 3: Do NOT rewrite historical entries**

Historical changelog entries describe what happened at the time. Leave them as-is.

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add 1.0.0 changelog entry for Shesha → Ananta rename"
```

---

### Task 13: Final Verification

**Requirement:** Validates all prior tasks are complete and consistent.

#### Steps

**Step 1: Reinstall the package**

```bash
pip install -e ".[dev]"
```

**Step 2: Run the full test suite**

```bash
make all
```

Expected: All tests pass, no lint errors, no type errors.

**Step 3: Grep for any remaining "shesha" in shipped code**

```bash
grep -ri "shesha" src/ananta/ tests/ examples/ scripts/ arxiv-explorer/ code-explorer/ document-explorer/ oolong/*.py Makefile pyproject.toml .env CLAUDE.md SECURITY.md README.md --include="*.py" --include="*.toml" --include="*.sh" --include="*.yml" --include="*.yaml" --include="*.tsx" --include="*.ts" --include="*.json" --include="*.md" | grep -v node_modules | grep -v package-lock | grep -v ".mypy_cache" | grep -v "__pycache__"
```

If any results remain in shipped code (not docs/plans/, not paad/, not oolong/*.md), fix them.

**Step 4: Check that the version resolves**

```bash
python -c "import ananta; print(ananta.__version__)"
```

**Step 5: Commit any remaining fixes**

```bash
git add -A
git commit -m "rename: fix remaining shesha references found in final sweep"
```

> **Note:** The git tag `v1.0.0` should be created at merge time via the `/release` skill, not during implementation.

---

### Task 14: Update Claude Memory

**Requirement:** Operational — keep Claude's memory consistent with new project name.

**Step 1: Update MEMORY.md and memory files**

The Claude project memory at `~/.claude/projects/.../memory/` references "Shesha". Update:
- `MEMORY.md` — update any references
- Individual memory files — update project name references

This is outside the repo, so no git commit needed.
