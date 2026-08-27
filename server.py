"""Reddit MCP Server.

A Model Context Protocol (MCP) server that lets AI assistants (Claude Desktop,
Claude Code, and other MCP clients) search, browse and analyze Reddit in
real time — without any Reddit API key, by scraping the public web interface
with Playwright.

Everything that does not require a browser is kept in small pure functions so
it can be unit-tested without network access (see tests/test_server.py).
"""

from __future__ import annotations

import atexit
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote_plus

from fastmcp import FastMCP
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

logger = logging.getLogger("reddit-mcp")

# ============================================================================
# Configuration — every knob can be overridden with environment variables
# ============================================================================


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Runtime settings, overridable through REDDIT_* environment variables."""

    BASE_URL = "https://www.reddit.com"

    HEADLESS = _env_bool("REDDIT_HEADLESS", True)
    VIEWPORT_WIDTH = _env_int("REDDIT_VIEWPORT_WIDTH", 1280)
    VIEWPORT_HEIGHT = _env_int("REDDIT_VIEWPORT_HEIGHT", 900)
    USER_AGENT = os.getenv(
        "REDDIT_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36",
    )

    NAV_TIMEOUT_MS = _env_int("REDDIT_NAV_TIMEOUT_MS", 45000)
    WAIT_TIMEOUT_MS = _env_int("REDDIT_WAIT_TIMEOUT_MS", 15000)
    REQUEST_DELAY = _env_float("REDDIT_REQUEST_DELAY", 1.5)
    MAX_SCROLLS = _env_int("REDDIT_MAX_SCROLLS", 4)
    MAX_RETRIES = _env_int("REDDIT_MAX_RETRIES", 3)
    RETRY_BACKOFF = _env_float("REDDIT_RETRY_BACKOFF", 2.0)

    LOG_LEVEL = os.getenv("REDDIT_LOG_LEVEL", "INFO")

    # In-memory cache TTL for subreddit listings / subreddit info (seconds).
    # Set REDDIT_CACHE_TTL=0 to disable caching entirely.
    CACHE_TTL = _env_float("REDDIT_CACHE_TTL", 300.0)


# ============================================================================
# MCP server instance
# ============================================================================

mcp = FastMCP(
    "RedditSearch",
    instructions=(
        "MCP server to search and analyze Reddit in real time. "
        "Tools: search_reddit (browse subreddits), search_reddit_query "
        "(keyword search), get_post_comments, get_post_details, "
        "get_subreddit_info, get_user_posts, get_trending_posts and "
        "analyze_opportunities (business opportunity scoring)."
    ),
)

# ============================================================================
# Defaults & keyword lists
# ============================================================================

DEFAULT_SUBREDDITS = [
    "SomebodyMakeThis",
    "StartupIdeas",
    "businessideas",
    "Entrepreneur",
    "saas",
    "technology",
    "antiwork",
]

MONEY_KEYWORDS = [
    "pay", "buy", "subscription", "charge", "business", "revenue",
    "monetize", "earn", "dollar", "pricing", "freemium", "saas",
    "startup", "mvp", "profit", "cost", "budget", "invest",
    "funding", "money", "income", "sale", "customer", "paywall",
    "recurring", "sales",
]

IMPACT_KEYWORDS = [
    "problem", "fix", "stop", "change", "community", "alternative",
    "sick of", "hate", "scam", "frustrated", "frustrating", "annoying",
    "broken", "need", "wish", "want", "missing", "terrible", "worst",
    "replace", "better than", "should exist", "why isn't there",
    "someone should make", "idea", "solution", "pain point", "pain",
    "struggle", "tedious", "workaround",
]

VALID_SUBREDDIT_SORTS = {"hot", "new", "top", "rising"}
VALID_SEARCH_SORTS = {"relevance", "hot", "top", "new", "comments"}
VALID_USER_SORTS = {"hot", "new", "top", "controversial"}
VALID_TIME_FILTERS = {"hour", "day", "week", "month", "year", "all"}

# ============================================================================
# Browser lifecycle — one shared browser, reused across tool calls
# ============================================================================

_pw: Playwright | None = None
_browser: Browser | None = None
_context: Any = None
_scrape_lock = threading.Lock()

_BLOCKED_ASSET_RE = re.compile(
    r"\.(?:png|jpe?g|gif|svg|webp|avif|mp4|webm|ogg|mp3|woff2?|ttf|eot|otf)(?:[?#]|$)",
    re.IGNORECASE,
)
_BLOCKED_TRACKERS = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "scorecardresearch.com",
    "facebook.net",
    "hotjar.com",
    "mixpanel.com",
    "segment.io",
)


def _handle_route(route: Any) -> None:
    """Abort heavy/tracking requests to speed up scraping and reduce load."""
    request = route.request
    if request.resource_type in ("image", "media", "font"):
        route.abort()
        return
    url = request.url
    if _BLOCKED_ASSET_RE.search(url) or any(t in url for t in _BLOCKED_TRACKERS):
        route.abort()
        return
    route.continue_()


def _get_page() -> Page:
    """Return a page from the shared browser, starting it lazily."""
    global _pw, _browser, _context
    if _context is None:
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=Settings.HEADLESS)
        _context = _browser.new_context(
            viewport={"width": Settings.VIEWPORT_WIDTH, "height": Settings.VIEWPORT_HEIGHT},
            user_agent=Settings.USER_AGENT,
            locale="en-US",
        )
        _context.route("**/*", _handle_route)
        logger.debug("Shared browser context created")
    return _context.new_page()


def close_browser() -> None:
    """Best-effort cleanup of the shared browser (also called at exit)."""
    global _pw, _browser, _context
    for closer in (_context.close if _context else None,
                   _browser.close if _browser else None,
                   _pw.stop if _pw else None):
        if closer is None:
            continue
        try:
            closer()
        except Exception:
            pass
    _context = _browser = _pw = None


atexit.register(close_browser)


@contextmanager
def _page_session() -> Iterator[Page]:
    """Yield a fresh page from the shared browser.

    Scraping is serialized with a lock: Playwright's sync API is not
    thread-safe and it also naturally enforces a polite request rate.
    """
    with _scrape_lock:
        page = _get_page()
        try:
            yield page
        finally:
            try:
                page.close()
            except Exception:
                pass


class TTLCache:
    """Thread-safe in-memory cache with TTL expiry, for JSON-safe values.

    ``ttl_seconds <= 0`` disables the cache (``get`` always returns None).
    The clock can be injected for deterministic unit tests.
    """

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: str) -> Any:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            timestamp, value = entry
            if self._clock() - timestamp > self._ttl:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._data[key] = (self._clock(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


_cache = TTLCache(ttl_seconds=Settings.CACHE_TTL)


def _cached(key: str, producer: Callable[[], Any]) -> Any:
    """Return the cached value for ``key`` or compute and store it.

    Only successful results are cached — exceptions propagate and are not
    stored, so transient failures never poison the cache.
    """
    value = _cache.get(key)
    if value is not None:
        logger.debug("Cache hit for %s", key)
        return value
    result = producer()
    _cache.set(key, result)
    return result


def _posts_producer(
    page: Page, url: str, max_scrolls: int | None = None
) -> Callable[[], list[dict[str, Any]]]:
    """Build a cache producer that scrapes the posts at ``url``."""
    return lambda: _scrape_posts(page, url, max_scrolls)


# ============================================================================
# Pure helpers (unit-tested in tests/test_server.py)
# ============================================================================


def _safe_int(value: Any, default: int | None = 0) -> int | None:
    """Convert a value to int, falling back to ``default`` on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_abbreviated_number(text: str | None) -> int | None:
    """Parse strings like '1.2M', '45k', '1,200' into an int (None if not found)."""
    if not text:
        return None
    match = re.search(r"([\d.,]+\s*[kmb]?)", text.strip(), re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(",", "")
    if not raw:
        return None
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(raw[-1].lower(), 1)
    number_part = raw[:-1] if raw[-1].lower() in "kmb" else raw
    try:
        return int(float(number_part) * multiplier)
    except ValueError:
        return None


def _keyword_hit(text: str, keyword: str) -> bool:
    """Word-boundary match on ``keyword`` in ``text`` (allows plural/verb forms).

    e.g. 'pay' matches 'paying' and 'paywall'? No — 'paywall' fails the
    word-boundary test; 'subscription' matches 'subscriptions'.
    """
    pattern = rf"(?<!\w){re.escape(keyword.lower())}(?:s|es|ed|ing)?(?!\w)"
    return re.search(pattern, text.lower()) is not None


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if _keyword_hit(text, kw))


