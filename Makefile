.PHONY: install test test-frontend lint typecheck typecheck-frontend format all loc cover

install:
	pip install -e ".[dev]"

# -W filter suppresses RequestsDependencyWarning from urllib3/chardet version skew in transitive deps;
# must be on the interpreter to catch import-time warnings before pytest resets filters.
test:
	python -W "ignore:urllib3:Warning" -m pytest

test-frontend:
	cd src/ananta/experimental/web/frontend && NODE_OPTIONS="--disable-warning=ExperimentalWarning" npx vitest run

lint:
	ruff check src tests

typecheck:
	mypy src/ananta

typecheck-frontend:
	cd src/ananta/experimental/shared/frontend && npx tsc --noEmit

format:
	ruff format src tests
	ruff check --fix src tests

all: format lint typecheck typecheck-frontend test test-frontend

cover:
	pytest --cov=src/ananta --cov-report=term-missing --cov-report=html

loc:
	@cloc src arxiv-explorer code-explorer document-explorer examples pyproject.toml Makefile \
		--exclude-dir=node_modules,dist \
		--not-match-f='package-lock\.json'
