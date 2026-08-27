"""Minimal fakes for the Playwright objects used by the scraping helpers.

These let the extraction logic (selectors, attributes, dedup, retries) be
unit-tested offline — no browser, no network. The fakes only implement the
subset of the API that server.py actually uses.
"""


from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    # These names ARE used at runtime, as base classes via the conditional-
    # expression trick (Page if TYPE_CHECKING else object).
    from playwright.sync_api import ElementHandle, Locator, Page  # noqa: TC004


class FakeElement(ElementHandle if TYPE_CHECKING else object):  # type: ignore[misc]
    """Fake of a Playwright element (used both directly and via locators)."""

    def __init__(self, attrs=None, text="", children=None):
        self._attrs = attrs or {}
        self._text = text
        self._children = children or {}

    def get_attribute(self, name):
        return self._attrs.get(name)

    def inner_text(self):
        return self._text

    def children(self, selector):
        return self._children.get(selector, [])

    def locator(self, selector):
        return FakeLocator(self.children(selector))


class FakeLocator(Locator if TYPE_CHECKING else object):  # type: ignore[misc]
    """Fake of a Playwright locator wrapping a list of FakeElements."""

    def __init__(self, elements=None):
        self._elements = elements or []

    @property
    def first(self):
        return FakeLocator(self._elements[:1])

    def all(self):
        return list(self._elements)

    def count(self):
        return len(self._elements)

    def get_attribute(self, name):
        return self._elements[0].get_attribute(name) if self._elements else None

    def inner_text(self, timeout=None):
        return self._elements[0].inner_text() if self._elements else ""

    def locator(self, selector):
        children = []
        for element in self._elements:
            children.extend(element.children(selector))
        return FakeLocator(children)


class FakePage(Page if TYPE_CHECKING else object):  # type: ignore[misc]
    """Fake of a Playwright Page with configurable locators and navigation."""

    def __init__(self, url="https://www.reddit.com/r/python/"):
        self.url = url
        self._locators = {}
        self._goto_failures = 0
        self._evaluate_result = ""
        self._goto_login_redirect = False
        self._scroll_fail = False
        self.closed = False

    # --- configuration helpers used by the tests ---

    def set_locator(self, selector, elements):
        self._locators[selector] = FakeLocator(elements)

    def set_evaluate_result(self, value):
        self._evaluate_result = value

    def set_goto_failures(self, count):
        self._goto_failures = count

    def set_goto_login_redirect(self, enabled=True):
        self._goto_login_redirect = enabled

    def set_scroll_fail(self, enabled=True):
        self._scroll_fail = enabled

    # --- Playwright API used by server.py ---

    def locator(self, selector):
        return self._locators.get(selector, FakeLocator([]))

    def evaluate(self, expression):
        if self._scroll_fail:
            raise RuntimeError("scroll failed")
        if expression.startswith("window.scrollTo"):
            return None
        return self._evaluate_result

    def close(self):
        self.closed = True

    def wait_for_timeout(self, ms):
        pass

    def wait_for_selector(self, selector, timeout=None):
        if not self._locators.get(selector, FakeLocator([])).count():
            raise TimeoutError(f"selector {selector} never appeared")

    def goto(self, url, wait_until=None, timeout=None):
        if self._goto_failures > 0:
            self._goto_failures -= 1
            raise TimeoutError("navigation timed out")
        self.url = (
            "https://www.reddit.com/login/"
            if self._goto_login_redirect
            else url
        )


def post_element(**attrs):
    """Build a FakeElement shaped like a <shreddit-post> with sensible defaults."""
    defaults = {
        "post-title": "A sample post",
        "permalink": "/r/python/comments/1abc/a_sample_post/",
        "score": "42",
        "comment-count": "7",
        "author": "someuser",
        "created-timestamp": "2026-01-01T00:00:00.000000+0000",
    }
    # Python kwargs cannot contain hyphens, so content_href -> content-href
    defaults.update({k.replace("_", "-"): v for k, v in attrs.items()})
    return FakeElement(attrs=defaults)


class FakeRequest:
    """Fake of a Playwright Request (used by _handle_route tests)."""

    def __init__(self, resource_type="document", url="https://www.reddit.com/"):
        self.resource_type = resource_type
        self.url = url


class FakeRoute:
    """Fake of a Playwright Route recording abort/continue calls."""

    def __init__(self, resource_type="document", url="https://www.reddit.com/"):
        self.request = FakeRequest(resource_type, url)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class FakePlaywright:
    """Fake of the sync_playwright() result."""

    def __init__(self):
        self.chromium = FakeChromium()
        self.stopped = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True


class FakeChromium:
    """Fake of playwright.chromium."""

    def __init__(self):
        self.browser = FakeBrowser()

    def launch(self, headless=True):
        return self.browser


class FakeBrowser:
    """Fake of a Playwright Browser."""

    def __init__(self):
        self.context = FakeContext()
        self.closed = False
        self.last_context_kwargs = {}

    def new_context(self, **kwargs):
        self.last_context_kwargs = kwargs
        return self.context

    def close(self):
        self.closed = True


class FakeContext:
    """Fake of a Playwright BrowserContext."""

    def __init__(self):
        self.page = FakePage()
        self.routes = []
        self.closed = False

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


def comment_element(author="someone", score="5", depth="1", text_paragraphs=None):
    """Build a FakeElement shaped like a <shreddit-comment>."""
    paragraphs = text_paragraphs or ["Hello world"]
    children = {
        "div[slot='comment'] p": [
            FakeElement(text=p) for p in paragraphs
        ]
    }
    return FakeElement(
        attrs={"author": author, "score": score, "depth": depth},
        children=children,
    )