def _matches_any_keyword(text: str, keywords: list[str] | None) -> bool:
    """True when ``text`` matches at least one keyword (empty list = no filter)."""
    if not keywords:
        return True
    return any(_keyword_hit(text, kw) for kw in keywords)


def _normalize_sort(value: str, allowed: set[str], default: str) -> str:
    return value if value in allowed else default


def _normalize_time_filter(value: str) -> str:
    return value if value in VALID_TIME_FILTERS else "day"


def _clean_subreddit(subreddit: str) -> str:
    """Normalize a subreddit name: '/r/python/' -> 'python', 'r/webdev' -> 'webdev'."""
    return subreddit.strip().strip("/").removeprefix("r/").strip()


def _normalize_post_url(url: str) -> str:
    """Accept full URLs, absolute paths ('/r/...') and bare 'r/...' paths."""
    url = url.strip()
    if url.startswith("/"):
        return Settings.BASE_URL + url
    if url.startswith("r/"):
        return f"{Settings.BASE_URL}/{url}"
    return url


def _build_subreddit_url(subreddit: str, sort: str, time_filter: str) -> str:
    sub = _clean_subreddit(subreddit)
    if sort == "top":
        return f"{Settings.BASE_URL}/r/{sub}/top/?t={time_filter}"
    return f"{Settings.BASE_URL}/r/{sub}/{sort}/"


