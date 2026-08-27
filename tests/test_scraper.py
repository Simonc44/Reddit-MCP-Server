"""Offline tests for the scraping logic, using fake Playwright objects.

These exercise the extraction helpers (posts, comments, body, stats) and the
navigation/retry logic without a browser or network access. Live end-to-end
coverage lives in test_integration.py.
"""

from contextlib import contextmanager

import pytest

import server
from server import (
    _extract_comments,
    _extract_created_date,
    _extract_members_from_sidebar,
    _extract_post_body,
    _extract_posts_from_page,
    _extract_user_karma,
    _goto,
)
from tests.fakes import FakeElement, FakePage, comment_element, post_element

BASE = server.Settings.BASE_URL


# ---------------------------------------------------------------------------
# _extract_posts_from_page
# ---------------------------------------------------------------------------

def test_extract_posts_full_fields_and_types():
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(),  # self post (defaults)
        post_element(
            content_href="https://i.redd.it/abc123.png",
            permalink="/r/python/comments/1b/image_post/",
        ),
        post_element(
            content_href="https://v.redd.it/xyz.mp4",
            permalink="/r/python/comments/1c/video_post/",
        ),
        post_element(
            content_href="https://example.com/article",
            permalink="/r/python/comments/1d/link_post/",
        ),
        post_element(permalink=None),  # no URL but still valid
    ])
    posts = _extract_posts_from_page(page, max_scrolls=1)

    assert len(posts) == 5
    first = posts[0]
    assert first["title"] == "A sample post"
    assert first["score"] == 42
    assert first["num_comments"] == 7
    assert first["author"] == "someuser"
    assert first["url"] == BASE + "/r/python/comments/1abc/a_sample_post/"
    assert first["post_type"] == "self"
    assert first["flair"] is None
    assert first["created"] == "2026-01-01T00:00:00.000000+0000"

    assert posts[1]["post_type"] == "image"
    assert posts[2]["post_type"] == "video"
    assert posts[3]["post_type"] == "link"
    assert posts[4]["url"] is None


def test_extract_posts_deduplicates_by_url():
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(),
        post_element(score="99"),  # duplicate URL, higher score — must be dropped
    ])
    posts = _extract_posts_from_page(page, max_scrolls=1)
    assert len(posts) == 1
    assert posts[0]["score"] == 42


def test_extract_posts_skips_posts_without_title():
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(post_title=None),
        post_element(),
    ])
    posts = _extract_posts_from_page(page, max_scrolls=1)
    assert len(posts) == 1
    assert posts[0]["title"] == "A sample post"


def test_extract_posts_returns_empty_when_no_content():
    page = FakePage()  # no shreddit-post locator registered
    assert _extract_posts_from_page(page, max_scrolls=1) == []


# ---------------------------------------------------------------------------
# _extract_comments
# ---------------------------------------------------------------------------

def test_extract_comments_joins_paragraphs_and_limits():
    page = FakePage()
    page.set_locator("shreddit-comment", [
        comment_element(author="alice", score="5", depth="1",
                        text_paragraphs=["First line", "Second line"]),
        comment_element(author="bob", score="-1", depth="2", text_paragraphs=[]),
        comment_element(author="carol", score="0", depth="3",
                        text_paragraphs=["Third"]),
    ])
    comments = _extract_comments(page, limit=2)
    assert len(comments) == 2
    assert comments[0]["author"] == "alice"
    assert comments[0]["text"] == "First line Second line"
    assert comments[0]["score"] == 5
    assert comments[0]["depth"] == 1


def test_extract_comments_fallback_selector():
    element = FakeElement(
        attrs={"author": "dave", "score": "2", "depth": "0"},
        children={"p": [FakeElement(text="fallback text")]},
    )
    page = FakePage()
    page.set_locator("shreddit-comment", [element])
    comments = _extract_comments(page, limit=10)
    assert len(comments) == 1
    assert comments[0]["text"] == "fallback text"


