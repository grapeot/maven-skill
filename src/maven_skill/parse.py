from __future__ import annotations

import csv
import io
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from maven_skill.errors import MavenError


CONSUMED_COLUMNS = ("email", "status", "enrolled_at")
OBSERVED_EXPORT_COLUMNS = (
    "full_name",
    "preferred_name",
    "email",
    "status",
    "company",
    "job_title",
    "linkedin_url",
    "twitter_username",
    "course_join_question",
    "enrolled_at",
    "source",
)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        1,
    )
}
DATE_RE = re.compile(
    r"\b(?P<sm>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(?P<sd>\d{1,2})"
    r"(?:,?\s*(?P<sy>20\d{2}))?"
    r"(?:\s*[\u2014\u2013-]\s*(?:(?P<em>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?"
    r"(?P<ed>\d{1,2})(?:,?\s*(?P<ey>20\d{2}))?)?",
    re.IGNORECASE,
)
SAFE_SLUG = re.compile(r"[A-Za-z0-9_-]{1,64}")


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def dedupe_courses(links: list[dict]) -> tuple[list[dict], int]:
    chosen: dict[str, dict] = {}
    order: list[str] = []
    for link in links:
        href = link.get("href") or ""
        if not href:
            continue
        key = canonical_url(href)
        title = public_text(link.get("text") or "")
        if key not in chosen:
            chosen[key] = {"url": key, "title": title}
            order.append(key)
            continue
        if len(title) > len(chosen[key]["title"]):
            chosen[key]["title"] = title
    courses = [chosen[key] for key in order]
    return courses, len(links) - len(courses)


def public_text(value: str) -> str:
    text = " ".join(value.split())
    if EMAIL.search(text):
        return ""
    return text[:200]


