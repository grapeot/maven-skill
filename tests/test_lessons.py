import json
import re

import pytest

from maven_skill import ops
from maven_skill.errors import MavenError
from maven_skill.ops import (
    LESSON_EDITOR_JS,
    LESSON_EDITOR_READY_JS,
    LESSON_PUBLISHED_JS,
    LESSON_ROUTE_READY_JS,
    LESSON_SIGNUPS_READY_JS,
    LESSON_TEXT_COUNTS_JS,
    LESSONS_LIST_JS,
    LESSONS_LIST_READY_JS,
    LESSONS_NAV_JS,
    READ_ONLY_SCRIPTS,
    ReadOnlyPage,
    lessons_stats,
    list_lessons,
    show_lesson,
    work_page,
)
from maven_skill.parse import (
    DENIED_CONTROL_LABELS,
    assert_click_allowed,
    assert_public_output,
    measure,
    parse_duration_minutes,
    parse_editor_date,
    parse_lesson_list,
    parse_lesson_ref,
    parse_list_date,
    parse_recording_viewers,
    parse_signups_tab,
    summarize_editor,
    summarize_published,
)


BASE = "https://maven.com/acme/admin/lightning-lessons"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def list_state():
    return {
        "sections": [
            {"label": "Drafts", "count": 1, "cards": [
                {"href": f"{BASE}/abc123", "title": "Build a Toy Compiler", "items": ["Draft"]},
            ]},
            {"label": "Upcoming", "count": 1, "cards": [
                {"href": f"{BASE}/def456", "title": "Ship Small Tools",
                 "items": ["12 students", "Wed, Oct 21, 2026, 11:00AM PDT"]},
            ]},
            {"label": "Past", "count": 2, "cards": [
                {"href": f"{BASE}/ghi789", "title": "Intro to Widgets",
                 "items": ["3,579 students", "Sat, Jun 1, 2024, 1:00PM PDT"]},
                {"href": f"{BASE}/jkl012", "title": "Contact ada@example.com", "items": []},
            ]},
        ],
        "ungrouped": 0,
        "next_control": False,
    }


def editor_state(**overrides):
    state = {
        "title": {"value": "Build a Toy Compiler", "counter": "20/60"},
        "date": "10/21/2026",
        "start_time": "11:00 AM",
        "duration": "1 hour 15 minutes",
        "timezone_text": "All times are in America/Los_Angeles",
        "link": {"add_button": True, "update_button": False},
        "outcomes": [
            {"title": "Parse tokens", "title_counter": "12/60",
             "description": "x" * 100, "description_counter": "100/120", "error": False},
            {"title": "Emit code", "title_counter": None,
             "description": "y" * 130, "description_counter": None, "error": True},
        ],
        "topic": {"value": "z" * 300, "counter": "300/450"},
        "instructors": [
            {"texts": ["01", "Name"], "error": True},
            {"texts": ["Pat Example"], "error": False},
        ],
        "header": ["50% Complete", "Review 2 errors", "Publish"],
        "inline_errors": ["Add an event link before publishing.", "Add an event link before publishing."],
    }
    state.update(overrides)
    return state


def published_data(**overrides):
    data = {
        "published": True,
        "slug": "ghi789",
        "now": "2026-10-03T12:00:00Z",
        "start_datetime": "2024-06-01T20:00:00Z",
        "start_date": "2024-06-01",
        "start_time": "13:00:00",
        "timezone": "America/Los_Angeles",
        "duration_min": 30,
        "has_location": True,
        "signup_count": 120,
        "recording_unique_viewer_count": 45,
        "is_canceled": False,
        "is_delisted": False,
        "is_visible_on_discovery_page": True,
        "connected_course": True,
        "promo_code": False,
        "location": "https://zoom.us/j/123?pwd=abc",
    }
    data.update(overrides)
    return data


# --- list parsing ------------------------------------------------------------------

