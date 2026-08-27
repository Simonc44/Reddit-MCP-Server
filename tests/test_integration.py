"""Live integration tests against the real Reddit website.

These tests make real network requests and require Playwright Chromium to be
installed, so they are **skipped by default**. Run them explicitly with:

    REDDIT_LIVE_TESTS=1 pytest -m integration

They validate the scraping selectors end-to-end (the unit tests in
test_server.py never touch the network). If they fail, Reddit probably
changed its DOM — open an issue with the failure output.
"""

import os

import pytest

import server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("REDDIT_LIVE_TESTS") != "1",
        reason="set REDDIT_LIVE_TESTS=1 to run live tests against reddit.com",
    ),
]


def test_search_reddit_live():
    result = server.search_reddit(["python"], sort="hot", limit=3)
    assert result.get("error") is None, result
    assert result["total_results"] > 0
    for post in result["posts"]:
        assert post["title"]
        assert post["url"] and post["url"].startswith("https://")
        assert post["author"]
        assert isinstance(post["score"], int)
        assert isinstance(post["num_comments"], int)


def test_search_reddit_keyword_filter_live():
    result = server.search_reddit(["python"], limit=5, keywords=["package"])
    assert result.get("error") is None, result
    for post in result["posts"]:
        assert "package" in post["title"].lower()


def test_subreddit_info_live():
    info = server.get_subreddit_info("python")
    assert info.get("error") is None, info
    assert info["name"]
    assert info["prefixed_name"] == "r/Python" or info["prefixed_name"]
    assert info["description"]
    assert isinstance(info["top_posts"], list) and len(info["top_posts"]) > 0


def test_post_details_and_comments_live():
    listing = server.search_reddit(["python"], limit=1)
    assert listing["total_results"] > 0
    post_url = listing["posts"][0]["url"]

    details = server.get_post_details(post_url)
    assert details.get("error") is None, details
    assert details["title"]
    assert details["subreddit"]

    comments = server.get_post_comments(post_url, limit=3)
    assert comments.get("error") is None, comments
    assert comments["post_title"]
    assert isinstance(comments["comments"], list)


def test_analyze_opportunities_live():
    result = server.analyze_opportunities(["Python"], min_score=0, limit=3)
    assert result.get("error") is None, result
    assert result["total_posts_scanned"] > 0
    assert isinstance(result["ideas"], list)
    for idea in result["ideas"]:
        assert idea["opportunity_score"] >= 0
        assert idea["title"]
        assert idea["url"]


def test_trending_posts_live():
    result = server.get_trending_posts(limit=3)
    assert result.get("error") is None, result
    assert result["total_results"] > 0
