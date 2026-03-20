# Changelog & Versioning Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reconstruct version history for 13 unversioned branch merges, create a `/release` skill to prevent this from recurring, and update CLAUDE.md with new versioning rules.

**Architecture:** All work is docs/config (no code changes). The CHANGELOG.md is rewritten from scratch for post-v0.9.0 history using git log analysis. A Claude Code skill replaces the manual release workflow. CLAUDE.md encodes the new rules.

**Tech Stack:** Git, Markdown, Claude Code skills

**TDD Exception:** Per CLAUDE.md, TDD is not required for config/docs changes. All tasks in this plan are docs/config.

---

### Task 1: Analyze all 13 branches and draft changelog entries

This task can be parallelized — each branch analysis is independent. Use `superpowers:dispatching-parallel-agents` to analyze branches concurrently.

**For each branch, the analysis agent should:**

1. Run the git commands below to see what the branch changed
2. Categorize changes into keepachangelog 1.1.0 categories: Added, Changed, Deprecated, Removed, Fixed, Security
3. Write human-readable changelog entries (not commit messages — describe what changed and why it matters)
4. Return the categorized entries

**Branch analysis commands (substitute MERGE_SHA for each branch):**

```bash
# See commit messages
git log MERGE_SHA^..MERGE_SHA --no-merges --oneline

# See files changed
git diff --stat MERGE_SHA^...MERGE_SHA

# See actual changes (for understanding what was done)
git diff MERGE_SHA^...MERGE_SHA
```

**Branches to analyze:**

| # | Branch | Merge SHA | Merge Date |
|---|--------|-----------|------------|
| 1 | ovid/arxiv | 6e4cfa0 | 2026-02-12 |
| 2 | ovid/arxiv-explorer | 704aad3 | 2026-02-13 |
| 3 | ovid/code-explorer | d3dfd76 | 2026-02-17 |
| 4 | ovid/shared-code | 358963d | 2026-02-18 |
| 5 | ovid/arxiv-markdown | f444d1f | 2026-02-28 |
| 6 | ovid/ux-fixes | 5a29ebe | 2026-03-05 |
| 7 | ovid/document-explorer | 6c15944 | 2026-03-06 |
| 8 | ovid/refactor-explorers | 573de39 | 2026-03-16 |
| 9 | ovid/deep-research | df9a929 | 2026-03-18 |
| 10 | ovid/augmented-knowledge | 91fdcde | 2026-03-18 |
| 11 | ovid/architecture (1st) | 053b669 | 2026-03-18 |
| 12 | ovid/architecture (2nd) | 285bbc9 | 2026-03-20 |
| 13 | ovid/accidentally-shared-prompts | 8c7a59a | 2026-03-20 |

**Changelog entry style (match existing):**
- Lead with the user-visible behavior change, not the implementation detail
- Bold feature names for major additions (e.g., **Document Explorer**)
- Technical details in parentheses or after em-dash when helpful
- One bullet per distinct change; group sub-items with indentation

**Category assignment rules:**
- Added: wholly new features, new CLI options, new UI elements
- Changed: modifications to existing behavior, API changes, refactoring that changes interfaces
- Deprecated: features marked for future removal
- Removed: features deleted
- Fixed: bug fixes
- Security: vulnerability fixes, hardening

### Task 2: Assign version numbers

**This must be done sequentially after all branch analyses are complete.**

Starting from v0.9.0, walk through each branch in order and apply the auto-increment rules:

| Highest category present | Bump |
|---|---|
| Removed, or explicit breaking change | minor |
| Added, Changed, Deprecated | minor |
| Fixed, Security only | patch |

**Step 1:** For each branch (1-13), note which categories are present from the Task 1 analysis.

**Step 2:** Compute the version chain. Example:

```
v0.9.0 (starting point)
Branch 1 has Added → minor → v0.10.0
Branch 2 has Added → minor → v0.11.0
Branch 3 has Added → minor → v0.12.0
...
Branch 6 has Fixed only → patch → v0.X.1
...
```

