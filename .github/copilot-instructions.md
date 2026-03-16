# GitHub Copilot Instructions

Use these guidelines when reviewing code for Shesha.

## Code Review Guidelines

**Verify before commenting:**
- Read the actual code before claiming it does something wrong.
- If citing a bug, quote the exact line - don't paraphrase.
- Check that the scenario you're warning about can actually occur.

**Match project conventions:**
- Check how similar code is handled elsewhere before suggesting changes.
- Don't apply generic "best practices" that conflict with existing patterns, unless those patterns are clearly wrong (security issues, bugs, deprecated APIs).
- Consistency with the codebase trumps theoretical ideals.

**Avoid hypotheticals:**
- Focus on real inputs and actual usage, not invented edge cases.
- If a scenario requires unlikely conditions, it's probably not worth flagging.

## Project Conventions

- Follow **MANDATORY TDD** from [CLAUDE.md](../CLAUDE.md): write a failing test first, then implement minimal code.
- Prefer minimal, focused changes that match existing patterns in `src/shesha/`.
- Keep security boundaries intact: document content is untrusted, and sandbox code must stay isolated.
- **Ruff isort (`I001`) splits imports that use `as` aliases** into separate `from ... import` blocks, even when they come from the same module. Do not suggest merging these — ruff will re-split them and the lint check will fail.

## Developer Workflow

- Install dev dependencies with `pip install -e ".[dev]"`.
- Use existing tools: `ruff`, `mypy`, and `pytest` (see README).
- Avoid adding new dependencies unless absolutely required.

## Helpful Context

- Read `README.md` for configuration and usage.
- Refer to `docs/DEVELOPMENT.md` for local setup and IDE guidance.
