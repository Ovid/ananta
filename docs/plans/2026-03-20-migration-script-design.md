# Migration Script — Design

## Motivation

Existing Shesha users need a path to rename their data directories after the Ananta rename. The runtime warnings tell them what to do, but a script that does it for them is friendlier.

## Script

`python -m ananta.migrate` — interactive, confirmation-based migration.

### What it migrates (auto):

- `./shesha_data/` → `./ananta_data/` (current directory)
- `~/.shesha-arxiv/` → `~/.ananta-arxiv/`
- `~/.shesha/code-explorer/` → `~/.ananta/code-explorer/`
- `~/.shesha/document-explorer/` → `~/.ananta/document-explorer/`

### What it reminds about (manual):

- Rename `SHESHA_*` env vars to `ANANTA_*` in shell config
- Rebuild Docker image: `docker build -t ananta-sandbox src/ananta/sandbox/`
- Update any `.env` files

### Flow:

1. Scan for legacy directories that exist AND whose new counterpart does NOT exist
2. If nothing found: "Nothing to migrate. You're all set."
3. If found: list them with planned renames, ask "Proceed? [y/N]"
4. On confirmation: `Path.rename()` each one (creating parent dirs if needed)
5. Print summary + manual reminders

No flags, no options, no dry-run mode. Handful of users, one-time script.

## README

Add "Migrating from Shesha" section after installation, documenting the command and manual steps.
