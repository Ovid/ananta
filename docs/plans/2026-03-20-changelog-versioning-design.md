# Changelog & Versioning Overhaul

## Problem

Since v0.9.0 (2026-02-10), 13 feature branches have been merged to main — each representing a release — but none received a version tag or its own changelog section. The `[Unreleased]` section has accumulated entries that partially cover these changes, but with gaps and no version boundaries. The CLAUDE.md release workflow is documented but not enforced.

## Goals

1. **Retroactively version the 13 merged branches** — each merge = a release with its own version and changelog section
2. **Create a `/release` skill** — replaces bare `git done -y` as the only way to merge feature branches
3. **Update CLAUDE.md** — make changelog updates mandatory and `/release` the sole merge path
4. **Full keepachangelog 1.1.0 compliance** — proper category ordering, comparison links, format

## Deliverables

### 1. Historical Reconciliation

Rewrite CHANGELOG.md from scratch for all changes since v0.9.0. Discard the current `[Unreleased]` section and reconstruct versioned sections for each of the 13 merged branches by analyzing git history. Each branch gets its own version number determined by auto-increment rules.

**Version numbers are a sequential dependency:** branch 1 increments from v0.9.0, branch 2 increments from branch 1's version, and so on. All 13 versions must be computed as an ordered batch.

**Branches to version (oldest → newest):**

| # | Branch | Merge Date | Commits | Scope |
|---|--------|-----------|---------|-------|
| 1 | ovid/arxiv | 2026-02-12 | 66 | arXiv TUI, search, citations |
| 2 | ovid/arxiv-explorer | 2026-02-13 | 123 | Web interface for arXiv Explorer |
| 3 | ovid/code-explorer | 2026-02-17 | 64 | Code Explorer web app |
| 4 | ovid/shared-code | 2026-02-18 | 40 | Shared web infrastructure extraction |
| 5 | ovid/arxiv-markdown | 2026-02-28 | 3 | Inline paper citations, markdown |
| 6 | ovid/ux-fixes | 2026-03-05 | 10 | UX bug fixes |
| 7 | ovid/document-explorer | 2026-03-06 | 102 | Document Explorer web app |
| 8 | ovid/refactor-explorers | 2026-03-16 | 19 | Shared components, unified API routes |
| 9 | ovid/deep-research | 2026-03-18 | 27 | "More" button, deeper analysis |
| 10 | ovid/augmented-knowledge | 2026-03-18 | 34 | Background knowledge toggle |
| 11 | ovid/architecture (1st) | 2026-03-18 | 16 | Architecture fixes |
| 12 | ovid/architecture (2nd) | 2026-03-20 | 146 | Architecture review, PARTIAL() callable |
| 13 | ovid/accidentally-shared-prompts | 2026-03-20 | 2 | Prompt scope fix |

**Process per branch:**
1. `git diff --stat <merge>^...<merge>` to see files changed
2. `git log <merge>^..<merge> --no-merges --oneline` to see commit messages
3. Categorize changes into Added/Changed/Deprecated/Removed/Fixed/Security
4. Apply auto-increment rules to the *previous branch's version* to determine this branch's version number
5. Write the versioned section

**Auto-increment rules (pre-1.0):**

| Highest category present | Bump |
|---|---|
| Removed, or explicit breaking change | minor |
| Added, Changed, Deprecated | minor |
| Fixed, Security | patch |

Post-1.0, Removed/breaking becomes major.

**Category ordering per keepachangelog 1.1.0:**
Added → Changed → Deprecated → Removed → Fixed → Security

**Comparison links at bottom of file:**
```
[unreleased]: https://github.com/Ovid/shesha/compare/vLATEST...HEAD
[X.Y.Z]: https://github.com/Ovid/shesha/compare/vPREVIOUS...vX.Y.Z
...
[0.1.0]: https://github.com/Ovid/shesha/releases/tag/v0.1.0
```

**End state:** `[Unreleased]` section is empty (all changes on main have been released). Versions v0.1.0–v0.9.0 sections are preserved as-is from the existing changelog.

### 2. `/release` Skill

A global Claude Code skill at `~/.claude/skills/release/SKILL.md` invoked via `/release`.

**Precondition checks:**
- Working tree must be clean (`git status --porcelain` is empty) — fail with an error if uncommitted changes exist, unless the user explicitly says to ignore them
- Must be on a feature branch (not main/master)
- All tests pass (`make all`) — hard gate, no bypass
- `[Unreleased]` section in CHANGELOG.md checked (see empty-section handling below)

**Empty `[Unreleased]` handling:**
If `[Unreleased]` is empty (no user-visible changes), the skill falls back to a plain merge:
- Inform user: "No user-visible changes — this will merge without a version bump. Proceed?"
- If confirmed, run `git done -y` without tagging or changelog modification
- If declined, abort

**Workflow (with user-visible changes):**