def _build_search_url(query: str, sort: str, time_filter: str, subreddit: str | None = None) -> str:
    encoded = quote_plus(query)
    params = f"q={encoded}&sort={sort}&t={time_filter}"
    if subreddit:
        sub = _clean_subreddit(subreddit)
        return f"{Settings.BASE_URL}/r/{sub}/search/?{params}&restrict_sr=1"
    return f"{Settings.BASE_URL}/search/?{params}"


def _analyze_title(title: str, score: int, num_comments: int) -> dict[str, Any]:
    """Score how promising a post is as a business opportunity.

    Score = (upvotes * 2) + (comments * 3), then:
    * engagement multiplier (comments/upvotes > 0.3 -> x1.3, > 0.15 -> x1.15)
    * +15 per monetization keyword, +20 per pain-point keyword
    * x1.25 bonus when both categories are detected
    """
    base_score = (score * 2) + (num_comments * 3)
    engagement_ratio = (num_comments / score) if score > 0 else 0.0

    if engagement_ratio > 0.3:
        base_score = int(base_score * 1.3)
    elif engagement_ratio > 0.15:
        base_score = int(base_score * 1.15)

    money_hits = [kw for kw in MONEY_KEYWORDS if _keyword_hit(title, kw)]
    impact_hits = [kw for kw in IMPACT_KEYWORDS if _keyword_hit(title, kw)]

    base_score += len(money_hits) * 15
    base_score += len(impact_hits) * 20
    if money_hits and impact_hits:
        base_score = int(base_score * 1.25)

    return {
        "opportunity_score": base_score,
        "engagement_ratio": round(engagement_ratio, 3),
        "matched_keywords": money_hits + impact_hits,
    }


# ============================================================================
# Browser helpers
# ============================================================================


def _goto(page: Page, url: str) -> None:
    """Navigate with retries and basic anti-bot detection."""
    last_error: Exception | None = None
    for attempt in range(1, Settings.MAX_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=Settings.NAV_TIMEOUT_MS)
            if "reddit.com/login" in page.url:
                raise RuntimeError(
                    "Reddit redirected to the login page (anti-bot). "
                    "Wait a bit and retry, or reduce the request rate."
                )
            return
        except Exception as exc:  # Playwright timeouts and bot blocks
            last_error = exc
            if attempt == Settings.MAX_RETRIES:
                break
            delay = Settings.RETRY_BACKOFF * attempt
            logger.warning(
                "Navigation to %s failed (attempt %d/%d): %s — retrying in %.1fs",
                url, attempt, Settings.MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"Failed to load {url} after {Settings.MAX_RETRIES} attempts: {last_error}"
    )


