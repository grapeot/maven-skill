import stat
from pathlib import Path

import pytest

from maven_skill.errors import MavenError
from maven_skill.parse import (
    CONSUMED_COLUMNS,
    OBSERVED_EXPORT_COLUMNS,
    choose_cohort,
    dedupe_courses,
    parse_cohort_card,
    refuse_partial_latest,
    reserve_output,
    students_url_for,
    validate_students_csv,
)


HEADER = (
    "full_name,preferred_name,email,status,company,job_title,linkedin_url,"
    "twitter_username,course_join_question,enrolled_at,source"
)


def card(slug, text, home_slug=None, settings_slug=None):
    home_slug = slug if home_slug is None else home_slug
    settings_slug = slug if settings_slug is None else settings_slug
    return {
        "text": text,
        "home": f"https://maven.com/example-school/example-course/{home_slug}/home",
        "settings": (
            "https://maven.com/example-school/admin/courses/example-course/settings"
            f"?cohort={settings_slug}"
        ),
    }


def cohorts():
    return [
        parse_cohort_card(card("9", "Cohort 9 Jan 2 — Jan 9 Edit Student home")),
        parse_cohort_card(card("2", "UPCOMING Cohort 2 Mar 4 — Mar 18 Edit Student home")),
        parse_cohort_card(card("async", "Self-paced cohort Dec 1 — Dec 20 Edit Student home")),
    ]


def test_latest_uses_upcoming_not_max_slug_or_self_paced():
    chosen, reason = choose_cohort(cohorts(), "latest")
    assert chosen["slug"] == "2"
    assert chosen["status"] == "upcoming"
    assert reason == "upcoming"


def test_latest_among_upcoming_uses_year_not_slug():
    items = [
        parse_cohort_card(card("9", "UPCOMING Cohort 9 Dec 2, 2025 — Dec 9, 2025 Edit Student home")),
        parse_cohort_card(card("2", "UPCOMING Cohort 2 Mar 4, 2026 — Mar 18, 2026 Edit Student home")),
        parse_cohort_card(card("async", "Self-paced cohort Jan 1, 2026 — Jan 20, 2026 Edit Student home")),
    ]
    chosen, reason = choose_cohort(items, "latest")
    assert chosen["slug"] == "2"
    assert reason == "upcoming_date"


def test_multiple_upcoming_without_year_are_refused():
    items = [
        parse_cohort_card(card("9", "UPCOMING Cohort 9 Jan 2 — Jan 9 Edit Student home")),
        parse_cohort_card(card("2", "UPCOMING Cohort 2 Mar 4 — Mar 18 Edit Student home")),
    ]
    with pytest.raises(MavenError, match="no year"):
        choose_cohort(items, "latest")
    chosen, reason = choose_cohort(items, "9")
    assert chosen["slug"] == "9"
    assert reason == "slug"


def test_past_cohorts_without_year_do_not_sort_by_month():
    items = [
        parse_cohort_card(card("9", "Cohort 9 Dec 2 — Dec 9 Edit Student home")),
        parse_cohort_card(card("2", "Cohort 2 Mar 4 — Mar 18 Edit Student home")),
    ]
    with pytest.raises(MavenError, match="no year"):
        choose_cohort(items, "latest")
    assert choose_cohort(items, "2")[0]["slug"] == "2"


def test_partial_list_refuses_latest_but_not_explicit_slug():
    with pytest.raises(MavenError, match="partial"):
        refuse_partial_latest("latest", {"status": "partial"})
    refuse_partial_latest("example-slug", {"status": "partial"})
    refuse_partial_latest("latest", {"status": "complete"})


def test_date_tie_does_not_fall_back_to_slug():
    items = [
        parse_cohort_card(card("9", "UPCOMING Cohort 9 Jan 2, 2026 — Jan 9, 2026 Edit Student home")),
        parse_cohort_card(card("2", "UPCOMING Cohort 2 Jan 2, 2026 — Jan 9, 2026 Edit Student home")),
    ]
    with pytest.raises(MavenError, match="tie"):
        choose_cohort(items, "latest")


def test_slug_must_match_home_and_settings():
    with pytest.raises(MavenError, match="disagree"):
        parse_cohort_card(card("2", "Cohort 2 Jan 2 — Jan 9 Edit Student home", settings_slug="9"))


