# Development Guide

## GitHub Copilot Setup

GitHub Copilot can help you work on Ananta if it is configured with the same
context and guardrails used by the project.

### 1) Install Copilot in your IDE

- **VS Code**: Install the "GitHub Copilot" and "GitHub Copilot Chat" extensions.
- **JetBrains**: Install the "GitHub Copilot" plugin.

Then sign in with your GitHub account that has Copilot enabled.

### 2) Add repository instructions

This repo ships with Copilot guidance at `.github/copilot-instructions.md`.
Most IDEs pick this up automatically, but if yours does not, open the file and
reference it when starting a Copilot Chat session.

### 3) Keep Copilot aligned with project rules

- **TDD is mandatory**. Write a failing test before implementation changes.
- Make the **smallest possible change** that solves the problem.
- Prefer existing patterns and modules in `src/ananta/`.
- Do not introduce new dependencies unless absolutely necessary.

### 4) Recommended workflow

```bash
pip install -e ".[dev]"
ruff check src tests
mypy src/ananta
pytest
```

### 5) Optional: Reduce noisy context

If Copilot suggestions are noisy, consider excluding large or irrelevant paths
in your IDE settings:

- `test-datasets/`
- `docs/plans/`
- `__pycache__/`

## Getting Help

- Project overview: `README.md`
- Architecture and rules: `CLAUDE.md`