```
/release
  ├─ Validate preconditions (clean tree, feature branch, make all)
  ├─ Parse current version from git tags
  ├─ Parse [Unreleased] categories from CHANGELOG.md
  ├─ Auto-suggest version (rules above)
  ├─ Present suggestion + justification to user
  │   └─ User accepts or counter-proposes
  │       └─ Reject if proposed version ≤ current
  ├─ Update CHANGELOG.md on the feature branch:
  │   ├─ Move [Unreleased] entries → [X.Y.Z] - YYYY-MM-DD
  │   ├─ Add fresh ## [Unreleased] header
  │   ├─ Update comparison links at bottom
  │   └─ Enforce category ordering
  ├─ Commit on branch: "release: vX.Y.Z"
  ├─ Run: git done -y
  │   └─ If fails → the release commit is on the branch
  │       but not on main. User can git reset HEAD~1
  │       and retry. No partial state on main.
  ├─ Now on main — tag: git tag vX.Y.Z
  ├─ Push tag: git push --tags
  └─ Print branch cleanup suggestion (matching git done behavior):
      "You can now clean up with:
       git branch -d <branch>
       git push origin :<branch>"
```

**Key design choice:** The changelog update is committed on the feature branch (it's part of the release work). Only the tag happens on main after merge. If `git done -y` fails, the release commit lives on the branch and can be trivially reverted with `git reset HEAD~1`.

**Version suggestion presentation:**
```
Suggested version: v0.15.0 (minor bump)

Justification:
- [Unreleased] contains "Added" entries (new features)
- Current version: v0.14.1
- Pre-1.0 rules: Added → minor bump

Accept this version? Or suggest an alternative:
```

**Validation rules:**
- Proposed version must be > current version (compared as semver tuples)
- If user proposes a version, accept it as long as it's > current
- Never auto-accept a major bump to 1.0.0+ — always flag this for explicit confirmation

### 3. CLAUDE.md Updates

Replace the current "Changelog & Versioning" section with:

**Key rules to encode:**
- CHANGELOG.md must be updated under `[Unreleased]` with every user-visible change (already there, reinforce)
- Category ordering: Added, Changed, Deprecated, Removed, Fixed, Security
- Format: [keepachangelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
- `/release` is the **only** way to merge feature branches — never use bare `git done`
- Version auto-increment rules documented inline
- Comparison links are mandatory at the bottom of CHANGELOG.md
- Remove the manual 5-step release workflow (replaced by `/release`)
- Keep the git commit message rule (plain text, no heredoc tricks)

### 4. Retroactive Git Tags

After the changelog is reconciled, create tags for all 13 historical versions on their respective merge commits:

```bash
git tag v0.10.0 6e4cfa0   # ovid/arxiv
git tag v0.11.0 704aad3   # ovid/arxiv-explorer
# ... etc for all 13
git push --tags
```

Exact version numbers TBD during reconciliation (depends on sequential category analysis of each branch).

## Implementation Order

All work happens on the `ovid/changelog` branch. This is the **bootstrap exception** — the last release that uses `git done -y` directly, before `/release` exists.

1. **Reconcile CHANGELOG.md** — rewrite from scratch using git history for all 13 branches, compute version numbers as an ordered batch, add comparison links
2. **Write `/release` skill** — `~/.claude/skills/release/SKILL.md`
3. **Update CLAUDE.md** — new versioning rules
4. **Merge via `git done -y`** — bootstrap exception, last time this is used directly
5. **Create retroactive git tags on main** — tag each of the 13 historical merge commits with its version, plus tag the `ovid/changelog` merge itself
6. **Push tags** — `git push --tags`

## Out of Scope

- CI enforcement of changelog updates (can be added later as a pre-commit hook)
- Automated changelog generation from commit messages (we want human-written entries)
- Version file in source code (hatch-vcs derives from tags)

## Pushback Reviews

### Round 1 (2026-03-20)

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| 1 | Changelog committed on branch before `git done` — partial state if merge fails | Serious | Changelog update moved to main after `git done` succeeds |
| 2 | Plan auto-deletes branch, but `git done` deliberately leaves this to user | Serious | Print cleanup suggestion, don't auto-delete |
| 3 | Security-only fixes bumped to minor unnecessarily | Moderate | Security treated like Fixed for bump purposes (patch) |
| 4 | No path for branches with no user-visible changes | Moderate | Fall back to plain `git done -y` with confirmation |
| 5 | `make all` as precondition is slow | Moderate | Kept as hard gate — safety over speed |
| 6 | Retroactive tags may surprise existing clones via `hatch-vcs` | Minor | Accepted — version history more valuable than edge case |
| + | Uncommitted changes not checked | — | Added: fail unless user explicitly overrides |
| + | Skill path wrong (`.claude/skills/release.md`) | — | Fixed: `~/.claude/skills/release/SKILL.md` |

### Round 2 (2026-03-20)

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| 1 | Release commit directly on main after `git done` pushes — two pushes, window of inconsistency | Serious | Two-phase: changelog committed on branch, only tag on main |
| 2 | Existing `[Unreleased]` entries need redistribution across 13 versions | Moderate | Start from scratch — rewrite all entries from git history |
| 3 | Implementation order has chicken-and-egg: need `/release` to merge, but `/release` doesn't exist yet | Moderate | Feature branch `ovid/changelog` merged with `git done -y` as bootstrap exception |
| 4 | Version numbers are sequential dependencies, not independent | Minor | Made batch computation explicit in plan |