# ---------------------------------------------------------------------------
# _extract_post_body
# ---------------------------------------------------------------------------

def test_extract_post_body_deduplicates():
    page = FakePage()
    page.set_locator("[slot='text-body'] p", [
        FakeElement(text="Hello"),
        FakeElement(text="Hello"),  # duplicate across selectors
        FakeElement(text="World"),
    ])
    body = _extract_post_body(page)
    assert body == "Hello\nWorld"


# ---------------------------------------------------------------------------
# Subreddit stats helpers
# ---------------------------------------------------------------------------

def test_extract_created_date():
    page = FakePage()
    page.set_locator("shreddit-subreddit-header .community-details", [
        FakeElement(text="Created Jan 25, 2008 | Public"),
    ])
    assert _extract_created_date(page) == "Jan 25, 2008"
    assert _extract_created_date(FakePage()) is None


def test_extract_members_from_sidebar_found():
    page = FakePage()
    page.set_locator(
        "li.relative.list-none:has(span:text-matches('members', 'i'))",
        [
            FakeElement(
                text="r/learnpython | 27,335 members",
                children={"a[href*='/r/']": [
                    FakeElement(attrs={"href": "/r/learnpython/"})
                ]},
            ),
            FakeElement(
                text="r/Python | 1,051,152 members",
                children={"a[href*='/r/']": [
                    FakeElement(attrs={"href": "/r/Python/"})
                ]},
            ),
        ],
    )
    assert _extract_members_from_sidebar(page, "python") == 1_051_152
    assert _extract_members_from_sidebar(page, "golang") is None
    assert _extract_members_from_sidebar(FakePage(), "python") is None


def test_extract_user_karma():
    page = FakePage()
    page.set_evaluate_result("12k post karma\n3k comment karma")
    assert _extract_user_karma(page) == 12_000
    assert _extract_user_karma(FakePage()) is None


# ---------------------------------------------------------------------------
# _goto (navigation + retries)
# ---------------------------------------------------------------------------

def test_goto_success(monkeypatch):
    monkeypatch.setattr(server.Settings, "MAX_RETRIES", 3)
    monkeypatch.setattr(server.Settings, "RETRY_BACKOFF", 0)
    page = FakePage()
    _goto(page, "https://www.reddit.com/r/python/hot/")
    assert page.url == "https://www.reddit.com/r/python/hot/"


def test_goto_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(server.Settings, "MAX_RETRIES", 3)
    monkeypatch.setattr(server.Settings, "RETRY_BACKOFF", 0)
    page = FakePage()
    page.set_goto_failures(2)
    _goto(page, "https://www.reddit.com/r/python/hot/")
    assert page.url == "https://www.reddit.com/r/python/hot/"


def test_goto_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(server.Settings, "MAX_RETRIES", 2)
    monkeypatch.setattr(server.Settings, "RETRY_BACKOFF", 0)
    page = FakePage()
    page.set_goto_failures(5)
    with pytest.raises(RuntimeError, match="Failed to load"):
        _goto(page, "https://www.reddit.com/r/python/hot/")


def test_goto_detects_login_redirect(monkeypatch):
    monkeypatch.setattr(server.Settings, "MAX_RETRIES", 1)
    page = FakePage()
    page.set_goto_login_redirect(True)
    with pytest.raises(RuntimeError, match="login"):
        _goto(page, "https://www.reddit.com/r/python/hot/")


# ---------------------------------------------------------------------------
# search_reddit end-to-end (with fake page)
# ---------------------------------------------------------------------------

def _fake_session(page):
    @contextmanager
    def session():
        yield page
    return session()


def test_search_reddit_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element()])
    monkeypatch.setattr(server, "_page_session", lambda: _fake_session(page))
    monkeypatch.setattr(server, "_cache", server.TTLCache(0))
    monkeypatch.setattr(server.Settings, "REQUEST_DELAY", 0)

    result = server.search_reddit(["python"], limit=5)
    assert "error" not in result, result
    assert result["total_results"] == 1
    assert result["posts"][0]["subreddit"] == "python"
    assert result["posts"][0]["title"] == "A sample post"


