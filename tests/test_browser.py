"""Offline tests for the browser lifecycle.

Covers request blocking (_handle_route), the shared browser lifecycle
(_get_page, close_browser, _page_session), the environment helpers and
main() — all without launching a real browser.
"""

import pytest

import server
from tests.fakes import (
    FakeBrowser,
    FakeContext,
    FakePage,
    FakePlaywright,
    FakeRoute,
)

# ---------------------------------------------------------------------------
# _handle_route — request blocking
# ---------------------------------------------------------------------------

def test_handle_route_aborts_media():
    route = FakeRoute(resource_type="image", url="https://i.redd.it/x.png")
    server._handle_route(route)
    assert route.aborted
    assert not route.continued


@pytest.mark.parametrize("resource_type", ["media", "font"])
def test_handle_route_aborts_heavy_resource_types(resource_type):
    route = FakeRoute(resource_type=resource_type, url="https://x.com/anything")
    server._handle_route(route)
    assert route.aborted


def test_handle_route_aborts_asset_urls():
    route = FakeRoute(resource_type="script", url="https://x.com/logo.png?v=2")
    server._handle_route(route)
    assert route.aborted


def test_handle_route_aborts_tracker_domains():
    route = FakeRoute(
        resource_type="script",
        url="https://www.google-analytics.com/ga.js",
    )
    server._handle_route(route)
    assert route.aborted


def test_handle_route_continues_other_requests():
    route = FakeRoute(
        resource_type="script",
        url="https://www.reddit.com/static/app.js",
    )
    server._handle_route(route)
    assert route.continued
    assert not route.aborted


# ---------------------------------------------------------------------------
# _get_page / close_browser / _page_session
# ---------------------------------------------------------------------------

def test_get_page_creates_shared_browser(monkeypatch):
    fake = FakePlaywright()
    monkeypatch.setattr(server, "sync_playwright", lambda: fake)
    monkeypatch.setattr(server, "_pw", None)
    monkeypatch.setattr(server, "_browser", None)
    monkeypatch.setattr(server, "_context", None)

    page1 = server._get_page()
    page2 = server._get_page()

    assert page1 is page2  # shared context reused across calls
    assert server._context is fake.chromium.browser.context
    assert server._context.routes == [("**/*", server._handle_route)]
    assert fake.chromium.browser.last_context_kwargs["locale"] == "en-US"


def test_close_browser_closes_everything(monkeypatch):
    ctx, browser, pw = FakeContext(), FakeBrowser(), FakePlaywright()
    monkeypatch.setattr(server, "_context", ctx)
    monkeypatch.setattr(server, "_browser", browser)
    monkeypatch.setattr(server, "_pw", pw)

    server.close_browser()

    assert ctx.closed
    assert browser.closed
    assert pw.stopped
    assert server._context is None
    assert server._browser is None
    assert server._pw is None


def test_close_browser_with_nothing(monkeypatch):
    monkeypatch.setattr(server, "_context", None)
    monkeypatch.setattr(server, "_browser", None)
    monkeypatch.setattr(server, "_pw", None)
    server.close_browser()  # must not raise
    assert server._pw is None


def test_close_browser_swallows_errors(monkeypatch):
    class BadContext(FakeContext):
        def close(self):
            raise RuntimeError("boom")

    class BadBrowser(FakeBrowser):
        def close(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(server, "_context", BadContext())
    monkeypatch.setattr(server, "_browser", BadBrowser())
    monkeypatch.setattr(server, "_pw", None)

    server.close_browser()  # must not raise
    assert server._context is None


def test_page_session_yields_and_closes_page(monkeypatch):
    page = FakePage()
    monkeypatch.setattr(server, "_get_page", lambda: page)

    with server._page_session() as yielded:
        assert yielded is page
    assert page.closed


def test_page_session_closes_page_on_error(monkeypatch):
    page = FakePage()
    monkeypatch.setattr(server, "_get_page", lambda: page)

    with pytest.raises(RuntimeError), server._page_session():
        raise RuntimeError("boom")
    assert page.closed


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def test_env_int(monkeypatch):
    monkeypatch.setenv("REDDIT_TEST_INT", "not-a-number")
    assert server._env_int("REDDIT_TEST_INT", 5) == 5
    monkeypatch.setenv("REDDIT_TEST_INT", "42")
    assert server._env_int("REDDIT_TEST_INT", 5) == 42


def test_env_float(monkeypatch):
    monkeypatch.setenv("REDDIT_TEST_FLOAT", "abc")
    assert server._env_float("REDDIT_TEST_FLOAT", 1.5) == 1.5
    monkeypatch.setenv("REDDIT_TEST_FLOAT", "2.5")
    assert server._env_float("REDDIT_TEST_FLOAT", 1.5) == 2.5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("off", False),
        ("garbage", False),
    ],
)
def test_env_bool(monkeypatch, raw, expected):
    monkeypatch.setenv("REDDIT_TEST_BOOL", raw)
    assert server._env_bool("REDDIT_TEST_BOOL", False) is expected


def test_env_bool_default_when_unset(monkeypatch):
    monkeypatch.delenv("REDDIT_TEST_BOOL", raising=False)
    assert server._env_bool("REDDIT_TEST_BOOL", True) is True


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def test_main_runs_mcp(monkeypatch):
    ran = []
    monkeypatch.setattr(server.mcp, "run", lambda: ran.append(1))
    server.main()
    assert ran == [1]
