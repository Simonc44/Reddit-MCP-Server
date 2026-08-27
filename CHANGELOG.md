# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-27

### Added
- In-memory TTL cache for subreddit listings and subreddit info
  (`REDDIT_CACHE_TTL`, default 300 s; `0` disables it).
- Offline unit tests for the scraping helpers using fake Playwright objects,
  plus live integration tests against reddit.com
  (`REDDIT_LIVE_TESTS=1 pytest -m integration`).
- GitHub Actions CI: ruff, mypy, pytest with an 80% coverage gate, and a
  manual/scheduled live-test job.
- `Makefile` with `test`, `test-live`, `lint`, `typecheck`, `coverage` targets.
- `uv.lock` for reproducible development environments.

### Changed
- `get_subreddit_info` now reads the structured `shreddit-subreddit-header`
  attributes (name, description, active users, weekly contributions) instead of
  brittle sidebar selectors. The member count is only returned when Reddit's
  anonymous UI renders it (it usually does not anymore).
- Keyword matching now handles plural/verb forms (`pay` matches `paying`) while
  still respecting word boundaries (`pay` does not match `paywall`).
- Scraping requests are cached per URL for `REDDIT_CACHE_TTL` seconds.
- Pytest disables the `anyio`/`pytest-asyncio` plugins (transitive deps of
  fastmcp) which conflict with Playwright's sync API.
- `analyze_opportunities` reports `matched_keywords` per idea.

### Fixed
- Karma extraction regex: `12k post karma` was not matched, only `3k comment
  karma` (missing `\s+` after `post`).
- Comment extraction could return fewer than `limit` comments when empty
  comments appeared first (limit now applies after filtering).
- Subreddit info headers were read before React hydration completed.

## [0.2.0] - 2026-08-27

### Added
- `get_user_posts`, `get_trending_posts` and `health_check` tools.
- Retry logic with exponential backoff and anti-bot detection (login redirects).
- Unit test suite for the pure logic (URL building, scoring, keywords, cache).
- Packaging: `pyproject.toml` with a `reddit-mcp` console script, `Dockerfile`,
  `requirements-dev.txt`.
- All scraping knobs configurable through `REDDIT_*` environment variables.

### Changed
- A single shared browser is launched lazily and reused across tool calls
  (previously each call started Chromium from scratch).
- Tools return structured dicts instead of pre-serialized JSON strings.
- `analyze_opportunities` accepts `sort` and `time_filter`.

## [0.1.0] - 2026-08-27

Initial version of the project as received: 6 tools scraping Reddit's public
interface with Playwright (`search_reddit`, `search_reddit_query`,
`get_post_comments`, `get_post_details`, `get_subreddit_info`,
`analyze_opportunities`).
