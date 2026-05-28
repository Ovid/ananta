.PHONY: install rebuild test test-frontend lint typecheck typecheck-examples typecheck-frontend format all loc cover

install:
	pip install -e ".[dev]"

# Recreate .venv from scratch. Use when the venv is stale (e.g. moved between
# hosts) or when `pip install -e ".[dev]"` fails due to an outdated pip.
rebuild:
	rm -rf .venv
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"
	@echo
	@echo "[ananta] .venv rebuilt. Re-activate it in your shell:"
	@echo "    source .venv/bin/activate"

# -W filter suppresses RequestsDependencyWarning from urllib3/chardet version skew in transitive deps;
# must be on the interpreter to catch import-time warnings before pytest resets filters.
test:
	python -W "ignore:urllib3:Warning" -m pytest

test-frontend:
	cd src/ananta/explorers/arxiv/frontend && NODE_OPTIONS="--disable-warning=ExperimentalWarning" npx vitest run

lint:
	ruff check src tests

typecheck:
	mypy src/ananta

# Run from examples/ with MYPYPATH=. so script_utils.py resolves as a top-level
# module (matching how the example scripts actually import it at runtime).
typecheck-examples:
	cd examples && MYPYPATH=. mypy --explicit-package-bases .

typecheck-frontend:
	cd src/ananta/explorers/shared_ui/frontend && npx tsc --noEmit

format:
	ruff format src tests
	ruff check --fix src tests

all: format lint typecheck typecheck-examples typecheck-frontend test test-frontend

cover:
	pytest --cov=src/ananta --cov-report=term-missing --cov-report=html

loc:
	@cloc src arxiv-explorer code-explorer document-explorer examples pyproject.toml Makefile \
		--exclude-dir=node_modules,dist \
		--not-match-f='package-lock\.json'
