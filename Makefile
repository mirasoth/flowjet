# Makefile for fj-ai
UV_RUN ?= uv run

.PHONY: sync sync-dev format format-check lint lint-fix \
	test test-unit test-coverage build clean help

help:
	@echo "fj-ai"
	@echo ""
	@echo "  make sync            - Sync dependencies"
	@echo "  make sync-dev        - Sync with dev extras"
	@echo "  make format          - Format with ruff"
	@echo "  make format-check    - Check formatting (CI)"
	@echo "  make lint            - Lint with ruff"
	@echo "  make lint-fix        - Auto-fix lint issues"
	@echo "  make test            - Run unit tests"
	@echo "  make test-unit       - Run unit tests"
	@echo "  make test-coverage   - Tests with coverage"
	@echo "  make build           - Build dist/"
	@echo "  make clean           - Remove build artifacts"

sync:
	uv sync

sync-dev:
	uv sync --extra dev

format:
	$(UV_RUN) ruff format src/ tests/

format-check:
	$(UV_RUN) ruff format --check src/ tests/

lint:
	$(UV_RUN) ruff check src/ tests/

lint-fix:
	$(UV_RUN) ruff check --fix src/ tests/

test test-unit:
	$(UV_RUN) python -m pytest tests/unit/ -q

test-coverage:
	$(UV_RUN) python -m pytest tests/unit/ --cov=fj_ai --cov-report=term-missing --cov-report=xml

build:
	rm -rf dist/
	uv build

clean:
	rm -rf dist/ build/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/ coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