def _scroll_page(page: Page, max_scrolls: int | None = None) -> None:
    """Scroll to the bottom progressively to trigger lazy-loaded content."""
    if max_scrolls is None:
        max_scrolls = Settings.MAX_SCROLLS
    for i in range(max(0, max_scrolls)):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500 + i * 300)
        except Exception:
            break


def _extract_posts_from_page(page: Page, max_scrolls: int | None = None) -> list[dict[str, Any]]:
    """Extract every visible shreddit-post element, deduplicated by URL."""
    if max_scrolls is None:
        max_scrolls = Settings.MAX_SCROLLS
    try:
        page.wait_for_selector("shreddit-post", timeout=Settings.WAIT_TIMEOUT_MS)
    except Exception:
        logger.info("No shreddit-post elements found on %s", page.url)
        return []

    _scroll_page(page, max_scrolls)

    posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for el in page.locator("shreddit-post").all():
        try:
            title = el.get_attribute("post-title")
            if not title:
                continue

            permalink = el.get_attribute("permalink")
            url = f"{Settings.BASE_URL}{permalink}" if permalink else None
            if url:
                if url in seen_urls:
                    continue
                seen_urls.add(url)

            content_href = el.get_attribute("content-href") or ""
            if "reddit.com" in content_href or not content_href:
                post_type = "self"
            elif any(ext in content_href for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")):
                post_type = "image"
            elif any(ext in content_href for ext in (".mp4", ".webm", "youtu", "vimeo")):
                post_type = "video"
            else:
                post_type = "link"

            posts.append({
                "id": el.get_attribute("id") or None,
                "title": title,
                "score": _safe_int(el.get_attribute("score")),
                "num_comments": _safe_int(el.get_attribute("comment-count")),
                "author": el.get_attribute("author") or "unknown",
                "url": url,
                "flair": el.get_attribute("flair-text") or None,
                "post_type": post_type,
                "created": el.get_attribute("created-timestamp") or None,
            })
        except Exception:
            continue

    return posts


_BODY_SELECTORS = (
    "[slot='text-body'] p",
    "[slot='text-body'] li",
    "[slot='text-body'] h1",
    "[slot='text-body'] h2",
    "[slot='text-body'] h3",
    ".md p",
    ".md li",
)

_COMMENT_TEXT_SELECTORS = (
    "div[slot='comment'] p",
    "div[id*='comment-content'] p",
    "div.md p",
    "p",
)


def _extract_post_body(page: Page, max_blocks: int = 50) -> str:
    """Extract the selftext of a post with fallback selectors."""
    lines: list[str] = []
    for selector in _BODY_SELECTORS:
        try:
            for el in page.locator(selector).all():
                text = el.inner_text().strip()
                if text and text not in lines:
                    lines.append(text)
        except Exception:
            continue
        if len(lines) >= max_blocks:
            break
    return "\n".join(lines[:max_blocks])


def _extract_comments(page: Page, limit: int) -> list[dict[str, Any]]:
    """Extract threaded comments (author, text, score, depth) up to ``limit``."""
    _scroll_page(page, 2)
    comments: list[dict[str, Any]] = []

    for el in page.locator("shreddit-comment").all():
        if len(comments) >= limit:
            break
        try:
            text = ""
            for selector in _COMMENT_TEXT_SELECTORS:
                try:
                    pieces = [
                        p.inner_text().strip()
                        for p in el.locator(selector).all()
                        if p.inner_text().strip()
                    ]
                    if pieces:
                        text = " ".join(pieces)
                        break
                except Exception:
                    continue

            if text:
                comments.append({
                    "id": el.get_attribute("id") or None,
                    "author": el.get_attribute("author") or "unknown",
                    "text": text[:2000],
                    "score": _safe_int(el.get_attribute("score")),
                    "depth": _safe_int(el.get_attribute("depth")),
                })
        except Exception:
            continue

    return comments


def _find_stat(text: str, label: str) -> int | None:
    """Find '42 members' / '1.2M online' style stats in a text blob."""
    match = re.search(rf"([\d.,]+\s*[kmb]?)\s+{re.escape(label)}", text.lower())
    return _parse_abbreviated_number(match.group(1)) if match else None


def _extract_user_karma(page: Page) -> int | None:
    """Best-effort extraction of total karma from a user profile page."""
    try:
        snippet = page.evaluate("document.body.innerText.slice(0, 6000)") or ""
    except Exception:
        return None
    match = re.search(
        r"([\d.,]+\s*[kmb]?)\s+(?:post\s+|comment\s+)?karma", snippet.lower()
    )
    return _parse_abbreviated_number(match.group(1)) if match else None


def _error(message: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"error": message}
    result.update(extra)
    return result


def _scrape_posts(page: Page, url: str, max_scrolls: int | None = None) -> list[dict[str, Any]]:
    """Navigate to ``url`` and extract its posts (used with the TTL cache)."""
    _goto(page, url)
    return _extract_posts_from_page(page, max_scrolls)


def _extract_created_date(page: Page) -> str | None:
    """Parse 'Created Jan 25, 2008' from the subreddit header details."""
    try:
        text = page.locator(
            "shreddit-subreddit-header .community-details"
        ).first.inner_text(timeout=4000)
    except Exception:
        return None
    match = re.search(r"Created\s+([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})", text)
    return match.group(1) if match else None


def _extract_members_from_sidebar(page: Page, subreddit: str) -> int | None:
    """Best-effort member count from the sidebar 'Top communities' list.

    Reddit's anonymous UI no longer shows the current subreddit's total
    member count, only *related* communities. A count is returned when the
    current subreddit happens to appear in that list, otherwise None.
    """
    try:
        items = page.locator(
            "li.relative.list-none:has(span:text-matches('members', 'i'))"
        ).all()
    except Exception:
        return None
    needle = f"/r/{subreddit.lower()}"
    for li in items:
        try:
            link = li.locator("a[href*='/r/']").first
            if not link.count():
                continue
            href = (link.get_attribute("href") or "").lower()
            if needle in href:
                return _find_stat(li.inner_text(), "members")
        except Exception:
            continue
    return None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


# ============================================================================
# TOOL 1 : Browse one or several subreddits
# ============================================================================

@mcp.tool()
def search_reddit(
    subreddits: list[str],
    sort: str = "hot",
    time_filter: str = "day",
    limit: int = 25,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Browse posts from one or more subreddits, optionally filtered by keywords.

    Args:
        subreddits: Subreddits to scan, with or without the r/ prefix (e.g. ["python", "webdev"]).
        sort: "hot", "new", "top" or "rising".
        time_filter: Time window for "top": "hour", "day", "week", "month", "year", "all".
        limit: Maximum number of posts to return (capped at 100).
        keywords: Optional list of keywords to filter posts by title.

    Returns:
        A dict with the posts found (title, score, comments, author, URL, flair, type).
    """
    if not subreddits:
        return _error("The 'subreddits' argument must contain at least one subreddit.")

    sort = _normalize_sort(sort, VALID_SUBREDDIT_SORTS, "hot")
    time_filter = _normalize_time_filter(time_filter)
    limit = _clamp(limit, 1, 100)

    all_posts: list[dict[str, Any]] = []
    errors: list[str] = []

    with _page_session() as page:
        for sub in subreddits:
            url = _build_subreddit_url(sub, sort, time_filter)
            try:
                posts = _cached(f"posts|{url}", _posts_producer(page, url))
                for post in posts:
                    if not _matches_any_keyword(post["title"], keywords):
                        continue
                    post["subreddit"] = _clean_subreddit(sub)
                    all_posts.append(post)
            except Exception as exc:
                errors.append(f"r/{_clean_subreddit(sub)}: {str(exc)[:150]}")
            time.sleep(Settings.REQUEST_DELAY)

    all_posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    all_posts = all_posts[:limit]

    result: dict[str, Any] = {
        "total_results": len(all_posts),
        "subreddits_scanned": [_clean_subreddit(s) for s in subreddits],
        "sort": sort,
        "time_filter": time_filter,
        "posts": all_posts,
    }
    if errors:
        result["errors"] = errors
    return result


# ============================================================================
# TOOL 2 : Global keyword search
# ============================================================================

@mcp.tool()
def search_reddit_query(
    query: str,
    sort: str = "relevance",
    time_filter: str = "week",
    subreddit: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search Reddit by keywords through the search page.

    Args:
        query: Search text (e.g. "best python framework 2025").
        sort: "relevance", "hot", "top", "new" or "comments".
        time_filter: "hour", "day", "week", "month", "year", "all".
        subreddit: Optionally restrict the search to a single subreddit.
        limit: Maximum number of results (capped at 100).

    Returns:
        A dict with the search results.
    """
    sort = _normalize_sort(sort, VALID_SEARCH_SORTS, "relevance")
    time_filter = _normalize_time_filter(time_filter)
    limit = _clamp(limit, 1, 100)
    url = _build_search_url(query, sort, time_filter, subreddit)

    posts: list[dict[str, Any]] = []
    with _page_session() as page:
        try:
            _goto(page, url)
            posts = _extract_posts_from_page(page, max_scrolls=3)
        except Exception as exc:
            return _error(f"Search failed: {exc}", query=query, url=url)

    for post in posts:
        if post.get("url"):
            parts = post["url"].split("/r/")
            if len(parts) > 1:
                post["subreddit"] = parts[1].split("/")[0]

    return {
        "total_results": len(posts[:limit]),
        "query": query,
        "sort": sort,
        "time_filter": time_filter,
        "subreddit": _clean_subreddit(subreddit) if subreddit else None,
        "posts": posts[:limit],
    }


# ============================================================================
# TOOL 3 : Comments of a specific post
# ============================================================================

@mcp.tool()
def get_post_comments(
    post_url: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Extract the threaded comments of a Reddit post.

    Args:
        post_url: Full URL of the post (absolute paths like /r/.../comments/... also work).
        limit: Maximum number of comments to return (capped at 200).

    Returns:
        A dict with the post title and its comments (author, text, score, depth).
    """
    url = _normalize_post_url(post_url)
    limit = _clamp(limit, 1, 200)

    with _page_session() as page:
        try:
            _goto(page, url)
            post_title, post_score = "", 0
            post_el = page.locator("shreddit-post").first
            if post_el.count():
                post_title = post_el.get_attribute("post-title") or ""
                post_score = _safe_int(post_el.get_attribute("score")) or 0
            post_body = _extract_post_body(page)
            comments = _extract_comments(page, limit)
        except Exception as exc:
            return _error(f"Failed to load post: {exc}", post_url=url)

    return {
        "post_url": url,
        "post_title": post_title,
        "post_score": post_score,
        "post_body": post_body[:3000] if post_body else None,
        "total_comments": len(comments),
        "comments": comments,
    }


# ============================================================================
# TOOL 4 : Full details of a post
# ============================================================================

@mcp.tool()
def get_post_details(
    post_url: str,
) -> dict[str, Any]:
    """Get the full content of a Reddit post: title, author, score, selftext, flair and metadata.

    Args:
        post_url: Full URL of the post (absolute paths also work).

    Returns:
        A dict with all the post details.
    """
    url = _normalize_post_url(post_url)

    with _page_session() as page:
        try:
            _goto(page, url)
            post_el = page.locator("shreddit-post").first
            if not post_el.count():
                return _error("Post not found on this page", post_url=url)

            content_href = post_el.get_attribute("content-href") or ""
            external_url = content_href if content_href and "reddit.com" not in content_href else None

            result: dict[str, Any] = {
                "post_url": url,
                "title": post_el.get_attribute("post-title") or "",
                "author": post_el.get_attribute("author") or "unknown",
                "subreddit": post_el.get_attribute("subreddit-prefixed-name") or None,
                "score": _safe_int(post_el.get_attribute("score")),
                "num_comments": _safe_int(post_el.get_attribute("comment-count")),
                "flair": post_el.get_attribute("flair-text") or None,
                "created": post_el.get_attribute("created-timestamp") or None,
                "post_type": None,
                "external_url": external_url,
            }

            # post_type, same logic as _extract_posts_from_page
            if "reddit.com" in content_href or not content_href:
                result["post_type"] = "self"
            elif any(ext in content_href for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")):
                result["post_type"] = "image"
            elif any(ext in content_href for ext in (".mp4", ".webm", "youtu", "vimeo")):
                result["post_type"] = "video"
            elif content_href:
                result["post_type"] = "link"

            selftext = _extract_post_body(page)
            result["selftext"] = selftext[:5000] if selftext else None
        except Exception as exc:
            return _error(f"Failed to load post: {exc}", post_url=url)

    return result


# ============================================================================
# TOOL 5 : Subreddit information
# ============================================================================

@mcp.tool()
def get_subreddit_info(
    subreddit: str,
) -> dict[str, Any]:
    """Get public info about a subreddit: description, stats and top posts.

    Stats are read from the structured ``shreddit-subreddit-header`` element
    (name, description, active users). Note: Reddit's anonymous UI no longer
    displays the total member count, so ``members`` is only populated when the
    current subreddit appears in the sidebar "Top communities" list.

    Args:
        subreddit: Subreddit name, with or without the r/ prefix (e.g. "python").

    Returns:
        A dict with subreddit info and its 5 current top posts.
    """
    sub = _clean_subreddit(subreddit)
    url = _build_subreddit_url(sub, "hot", "day")
    cache_key = f"subreddit_info|{sub}"

    cached_info = _cache.get(cache_key)
    if cached_info is not None:
        return cached_info

    with _page_session() as page:
        try:
            _goto(page, url)
            try:
                page.wait_for_selector(
                    "shreddit-subreddit-header", timeout=Settings.WAIT_TIMEOUT_MS
                )
            except Exception:
                return _error(
                    "Subreddit page did not render its header", subreddit=sub, url=url
                )
            header = page.locator("shreddit-subreddit-header").first

            info: dict[str, Any] = {
                "subreddit": f"r/{sub}",
                "url": url,
                "name": header.get_attribute("display-name") or header.get_attribute("name"),
                "prefixed_name": header.get_attribute("prefixed-name"),
                "description": header.get_attribute("description"),
                "subscribers_label": header.get_attribute("subscribers-text"),
                "members": _extract_members_from_sidebar(page, sub),
                "active_users": _safe_int(header.get_attribute("weekly-active-users"), default=None),
                "weekly_contributions": _safe_int(
                    header.get_attribute("weekly-contributions"), default=None
                ),
                "created": _extract_created_date(page),
            }
            posts = _extract_posts_from_page(page, max_scrolls=1)
            info["top_posts"] = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)[:5]
        except Exception as exc:
            return _error(f"Failed to load subreddit: {exc}", subreddit=sub, url=url)

    _cache.set(cache_key, info)
    return info


# ============================================================================
# TOOL 6 : Business opportunity analysis
# ============================================================================

@mcp.tool()
def analyze_opportunities(
    subreddits: list[str] | None = None,
    min_score: int = 100,
    limit: int = 30,
    keywords: list[str] | None = None,
    sort: str = "hot",
    time_filter: str = "day",
) -> dict[str, Any]:
    """Scan subreddits for business opportunities (SaaS/startup pain points).

    Scores posts with: popularity (upvotes), engagement (comments) and semantic
    relevance (monetization + pain-point keywords). See README for the formula.

    Args:
        subreddits: Subreddits to analyze (defaults to a curated startup set).
        min_score: Minimum opportunity score to include a post.
        limit: Maximum number of ideas to return (capped at 200).
        keywords: Optional extra keywords to filter posts by title.
        sort: "hot", "new", "top" or "rising".
        time_filter: Time window for "top": "hour", "day", "week", "month", "year", "all".

    Returns:
        A dict with the ideas sorted by descending opportunity score.
    """
    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS
    if not subreddits:
        return _error("The 'subreddits' argument must contain at least one subreddit.")

    sort = _normalize_sort(sort, VALID_SUBREDDIT_SORTS, "hot")
    time_filter = _normalize_time_filter(time_filter)
    min_score = _clamp(min_score, 0, 1_000_000)
    limit = _clamp(limit, 1, 200)

    all_ideas: list[dict[str, Any]] = []
    errors: list[str] = []
    total_scanned = 0

    with _page_session() as page:
        for sub in subreddits:
            url = _build_subreddit_url(sub, sort, time_filter)
            try:
                posts = _cached(f"posts|{url}", _posts_producer(page, url, max_scrolls=5))
                total_scanned += len(posts)

                for post in posts:
                    if not _matches_any_keyword(post["title"], keywords):
                        continue

                    analysis = _analyze_title(post["title"], post["score"], post["num_comments"])
                    if analysis["opportunity_score"] < min_score:
                        continue

                    all_ideas.append({
                        "subreddit": _clean_subreddit(sub),
                        "title": post["title"],
                        "opportunity_score": analysis["opportunity_score"],
                        "reddit_score": post["score"],
                        "num_comments": post["num_comments"],
                        "engagement_ratio": analysis["engagement_ratio"],
                        "matched_keywords": analysis["matched_keywords"],
                        "author": post["author"],
                        "flair": post.get("flair"),
                        "url": post["url"],
                    })
            except Exception as exc:
                errors.append(f"r/{_clean_subreddit(sub)}: {str(exc)[:150]}")
            time.sleep(Settings.REQUEST_DELAY)

    all_ideas.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
    all_ideas = all_ideas[:limit]

    high_score_count = sum(1 for x in all_ideas if x.get("opportunity_score", 0) >= 1000)
    avg_score = (
        round(sum(x.get("opportunity_score", 0) for x in all_ideas) / len(all_ideas))
        if all_ideas else 0
    )

    result: dict[str, Any] = {
        "total_results": len(all_ideas),
        "total_posts_scanned": total_scanned,
        "high_score_ideas": high_score_count,
        "average_opportunity_score": avg_score,
        "min_score_filter": min_score,
        "sort": sort,
        "time_filter": time_filter,
        "subreddits_scanned": [_clean_subreddit(s) for s in subreddits],
        "ideas": all_ideas,
    }
    if errors:
        result["errors"] = errors
    return result


# ============================================================================
# TOOL 7 : Posts of a specific user
# ============================================================================

@mcp.tool()
def get_user_posts(
    username: str,
    sort: str = "new",
    limit: int = 25,
) -> dict[str, Any]:
    """Browse the public posts of a Reddit user.

    Args:
        username: Reddit username, with or without the u/ prefix.
        sort: "hot", "new", "top" or "controversial".
        limit: Maximum number of posts to return (capped at 100).

    Returns:
        A dict with the user's public profile info and their posts.
    """
    name = username.strip().removeprefix("u/").strip()
    if not name:
        return _error("The 'username' argument is required.")
    sort = _normalize_sort(sort, VALID_USER_SORTS, "new")
    limit = _clamp(limit, 1, 100)
    url = f"{Settings.BASE_URL}/user/{name}/submitted/?sort={sort}"

    with _page_session() as page:
        try:
            posts = _cached(f"posts|{url}", lambda: _scrape_posts(page, url, max_scrolls=3))
            karma = _extract_user_karma(page)
        except Exception as exc:
            return _error(f"Failed to load profile u/{name}: {exc}", username=name, url=url)

    return {
        "username": name,
        "karma": karma,
        "sort": sort,
        "total_results": len(posts[:limit]),
        "posts": posts[:limit],
        "url": url,
    }


# ============================================================================
# TOOL 8 : Trending posts across Reddit
# ============================================================================

@mcp.tool()
def get_trending_posts(
    limit: int = 25,
    time_filter: str = "day",
) -> dict[str, Any]:
    """Get the currently trending posts across Reddit (r/popular).

    Args:
        limit: Maximum number of posts to return (capped at 100).
        time_filter: "hour", "day", "week", "month", "year", "all".

    Returns:
        A dict with the top posts of r/popular for the given time window.
    """
    time_filter = _normalize_time_filter(time_filter)
    limit = _clamp(limit, 1, 100)
    url = f"{Settings.BASE_URL}/r/popular/top/?t={time_filter}"

    with _page_session() as page:
        try:
            posts = _cached(f"posts|{url}", lambda: _scrape_posts(page, url))
        except Exception as exc:
            return _error(f"Failed to load trending posts: {exc}", url=url)

    return {
        "total_results": len(posts[:limit]),
        "source": "r/popular",
        "time_filter": time_filter,
        "posts": posts[:limit],
        "url": url,
    }


# ============================================================================
# TOOL 9 : Health check
# ============================================================================

@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check that the server is alive and ready to scrape.

    Returns:
        A dict with the server status and version.
    """
    return {
        "status": "ok",
        "server": "reddit-mcp",
        "version": "0.3.0",
    }


# ============================================================================
# Entry point
# ============================================================================

def main() -> None:
    logging.basicConfig(
        level=getattr(logging, Settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - entry point guard
    main()
