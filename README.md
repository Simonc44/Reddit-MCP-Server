# Reddit MCP Server
---
<div align="center">

[![Latest Version](https://img.shields.io/badge/version-v0.3.0-blue.svg)](#)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/Simonc44/Reddit-MCP-Server/actions/workflows/ci.yml/badge.svg)](https://github.com/Simonc44/Reddit-MCP-Server/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](#)
[![Model Context Protocol](https://img.shields.io/badge/MCP-1.0.0-green.svg)](https://modelcontextprotocol.io)
[![Playwright](https://img.shields.io/badge/playwright-chromium-orange.svg)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>


**Your AI, plugged into Reddit. No API key. No login. Just the raw feed.**

Give Claude — or any MCP client — real-time access to Reddit: browse subreddits, pull comment threads, mine startup ideas and pain points. Built on **FastMCP** and **Playwright**, it scrapes the public web interface with a fast, headless browser. The result: live Reddit data, straight from the source, with zero setup cost.

```text
You:  "What are people complaining about in r/SaaS this week?"
AI:   ▸ 214 posts scanned · 37 pain points found · score 1260 "Paying for
      overpriced subscriptions is ridiculous" · 8 ideas over 1000 points
```
---

## What's inside

- 🔍 **Search & browse** — scan one or many subreddits with native sorting, time filters and keyword filtering
- 💬 **Comments & details** — threaded comment trees with authors, scores and depth, plus full post bodies
- 📊 **Subreddit & user intel** — description, active users, top posts; any user's public posts and karma
- 🚀 **Business opportunity radar** — scores posts for startup/pain-point potential (see the [algorithm](#opportunity-scoring-algorithm))
- ⚡ **Built for speed** — one shared browser reused across calls, an in-memory TTL cache, asset blocking, retries with backoff, anti-bot detection

## Table of Contents

1. [10-second demo](#10-second-demo)
2. [Available Tools](#available-tools)
3. [Quick Start](#quick-start)
4. [Client Configuration](#client-configuration)
   - [Claude Desktop](#claude-desktop) / [Claude Code](#claude-code)
5. [Opportunity Scoring Algorithm](#opportunity-scoring-algorithm)
6. [Configuration](#configuration)
7. [Development](#development)
8. [Docker](#docker)
9. [Troubleshooting & Limitations](#troubleshooting--limitations)
10. [Contributing](#contributing) · [Security](#security) · [License](#license)

## 10-second demo

Ask your assistant in plain language — it speaks MCP natively:

> *"Search Reddit for 'best mechanical keyboard 2025' from the last month."*

```json
{
  "total_results": 25,
  "query": "best mechanical keyboard 2025",
  "posts": [
    {
      "title": "The Keychron Q3 is criminally underrated",
      "score": 812,
      "num_comments": 143,
      "author": "keeblover42",
      "url": "https://www.reddit.com/r/MechanicalKeyboards/comments/...",
      "post_type": "self"
    }
  ]
}
```

> *"Analyze r/SaaS and r/Entrepreneur for startup pain points."*

```json
{
  "total_posts_scanned": 214,
  "high_score_ideas": 8,
  "ideas": [
    {
      "title": "Paying for overpriced subscriptions is ridiculous — someone should make a smart subscription manager",
      "opportunity_score": 1260,
      "matched_keywords": ["pay", "subscription", "should exist", "problem"],
      "url": "https://www.reddit.com/r/SaaS/comments/..."
    }
  ]
}
```

## Available Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `search_reddit` | `subreddits` (list), `sort`, `time_filter`, `limit`, `keywords` (list) | Browse posts from specific subreddits with sorting. |
| `search_reddit_query` | `query` (str), `sort`, `time_filter`, `subreddit`, `limit` | Perform a global keyword search across Reddit. |
| `get_post_comments` | `post_url` (str), `limit` | Extract threaded comments with hierarchical depth. |
| `get_post_details` | `post_url` (str) | Get full details: selftext, link, flair, metadata. |
| `get_subreddit_info` | `subreddit` (str) | Name, description, active users and top posts. |
| `get_user_posts` | `username` (str), `sort`, `limit` | Browse a user's public posts and karma. |
| `get_trending_posts` | `limit`, `time_filter` | Get the current top posts of `r/popular`. |
| `analyze_opportunities`| `subreddits` (list), `min_score`, `limit`, `keywords` (list), `sort`, `time_filter` | Identify high-potential SaaS/startup pain points. |
| `health_check` | — | Verify the server is alive (no network access). |

## Quick Start

```bash
git clone https://github.com/Simonc44/Reddit-MCP-Server.git
cd Reddit-MCP-Server

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium                          # one-time browser download
```

That's it — the server is ready. Point your MCP client at `python /path/to/server.py`.

## Client Configuration

### Claude Desktop

Add to `claude_desktop_config.json` (use absolute paths):

```json
{
  "mcpServers": {
    "reddit-mcp": {
      "command": "/path/to/your/virtualenv/bin/python",
      "args": ["/path/to/reddit-mcp-server/server.py"]
    }
  }
}
```

*Windows: use double backslashes in your paths.*

### Claude Code

```bash
claude mcp add reddit-mcp -- python /path/to/reddit-mcp-server/server.py
```

## Opportunity Scoring Algorithm

$$Score = (Upvotes \times 2) + (Comments \times 3)$$

With multipliers and bonuses:

* **High engagement** — comments/upvotes ratio $> 0.3$ → **×1.3** (or **×1.15** if $> 0.15$)
* **Monetization keywords** — $+15$ per match (`pay`, `subscription`, `SaaS`, `pricing`, …)
* **Pain-point keywords** — $+20$ per match (`problem`, `frustrated`, `broken`, `wish`, `hate`, …)
* **Dual-category bonus** — both categories detected → overall **×1.25**

Keyword matching respects **word boundaries** (`pay` matches `paying`, not `paywall`), and every idea includes its `matched_keywords` so the AI can explain its reasoning.

## Configuration

Every knob is an environment variable — no code changes needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDDIT_HEADLESS` | `true` | Run Chromium headless (`false` to watch the browser). |
| `REDDIT_VIEWPORT_WIDTH` / `REDDIT_VIEWPORT_HEIGHT` | `1280` / `900` | Browser viewport. |
| `REDDIT_USER_AGENT` | modern Chrome UA | User-agent sent to Reddit. |
| `REDDIT_NAV_TIMEOUT_MS` | `45000` | Navigation timeout (ms). |
| `REDDIT_WAIT_TIMEOUT_MS` | `15000` | Content wait timeout (ms). |
| `REDDIT_REQUEST_DELAY` | `1.5` | Pause (s) between subreddit requests — be polite to Reddit. |
| `REDDIT_MAX_SCROLLS` | `4` | Scroll iterations to trigger lazy-loaded content. |
| `REDDIT_MAX_RETRIES` | `3` | Retry attempts per page load (exponential backoff). |
| `REDDIT_RETRY_BACKOFF` | `2.0` | Base backoff (s) between retries. |
| `REDDIT_CACHE_TTL` | `300` | TTL (s) of the in-memory cache for listings (`0` disables). |
| `REDDIT_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

## Development

```bash
uv sync --extra dev      # reproducible env in .venv/ (uv is optional — pip works too)
make lint                # ruff
make typecheck           # mypy (server + tests)
make test                # pytest — 133 offline unit tests
make coverage            # pytest + coverage gate (100 %)
make test-live           # live tests against real reddit.com (needs Chromium)
make run                 # start the MCP server
```

**Tests are a first-class citizen here:**

- `tests/test_server.py`, `tests/test_scraper.py`, `tests/test_browser.py` — 133 offline tests using fake Playwright objects: **100 % coverage**, no browser, no network.
- `tests/test_integration.py` — live end-to-end tests against the real Reddit website (opt-in: `REDDIT_LIVE_TESTS=1 pytest -m integration`).

CI (`.github/workflows/ci.yml`) runs ruff, mypy and the coverage gate on Python 3.10–3.12, plus an opt-in live job.

## Docker

```bash
docker build -t reddit-mcp-server .
docker run -i --rm reddit-mcp-server
```

Chromium is installed inside the image, and the server runs as an **unprivileged user**.

## Troubleshooting & Limitations

- **Rate limits & IP blocks** — heavy scraping can trigger Reddit's anti-bot (HTTP 429 / login redirects). The server retries with backoff and detects them; increase `REDDIT_REQUEST_DELAY` if you get blocked.
- **Dynamic DOM** — this is a scraper, not an API: if Reddit changes its frontend, selectors may break. The live test suite exists to catch exactly that — run it before opening an issue.
- **Member counts** — Reddit's anonymous UI no longer exposes a subreddit's total member count; `get_subreddit_info` returns `members: null` when unavailable (other stats come from the structured page header and are reliable).
- **Speed** — first call of a session launches Chromium (5–30 s); subsequent calls reuse the shared browser and cache.
- **No private auth** — public-facing pages only; no account login.

## Contributing

Contributions are very welcome — improving selectors, adding tools, refining docs. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Found a vulnerability? Report it privately — see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Simon Chusseau
