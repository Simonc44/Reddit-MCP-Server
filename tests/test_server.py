"""Unit tests for the pure logic of the Reddit MCP server.

These tests never touch the network or launch a browser: they cover the
helpers (URL building, normalization, keyword matching, scoring) extracted
from server.py.
"""

import pytest

import server
from server import (
    TTLCache,
    _analyze_title,
    _build_search_url,
    _build_subreddit_url,
    _cached,
    _clamp,
    _clean_subreddit,
    _count_keyword_hits,
    _find_stat,
    _keyword_hit,
    _matches_any_keyword,
    _normalize_post_url,
    _normalize_sort,
    _normalize_time_filter,
    _parse_abbreviated_number,
    _safe_int,
)

# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0),
        ("42", 42),
        (0, 0),
        (-5, -5),
        ("abc", 0),
        ("", 0),
        (12.9, 12),  # int() truncation is intended
    ],
)
def test_safe_int(value, expected):
    assert _safe_int(value) == expected


def test_safe_int_custom_default():
    assert _safe_int(None, default=7) == 7
    assert _safe_int("nope", default=7) == 7


# ---------------------------------------------------------------------------
# _parse_abbreviated_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2M members", 1_200_000),
        ("45k", 45_000),
        ("3.5K", 3_500),
        ("1,200", 1_200),
        ("900 online", 900),
        ("2B views", 2_000_000_000),
        (",", None),  # digits-only characters, but empty after stripping
        ("1.2.3", None),  # unparseable float
        ("nope", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_abbreviated_number(text, expected):
    assert _parse_abbreviated_number(text) == expected


def test_find_stat():
    assert _find_stat("1,051,152 members", "members") == 1_051_152
    assert _find_stat("42 online", "online") == 42
    assert _find_stat("no numbers here", "members") is None
    assert _find_stat("42 members", "online") is None


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "keyword", "expected"),
    [
        ("I need a SaaS for this", "saas", True),
        ("saasy tool", "saas", False),
        ("paying for stuff", "pay", True),
        ("subscriptions are cheap", "subscription", True),
        ("someone should make this", "someone should make", True),
        ("why isn't there a tool", "why isn't there", True),
        ("I hate paywalls", "paywall", True),
        ("changes are coming", "change", True),
        ("no keywords here", "saas", False),
    ],
)
def test_keyword_hit(text, keyword, expected):
    assert _keyword_hit(text, keyword) is expected


def test_count_keyword_hits():
    assert _count_keyword_hits("paying for saas subscriptions", ["pay", "saas", "subscription"]) == 3
    assert _count_keyword_hits("nothing to see", ["pay", "saas"]) == 0


def test_matches_any_keyword():
    assert _matches_any_keyword("Python 3.12 released", ["python"]) is True
    assert _matches_any_keyword("pythonic approach", ["python"]) is False
    assert _matches_any_keyword("anything", None) is True
    assert _matches_any_keyword("anything", []) is True


# ---------------------------------------------------------------------------
# Normalization & URL building
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("r/python", "python"),
        ("/r/webdev/", "webdev"),
        ("  python  ", "python"),
        ("R/programming", "R/programming"),  # case kept, only prefix stripped
    ],
)
def test_clean_subreddit(raw, expected):
    assert _clean_subreddit(raw) == expected


def test_build_subreddit_url():
    assert _build_subreddit_url("python", "hot", "day") == "https://www.reddit.com/r/python/hot/"
    assert _build_subreddit_url("r/python", "top", "week") == "https://www.reddit.com/r/python/top/?t=week"


def test_build_search_url():
    assert _build_search_url("hello world", "new", "week") == (
        "https://www.reddit.com/search/?q=hello+world&sort=new&t=week"
    )
    assert _build_search_url("hello world", "relevance", "month", "python") == (
        "https://www.reddit.com/r/python/search/?q=hello+world&sort=relevance&t=month&restrict_sr=1"
    )


def test_normalize_post_url():
    assert _normalize_post_url("/r/python/comments/abc") == "https://www.reddit.com/r/python/comments/abc"
    assert _normalize_post_url("r/python/comments/abc") == "https://www.reddit.com/r/python/comments/abc"
    assert _normalize_post_url("https://redd.it/abc") == "https://redd.it/abc"
    assert _normalize_post_url("  https://www.reddit.com/r/x/comments/1  ") == "https://www.reddit.com/r/x/comments/1"


def test_normalize_sort_and_time_filter():
    assert _normalize_sort("bogus", server.VALID_SUBREDDIT_SORTS, "hot") == "hot"
    assert _normalize_sort("top", server.VALID_SUBREDDIT_SORTS, "hot") == "top"
    assert _normalize_sort("relevance", server.VALID_SEARCH_SORTS, "relevance") == "relevance"
    assert _normalize_time_filter("bogus") == "day"
    assert _normalize_time_filter("week") == "week"


