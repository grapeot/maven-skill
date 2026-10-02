from pathlib import Path

import pytest

from maven_skill.errors import MavenError
from maven_skill.ops import work_page


class Page:
    def __init__(self):
        self.closed = False
        self.viewport = None

    def set_viewport_size(self, size):
        self.viewport = size

    def close(self):
        self.closed = True


class Context:
    def __init__(self):
        self.pages = [Page()]
        self.closed = False
        self.created = []

    def new_page(self):
        page = Page()
        self.created.append(page)
        return page

    def close(self):
        self.closed = True
        for page in self.created:
            page.close()


class Browser:
    def __init__(self):
        self.contexts = [Context()]
        self.closed = False
        self.storage = None

    def new_context(self, storage_state=None):
        self.storage = storage_state
        context = Context()
        self.contexts.append(context)
        return context

    def close(self):
        self.closed = True


def test_default_work_page_closes_only_the_new_tab():
    browser = Browser()
    existing = browser.contexts[0].pages[0]
    with work_page(browser, None) as page:
        assert page is not existing
        assert page.viewport == {"width": 1440, "height": 1000}
    assert page.closed
    assert not existing.closed
    assert not browser.contexts[0].closed
    assert not browser.closed


def test_auth_state_uses_a_new_context_and_does_not_close_browser(tmp_path):
    state = tmp_path / "auth.json"
    state.write_text("{}")
    browser = Browser()
    with work_page(browser, state) as page:
        assert page in browser.contexts[1].created
    assert browser.storage == str(state)
    assert browser.contexts[1].closed
    assert not browser.contexts[0].closed
    assert not browser.closed


def test_missing_auth_state_does_not_open_a_context(tmp_path):
    browser = Browser()
    with pytest.raises(MavenError, match="auth state"):
        with work_page(browser, Path(tmp_path / "missing.json")):
            pass
    assert browser.storage is None
    assert not browser.closed
