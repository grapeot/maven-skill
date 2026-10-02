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