def test_clamp():
    assert _clamp(5, 1, 3) == 3
    assert _clamp(-5, 1, 3) == 1
    assert _clamp(2, 1, 3) == 2


# ---------------------------------------------------------------------------
# Opportunity scoring
# ---------------------------------------------------------------------------

def test_analyze_title_base_and_engagement_bonus():
    result = _analyze_title("Just shipped my SaaS MVP", score=100, num_comments=20)
    # base = 100*2 + 20*3 = 260, ratio 0.2 -> x1.15 -> 299
    # + 2 money keywords (saas, mvp) * 15 = 329
    assert result["opportunity_score"] == 329
    assert result["engagement_ratio"] == 0.2
    assert result["matched_keywords"] == ["saas", "mvp"]


def test_analyze_title_high_engagement_and_dual_bonus():
    result = _analyze_title("Hate paying for SaaS subscriptions", score=50, num_comments=25)
    # base = 100 + 75 = 175, ratio 0.5 -> x1.3 -> 227
    # + 3 money keywords (pay, subscription, saas) * 15 = 272
    # + 1 impact keyword (hate) * 20 = 292, dual bonus x1.25 -> 365
    assert result["opportunity_score"] == 365
    assert result["engagement_ratio"] == 0.5
    assert set(result["matched_keywords"]) == {"pay", "subscription", "saas", "hate"}


def test_analyze_title_no_bonus():
    result = _analyze_title("A quiet post about nothing", score=500, num_comments=10)
    # base = 1000 + 30 = 1030, ratio 0.02 -> no multiplier, no keywords
    assert result["opportunity_score"] == 1030
    assert result["matched_keywords"] == []


def test_analyze_title_pain_points_only():
    result = _analyze_title("This tool is broken and I need a fix", score=0, num_comments=5)
    # base = 0 + 15 = 15, no engagement (score 0), 3 impact keywords (broken, need, fix)
    assert result["opportunity_score"] == 75
    assert set(result["matched_keywords"]) == {"broken", "need", "fix"}


# ---------------------------------------------------------------------------
# Sanity checks on module-level definitions
# ---------------------------------------------------------------------------

def test_defaults_present():
    assert len(server.DEFAULT_SUBREDDITS) > 0
    assert len(server.MONEY_KEYWORDS) > 0
    assert len(server.IMPACT_KEYWORDS) > 0


def test_all_tools_are_defined():
    for name in (
        "search_reddit",
        "search_reddit_query",
        "get_post_comments",
        "get_post_details",
        "get_subreddit_info",
        "analyze_opportunities",
        "get_user_posts",
        "get_trending_posts",
        "health_check",
    ):
        assert callable(getattr(server, name)), f"missing tool: {name}"


# ---------------------------------------------------------------------------
# TTLCache & _cached
# ---------------------------------------------------------------------------


class _FakeClock:
    """Deterministic clock for TTL tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ttl_cache_set_get():
    cache = TTLCache(ttl_seconds=10, clock=_FakeClock())
    assert cache.get("a") is None
    cache.set("a", [1, 2, 3])
    assert cache.get("a") == [1, 2, 3]
    assert len(cache) == 1


def test_ttl_cache_expiry():
    clock = _FakeClock()
    cache = TTLCache(ttl_seconds=10, clock=clock)
    cache.set("a", "value")
    clock.now = 9.9
    assert cache.get("a") == "value"
    clock.now = 10.1
    assert cache.get("a") is None
    assert len(cache) == 0  # expired entry is evicted


def test_ttl_cache_disabled_when_ttl_zero():
    cache = TTLCache(ttl_seconds=0)
    cache.set("a", "value")
    assert cache.get("a") is None
    assert len(cache) == 0


def test_ttl_cache_clear():
    cache = TTLCache(ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


def test_ttl_cache_does_not_evict_fresh_values():
    clock = _FakeClock()
    cache = TTLCache(ttl_seconds=5, clock=clock)
    cache.set("a", 1)
    clock.now = 4.99
    cache.set("b", 2)  # refresh timestamp of a? no — only b is fresh
    assert cache.get("a") == 1
    assert cache.get("b") == 2


def test_cached_producer_runs_once(monkeypatch):
    calls = []
    cache = TTLCache(ttl_seconds=60)
    monkeypatch.setattr(server, "_cache", cache)

    def producer() -> dict:
        calls.append(1)
        return {"data": 42}

    assert _cached("k", producer) == {"data": 42}
    assert _cached("k", producer) == {"data": 42}
    assert len(calls) == 1  # producer invoked only once


def test_cached_does_not_cache_exceptions(monkeypatch):
    cache = TTLCache(ttl_seconds=60)
    monkeypatch.setattr(server, "_cache", cache)

    def flaky() -> dict:
        raise RuntimeError("network down")

    with pytest.raises(RuntimeError):
        _cached("k", flaky)
    # failure was not cached — the key is absent
    assert cache.get("k") is None