def test_duplicate_slugs_are_rejected():
    items = [
        parse_cohort_card(card("2", "Cohort 2 Jan 2 — Jan 9 Edit Student home")),
        parse_cohort_card(card("2", "Cohort 2 Feb 2 — Feb 9 Edit Student home")),
    ]
    with pytest.raises(MavenError, match="duplicate"):
        choose_cohort(items, "2")


def test_students_url_replaces_cohort_from_nav_link():
    nav = "https://maven.com/example-school/admin/courses/example-course/students?cohort=old"
    assert students_url_for(nav, "async") == (
        "https://maven.com/example-school/admin/courses/example-course/students?cohort=async"
    )


def test_course_links_are_deduped_without_dropping_distinct_courses():
    links = [
        {"href": "https://maven.com/example-school/admin/courses/one", "text": "One"},
        {"href": "https://maven.com/example-school/admin/courses/one/", "text": "One longer title"},
        {"href": "https://maven.com/example-school/admin/courses/two?tab=1", "text": "Two"},
    ]
    courses, deduped = dedupe_courses(links)
    assert deduped == 1
    assert [item["url"] for item in courses] == [
        "https://maven.com/example-school/admin/courses/one",
        "https://maven.com/example-school/admin/courses/two",
    ]
    assert courses[0]["title"] == "One longer title"


def csv_text(rows):
    lines = [HEADER, *rows]
    return "\n".join(lines).encode()


def test_csv_accepts_consumed_columns_and_future_columns():
    payload = (
        "email,status,enrolled_at,future_note\n"
        "ada@example.com,enrolled,2026-01-02T03:04:05Z,note\n"
    ).encode()
    result = validate_students_csv(payload, 1)
    assert result["columns"] == ["email", "status", "enrolled_at", "future_note"]
    assert set(CONSUMED_COLUMNS).issubset(OBSERVED_EXPORT_COLUMNS)
    assert len(OBSERVED_EXPORT_COLUMNS) == 11


def test_csv_accepts_enrolled_timezone_rows():
    payload = csv_text([
        "Ada,Ada,ada@example.com,enrolled,Example,Engineer,,,,2026-01-02T03:04:05.1Z,direct",
        "Bea,Bea,bea@example.com,Enrolled,Example,Engineer,,,,2026-02-03T03:04:05+00:00,direct",
    ])
    result = validate_students_csv(payload, 2)
    assert result["counts"]["unique_emails"] == 2
    assert "email" in result["columns"]


@pytest.mark.parametrize("payload,enrolled,match", [
    (b"<html>login</html>", 0, "HTML"),
    (csv_text(["A,A,a@example.com,enrolled,E,E,,,,2026-01-02T00:00:00Z,s"]), 2, "count"),
    (csv_text([
        "A,A,a@example.com,enrolled,E,E,,,,2026-01-02T00:00:00Z,s",
        "B,B,A@example.com,enrolled,E,E,,,,2026-01-02T00:00:00Z,s",
    ]), 2, "duplicate"),
    (csv_text(["A,A,a@example.com,dropped,E,E,,,,2026-01-02T00:00:00Z,s"]), 1, "not enrolled"),
    (csv_text(["A,A,a@example.com,enrolled,E,E,,,,2026-01-02T00:00:00,s"]), 1, "timezone"),
    (b"full_name,email\nA,a@example.com\n", 1, "required columns"),
    (b"email,status,enrolled_at,email\na@example.com,enrolled,2026-01-02T00:00:00Z,a@example.com\n", 1, "malformed"),
    (b"email,status,enrolled_at\na@example.com,enrolled,2026-01-02T00:00:00Z,extra\n", 1, "malformed"),
    (b"email,status,enrolled_at\na@example.com,enrolled\n", 1, "malformed"),
])
def test_csv_rejects_incomplete_or_unsafe_exports(payload, enrolled, match):
    with pytest.raises(MavenError, match=match):
        validate_students_csv(payload, enrolled)


def test_reserve_output_is_private_and_refuses_overwrite(tmp_path):
    path = tmp_path / "out.csv"
    reserve_output(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(MavenError, match="already exists"):
        reserve_output(path)
    assert path.read_bytes() == b""


def test_public_source_has_no_live_account_or_course():
    root = Path(__file__).resolve().parents[1]
    banned = ("super" + "linear", "ai" + "builders")
    for directory in ("src", "tests"):
        for path in (root / directory).rglob("*.py"):
            text = path.read_text().lower()
            for token in banned:
                assert token not in text