def test_lesson_list_parses_status_dates_and_signups():
    lessons, completeness = parse_lesson_list(list_state(), BASE)
    assert [item["id"] for item in lessons] == ["abc123", "def456", "ghi789", "jkl012"]
    assert [item["status"] for item in lessons] == ["draft", "upcoming", "past", "past"]
    assert lessons[0]["signups"] is None and lessons[0]["date"] is None
    assert lessons[1]["date"] == "2026-10-21" and lessons[1]["time"] == "11:00AM"
    assert lessons[1]["signups"] == 12
    assert lessons[2]["signups"] == 3579
    assert lessons[2]["admin_url"] == f"{BASE}/ghi789"
    assert lessons[3]["title"] == ""
    assert completeness["status"] == "complete"
    assert completeness["sections"]["past"] == {"declared": 2, "parsed": 2}


@pytest.mark.parametrize("mutate", [
    lambda s: s["sections"][2].update(count=3),
    lambda s: s.update(ungrouped=1),
    lambda s: s.update(next_control=True),
    lambda s: s["sections"][0].update(label="Archived"),
    lambda s: s["sections"][0]["cards"].append({"href": "https://maven.com/acme/admin/courses/x", "title": "", "items": []}),
])
def test_lesson_list_reports_partial(mutate):
    state = list_state()
    mutate(state)
    _, completeness = parse_lesson_list(state, BASE)
    assert completeness["status"] == "partial"


def test_list_date_parser():
    assert parse_list_date("Tue, Mar 3, 2026, 9:00AM PST") == {
        "date": "2026-03-03", "time": "9:00AM", "tz_abbr": "PST"}
    assert parse_list_date("Draft") is None


# --- references --------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("abc123", (None, "abc123")),
    (f"{BASE}/abc123", (BASE, "abc123")),
    (f"{BASE}/abc123/edit", (BASE, "abc123")),
    (f"{BASE}/abc123?tab=signups", (BASE, "abc123")),
])
def test_lesson_ref_accepts_ids_and_admin_urls(value, expected):
    assert parse_lesson_ref(value) == expected


@pytest.mark.parametrize("value", [
    "https://example.com/acme/admin/lightning-lessons/abc123",
    "http://maven.com/acme/admin/lightning-lessons/abc123",
    "https://maven.com/acme/admin/courses/abc123",
    "abc/../123",
    "",
])
def test_lesson_ref_rejects_other_urls(value):
    with pytest.raises(MavenError):
        parse_lesson_ref(value)


# --- editor summary ----------------------------------------------------------------

def test_measure_prefers_page_counter_and_flags_over_limit():
    assert measure("abc", "5/60", 60) == {"length": 5, "limit": 60, "over_limit": False, "source": "page_counter"}
    assert measure("a" * 61, None, 60) == {"length": 61, "limit": 60, "over_limit": True, "source": "computed"}


@pytest.mark.parametrize("text,minutes", [
    ("30 minutes", 30), ("1 hour", 60), ("1 hour 15 minutes", 75), ("3 hours", 180),
    ("1.5 hours", 90), ("", None), ("soon", None),
])
def test_duration_parser(text, minutes):
    assert parse_duration_minutes(text) == minutes


def test_editor_date_parser():
    assert parse_editor_date("10/21/2026") == "2026-10-21"
    assert parse_editor_date("2026-10-21") is None


def test_editor_summary_reports_limits_errors_and_link_boolean():
    summary = summarize_editor(editor_state())
    assert summary["title_chars"]["length"] == 20
    assert summary["date"] == "2026-10-21"
    assert summary["start_time"] == "11:00 AM"
    assert summary["timezone"] == "America/Los_Angeles"
    assert summary["duration_minutes"] == 75
    assert summary["event_link_set"] is False
    assert summary["learning_outcome_count"] == 2
    assert summary["recommended_outcomes"] == 3
    second = summary["learning_outcomes"][1]
    assert second["description_chars"] == {"length": 130, "limit": 120, "over_limit": True, "source": "computed"}
    assert summary["topic_desc_chars"]["limit"] == 450
    assert [item["name"] for item in summary["instructors"]] == [None, "Pat Example"]
    assert summary["completion_percent"] == 50
    assert summary["header_reports_complete"] is False
    errors = summary["publish_errors"]
    assert errors["review_count"] == 2
    assert errors["visible_messages"] == ["Add an event link before publishing."]
    assert errors["flagged_outcomes"] == [2]
    assert errors["flagged_instructors"] == [1]
    assert "event link is missing (hard publish blocker)" in errors["derived_checks"]
    assert "learning outcome 2 exceeds a character limit" in errors["derived_checks"]