def test_search_reddit_tool_keyword_filter(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(post_title="Best python packages"),
        post_element(post_title="Unrelated topic", permalink="/r/python/comments/1z/other/"),
    ])
    monkeypatch.setattr(server, "_page_session", lambda: _fake_session(page))
    monkeypatch.setattr(server, "_cache", server.TTLCache(0))
    monkeypatch.setattr(server.Settings, "REQUEST_DELAY", 0)

    result = server.search_reddit(["python"], limit=5, keywords=["package"])
    assert result["total_results"] == 1
    assert "package" in result["posts"][0]["title"].lower()


def test_search_reddit_tool_reports_subreddit_errors(monkeypatch):
    page = FakePage()
    page.set_goto_failures(10)  # navigation always fails
    monkeypatch.setattr(server, "_page_session", lambda: _fake_session(page))
    monkeypatch.setattr(server, "_cache", server.TTLCache(0))
    monkeypatch.setattr(server.Settings, "REQUEST_DELAY", 0)
    monkeypatch.setattr(server.Settings, "MAX_RETRIES", 1)

    result = server.search_reddit(["python"], limit=5)
    assert result["total_results"] == 0
    assert result["errors"] and "python" in result["errors"][0]


# ---------------------------------------------------------------------------
# Remaining tools, end-to-end with fake pages
# ---------------------------------------------------------------------------


def _configure(monkeypatch, page):
    """Shared plumbing: replace the browser session and cache with fakes."""
    monkeypatch.setattr(server, "_page_session", lambda: _fake_session(page))
    monkeypatch.setattr(server, "_cache", server.TTLCache(0))
    monkeypatch.setattr(server.Settings, "REQUEST_DELAY", 0)
    monkeypatch.setattr(server.Settings, "MAX_RETRIES", 2)
    monkeypatch.setattr(server.Settings, "RETRY_BACKOFF", 0)


class _FailingLocatorPage(FakePage):
    """A page whose locator raises for one specific selector."""

    def __init__(self, failing_selector):
        super().__init__()
        self._failing = failing_selector

    def locator(self, selector):
        if selector == self._failing:
            raise RuntimeError("locator exploded")
        return super().locator(selector)


class _RaisingElement(FakeElement):
    """An element that blows up when its attributes are read."""

    def __init__(self, children=None):
        super().__init__(text="", children=children)

    def get_attribute(self, name):
        raise RuntimeError("boom")


class _RaisingClosePage(FakePage):
    """A page whose close() raises (must be tolerated)."""

    def close(self):
        raise RuntimeError("close boom")


class _RaisingLocatorElement(FakeElement):
    """An element whose locator() raises (broken nested content)."""

    def locator(self, selector):
        raise RuntimeError("boom")


def test_search_reddit_query_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element()])
    _configure(monkeypatch, page)

    result = server.search_reddit_query("python packages", limit=5)
    assert "error" not in result, result
    assert result["total_results"] == 1
    assert result["posts"][0]["subreddit"] == "python"


def test_get_post_comments_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element(score="99")])
    page.set_locator("[slot='text-body'] p", [FakeElement(text="Post body text")])
    page.set_locator("shreddit-comment", [comment_element(author="alice")])
    _configure(monkeypatch, page)

    result = server.get_post_comments("/r/python/comments/1abc/a_sample_post/")
    assert "error" not in result, result
    assert result["post_title"] == "A sample post"
    assert result["post_score"] == 99
    assert result["post_body"] == "Post body text"
    assert result["total_comments"] == 1
    assert result["comments"][0]["author"] == "alice"
    # relative path was normalized to an absolute URL
    assert result["post_url"].startswith("https://www.reddit.com")