def course_admin_path(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    marker = "/admin/courses/"
    index = path.find(marker)
    if index < 0:
        raise MavenError("course URL is not a Maven course admin page")
    rest = path[index + len(marker):]
    slug = rest.split("/", 1)[0]
    if not slug:
        raise MavenError("course URL is not a Maven course admin page")
    return path[: index + len(marker) + len(slug)]


def slug_from_home(url: str) -> str | None:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    if len(parts) >= 2 and parts[-1] == "home":
        return parts[-2]
    return None


def slug_from_settings(url: str) -> str | None:
    path = urlsplit(url).path
    if "/settings" not in path:
        return None
    values = [value for key, value in parse_qsl(urlsplit(url).query) if key == "cohort" and value]
    if len(values) != 1:
        return None
    return values[0]


def parse_cohort_card(card: dict) -> dict:
    text = " ".join((card.get("text") or "").split())
    if not text or len(text) > 180 or EMAIL.search(text):
        raise MavenError("cohort card boundary was not found")
    home = card.get("home") or ""
    settings = card.get("settings") or ""
    home_slug = slug_from_home(home)
    settings_slug = slug_from_settings(settings)
    found = [slug for slug in (home_slug, settings_slug) if slug]
    if not found:
        raise MavenError("cohort card did not expose a cohort parameter")
    if len(set(found)) != 1:
        raise MavenError("cohort student home and settings links disagree")
    lowered = text.lower()
    if "upcoming" in lowered:
        status = "upcoming"
    elif "self-paced" in lowered:
        status = "self_paced"
    else:
        status = "scheduled"
    match = DATE_RE.search(text)
    start = None
    date_text = ""
    if match:
        date_text = match.group(0)
        year = match.group("sy") or match.group("ey")
        start = {
            "month": MONTHS[match.group("sm").lower()],
            "day": int(match.group("sd")),
            "year": int(year) if year else None,
        }
    label = text
    if match:
        label = text[: match.start()]
    label = re.sub(r"\bupcoming\b", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\b(edit|student home)\b", "", label, flags=re.IGNORECASE)
    label = " ".join(label.split())
    return {
        "slug": found[0],
        "label": label,
        "status": status,
        "self_paced": status == "self_paced",
        "date_text": date_text,
        "start": start,
    }


def assert_unique_slugs(cohorts: list[dict]) -> None:
    slugs = [cohort["slug"] for cohort in cohorts]
    if len(slugs) != len(set(slugs)):
        raise MavenError("cohort list contains duplicate slugs")


def select_latest(cohorts: list[dict]) -> tuple[dict, str]:
    if not cohorts:
        raise MavenError("cohort list is empty")
    upcoming = [cohort for cohort in cohorts if cohort["status"] == "upcoming"]
    if len(upcoming) == 1:
        return upcoming[0], "upcoming"
    if len(upcoming) > 1:
        if _years_missing(upcoming):
            raise MavenError("upcoming cohort dates have no year; refusing month ordering")
        return _latest_by_date(upcoming), "upcoming_date"
    dated = [cohort for cohort in cohorts if cohort["status"] != "self_paced" and cohort.get("start")]
    if dated:
        if _years_missing(dated):
            raise MavenError("cohort dates have no year; refusing month ordering")
        return _latest_by_date(dated), "latest_start"
    raise MavenError("could not choose latest cohort from dates; refusing numeric slug ordering")


def refuse_partial_latest(selector: str, completeness: dict) -> None:
    if selector == "latest" and completeness.get("status") != "complete":
        raise MavenError("cohort list is partial; refusing to choose latest")


def _years_missing(cohorts: list[dict]) -> bool:
    return any(not cohort.get("start") or cohort["start"].get("year") is None for cohort in cohorts)


def _latest_by_date(cohorts: list[dict]) -> dict:
    dated = [cohort for cohort in cohorts if cohort.get("start")]
    if len(dated) != len(cohorts) or _years_missing(dated):
        raise MavenError("cohort dates are incomplete; refusing month ordering")
    years = [cohort["start"]["year"] for cohort in dated]
    if any(year is None for year in years) and any(year is not None for year in years):
        raise MavenError("cohort dates are not comparable; refusing numeric slug ordering")
    def key(cohort: dict) -> tuple:
        return (
            cohort["start"]["year"] or 0,
            cohort["start"]["month"],
            cohort["start"]["day"],
        )
    best = max(key(cohort) for cohort in dated)
    winners = [cohort for cohort in dated if key(cohort) == best]
    if len(winners) != 1:
        raise MavenError("cohort dates tie; refusing numeric slug ordering")
    return winners[0]


def choose_cohort(cohorts: list[dict], selector: str) -> tuple[dict, str]:
    assert_unique_slugs(cohorts)
    if selector == "latest":
        return select_latest(cohorts)
    matches = [cohort for cohort in cohorts if cohort["slug"] == selector]
    if len(matches) != 1:
        raise MavenError("requested cohort was not in the observed cohort list")
    return matches[0], "slug"


def students_url_for(nav_href: str, slug: str) -> str:
    parsed = urlsplit(nav_href)
    path = parsed.path.rstrip("/")
    if not path.endswith("/students") or "/admin/courses/" not in path:
        raise MavenError("Students navigation link is not a students page")
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "cohort"]
    query.append(("cohort", slug))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def choose_students_nav(hrefs: list[str], course_path: str) -> str:
    matches = []
    for href in hrefs:
        path = urlsplit(href).path.rstrip("/")
        if path.endswith("/students") and path.startswith(course_path + "/"):
            matches.append(href)
    if not matches:
        raise MavenError("Students navigation link was not found on the course page")
    paths = {urlsplit(href).path.rstrip("/") for href in matches}
    if len(paths) != 1:
        raise MavenError("Students navigation links disagree")
    return matches[0]


def safe_slug_token(slug: str) -> str:
    if SAFE_SLUG.fullmatch(slug):
        return slug
    raise MavenError("cohort slug is not a safe file token")


def reserve_output(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists():
        raise MavenError("output already exists; refusing to overwrite")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    path.chmod(0o600)
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        path.unlink(missing_ok=True)
        raise MavenError("could not restrict export file permissions")


def parse_enrolled_at(value: str) -> datetime:
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise MavenError("enrolled_at is not a timezone-aware timestamp") from None
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise MavenError("enrolled_at is not a timezone-aware timestamp")
    return parsed


def validate_students_csv(payload: bytes, page_enrolled: int) -> dict:
    sample = payload[:2000].lstrip()
    lowered = sample[:500].lower()
    if sample.startswith(b"<") or b"<html" in lowered or b"<!doctype" in lowered:
        raise MavenError("download was HTML, not a CSV; session may have expired")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MavenError("export file is not UTF-8 text") from None
    if "<html" in text[:500].lower():
        raise MavenError("download was HTML, not a CSV; session may have expired")
    reader = csv.DictReader(io.StringIO(text))
    columns = list(reader.fieldnames or [])
    if len(columns) != len(set(columns)) or any(name in (None, "") for name in columns):
        raise MavenError("CSV header is malformed")
    missing = [name for name in CONSUMED_COLUMNS if name not in columns]
    if missing:
        raise MavenError("CSV is missing required columns")
    rows = list(reader)
    emails = []
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise MavenError("CSV header is malformed")
        status = (row.get("status") or "").strip().casefold()
        if status != "enrolled":
            raise MavenError("CSV contains a row that is not enrolled")
        email = (row.get("email") or "").strip().casefold()
        if not email or EMAIL.fullmatch(email) is None:
            raise MavenError("CSV contains a row without a usable email")
        emails.append(email)
        parse_enrolled_at(row.get("enrolled_at") or "")
    if len(emails) != len(set(emails)):
        raise MavenError("CSV contains duplicate normalized emails")
    if len(rows) != page_enrolled:
        raise MavenError("CSV row count does not match the page enrolled count")
    return {
        "columns": columns,
        "counts": {
            "page_enrolled": page_enrolled,
            "csv_rows": len(rows),
            "unique_emails": len(set(emails)),
        },
    }


# --- Lightning Lessons (read-only) -------------------------------------------------

LESSON_LIMITS = {
    "title": 60,
    "outcome_title": 60,
    "outcome_description": 120,
    "topic_desc": 450,
    "instructors": 4,
}
RECOMMENDED_OUTCOMES = 3
LESSON_TIMEZONE = "America/Los_Angeles"
LESSON_SECTIONS = {"drafts": "draft", "upcoming": "upcoming", "past": "past"}
LESSONS_PATH = re.compile(r"^/(?P<org>[A-Za-z0-9_-]{1,64})/admin/lightning-lessons/?$")
LESSON_PATH = re.compile(
    r"^/(?P<org>[A-Za-z0-9_-]{1,64})/admin/lightning-lessons/(?P<id>[A-Za-z0-9_-]{1,64})(?:/edit)?/?$"
)
COUNTER = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
LIST_DATE = re.compile(
    r"(?:[A-Za-z]{3},\s*)?(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(?P<day>\d{1,2}),\s*(?P<year>20\d{2})"
    r"(?:,\s*(?P<time>\d{1,2}:\d{2}\s*[AP]M)(?:\s+(?P<tz>[A-Z]{2,5}))?)?",
    re.IGNORECASE,
)
SIGNUP_ITEM = re.compile(r"^([\d,]+)\s+(?:students?|signups?)$", re.IGNORECASE)
PRIVATE_OUTPUT = (
    EMAIL,
    re.compile(r"zoom\.us", re.IGNORECASE),
    re.compile(r"[?&]pwd=", re.IGNORECASE),
)
# Labels of controls that create, publish, delete, send, or otherwise write. Lessons
# commands never click any of them; the guard is shared with every guarded click.
DENIED_CONTROL_LABELS = (
    "publish",
    "unpublish",
    "create a lightning lesson",
    "create a zoom meeting",
    "add event link",
    "update event link",
    "add outcome",
    "delete learning outcome",
    "add instructor",
    "delete instructor",
    "save",
    "upload",
    "replace image",
    "clear custom image",
    "send an email",
    "send recording now",
    "manage recording",
    "create a promo code",
    "create discount code",
    "join waitlist",
)
DENIED_CONTROL_VERBS = re.compile(
    r"\b(publish|unpublish|create|delete|remove|save|upload|send|add|update|replace|clear|"
    r"join|submit|confirm|cancel|duplicate|archive)\b",
    re.IGNORECASE,
)


def assert_click_allowed(label: str | None) -> None:
    """Refuse clicks on controls whose visible label suggests a business write."""
    text = " ".join((label or "").split()).casefold()
    if text in DENIED_CONTROL_LABELS or DENIED_CONTROL_VERBS.search(text):
        raise MavenError("refusing to click a control that can write to Maven")


def lessons_admin_base(url: str) -> str:
    parsed = urlsplit(url)
    match = LESSONS_PATH.match(parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "maven.com" or not match:
        raise MavenError("Lightning Lessons link is not a Maven admin lessons page")
    return f"https://maven.com/{match.group('org')}/admin/lightning-lessons"


def parse_lesson_ref(value: str) -> tuple[str | None, str]:
    """Return (lessons admin base or None, lesson id) from an id or admin URL."""
    text = (value or "").strip()
    if SAFE_SLUG.fullmatch(text):
        return None, text
    parsed = urlsplit(text)
    match = LESSON_PATH.match(parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "maven.com" or not match:
        raise MavenError("lesson must be a lesson id or a Maven Lightning Lesson admin URL")
    return f"https://maven.com/{match.group('org')}/admin/lightning-lessons", match.group("id")


def lesson_admin_url(base: str, lesson_id: str) -> str:
    if not SAFE_SLUG.fullmatch(lesson_id or ""):
        raise MavenError("lesson id is not a safe token")
    return f"{lessons_admin_base(base)}/{lesson_id}"


def parse_list_date(text: str) -> dict | None:
    match = LIST_DATE.search(text or "")
    if not match:
        return None
    month = MONTHS[match.group("month").lower()]
    return {
        "date": f"{int(match.group('year')):04d}-{month:02d}-{int(match.group('day')):02d}",
        "time": " ".join(match.group("time").split()) if match.group("time") else None,
        "tz_abbr": match.group("tz"),
    }


def _section_status(label: str) -> str | None:
    return LESSON_SECTIONS.get(" ".join((label or "").split()).casefold())


def parse_lesson_list(state: dict, base: str) -> tuple[list[dict], dict]:
    lessons: list[dict] = []
    seen: set[str] = set()
    sections = {}
    complete = not state.get("next_control")
    for section in state.get("sections") or []:
        status = _section_status(section.get("label") or "")
        cards = section.get("cards") or []
        declared = section.get("count")
        if status is None:
            complete = False
            status = "unknown"
        parsed = 0
        for card in cards:
            lesson = _parse_lesson_card(card, status, base)
            if lesson is None:
                complete = False
                continue
            if lesson["id"] in seen:
                continue
            seen.add(lesson["id"])
            lessons.append(lesson)
            parsed += 1
        if declared is None or declared != parsed:
            complete = False
        sections[status] = {"declared": declared, "parsed": parsed}
    ungrouped = int(state.get("ungrouped") or 0)
    if ungrouped:
        complete = False
    return lessons, {
        "status": "complete" if complete else "partial",
        "sections": sections,
        "ungrouped_cards": ungrouped,
        "next_control": bool(state.get("next_control")),
    }


def _parse_lesson_card(card: dict, status: str, base: str) -> dict | None:
    match = LESSON_PATH.match(urlsplit(card.get("href") or "").path)
    if not match:
        return None
    signups = None
    when = None
    date_text = None
    for item in card.get("items") or []:
        text = " ".join((item or "").split())
        hit = SIGNUP_ITEM.match(text)
        if hit:
            signups = int(hit.group(1).replace(",", ""))
            continue
        parsed = parse_list_date(text)
        if parsed and when is None:
            when = parsed
            date_text = public_text(text)
    return {
        "id": match.group("id"),
        "title": public_text(card.get("title") or ""),
        "status": status,
        "admin_url": lesson_admin_url(base, match.group("id")),
        "date_text": date_text,
        "date": when["date"] if when else None,
        "time": when["time"] if when else None,
        "signups": signups,
    }


def parse_counter(text: str | None) -> tuple[int, int] | None:
    match = COUNTER.match(text or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def measure(value: str | None, counter: str | None, default_limit: int) -> dict:
    """Character count vs limit, preferring the page's own N/M counter when present."""
    parsed = parse_counter(counter)
    length = parsed[0] if parsed else len(value or "")
    limit = parsed[1] if parsed else default_limit
    return {
        "length": length,
        "limit": limit,
        "over_limit": length > limit,
        "source": "page_counter" if parsed else "computed",
    }


def parse_duration_minutes(text: str | None) -> int | None:
    value = " ".join((text or "").split()).lower()
    if not value:
        return None
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", value)
    minutes = re.search(r"(\d+)\s*(?:m|min|mins|minute|minutes)\b", value)
    if not hours and not minutes:
        return None
    total = 0.0
    if hours:
        total += float(hours.group(1)) * 60
    if minutes:
        total += int(minutes.group(1))
    return int(round(total))


def parse_editor_date(text: str | None) -> str | None:
    match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(20\d{2})\s*", text or "")
    if not match:
        return None
    month, day, year = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _percent(text: str | None) -> int | None:
    match = re.search(r"(\d{1,3})\s*%\s*complete", text or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def _review_count(text: str | None) -> int | None:
    match = re.search(r"review\s+(\d+)\s+errors?", text or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def instructor_name(texts: list[str]) -> str | None:
    """Card headers show an index ("01") plus the name, or the placeholder "Name"."""
    parts = [" ".join((text or "").split()) for text in texts or []]
    parts = [part for part in parts if part and not re.fullmatch(r"\d{1,2}", part)]
    if not parts:
        return None
    name = public_text(parts[-1])
    if not name or name.casefold() == "name":
        return None
    return name[:80]


def summarize_editor(state: dict) -> dict:
    title = state.get("title") or {}
    outcomes = []
    for index, item in enumerate(state.get("outcomes") or [], 1):
        title_measure = measure(item.get("title"), item.get("title_counter"), LESSON_LIMITS["outcome_title"])
        description_measure = measure(
            item.get("description"), item.get("description_counter"), LESSON_LIMITS["outcome_description"]
        )
        outcomes.append({
            "index": index,
            "title": public_text(item.get("title") or ""),
            "title_chars": title_measure,
            "description_chars": description_measure,
            "flagged_error": bool(item.get("error")),
        })
    instructors = [
        {"name": instructor_name(item.get("texts") or []), "flagged_error": bool(item.get("error"))}
        for item in state.get("instructors") or []
    ]
    link = state.get("link") or {}
    if link.get("update_button"):
        event_link_set = True
    elif link.get("add_button"):
        event_link_set = False
    else:
        event_link_set = None
    header = state.get("header") or []
    percent = next((value for value in (_percent(text) for text in header) if value is not None), None)
    review = next((value for value in (_review_count(text) for text in header) if value is not None), None)
    publish_shown = any(" ".join((text or "").split()) == "Publish" for text in header)
    visible = []
    for text in state.get("inline_errors") or []:
        clean = public_text(text)
        if clean and clean not in visible:
            visible.append(clean[:200])
    title_measure = measure(title.get("value"), title.get("counter"), LESSON_LIMITS["title"])
    topic = state.get("topic") or {}
    topic_measure = measure(topic.get("value"), topic.get("counter"), LESSON_LIMITS["topic_desc"])
    checks = []
    if event_link_set is False:
        checks.append("event link is missing (hard publish blocker)")
    if title_measure["over_limit"]:
        checks.append("title exceeds its character limit")
    if topic_measure["over_limit"]:
        checks.append("topic_desc exceeds its character limit")
    for outcome in outcomes:
        if outcome["title_chars"]["over_limit"] or outcome["description_chars"]["over_limit"]:
            checks.append(f"learning outcome {outcome['index']} exceeds a character limit")
    if not outcomes:
        checks.append("no learning outcomes")
    if not instructors:
        checks.append("no instructors")
    if len(instructors) > LESSON_LIMITS["instructors"]:
        checks.append("more than 4 instructors")
    timezone_text = state.get("timezone_text") or ""
    return {
        "title": public_text(title.get("value") or ""),
        "title_chars": title_measure,
        "date": parse_editor_date(state.get("date")),
        "start_time": public_text(state.get("start_time") or "") or None,
        "timezone": LESSON_TIMEZONE if LESSON_TIMEZONE in timezone_text else None,
        "duration_text": public_text(state.get("duration") or "") or None,
        "duration_minutes": parse_duration_minutes(state.get("duration")),
        "event_link_set": event_link_set,
        "learning_outcomes": outcomes,
        "learning_outcome_count": len(outcomes),
        "recommended_outcomes": RECOMMENDED_OUTCOMES,
        "topic_desc_chars": topic_measure,
        "instructors": instructors,
        "instructor_count": len(instructors),
        "instructor_limit": LESSON_LIMITS["instructors"],
        "completion_percent": percent,
        # Maven drops the "N% Complete" and "Review N errors" header controls once the
        # form is complete, leaving only Preview and Publish.
        "header_reports_complete": publish_shown and percent is None and review is None,
        "publish_errors": {
            "review_count": review,
            "visible_messages": visible,
            "flagged_outcomes": [o["index"] for o in outcomes if o["flagged_error"]],
            "flagged_instructors": [i + 1 for i, item in enumerate(instructors) if item["flagged_error"]],
            "derived_checks": checks,
        },
    }


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def summarize_published(data: dict | None) -> dict:
    """Reduce the page's embedded published-lesson data to safe aggregate fields."""
    if not data or not data.get("published"):
        return {"published": False}
    start = _parse_utc(data.get("start_datetime"))
    now = _parse_utc(data.get("now"))
    if data.get("is_canceled"):
        phase = "canceled"
    elif start and now:
        phase = "past" if start <= now else "upcoming"
    else:
        phase = None
    def count(key: str) -> int | None:
        value = data.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    return {
        "published": True,
        "phase": phase,
        "start_datetime_utc": start.isoformat() if start else None,
        "start_date": data.get("start_date") if isinstance(data.get("start_date"), str) else None,
        "start_time": data.get("start_time") if isinstance(data.get("start_time"), str) else None,
        "timezone": data.get("timezone") if isinstance(data.get("timezone"), str) else None,
        "duration_minutes": count("duration_min"),
        "event_link_set": bool(data.get("has_location")),
        "signup_count": count("signup_count"),
        "recording_viewer_count": count("recording_unique_viewer_count"),
        "is_canceled": bool(data.get("is_canceled")),
        "is_delisted": bool(data.get("is_delisted")),
        "listed_on_marketplace": bool(data.get("is_visible_on_discovery_page")),
        "connected_course": bool(data.get("connected_course")),
        "promo_code": bool(data.get("promo_code")),
    }


def parse_count_text(text: str | None, pattern: str) -> int | None:
    match = re.search(pattern, " ".join((text or "").split()), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def parse_signups_tab(text: str | None) -> int | None:
    return parse_count_text(text, r"^([\d,]+)\s+signups?$")


def parse_recording_viewers(text: str | None) -> int | None:
    return parse_count_text(text, r"([\d,]+)\s+watched the recording")


def assert_public_output(value) -> None:
    """Refuse to print anything that looks like an email or meeting link."""
    if isinstance(value, dict):
        for key, item in value.items():
            assert_public_output(key)
            assert_public_output(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_public_output(item)
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in PRIVATE_OUTPUT):
            raise MavenError("lesson output contained private data; refusing to print")