**Step 3:** Record the final mapping — this is needed for Tasks 3 and 7.

### Task 3: Write CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

Rewrite the file with the following structure:

**Step 1:** Write the file header:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
```

The `[Unreleased]` section should be empty (no categories) — everything on main has been released.

**Step 2:** Add the 13 versioned sections in reverse chronological order (newest first), using the version numbers from Task 2 and the entries from Task 1. Each section:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added

- Entry here

### Changed

- Entry here

### Fixed

- Entry here
```

Category ordering within each section: Added, Changed, Deprecated, Removed, Fixed, Security. Omit empty categories.

**Step 3:** Include the existing v0.1.0–v0.9.0 sections after the 13 new sections. Preserve their content but fix two format inconsistencies for keepachangelog 1.1.0 compliance:
- **v0.3.0:** Change `## [0.3.0] 2026-02-04` to `## [0.3.0] - 2026-02-04` (add missing dash before date)
- **v0.8.0:** Reorder categories so `### Added` comes before `### Changed` (currently reversed)

Remove the `_Previous entries:_` separator line that currently appears between the old `[Unreleased]` content and the older versioned sections — it's no longer needed.

**Step 4:** Add comparison links at the very bottom of the file:

```markdown
[unreleased]: https://github.com/Ovid/shesha/compare/vLATEST...HEAD
[X.Y.Z]: https://github.com/Ovid/shesha/compare/vPREVIOUS...vX.Y.Z
...
[0.9.0]: https://github.com/Ovid/shesha/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Ovid/shesha/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Ovid/shesha/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Ovid/shesha/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Ovid/shesha/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Ovid/shesha/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Ovid/shesha/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Ovid/shesha/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Ovid/shesha/releases/tag/v0.1.0
```

Replace `vLATEST` and `vPREVIOUS` with the actual version numbers from Task 2.

**Step 5:** Verify the file by checking:
- `[Unreleased]` is at the top and empty
- All 13 new sections are present in reverse chronological order
- v0.1.0–v0.9.0 sections are preserved
- Comparison links cover every version
- No duplicate entries

**Step 6: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: rewrite changelog with versioned sections for 13 merged branches"
```

### Task 4: Write the `/release` skill

**Files:**
- Create: `~/.claude/skills/release/SKILL.md`

**Step 1:** Create the directory:

```bash
mkdir -p ~/.claude/skills/release
```

**Step 2:** Write `~/.claude/skills/release/SKILL.md` with the following content:

```markdown
---
name: release
description: Merge a feature branch to main with semantic versioning, changelog finalization, and git tagging via git done -y
---

# Release

Merge the current feature branch to main with proper versioning. This is the **only** sanctioned way to merge feature branches.

## Arguments

`/release` accepts optional arguments:
- `/release` — standard release flow
- `/release --ignore-dirty` — proceed despite uncommitted changes

## Preconditions

Check ALL of the following before proceeding. If any fail, stop and report the failure.

1. **Clean working tree:** Run `git status --porcelain`. If output is non-empty, fail with:
   "Working tree has uncommitted changes. Commit or stash them first, or re-run with `/release --ignore-dirty`."
   Exception: if `--ignore-dirty` was passed, skip this check.

2. **On a feature branch:** Run `git rev-parse --abbrev-ref HEAD`. If the result is `main` or `master`, fail with:
   "You're on the main branch. Switch to a feature branch first."

3. **Tests pass:** Run `make all`. If it fails, stop and report the failures. Do not proceed.

4. **CHANGELOG.md exists:** Verify `CHANGELOG.md` exists in the repo root.

## Determine Release Type

Parse `CHANGELOG.md` and look at the `## [Unreleased]` section.

**If `[Unreleased]` is empty (no entries under it before the next `## ` heading):**
- Inform the user: "No user-visible changes in [Unreleased]. This will merge without a version bump."
- Ask: "Proceed with a plain merge (no version, no tag)? [y/N]"
- If confirmed: run `git done -y`, print branch cleanup suggestion, and stop.
- If declined: abort.