def test_get_post_details_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(
            content_href="https://example.com/article",
            permalink="/r/python/comments/1d/link_post/",
        )
    ])
    page.set_locator("[slot='text-body'] p", [FakeElement(text="Details")])
    _configure(monkeypatch, page)

    result = server.get_post_details("/r/python/comments/1d/link_post/")
    assert "error" not in result, result
    assert result["post_type"] == "link"
    assert result["external_url"] == "https://example.com/article"
    assert result["selftext"] == "Details"
    assert result["author"] == "someuser"


def test_get_subreddit_info_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-subreddit-header", [
        FakeElement(attrs={
            "display-name": "Python",
            "prefixed-name": "r/Python",
            "description": "The largest Python community",
            "subscribers-text": "Pythonistas",
            "weekly-active-users": "119028",
            "weekly-contributions": "627",
        })
    ])
    page.set_locator("shreddit-post", [post_element()])
    _configure(monkeypatch, page)

    result = server.get_subreddit_info("python")
    assert "error" not in result, result
    assert result["name"] == "Python"
    assert result["prefixed_name"] == "r/Python"
    assert result["description"] == "The largest Python community"
    assert result["active_users"] == 119028
    assert result["weekly_contributions"] == 627
    assert len(result["top_posts"]) == 1


def test_get_subreddit_info_tool_without_header(monkeypatch):
    page = FakePage()  # no shreddit-subreddit-header -> wait_for_selector raises
    _configure(monkeypatch, page)

    result = server.get_subreddit_info("python")
    assert "error" in result
    assert "header" in result["error"]


def test_get_user_posts_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element()])
    page.set_evaluate_result("12k post karma\n3k comment karma")
    _configure(monkeypatch, page)

    result = server.get_user_posts("u/someuser")
    assert "error" not in result, result
    assert result["username"] == "someuser"
    assert result["karma"] == 12_000
    assert result["total_results"] == 1


def test_get_trending_posts_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element(), post_element(permalink="/r/popular/x/")])
    _configure(monkeypatch, page)

    result = server.get_trending_posts(limit=2)
    assert "error" not in result, result
    assert result["total_results"] == 2
    assert result["source"] == "r/popular"


def test_analyze_opportunities_tool(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(score="100", comment_count="20"),
        post_element(
            post_title="I hate paying for SaaS subscriptions",
            score="50",
            comment_count="25",
            permalink="/r/saas/comments/1e/pain/",
        ),
    ])
    _configure(monkeypatch, page)

    result = server.analyze_opportunities(["python"], min_score=0, limit=5)
    assert "error" not in result, result
    assert result["total_posts_scanned"] == 2
    assert result["total_results"] == 2
    # keyword-rich post scores higher
    assert result["ideas"][0]["opportunity_score"] > result["ideas"][1]["opportunity_score"]
    assert "saas" in result["ideas"][0]["matched_keywords"]
    assert result["ideas"][0]["subreddit"] == "python"


def test_analyze_opportunities_tool_respects_min_score(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element(score="5", comment_count="1")])
    _configure(monkeypatch, page)

    result = server.analyze_opportunities(["python"], min_score=5000, limit=5)
    assert "error" not in result, result
    assert result["total_results"] == 0


# ---------------------------------------------------------------------------
# Tool error paths
# ---------------------------------------------------------------------------


def _failing_page():
    page = FakePage()
    page.set_goto_failures(10)  # navigation always fails
    return page


def test_search_reddit_query_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.search_reddit_query("anything")
    assert "error" in result


def test_get_post_comments_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.get_post_comments("/r/python/comments/1abc/")
    assert "error" in result


def test_get_post_details_tool_not_found(monkeypatch):
    _configure(monkeypatch, FakePage())  # no shreddit-post on the page
    result = server.get_post_details("/r/python/comments/1abc/a_sample_post/")
    assert "error" in result
    assert "not found" in result["error"]


def test_get_post_details_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.get_post_details("/r/python/comments/1abc/a_sample_post/")
    assert "error" in result


