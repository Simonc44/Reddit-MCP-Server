.PHONY: install dev test test-live lint typecheck coverage run

## Install runtime dependencies (pip)
install:
	pip install -r requirements.txt

## Create the dev environment with uv (installs everything into .venv/)
dev:
	uv sync --extra dev

## Run unit tests (offline, no browser needed)
test:
	uv run pytest -m "not integration"

## Run live tests against reddit.com (needs Chromium + network)
test-live:
	REDDIT_LIVE_TESTS=1 uv run pytest -m integration

## Lint with ruff
lint:
	uv run ruff check server.py tests/

## Type check with mypy (server + tests)
typecheck:
	uv run mypy server.py tests/

## Unit tests with coverage report (fails under 95%)
coverage:
	uv run pytest -m "not integration" --cov=server --cov-report=term-missing --cov-fail-under=95

## Start the MCP server (stdio)
run:
	uv run python server.py