**If `[Unreleased]` has entries, continue to versioning.**

## Version Suggestion

**Step 1: Get current version**

```bash
git tag --sort=-v:refname | grep '^v[0-9]' | head -1
```

Parse as major.minor.patch (strip the leading `v`).

**Step 2: Determine bump type**

Scan the `### ` headings under `[Unreleased]`:
- If `Removed` is present, or any entry mentions "breaking change" → **minor** (pre-1.0) or **major** (post-1.0)
- If `Added`, `Changed`, or `Deprecated` is present → **minor**
- If only `Fixed` and/or `Security` → **patch**

**Step 3: Compute suggested version**

Apply the bump to the current version. Example: current v0.15.0, bump minor → v0.16.0.

**Step 4: Present to user**

```
Suggested version: vX.Y.Z (BUMP_TYPE bump)

Justification:
- [Unreleased] contains "CATEGORY" entries
- Current version: vCURRENT
- Pre-1.0 rules: CATEGORY → BUMP_TYPE bump

[Unreleased] entries that will be included:
SUMMARY_OF_ENTRIES

Accept this version? Or suggest an alternative:
```

**Step 5: Validate user response**

- If user accepts → proceed
- If user proposes an alternative version:
  - Parse it as semver
  - Reject if ≤ current version: "Version must be greater than current (vCURRENT)"
  - If proposed version is ≥ 1.0.0 and current is < 1.0.0: warn "This will mark the project as stable (1.0+). Are you sure?"
  - If valid → use the proposed version

## Finalize Changelog

**Step 1:** Reorder categories under `[Unreleased]` to match keepachangelog 1.1.0 ordering:
Added → Changed → Deprecated → Removed → Fixed → Security

**Step 2:** Replace `## [Unreleased]` heading and its entries with:

```markdown
## [Unreleased]

## [X.Y.Z] - YYYY-MM-DD

(entries moved here, properly ordered)
```

Where YYYY-MM-DD is today's date.

**Step 3:** Update comparison links at the bottom of the file:
- Change `[unreleased]` link to compare against the new version tag
- Add a new comparison link for the new version comparing against the previous version

**Step 4:** Commit on the feature branch:

```bash
git add CHANGELOG.md
git commit -m "release: vX.Y.Z"
```

## Merge

Run `git done -y`.

If it fails, inform the user:
"git done failed. The release commit is on your branch. To retry: `git reset HEAD~1`, fix the issue, then run `/release` again."

Do NOT proceed to tagging if `git done` fails.

## Tag and Push

After `git done -y` succeeds (you are now on main):

```bash
git tag vX.Y.Z
git push --tags
```

## Cleanup Suggestion

Print:
```
Release vX.Y.Z complete!

You can now clean up the branch:
  git branch -d BRANCH_NAME
  git push origin :BRANCH_NAME
```

Do NOT auto-delete the branch.
```

**Step 3:** Verify the skill is recognized:

```bash
ls -la ~/.claude/skills/release/SKILL.md
```

**Step 4: Commit** (this is a repo-external file, so no git commit — just verify it exists)

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (lines 91–118, the "Changelog & Versioning" section)

**Step 1:** Replace the entire "Changelog & Versioning" section (lines 91–118) with:

```markdown
## Changelog & Versioning