def test_get_user_posts_tool_empty_username(monkeypatch):
    _configure(monkeypatch, FakePage())
    result = server.get_user_posts("   ")
    assert "error" in result


def test_get_user_posts_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.get_user_posts("someuser")
    assert "error" in result


def test_get_trending_posts_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.get_trending_posts()
    assert "error" in result


def test_analyze_opportunities_tool_empty_subreddits(monkeypatch):
    _configure(monkeypatch, FakePage())
    result = server.analyze_opportunities([])
    assert "error" in result


def test_analyze_opportunities_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.analyze_opportunities(["python"], min_score=0)
    assert result["total_results"] == 0
    assert result["errors"]


def test_search_reddit_tool_empty_subreddits(monkeypatch):
    _configure(monkeypatch, FakePage())
    result = server.search_reddit([])
    assert "error" in result


# ---------------------------------------------------------------------------
# Fallback / resilience paths
# ---------------------------------------------------------------------------


def test_extract_post_body_respects_max_blocks():
    page = FakePage()
    page.set_locator("[slot='text-body'] p", [
        FakeElement(text=f"Paragraph {i}") for i in range(60)
    ])
    body = _extract_post_body(page, max_blocks=50)
    assert body.count("\n") == 49  # 50 paragraphs, then stops


def test_extract_post_body_falls_back_on_selector_error():
    page = _FailingLocatorPage("[slot='text-body'] p")
    page.set_locator(".md p", [FakeElement(text="Fallback text")])
    assert _extract_post_body(page) == "Fallback text"


def test_extract_posts_survives_scroll_failure():
    page = FakePage()
    page.set_locator("shreddit-post", [post_element()])
    page.set_scroll_fail()
    posts = _extract_posts_from_page(page, max_scrolls=2)
    assert len(posts) == 1


def test_extract_created_date_handles_missing_details():
    page = _FailingLocatorPage("shreddit-subreddit-header .community-details")
    assert _extract_created_date(page) is None


def test_extract_members_handles_locator_error():
    page = _FailingLocatorPage(
        "li.relative.list-none:has(span:text-matches('members', 'i'))"
    )
    assert _extract_members_from_sidebar(page, "python") is None


def test_extract_posts_skips_broken_elements():
    page = FakePage()
    page.set_locator("shreddit-post", [_RaisingElement(), post_element()])
    posts = _extract_posts_from_page(page, max_scrolls=1)
    assert len(posts) == 1
    assert posts[0]["title"] == "A sample post"


def test_extract_comments_skips_broken_elements():
    page = FakePage()
    page.set_locator("shreddit-comment", [
        _RaisingElement(children={"div[slot='comment'] p": [FakeElement(text="hi")]}),
        comment_element(author="ok"),
    ])
    comments = _extract_comments(page, limit=10)
    assert len(comments) == 1
    assert comments[0]["author"] == "ok"


def test_scroll_page_direct():
    page = FakePage()
    server._scroll_page(page)  # max_scrolls=None -> Settings.MAX_SCROLLS
    server._scroll_page(page, 2)  # success path
    server._scroll_page(page, 0)  # zero iterations
    server._scroll_page(page, -1)  # clamped to zero iterations


def test_extract_comments_handles_broken_nested_selector():
    page = FakePage()
    page.set_locator("shreddit-comment", [
        _RaisingLocatorElement(),  # locator raises -> inner except/continue
        comment_element(author="ok"),
    ])
    comments = _extract_comments(page, limit=10)
    assert len(comments) == 1
    assert comments[0]["author"] == "ok"


def test_extract_members_skips_items_without_link():
    page = FakePage()
    page.set_locator(
        "li.relative.list-none:has(span:text-matches('members', 'i'))",
        [
            FakeElement(text="r/other | 100 members"),  # no <a> child -> skip
            FakeElement(
                text="r/Python | 1,051,152 members",
                children={"a[href*='/r/']": [
                    FakeElement(attrs={"href": "/r/Python/"})
                ]},
            ),
        ],
    )
    assert _extract_members_from_sidebar(page, "python") == 1_051_152


