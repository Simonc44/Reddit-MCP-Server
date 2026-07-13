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
git clone https://github.com/YOUR_USERNAME/reddit-mcp-server.git
cd reddit-mcp-server
```

### 2. Configure Your Virtual Environment
Create a Python virtual environment to isolate project dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

### 3. Install Dependencies
Install the required packages in development mode:
```bash
pip install -r requirements.txt
```

### 4. Install Playwright Browsers
Download the required Playwright Chromium headless engine:
```bash
playwright install chromium
```

### 5. Running and Debugging Local Changes
To run and test the server dynamically during development:
```bash
# Start in MCP Dev Mode (using FastMCP inspector)
fastmcp dev server.py
```
This will spin up a local development UI allowing you to invoke tools and inspect inputs/outputs manually.

---

## Coding Style & Best Practices

To maintain high code quality, please adhere to the following guidelines:

### Python Standards
- Follow [PEP 8](https://peps.python.org/pep-0008/) naming conventions and formatting guidelines.
- Use type hints for all function signatures and tool definitions.
- Keep tool signatures clean and clearly documented using descriptive docstrings, as LLMs use these docstrings to understand how to call tools.

### Playwright Web Scraping
- **Efficiency First:** Always block assets that are not required for text extraction (images, videos, external widgets).
- **Selector Robustness:** Implement multi-fallback CSS selectors using native `shreddit-*` elements or generic CSS classes where appropriate to minimize the impact of frontend changes.
- **Rate Limit Consideration:** Add sensible sleep times (`time.sleep`) between consecutive requests if scanning multiple subreddits to respect Reddit's servers and avoid IP bans.

---

## Pull Request Process

1. **Create a Branch:** Create a branch with a descriptive name (e.g., `feat/add-sentiment-analysis` or `fix/comment-selector`).
2. **Commit Often, Document Well:** Write clear commit messages.
3. **Verify Your Changes:** Ensure your code works and is free of syntax/import errors. Test it locally using `fastmcp dev server.py`.
4. **Push and Submit PR:** Push your branch to your fork and submit a Pull Request to the main branch of the parent repository.
5. **Review:** Maintainers will review your PR and provide feedback. Once approved, your changes will be merged!

---

## Report Bugs and Suggest Features

If you encounter a bug or have a suggestion, please open an **Issue** on GitHub. Be sure to include:
- A clear, concise title.
- Steps to reproduce (for bugs).
- What you expected to happen vs. what actually happened.
- Details about your environment (OS, Python version, Playwright version).
- Context screenshots or error logs if available.
