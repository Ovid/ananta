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

| Highest category present | Pre-1.0 bump | Post-1.0 bump |
|---|---|---|
| `Removed`, or any entry mentions "breaking change" | minor | **major** |
| `Added`, `Changed`, or `Deprecated` | minor | minor |
| Only `Fixed` and/or `Security` | patch | patch |

**Step 3: Compute suggested version**

Apply the bump to the current version. Example: current v0.15.0, bump minor → v0.16.0.

**Step 4: Present to user**

```
Suggested version: vX.Y.Z (BUMP_TYPE bump)

Justification:
- [Unreleased] contains "CATEGORY" entries
- Current version: vCURRENT
- Rules: CATEGORY → BUMP_TYPE bump

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