def test_extract_members_ignores_broken_items():
    page = FakePage()
    page.set_locator(
        "li.relative.list-none:has(span:text-matches('members', 'i'))",
        [
            _RaisingLocatorElement(),  # broken item -> except/continue
            FakeElement(
                text="r/Python | 1,051,152 members",
                children={"a[href*='/r/']": [
                    FakeElement(attrs={"href": "/r/Python/"})
                ]},
            ),
        ],
    )
    assert _extract_members_from_sidebar(page, "python") == 1_051_152


def test_get_subreddit_info_tool_cache_hit(monkeypatch):
    info = {"subreddit": "r/python", "from_cache": True}
    cache = server.TTLCache(60)
    cache.set("subreddit_info|python", info)
    monkeypatch.setattr(server, "_cache", cache)

    def _boom():
        raise AssertionError("page session must not be opened on a cache hit")

    monkeypatch.setattr(server, "_page_session", _boom)
    assert server.get_subreddit_info("python") is info


def test_analyze_opportunities_tool_default_subreddits(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element(score="100", comment_count="20")])
    _configure(monkeypatch, page)
    result = server.analyze_opportunities()  # subreddits=None -> DEFAULT_SUBREDDITS
    assert "error" not in result
    assert result["subreddits_scanned"] == server.DEFAULT_SUBREDDITS
    assert result["total_posts_scanned"] == len(server.DEFAULT_SUBREDDITS)


def test_analyze_opportunities_tool_keyword_filter_skips(monkeypatch):
    page = FakePage()
    page.set_locator("shreddit-post", [post_element(score="100", comment_count="20")])
    _configure(monkeypatch, page)
    result = server.analyze_opportunities(
        ["python"], min_score=0, keywords=["zzz-no-match"]
    )
    assert result["total_posts_scanned"] == 1
    assert result["total_results"] == 0


def test_extract_user_karma_handles_evaluate_error():
    page = FakePage()
    page.set_scroll_fail()  # evaluate raises
    assert _extract_user_karma(page) is None


# ---------------------------------------------------------------------------
# get_post_details post_type branches
# ---------------------------------------------------------------------------


def _details_page(content_href=None):
    page = FakePage()
    page.set_locator("shreddit-post", [
        post_element(content_href=content_href, permalink="/r/python/comments/1d/link_post/")
    ])
    return page


def test_get_post_details_post_type_self(monkeypatch):
    page = _details_page()  # no content-href -> self
    _configure(monkeypatch, page)
    result = server.get_post_details("/r/python/comments/1d/link_post/")
    assert result["post_type"] == "self"
    assert result["external_url"] is None


def test_get_post_details_post_type_image(monkeypatch):
    page = _details_page(content_href="https://i.redd.it/abc.png")
    _configure(monkeypatch, page)
    result = server.get_post_details("/r/python/comments/1d/link_post/")
    assert result["post_type"] == "image"


def test_get_post_details_post_type_video(monkeypatch):
    page = _details_page(content_href="https://v.redd.it/abc.mp4")
    _configure(monkeypatch, page)
    result = server.get_post_details("/r/python/comments/1d/link_post/")
    assert result["post_type"] == "video"


# ---------------------------------------------------------------------------
# get_subreddit_info error path
# ---------------------------------------------------------------------------


def test_get_subreddit_info_tool_error(monkeypatch):
    _configure(monkeypatch, _failing_page())
    result = server.get_subreddit_info("python")
    assert "error" in result


def test_page_session_ignores_close_errors(monkeypatch):
    page = _RaisingClosePage()
    monkeypatch.setattr(server, "_get_page", lambda: page)
    with server._page_session():
        pass  # must exit cleanly even though page.close() raises


def test_health_check():
    result = server.health_check()
    assert result["status"] == "ok"
    assert result["version"]
