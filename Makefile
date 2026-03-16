.PHONY: install test test-frontend lint typecheck format all loc cover

install:
	pip install -e ".[dev]"

test:
	pytest

test-frontend:
	cd src/shesha/experimental/web/frontend && npx vitest run

lint:
	ruff check src tests
	cd src/shesha/experimental/shared/frontend && npx tsc --noEmit

typecheck:
	mypy src/shesha

format:
	ruff format src tests
	ruff check --fix src tests

all: format lint typecheck test test-frontend

cover:
	pytest --cov=src/shesha --cov-report=term-missing --cov-report=html

loc:
	@cloc src arxiv-explorer code-explorer document-explorer examples pyproject.toml Makefile \
		--exclude-dir=node_modules,dist \
		--not-match-f='package-lock\.json'