def test_editor_summary_complete_header_and_link_states():
    done = summarize_editor(editor_state(header=["Publish"], link={"add_button": False, "update_button": True}))
    assert done["event_link_set"] is True
    assert done["completion_percent"] is None
    assert done["header_reports_complete"] is True
    unknown = summarize_editor(editor_state(link={}))
    assert unknown["event_link_set"] is None


def test_editor_summary_never_prints_emails():
    state = editor_state(
        title={"value": "Mail ada@example.com", "counter": None},
        instructors=[{"texts": ["bea@example.com"], "error": False}],
        inline_errors=["Contact cy@example.com"],
    )
    summary = summarize_editor(state)
    assert not EMAIL_RE.search(json.dumps(summary))
    assert summary["instructors"][0]["name"] is None


# --- published data and stats ------------------------------------------------------

def test_published_summary_is_aggregate_only():
    summary = summarize_published(published_data())
    assert summary["phase"] == "past"
    assert summary["signup_count"] == 120
    assert summary["recording_viewer_count"] == 45
    assert summary["event_link_set"] is True
    dumped = json.dumps(summary)
    assert "zoom" not in dumped and "pwd" not in dumped and "location" not in dumped


@pytest.mark.parametrize("overrides,phase", [
    ({"start_datetime": "2026-10-21T18:00:00Z"}, "upcoming"),
    ({"is_canceled": True}, "canceled"),
    ({"now": None}, None),
])
def test_published_phase(overrides, phase):
    assert summarize_published(published_data(**overrides))["phase"] == phase


def test_unpublished_and_bad_counts():
    assert summarize_published(None) == {"published": False}
    assert summarize_published({"published": False}) == {"published": False}
    summary = summarize_published(published_data(signup_count="12", recording_unique_viewer_count=True))
    assert summary["signup_count"] is None and summary["recording_viewer_count"] is None


def test_count_text_parsers():
    assert parse_signups_tab("2,468 signups") == 2468
    assert parse_signups_tab("Signups") is None
    assert parse_recording_viewers("37 watched the recording after the live lesson.") == 37


@pytest.mark.parametrize("value", [
    {"title": "ada@example.com"},
    ["https://us01web.zoom.us/j/1"],
    {"nested": {"link": "https://example.com/j?pwd=abc"}},
])
def test_public_output_guard_refuses_private_data(value):
    with pytest.raises(MavenError, match="private"):
        assert_public_output(value)


# --- click guard and read-only page ------------------------------------------------

@pytest.mark.parametrize("label", [
    *DENIED_CONTROL_LABELS,
    "Publish", "  Create a   Lightning Lesson ", "Create a Zoom meeting", "Delete instructor",
    "Save", "Save draft", "Remove outcome", "Send recording now",
])
def test_click_guard_denies_write_controls(label):
    with pytest.raises(MavenError, match="write"):
        assert_click_allowed(label)


@pytest.mark.parametrize("label", ["", None, "Overview", "Signups", "Settings", "Preview", "Dashboard"])
def test_click_guard_allows_navigation_controls(label):
    assert_click_allowed(label)


class FakePage:
    """Records every call; lesson scripts return fixture data keyed by script."""

    def __init__(self, responses=None, redirects=None):
        self.url = "about:blank"
        self.calls = []
        self.responses = responses or {}
        self.redirects = redirects or {}
        self.closed = False

    def goto(self, url, **kwargs):
        self.calls.append(("goto", url))
        self.url = self.redirects.get(url, url)

    def evaluate(self, script, *args):
        self.calls.append(("evaluate", script))
        value = self.responses.get(script)
        return value(self) if callable(value) else value

    def wait_for_function(self, script, **kwargs):
        self.calls.append(("wait_for_function", script))
        return True

    def wait_for_timeout(self, timeout):
        self.calls.append(("wait_for_timeout", timeout))

    def click(self, *args, **kwargs):
        self.calls.append(("click", args))

    def fill(self, *args, **kwargs):
        self.calls.append(("fill", args))

    def set_viewport_size(self, size):
        pass

    def close(self):
        self.closed = True