**CHANGELOG.md must be updated with every user-visible change.** Format: [keepachangelog 1.1.0](https://keepachangelog.com/en/1.1.0/).

### Adding Changelog Entries

Add entries under `[Unreleased]` using these categories (in this order):
- **Added** — New features
- **Changed** — Changes to existing functionality
- **Deprecated** — Features to be removed in future
- **Removed** — Removed features
- **Fixed** — Bug fixes
- **Security** — Security-related changes

Omit empty categories. Entries should describe user-visible behavior changes, not implementation details.

### Merging Feature Branches

**Use `/release` to merge feature branches. Never use bare `git done`.**

`/release` handles: changelog finalization, semantic version suggestion, `git done -y`, tagging, and push. It is the only sanctioned merge path for feature branches.

### Version Auto-Increment Rules

Version numbers are derived from git tags via `hatch-vcs`. The `/release` skill suggests versions based on changelog categories:

**Pre-1.0 (current):**
| Highest category present | Bump |
|---|---|
| Removed, or explicit breaking change | minor |
| Added, Changed, Deprecated | minor |
| Fixed, Security only | patch |

**Post-1.0:** Removed/breaking → major. Otherwise same as above.

Comparison links at the bottom of CHANGELOG.md are mandatory. Format:
```
[unreleased]: https://github.com/Ovid/shesha/compare/vLATEST...HEAD
[X.Y.Z]: https://github.com/Ovid/shesha/compare/vPREVIOUS...vX.Y.Z
```

### git

CRITICAL: git commit messages MUST be plain text. Never do things similar to `git commit -m "$(cat <<'COMMITEOF'`
```

**Step 2:** Verify the file is valid markdown and the section reads correctly.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with /release workflow and keepachangelog 1.1.0 rules"
```

### Task 6: Merge the bootstrap branch

**This is the bootstrap exception — the last time `git done` is used directly, before `/release` exists.**

**Step 1:** Verify all prior tasks are committed:

```bash
git log --oneline -5
```

Expected: commits for CHANGELOG.md rewrite and CLAUDE.md update on `ovid/changelog`.

**Step 2:** Run `git done -y`:

```bash
git done -y
```

This will: checkout main, fetch, ff-only merge origin/main, rebase `ovid/changelog` on main, force-push-with-lease the branch, checkout main, merge `--no-ff`, push main.

**Step 3:** Verify you are now on main:

```bash
git rev-parse --abbrev-ref HEAD
# Expected: main
```

**Step 4:** Verify the merge landed:

```bash
git log --oneline -3
```

Expected: a merge commit for `ovid/changelog` at HEAD.

### Task 7: Create retroactive tags

**This task runs on main after the merge in Task 6.**

**Step 1:** Verify you are on main:

```bash
git rev-parse --abbrev-ref HEAD
# Expected: main
```

**Step 2:** Create tags for all 13 historical versions on their merge commits. Use the version numbers determined in Task 2:

```bash
git tag vVERSION MERGE_SHA
```

For each of the 13 branches (substitute actual version numbers from Task 2):

| Merge SHA | Branch | Tag |
|-----------|--------|-----|
| 6e4cfa0 | ovid/arxiv | vX.Y.Z |
| 704aad3 | ovid/arxiv-explorer | vX.Y.Z |
| d3dfd76 | ovid/code-explorer | vX.Y.Z |
| 358963d | ovid/shared-code | vX.Y.Z |
| f444d1f | ovid/arxiv-markdown | vX.Y.Z |
| 5a29ebe | ovid/ux-fixes | vX.Y.Z |
| 6c15944 | ovid/document-explorer | vX.Y.Z |
| 573de39 | ovid/refactor-explorers | vX.Y.Z |
| df9a929 | ovid/deep-research | vX.Y.Z |
| 91fdcde | ovid/augmented-knowledge | vX.Y.Z |
| 053b669 | ovid/architecture (1st) | vX.Y.Z |
| 285bbc9 | ovid/architecture (2nd) | vX.Y.Z |
| 8c7a59a | ovid/accidentally-shared-prompts | vX.Y.Z |

Also tag the `ovid/changelog` merge commit itself (the bootstrap release).

**Step 3:** Verify all tags:

```bash
git tag --sort=v:refname | grep '^v'
```

Should show v0.1.0 through v0.9.0 (existing) plus all 13+ new tags.

**Step 4:** Push all tags:

```bash
git push --tags
```

**Step 5:** Verify comparison links work by spot-checking one:

```bash
echo "https://github.com/Ovid/shesha/compare/v0.9.0...v0.10.0"
```

Confirm the URL structure is correct (user can open in browser).
