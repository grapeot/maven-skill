import pytest

from maven_skill.errors import MavenError
from maven_skill.ops import (
    _read_account_menu,
    account_menu_failure,
    account_menu_signal,
    choose_dashboard_href,
)


DASHBOARD = "https://maven.com/acme/admin"
OTHER_ADMIN = "https://maven.com/acme/admin/courses"


def item(text, href=None):
    return {"text": text, "href": href}


def test_exact_dashboard_label_wins_over_other_admin_links():
    items = [
        item("Logout"),
        item("Course settings", OTHER_ADMIN),
        item("Dashboard", DASHBOARD),
    ]
    assert choose_dashboard_href(items) == DASHBOARD


def test_unique_admin_root_is_used_when_logged_in_and_label_changed():
    items = [
        item("Logout"),
        item("Instructor home", DASHBOARD),
        item("Students", "https://maven.com/acme/admin/students"),
    ]
    assert choose_dashboard_href(items) == DASHBOARD


def test_admin_root_fallback_requires_an_authenticated_menu():
    items = [item("Instructor home", DASHBOARD)]
    assert choose_dashboard_href(items) is None
    assert account_menu_signal(items) == "unknown"


def test_admin_root_fallback_does_not_match_nested_admin_paths():
    items = [
        item("Logout"),
        item("Courses", OTHER_ADMIN),
    ]
    assert choose_dashboard_href(items) is None


def test_multiple_admin_roots_are_not_guessed():
    items = [
        item("Logout"),
        item("Home", DASHBOARD),
        item("Other", "https://maven.com/other/admin"),
    ]
    assert choose_dashboard_href(items) is None


def test_disagreeing_dashboard_labels_are_refused():
    items = [
        item("Dashboard", DASHBOARD),
        item("Dashboard", "https://maven.com/other/admin"),
    ]
    with pytest.raises(MavenError, match="more than one Dashboard"):
        choose_dashboard_href(items)


def test_logout_without_dashboard_is_a_layout_error_not_an_auth_error():
    items = [item("Logout"), item("Student profile", "https://maven.com/acme/profile")]
    error = account_menu_failure(items)
    assert "layout changed" in str(error)
    assert "unauthenticated" not in str(error)
    assert account_menu_signal(items) == "authenticated"


def test_login_action_is_unauthenticated():
    items = [item("Log in", "https://maven.com/login"), item("Sign up")]
    error = account_menu_failure(items)
    assert "not authenticated" in str(error)
    assert "layout changed" not in str(error)


def test_unknown_menu_keeps_the_ambiguous_error():
    error = account_menu_failure([item("Help")])
    assert "may be unauthenticated or the page layout changed" in str(error)


class PollPage:
    def __init__(self, frames):
        self.frames = frames
        self.calls = 0
        self.waits = 0

    def evaluate(self, script):
        frame = self.frames[min(self.calls, len(self.frames) - 1)]
        self.calls += 1
        return frame

    def wait_for_timeout(self, timeout):
        self.waits += 1


def test_menu_reader_waits_until_the_dashboard_link_appears():
    early = [item("Logout"), item("Student profile", "https://maven.com/acme/profile")]
    ready = early + [item("Dashboard", DASHBOARD)]
    page = PollPage([early, ready])
    items = _read_account_menu(page, timeout_ms=1000)
    assert choose_dashboard_href(items) == DASHBOARD
    assert page.calls == 2
    assert page.waits == 1


def test_renamed_admin_root_is_not_taken_from_the_first_paint():
    early = [item("Logout"), item("Instructor home", DASHBOARD)]
    page = PollPage([early])
    items = _read_account_menu(page, timeout_ms=250)
    assert page.calls > 1
    assert items == early