@pytest.mark.parametrize("name", [
    "click", "fill", "type", "press", "check", "set_checked", "select_option", "set_input_files",
    "dispatch_event", "keyboard", "mouse", "locator", "get_by_role", "get_by_text", "query_selector",
])
def test_read_only_page_has_no_interaction_surface(name):
    page = FakePage()
    reader = ReadOnlyPage(page)
    with pytest.raises(MavenError, match="read-only"):
        getattr(reader, name)
    assert page.calls == []


def test_read_only_page_only_runs_registered_scripts_and_maven_urls():
    page = FakePage(responses={LESSONS_LIST_JS: {"ok": True}})
    reader = ReadOnlyPage(page)
    assert reader.evaluate(LESSONS_LIST_JS) == {"ok": True}
    with pytest.raises(MavenError, match="registered"):
        reader.evaluate("() => document.querySelector('button').click()")
    with pytest.raises(MavenError, match="registered"):
        reader.wait_for_function("() => true")
    with pytest.raises(ValueError):
        reader.goto("https://example.com/")
    assert [call[0] for call in page.calls] == ["evaluate"]


WRITE_PATTERNS = re.compile(
    r"\.click\(|dispatchEvent|\.submit\(|\.focus\(|\.value\s*=[^=]|innerHTML\s*=|textContent\s*=[^=]|"
    r"fetch\(|XMLHttpRequest|sendBeacon|setAttribute|removeAttribute|\.remove\(|localStorage|sessionStorage",
)


def test_registered_scripts_are_read_only_and_never_return_meeting_links():
    assert len(READ_ONLY_SCRIPTS) == 9
    for script in READ_ONLY_SCRIPTS:
        assert not WRITE_PATTERNS.search(script), script[:60]
    assert not re.search(r"(?<!has_)location\s*:", LESSON_PUBLISHED_JS)
    assert "has_location: Boolean(event.location)" in LESSON_PUBLISHED_JS


def fake_session_page(published=None, editor=None):
    edit = f"{BASE}/abc123/edit"
    responses = {
        LESSONS_NAV_JS: BASE,
        LESSONS_LIST_READY_JS: True,
        LESSONS_LIST_JS: list_state(),
        LESSON_ROUTE_READY_JS: True,
        LESSON_PUBLISHED_JS: published,
        LESSON_TEXT_COUNTS_JS: {"signups": "100 signups", "viewers": "45 watched the recording after the live lesson."},
        LESSON_SIGNUPS_READY_JS: True,
        LESSON_EDITOR_READY_JS: True,
        LESSON_EDITOR_JS: editor or editor_state(),
    }
    redirects = {} if published else {f"{BASE}/abc123": edit}
    return FakePage(responses, redirects)


@pytest.fixture
def no_menu(monkeypatch):
    monkeypatch.setattr(ops, "_dashboard_href", lambda page: "https://maven.com/acme/admin")


def assert_no_interaction(page):
    assert not [call for call in page.calls if call[0] in ("click", "fill")]


def test_list_lessons_reads_without_clicking(no_menu):
    page = fake_session_page()
    result = list_lessons(page)
    assert result["count"] == 4
    assert result["counts"] == {"draft": 1, "upcoming": 1, "past": 2}
    assert result["completeness"]["status"] == "complete"
    assert_no_interaction(page)
    assert not EMAIL_RE.search(json.dumps(result))


def test_show_draft_lesson_reads_editor_only(no_menu):
    page = fake_session_page()
    result = show_lesson(page, "abc123")
    assert result["lesson"]["status"] == "draft"
    assert result["published"] == {"published": False}
    assert result["editor"]["event_link_set"] is False
    assert ("goto", f"{BASE}/abc123/edit") in page.calls
    assert_no_interaction(page)


