# Contributing to Reddit MCP Server

We're excited that you want to contribute to the Reddit MCP Server! This document outlines the guidelines and best practices for developing and contributing to this project.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [How Can I Contribute?](#how-can-i-contribute)
3. [Setting Up Your Local Environment](#setting-up-your-local-environment)
4. [Coding Style & Best Practices](#coding-style--best-practices)
5. [Pull Request Process](#pull-request-process)
6. [Report Bugs and Suggest Features](#report-bugs-and-suggest-features)

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful, welcoming, and collaborative environment. Please treat all contributors with respect and professionalism.

---

## How Can I Contribute?

There are many ways you can help improve the Reddit MCP Server:
- **Reporting Bugs:** Finding issues and describing them clearly.
- **Suggesting Features:** Proposing new tools or algorithms (e.g., enhanced sentiment analysis).
- **Writing Code:** Fixing open bugs, refactoring, or implementing new features.
- **Improving Selectors:** Fixing scraping selectors when Reddit updates its DOM structure.
- **Writing Tests:** Enhancing our testing capabilities to ensure reliability.
- **Documentation:** Enhancing README, adding comments, or translations.

---

## Setting Up Your Local Environment

To work on this project locally, follow these steps:

### 1. Fork and Clone
Fork the repository and clone your fork locally:
```bash
git clone https://github.com/Simonc44/Reddit-MCP-Server.git
cd Reddit-MCP-Server
```

### 2. Install Dependencies
We recommend [uv](https://docs.astral.sh/uv/) — it creates a reproducible `.venv/` from `uv.lock` in one command:
```bash
uv sync --extra dev
```
If you prefer pip:
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Install Playwright Chromium (only needed for the *live* tests)
```bash
playwright install chromium
```
None of the offline unit tests need a browser.

### 4. Develop
A `Makefile` wraps the common tasks — everything runs through the `.venv/` handled by uv:

```bash
make dev          # install dev dependencies
make lint         # ruff (fast)
make typecheck    # mypy over server.py and tests/
make test         # 133 offline unit tests (no browser, no network)
make coverage     # offline tests + coverage gate (100 %)
make run          # start the MCP server on stdio
make test-live    # live tests against real reddit.com (needs Chromium)
```

To inspect the tools interactively during development, run FastMCP's dev UI:
```bash
uv run fastmcp dev server.py
```

---

## Coding Style & Best Practices

To maintain high code quality, please adhere to the following guidelines:

### Python Standards
- Follow [PEP 8](https://peps.python.org/pep-0008/); the project uses [ruff](https://docs.astral.sh/ruff/) (run `make lint`).
- Add full type hints to all signatures (mypy runs in CI — `make typecheck` must stay green).
- Keep tool signatures clean and well documented in docstrings — LLMs read them to decide how to call tools.
- New logic that does not need a browser belongs in a small pure function so it can be unit-tested offline.

### Tests
- Add offline unit tests for any new logic in `tests/` (fakes for the browser live in `tests/fakes.py`). The offline suite targets **100 % coverage** (`make coverage`).
- If you change scraping selectors, extend `tests/test_integration.py` and verify locally with `REDDIT_LIVE_TESTS=1 make test-live`.
- Keep `make lint`, `make typecheck` and `make test` green before opening a PR.

### Playwright Web Scraping
- **Efficiency First:** Always block assets that are not required for text extraction (images, videos, external widgets).
- **Selector Robustness:** Implement multi-fallback CSS selectors using native `shreddit-*` elements or generic CSS classes where appropriate to minimize the impact of frontend changes.
- **Rate Limit Consideration:** Add sensible sleep times (`time.sleep`) between consecutive requests if scanning multiple subreddits to respect Reddit's servers and avoid IP bans.
- **Failures → `errors` keys:** tools surface partial failures in an `errors` list rather than raising, so the AI client keeps a useful response.

---

## Pull Request Process

1. **Create a Branch:** Create a branch with a descriptive name (e.g., `feat/sentiment-analysis` or `fix/comment-selector`).
2. **Commit Often, Document Well:** Write clear commit messages and update `CHANGELOG.md` under the **Unreleased** section.
3. **Verify Your Changes:** run `make lint`, `make typecheck` and `make test` (and `make coverage`). CI runs exactly these, plus the coverage gate, on Python 3.10–3.12.
4. **Push and Submit PR:** Push your branch to your fork and submit a Pull Request to `main`.
5. **Review:** Maintainers will review and merge. Before merging, maintainers ensure CI is green and may trigger the live tests workflow if selectors changed.
   - A **live tests** workflow runs against the real Reddit website (opt-in/`workflow_dispatch`). If you touch selectors, ask a maintainer to trigger it before merge.

---

## Report Bugs and Suggest Features

> **Before you report a scraping bug**: run `REDDIT_LIVE_TESTS=1 make test-live` first. If it fails, Reddit probably changed its DOM — please include the failure output in the issue so we can update the selectors.


If you encounter a bug or have a suggestion, please open an **Issue** on GitHub. Be sure to include:
- A clear, concise title.
- Steps to reproduce (for bugs).
- What you expected to happen vs. what actually happened.
- Details about your environment (OS, Python version, Playwright version).
- Context screenshots or error logs if available.
