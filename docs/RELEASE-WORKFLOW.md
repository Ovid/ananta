# Release Workflow

This document describes how to release a new version of Ananta.

## Overview

Ananta uses **semantic versioning** with version numbers automatically derived from git tags via `hatch-vcs`. You never manually set version numbers in code - they come from tags.

## Prerequisites

Before releasing:

1. All tests pass: `make all`
2. All changes are committed and pushed
3. CHANGELOG.md has entries under `[Unreleased]` for all user-visible changes

## Release Steps

### 1. Update CHANGELOG.md

Move entries from `[Unreleased]` to a new version section:

**Before:**
```markdown
## [Unreleased]

### Added
- New feature X
- New feature Y

### Fixed
- Bug fix Z
```

**After:**
```markdown
## [Unreleased]

## [0.2.0] - 2026-02-04

### Added
- New feature X
- New feature Y

### Fixed
- Bug fix Z
```

Use the current date in `YYYY-MM-DD` format.

### 2. Choose Version Number

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0 → 2.0.0): Breaking API changes
- **MINOR** (0.1.0 → 0.2.0): New features, backwards compatible
- **PATCH** (0.1.0 → 0.1.1): Bug fixes, backwards compatible

### 3. Commit the Changelog

```bash
git add CHANGELOG.md
git commit -m "docs: prepare release v0.2.0"
```

### 4. Create Git Tag

```bash
git tag v0.2.0
```

The `v` prefix is required.

### 5. Push Everything

```bash
git push && git push --tags
```

### 6. Verify

After pushing, verify the version is correct:

```bash
pip install -e .
python -c "import ananta; print(ananta.__version__)"
# Should print: 0.2.0
```

## How Versioning Works

### From Git Tags

`hatch-vcs` reads the latest git tag to determine the version:

- Tag `v0.2.0` → version `0.2.0`
- If there are commits after the tag → version `0.2.1.dev3+gabc1234`

### The `_version.py` File

When installed, `hatch-vcs` generates `src/ananta/_version.py` containing:

```python
__version__ = "0.2.0"
```

This file is:
- Auto-generated (never edit manually)
- Listed in `.gitignore` (never commit)
- Excluded from ruff linting

## Changelog Categories

Use these categories in CHANGELOG.md:

| Category | When to Use |
|----------|-------------|
| **Added** | New features |
| **Changed** | Changes to existing functionality |
| **Deprecated** | Features to be removed in future |
| **Removed** | Removed features |
| **Fixed** | Bug fixes |
| **Security** | Security-related changes |

## Example Release

```bash
# 1. Verify everything works
make all

# 2. Edit CHANGELOG.md (move [Unreleased] to [0.2.0] - 2026-02-04)
vim CHANGELOG.md

# 3. Commit
git add CHANGELOG.md
git commit -m "docs: prepare release v0.2.0"

# 4. Tag
git tag v0.2.0

# 5. Push
git push && git push --tags

# 6. Verify
pip install -e .
python -c "import ananta; print(ananta.__version__)"
```

## Hotfix Releases

For urgent fixes to a released version:

1. Create branch from the release tag: `git checkout -b hotfix/v0.2.1 v0.2.0`
2. Make the fix with tests
3. Update CHANGELOG.md with the fix under a new `[0.2.1]` section
4. Commit, tag `v0.2.1`, and push

## Pre-release Versions

For alpha/beta releases:

```bash
git tag v0.3.0a1   # Alpha 1
git tag v0.3.0b1   # Beta 1
git tag v0.3.0rc1  # Release candidate 1
```