def test_show_published_lesson_by_url_skips_discovery(monkeypatch):
    def boom(page):
        raise AssertionError("discovery should not run for admin URLs")
    monkeypatch.setattr(ops, "_dashboard_href", boom)
    page = fake_session_page(published=published_data(slug="abc123"))
    result = show_lesson(page, f"{BASE}/abc123?tab=overview")
    assert result["lesson"]["status"] == "past"
    assert result["published"]["signup_count"] == 120
    assert result["published"]["recording_viewer_text_count"] == 45
    dumped = json.dumps(result)
    assert "zoom" not in dumped and "pwd" not in dumped
    assert_no_interaction(page)


def test_show_refuses_data_from_another_lesson():
    page = fake_session_page(published=published_data(slug="zzz999"))
    with pytest.raises(MavenError, match="different lesson"):
        show_lesson(page, f"{BASE}/abc123")


def test_stats_are_aggregate_only(no_menu):
    page = fake_session_page(published=published_data(slug=None))
    result = lessons_stats(page, None, True)
    assert result["count"] == 3
    first = result["lessons"][0]
    assert first["signups"] == {"signup_count": 120, "signups_tab_count": 100}
    assert first["recording_viewers"] == {"recording_viewer_count": 45, "overview_text_count": 45}
    assert first["live_attendance"] is None
    assert first["signup_date_histogram"]["available"] is False
    assert result["totals"] == {"signup_count": 360, "recording_viewer_count": 135}
    assert not EMAIL_RE.search(json.dumps(result))
    assert_no_interaction(page)


def test_stats_require_exactly_one_target():
    with pytest.raises(MavenError, match="exactly one"):
        lessons_stats(FakePage(), None, False)
    with pytest.raises(MavenError, match="exactly one"):
        lessons_stats(FakePage(), "abc123", True)


def test_stats_for_draft_reports_unpublished():
    page = fake_session_page()
    result = lessons_stats(page, f"{BASE}/abc123", False)
    assert result["lessons"][0] == {"id": "abc123", "admin_url": f"{BASE}/abc123", "status": "draft", "published": False}
    assert result["totals"] == {"signup_count": None, "recording_viewer_count": None}


# --- lifecycle and CLI -------------------------------------------------------------

def test_work_tab_is_closed_when_a_lesson_command_fails():
    existing = FakePage()

    class Context:
        pages = [existing]

        def new_page(self):
            return FakePage()

    class Browser:
        contexts = [Context()]

    with pytest.raises(MavenError):
        with work_page(Browser(), None) as page:
            lessons_stats(page, None, False)
    assert page.closed
    assert not existing.closed


def test_cli_lessons_parsing():
    from maven_skill.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["lessons", "list"]).action == "list"
    assert parser.parse_args(["lessons", "show", "--lesson", "abc123"]).lesson == "abc123"
    assert parser.parse_args(["lessons", "stats", "--all"]).all_lessons is True
    with pytest.raises(SystemExit):
        parser.parse_args(["lessons", "stats"])
    with pytest.raises(SystemExit):
        parser.parse_args(["lessons", "stats", "--all", "--lesson", "abc123"])
    with pytest.raises(SystemExit):
        parser.parse_args(["lessons", "show"])


def test_cli_sanitizes_unexpected_lesson_errors(monkeypatch, capsys):
    from maven_skill import cli

    def explode(session, auth_state, action):
        raise RuntimeError("Bearer secret-token for ada@example.com at /private/path")
    monkeypatch.setattr(cli, "run_business", explode)
    assert cli.main(["lessons", "show", "--lesson", "abc123"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "secret-token" not in captured.err and "@" not in captured.err and "/private" not in captured.err
    assert "Browser operation failed" in captured.err


def test_cli_prints_lesson_json(monkeypatch, capsys):
    from maven_skill import cli

    monkeypatch.setattr(cli, "run_business", lambda session, auth_state, action: {"command": "lessons list", "count": 0})
    assert cli.main(["lessons", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == {"command": "lessons list", "count": 0}
