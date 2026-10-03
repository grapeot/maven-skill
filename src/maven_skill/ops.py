from __future__ import annotations

import hashlib
import re
import stat
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from maven_skill.errors import MavenError
from maven_skill.parse import (
    assert_click_allowed,
    assert_public_output,
    assert_unique_slugs,
    choose_cohort,
    choose_students_nav,
    course_admin_path,
    dedupe_courses,
    lesson_admin_url,
    lessons_admin_base,
    parse_cohort_card,
    parse_lesson_list,
    parse_lesson_ref,
    parse_recording_viewers,
    parse_signups_tab,
    refuse_partial_latest,
    reserve_output,
    safe_slug_token,
    students_url_for,
    summarize_editor,
    summarize_published,
    validate_students_csv,
)
from maven_skill.session import Session, private_json, validate_url


EXPORT_ICON = "M8.0625 10.3135L12 14.2499L15.9375 10.3135"
HOME = "https://maven.com/"
COURSE_LINKS_JS = """() => {
  const path = location.pathname.replace(/\\/$/, '');
  const links = [...document.querySelectorAll('a')].filter(el => {
    let url;
    try { url = new URL(el.href); } catch (e) { return false; }
    const item = url.pathname.replace(/\\/$/, '');
    return item.startsWith(path + '/') && item.split('/').length === path.split('/').length + 1;
  }).map(el => ({
    text: (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200),
    href: el.href.split('#')[0]
  }));
  const next = [...document.querySelectorAll('a, button')].find(el => {
    const name = (el.getAttribute('aria-label') || el.innerText || '').trim();
    return /^(next|load more|show more)$/i.test(name) || el.getAttribute('rel') === 'next';
  });
  return {
    links,
    next_href: next && next.tagName === 'A' ? next.href : null,
    next_control: Boolean(next)
  };
}"""
COURSE_READY_JS = """() => {
  const path = location.pathname.replace(/\\/$/, '');
  if (!/\\/admin\\/courses$/.test(path)) return false;
  const section = [...document.querySelectorAll('section')].find(el =>
    [...el.querySelectorAll('h3')].some(node => (node.innerText || '').trim() === 'PUBLISHED')
  );
  if (!section) return false;
  const links = [...section.querySelectorAll('a')].filter(el => {
    try {
      const item = new URL(el.href).pathname.replace(/\\/$/, '');
      return item.startsWith(path + '/') && item.split('/').length === path.split('/').length + 1;
    } catch (e) { return false; }
  });
  if (links.length > 0) return true;
  return [...document.querySelectorAll('button')].some(el => (el.innerText || '').trim() === 'Create a course');
}"""
OVERVIEW_READY_JS = """() => {
  const text = el => (el.innerText || '').trim();
  if ([...document.querySelectorAll('a')].some(el => text(el) === 'Student home')) return true;
  if ([...document.querySelectorAll('h1,h2,h3,p')].some(el => text(el) === 'No cohorts' || text(el) === 'No cohorts yet')) return true;
  const path = location.pathname.replace(/\\/$/, '');
  if (/\\/admin\\/courses\\/[^/]+$/.test(path)) return false;
  return [...document.querySelectorAll('a')].some(el => text(el) === 'Overview');
}"""
OVERVIEW_JS = """() => {
  const homes = [...document.querySelectorAll('a')].filter(el => (el.innerText || '').trim() === 'Student home');
  const cards = homes.map(el => {
    let node = el;
    while (node.parentElement) {
      const parent = node.parentElement;
      const count = [...parent.querySelectorAll('a')].filter(a => (a.innerText || '').trim() === 'Student home').length;
      if (count > 1) break;
      node = parent;
    }
    const settings = [...node.querySelectorAll('a')].find(a => {
      try {
        const url = new URL(a.href);
        return url.pathname.includes('/settings') && url.searchParams.has('cohort');
      } catch (e) { return false; }
    });
    return {
      text: (node.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300),
      home: el.href,
      settings: settings ? settings.href : null
    };
  });
  const named = label => [...document.querySelectorAll('a')].filter(
    el => (el.innerText || '').trim() === label
  ).map(el => el.href);
  const next = [...document.querySelectorAll('a, button')].some(el => {
    const name = (el.getAttribute('aria-label') || el.innerText || '').trim();
    return /^(next|load more|show more)$/i.test(name) || el.getAttribute('rel') === 'next';
  });
  return {cards, students: named('Students'), overview: named('Overview'), next_control: next};
}"""


@contextmanager
def work_page(browser, auth_state: Path | None):
    owned = None
    if auth_state is not None:
        if not Path(auth_state).is_file():
            raise MavenError("auth state file was not found")
        owned = browser.new_context(storage_state=str(auth_state))
        context = owned
    else:
        if not browser.contexts:
            raise MavenError("browser has no persistent context")
        context = browser.contexts[0]
    page = context.new_page()
    page.set_viewport_size({"width": 1440, "height": 1000})
    try:
        yield page
    finally:
        page.close()
        if owned is not None:
            owned.close()


def run_business(session: Session, auth_state: Path | None, action):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = session.connect(playwright)
        with work_page(browser, auth_state) as page:
            return action(page)


def _reject_login(page) -> None:
    path = urlsplit(page.url).path
    if path == "/login" or path.startswith("/login/"):
        raise MavenError("Maven redirected to login; session is not authenticated")


def _goto(page, url: str) -> None:
    validate_url(url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        raise MavenError("navigation timed out or failed") from None
    _reject_login(page)


def _dashboard_href(page) -> str:
    _goto(page, HOME)
    try:
        page.wait_for_selector("button[aria-haspopup='menu']", state="attached", timeout=15000)
    except Exception:
        raise MavenError("account menu was not found; session is not authenticated or the homepage layout changed") from None
    buttons = page.locator("button[aria-haspopup='menu']")
    for index in range(buttons.count()):
        button = buttons.nth(index)
        if not button.is_visible():
            continue
        try:
            name = " ".join(
                f"{button.inner_text(timeout=5000)} {button.get_attribute('aria-label') or ''}".split()
            )
            assert_click_allowed(name)
        except Exception:
            continue
        try:
            button.click(timeout=5000)
            page.locator("[role='menu']").wait_for(timeout=5000)
        except Exception:
            continue
        href = page.evaluate(
            """() => {
              const item = [...document.querySelectorAll('[role="menu"] a')].find(
                el => (el.innerText || '').trim().toLowerCase() === 'dashboard'
              );
              return item ? item.href : null;
            }"""
        )
        if href:
            validate_url(href)
            return href
        page.keyboard.press("Escape")
    raise MavenError("account menu did not expose a Dashboard link; session may be unauthenticated or the page layout changed")


def _courses_href(page, dashboard: str) -> str:
    _goto(page, dashboard)
    try:
        page.wait_for_selector("a", timeout=15000)
    except Exception:
        raise MavenError("Courses link was not found") from None
    href = page.evaluate(
        """() => {
          const item = [...document.querySelectorAll('a')].find(el => {
            const text = (el.innerText || '').trim();
            return text === 'Courses' && /\\/admin\\/courses\\/?$/.test(new URL(el.href).pathname);
          });
          return item ? item.href : null;
        }"""
    )
    if not href:
        raise MavenError("Courses link was not found")
    validate_url(href)
    return href


def _wait_for(page, expression: str, message: str) -> None:
    try:
        page.wait_for_function(expression, timeout=15000)
    except Exception:
        raise MavenError(message) from None


def _collect_course_links(page) -> tuple[list[dict], dict]:
    collected = []
    seen = set()
    pages = 0
    complete = True
    while pages < 20:
        current = canonical_page(page.url)
        if current in seen:
            complete = False
            break
        seen.add(current)
        pages += 1
        _wait_for(page, COURSE_READY_JS, "course list did not finish loading")
        try:
            batch = page.evaluate(COURSE_LINKS_JS)
        except Exception:
            raise MavenError("course links could not be read") from None
        collected.extend(batch["links"])
        next_href = batch.get("next_href")
        if not batch.get("next_control"):
            break
        if not next_href or canonical_page(next_href) in seen:
            complete = False
            break
        _goto(page, next_href)
    else:
        complete = False
    courses, deduped = dedupe_courses(collected)
    return courses, {
        "status": "complete" if complete else "partial",
        "pages_visited": pages,
        "deduped": deduped,
    }


def canonical_page(url: str) -> str:
    parsed = urlsplit(url)
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{query}"


def list_courses(page) -> dict:
    dashboard = _dashboard_href(page)
    courses_url = _courses_href(page, dashboard)
    _goto(page, courses_url)
    courses, completeness = _collect_course_links(page)
    return {
        "command": "courses list",
        "source": "browser",
        "dashboard_url": dashboard,
        "courses_url": courses_url,
        "courses": courses,
        "count": len(courses),
        "completeness": completeness,
        "observed_at": _now(),
    }


def _overview_state(page) -> dict:
    try:
        return page.evaluate(OVERVIEW_JS)
    except Exception:
        raise MavenError("course overview could not be read") from None


def _open_overview(page, course_url: str) -> dict:
    validate_url(course_url)
    course_path = course_admin_path(course_url)
    _goto(page, course_url)
    _wait_for(page, OVERVIEW_READY_JS, "course overview did not expose cohort Student home links")
    state = _overview_state(page)
    if state["cards"] or _explicit_empty_cohorts(page):
        return state
    overview = choose_students_like(state["overview"], course_path, exact=True)
    if not overview:
        raise MavenError("course overview did not expose cohort Student home links")
    _goto(page, overview)
    _wait_for(page, OVERVIEW_READY_JS, "course overview did not expose cohort Student home links")
    state = _overview_state(page)
    if not state["cards"] and not _explicit_empty_cohorts(page):
        raise MavenError("course overview did not expose cohort Student home links")
    return state


def _explicit_empty_cohorts(page) -> bool:
    try:
        return bool(page.evaluate(
            """() => [...document.querySelectorAll('h1,h2,h3,p')].some(el => {
              const text = (el.innerText || '').trim();
              return text === 'No cohorts' || text === 'No cohorts yet';
            })"""
        ))
    except Exception:
        return False


def choose_students_like(hrefs: list[str], course_path: str, exact: bool) -> str | None:
    matches = []
    for href in hrefs:
        path = urlsplit(href).path.rstrip("/")
        if exact and path == course_path:
            matches.append(href)
        if not exact and path.startswith(course_path + "/"):
            matches.append(href)
    if not matches:
        return None
    paths = {urlsplit(href).path.rstrip("/") for href in matches}
    if len(paths) != 1:
        raise MavenError("course navigation links disagree")
    return matches[0]


def _cohorts_from_state(state: dict, course_url: str) -> dict:
    cohorts = [parse_cohort_card(card) for card in state["cards"]]
    assert_unique_slugs(cohorts)
    latest = None
    if cohorts:
        try:
            chosen, reason = choose_cohort(cohorts, "latest")
        except MavenError as exc:
            latest = {"slug": None, "status": None, "reason": str(exc)}
        else:
            latest = {"slug": chosen["slug"], "status": chosen["status"], "reason": reason}
    course_path = course_admin_path(course_url)
    students = None
    if state["students"]:
        students = choose_students_nav(state["students"], course_path)
    return {
        "cohorts": cohorts,
        "latest": latest,
        "students_nav": students,
        "completeness": {
            "status": "partial" if state.get("next_control") else "complete",
            "pages_visited": 1,
            "next_control": bool(state.get("next_control")),
        },
    }


def list_cohorts(page, course_url: str) -> dict:
    state = _open_overview(page, course_url)
    parsed = _cohorts_from_state(state, page.url)
    return {
        "command": "cohorts list",
        "source": "browser",
        "course": course_url,
        "students_nav": parsed["students_nav"],
        "cohorts": parsed["cohorts"],
        "count": len(parsed["cohorts"]),
        "latest": parsed["latest"],
        "completeness": parsed["completeness"],
        "observed_at": _now(),
    }


def export_students(page, course_url: str, selector: str, output: Path | None, data_dir: Path) -> dict:
    state = _open_overview(page, course_url)
    parsed = _cohorts_from_state(state, page.url)
    if not parsed["students_nav"]:
        raise MavenError("Students navigation link was not found on the course page")
    refuse_partial_latest(selector, parsed["completeness"])
    cohort, reason = choose_cohort(parsed["cohorts"], selector)
    students_url = students_url_for(parsed["students_nav"], cohort["slug"])
    validate_url(students_url)
    _goto(page, students_url)
    page_enrolled = _wait_enrolled_count(page)
    target = output or _default_output(data_dir, cohort["slug"])
    target = Path(target).expanduser()
    _download_enrolled(page, target, page_enrolled)
    try:
        payload = target.read_bytes()
        checked = validate_students_csv(payload, page_enrolled)
        target.chmod(0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(payload).hexdigest()
    observed_at = _now()
    receipt = _write_receipt(data_dir, {
        "receipt_version": 1,
        "kind": "students_export",
        "source": "export_dialog",
        "course": course_url,
        "cohort": {"slug": cohort["slug"], "status": cohort["status"], "selection": reason},
        "file": str(target.resolve()),
        "sha256": digest,
        "bytes": len(payload),
        "columns": checked["columns"],
        "counts": checked["counts"],
        "observed_at": observed_at,
    })
    return {
        "command": "students export",
        "source": "export_dialog",
        "course": course_url,
        "cohort": {"slug": cohort["slug"], "status": cohort["status"], "selection": reason},
        "counts": checked["counts"],
        "columns": checked["columns"],
        "observed_at": observed_at,
        "sha256": digest,
        "file": _display_path(target),
        "receipt": _display_path(receipt),
    }


def _labeled_checkbox(dialog, label: str):
    return dialog.locator("div").filter(
        has_text=re.compile(rf"^{re.escape(label)}$")
    ).locator("input[type=checkbox]")


def _wait_enrolled_count(page) -> int:
    _enrolled_locator(page).first.wait_for(timeout=15000)
    started = time.monotonic()
    last = _enrolled_count(page)
    last_change = started
    while time.monotonic() - started < 15:
        page.wait_for_timeout(500)
        current = _enrolled_count(page)
        if current != last:
            last = current
            last_change = time.monotonic()
            continue
        if time.monotonic() - started >= 3 and time.monotonic() - last_change >= 1:
            return current
    return last


def _dialog_user_count(dialog, label: str) -> int:
    try:
        text = dialog.evaluate(
            """(root, label) => {
              const span = [...root.querySelectorAll('span')].find(el => (el.textContent || '').trim() === label);
              if (!span) return null;
              let node = span.parentElement;
              for (let i = 0; i < 4 && node; i += 1) {
                const hit = [...node.querySelectorAll('div')].find(el => /^\\d+\\s+users$/.test((el.textContent || '').trim()));
                if (hit) return hit.textContent.trim();
                node = node.parentElement;
              }
              return null;
            }""",
            label,
        )
    except Exception:
        raise MavenError("export dialog did not show a user count") from None
    match = re.fullmatch(r"(\d+)\s+users", text or "")
    if not match:
        raise MavenError("export dialog did not show a user count")
    return int(match.group(1))


def _enrolled_locator(page):
    return page.get_by_role("button", name=re.compile(r"^ENROLLED\s*\(\s*\d+\s*\)$", re.IGNORECASE))


def _enrolled_count(page) -> int:
    locator = _enrolled_locator(page)
    try:
        count = locator.count()
        text = locator.inner_text(timeout=10000) if count == 1 else ""
    except Exception:
        raise MavenError("page did not show an Enrolled count") from None
    match = re.fullmatch(r"ENROLLED\s*\(\s*(\d+)\s*\)", " ".join(text.split()), re.IGNORECASE)
    if count != 1 or not match:
        raise MavenError("page did not show an Enrolled count")
    return int(match.group(1))


def _download_enrolled(page, target: Path, page_enrolled: int) -> None:
    icon = page.locator(f"button:has(svg path[d='{EXPORT_ICON}'])")
    try:
        count = icon.count()
    except Exception:
        raise MavenError("students export control was not found; page layout changed") from None
    if count != 1:
        raise MavenError("students export control was not found; page layout changed")
    label = " ".join((icon.first.inner_text(timeout=5000) or "").split())
    aria = (icon.first.get_attribute("aria-label") or "").strip()
    if label or aria:
        raise MavenError("students export control was not found; page layout changed")
    try:
        icon.first.click(timeout=10000)
        dialog = page.get_by_role("dialog").filter(has_text="Export Students")
        dialog.wait_for(timeout=10000)
    except Exception:
        raise MavenError("Export Students dialog did not open") from None
    enrolled = _labeled_checkbox(dialog, "Enrolled")
    dropped = _labeled_checkbox(dialog, "Dropped off")
    if enrolled.count() != 1 or dropped.count() != 1:
        raise MavenError("export dialog checkboxes were not the expected Enrolled and Dropped off controls")
    if not enrolled.is_checked():
        enrolled.set_checked(True)
    if dropped.is_checked():
        dropped.set_checked(False)
    if not enrolled.is_checked() or dropped.is_checked():
        raise MavenError("could not limit export to Enrolled students")
    if _dialog_user_count(dialog, "Enrolled") != page_enrolled:
        raise MavenError("export dialog enrolled count did not match the page")
    button = dialog.get_by_role("button", name="Export Students", exact=True)
    if button.count() != 1:
        raise MavenError("Export Students confirmation button was not found")
    reserve_output(target)
    try:
        with page.expect_download(timeout=60000) as download_info:
            button.click()
        download_info.value.save_as(str(target))
    except Exception:
        target.unlink(missing_ok=True)
        raise MavenError("export did not start a download") from None
    target.chmod(0o600)
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        target.unlink(missing_ok=True)
        raise MavenError("could not restrict export file permissions")


def _default_output(data_dir: Path, slug: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return data_dir / "downloads" / f"students-{safe_slug_token(slug)}-{stamp}.csv"


def _write_receipt(data_dir: Path, payload: dict) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = data_dir / "receipts"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / f"students-export-{stamp}.json"
    if path.exists():
        raise MavenError("export receipt already exists; refusing to overwrite")
    private_json(path, payload)
    path.chmod(0o600)
    pointer = directory / "latest.json"
    private_json(pointer, payload | {"receipt": str(path.resolve())})
    pointer.chmod(0o600)
    return path


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Lightning Lessons (read-only) -------------------------------------------------
#
# Lessons commands only navigate and read. After org discovery (the shared account
# menu step, which passes the click guard), every lesson page is driven through
# ReadOnlyPage: it exposes navigation and a fixed set of read-only scripts, and has
# no click, fill, type, keyboard, or locator surface at all. The Lightning Lesson
# editor autosaves, so typing would already be a business write.

LESSONS_NAV_JS = """() => {
  const path = location.pathname.replace(/\\/$/, '');
  const org = path.split('/')[1] || '';
  const item = [...document.querySelectorAll('a')].find(el => {
    try {
      const target = new URL(el.href).pathname.replace(/\\/$/, '');
      return target === '/' + org + '/admin/lightning-lessons';
    } catch (e) { return false; }
  });
  return item ? item.href : null;
}"""
LESSONS_LIST_READY_JS = """() => {
  const label = /^(drafts|upcoming|past)\\s*\\(\\s*\\d+\\s*\\)$/i;
  if ([...document.querySelectorAll('summary')].some(el => label.test((el.textContent || '').trim()))) return true;
  return [...document.querySelectorAll('button')].some(el => (el.textContent || '').trim() === 'Create a Lightning Lesson');
}"""
LESSONS_LIST_JS = """() => {
  const isLesson = a => {
    try { return /\\/admin\\/lightning-lessons\\/[^/]+\\/?$/.test(new URL(a.href).pathname); }
    catch (e) { return false; }
  };
  const label = /^(drafts|upcoming|past|[a-z ]+)\\s*\\(\\s*(\\d+)\\s*\\)$/i;
  const card = a => {
    let node = a;
    while (node.parentElement) {
      const parent = node.parentElement;
      if ([...parent.querySelectorAll('a')].filter(isLesson).length > 1) break;
      node = parent;
    }
    return {
      href: a.href,
      title: (a.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 200),
      items: [...node.querySelectorAll('li')].map(li => (li.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120))
    };
  };
  const grouped = new Set();
  const sections = [...document.querySelectorAll('details')].map(details => {
    const summary = details.querySelector('summary');
    const match = summary ? (summary.textContent || '').trim().match(label) : null;
    if (!match) return null;
    const anchors = [...details.querySelectorAll('a')].filter(isLesson);
    anchors.forEach(a => grouped.add(a));
    return {label: match[1].trim(), count: Number(match[2]), cards: anchors.map(card)};
  }).filter(Boolean);
  const ungrouped = [...document.querySelectorAll('a')].filter(a => isLesson(a) && !grouped.has(a)).length;
  const next = [...document.querySelectorAll('a, button')].some(el => {
    const name = (el.getAttribute('aria-label') || el.textContent || '').trim();
    return /^(next|load more|show more)$/i.test(name) || el.getAttribute('rel') === 'next';
  });
  return {sections, ungrouped, next_control: next};
}"""
LESSON_ROUTE_READY_JS = """() => {
  const path = location.pathname.replace(/\\/$/, '');
  return /\\/edit$/.test(path) || new URLSearchParams(location.search).has('tab');
}"""
LESSON_PUBLISHED_JS = """() => {
  const el = document.getElementById('__NEXT_DATA__');
  if (!el) return null;
  let data;
  try { data = JSON.parse(el.textContent); } catch (e) { return null; }
  const props = (data.props || {}).pageProps || {};
  const w = props.adminPublishedWorkshop || props.initialWorkshop;
  if (!w) return {published: false, slug: props.slug || null};
  const page = w.page || {};
  const event = page.school_event || {};
  return {
    published: true,
    slug: page.slug || props.slug || null,
    now: props.now || null,
    start_datetime: event.start_datetime || null,
    start_date: event.start_date || null,
    start_time: event.start_time || null,
    timezone: event.timezone || null,
    duration_min: event.duration_min,
    has_location: Boolean(event.location),
    signup_count: w.signup_count,
    recording_unique_viewer_count: w.recording_unique_viewer_count,
    is_canceled: Boolean(w.is_canceled),
    is_delisted: Boolean(w.is_delisted),
    is_visible_on_discovery_page: Boolean(w.is_visible_on_discovery_page),
    connected_course: w.connected_course_id !== null && w.connected_course_id !== undefined,
    promo_code: w.connected_course_stripe_promo_code_id !== null && w.connected_course_stripe_promo_code_id !== undefined
  };
}"""
LESSON_TEXT_COUNTS_JS = """() => {
  const nodes = [...document.querySelectorAll('body *')].filter(el => (el.textContent || '').length < 200);
  const pick = re => {
    const hit = nodes.find(el => re.test((el.textContent || '').replace(/\\s+/g, ' ').trim()));
    return hit ? (hit.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120) : null;
  };
  return {
    signups: pick(/^[\\d,]+\\s+signups?$/i),
    viewers: pick(/^[\\d,]+\\s+watched the recording/i)
  };
}"""
LESSON_SIGNUPS_READY_JS = """() => [...document.querySelectorAll('body *')].some(el =>
  (el.textContent || '').length < 200 && /^[\\d,]+\\s+signups?$/i.test((el.textContent || '').replace(/\\s+/g, ' ').trim())
)"""
LESSON_EDITOR_READY_JS = """() => {
  const details = document.getElementById('free-lesson-section-details');
  if (!details || !details.querySelector('input[name="title"]')) return false;
  if (!document.getElementById('free-lesson-section-instructors')) return false;
  const start = [...details.querySelectorAll('h5, h4, label')].find(el => (el.textContent || '').trim() === 'Start time');
  return Boolean(start && start.nextElementSibling && (start.nextElementSibling.textContent || '').trim());
}"""
LESSON_EDITOR_JS = """() => {
  const norm = value => (value || '').replace(/\\s+/g, ' ').trim();
  const counterNear = el => {
    let node = el;
    for (let i = 0; i < 5 && node; i += 1) {
      const hit = [...node.querySelectorAll('p')].find(p => /^\\s*\\d+\\s*\\/\\s*\\d+\\s*$/.test(p.textContent || ''));
      if (hit) return norm(hit.textContent);
      node = node.parentElement;
    }
    return null;
  };
  const afterHeading = text => {
    const heading = [...document.querySelectorAll('h5, h4, label')].find(el => norm(el.textContent) === text);
    return heading ? heading.nextElementSibling : null;
  };
  const details = document.getElementById('free-lesson-section-details');
  const titleInput = details ? details.querySelector('input[name="title"]') : null;
  const dateBox = afterHeading('Date');
  const dateInput = dateBox ? dateBox.querySelector('input') : null;
  const selectText = text => {
    const box = afterHeading(text);
    return box ? norm(box.textContent) : null;
  };
  const buttons = details ? [...details.querySelectorAll('button')].map(el => norm(el.textContent)) : [];
  const outcomeSection = document.getElementById('free-lesson-section-learningOutcomes');
  const outcomes = outcomeSection ? [...outcomeSection.querySelectorAll('ol > li')].map(li => {
    const title = li.querySelector('input[name$=".title"]');
    const description = li.querySelector('textarea[name$=".description"]');
    const flagged = li.querySelector('[data-error]');
    return {
      title: title ? title.value : null,
      title_counter: title ? counterNear(title) : null,
      description: description ? description.value : null,
      description_counter: description ? counterNear(description) : null,
      error: flagged ? flagged.getAttribute('data-error') === 'true' : false
    };
  }).filter(item => item.title !== null || item.description !== null) : [];
  const topicSection = document.getElementById('free-lesson-section-topic');
  const topic = topicSection ? topicSection.querySelector('textarea[name="topic_desc"]') : null;
  const instructorSection = document.getElementById('free-lesson-section-instructors');
  const instructors = instructorSection ? [...instructorSection.querySelectorAll('ol > li > button[data-error]')].map(button => ({
    texts: [...button.querySelectorAll('div')].filter(el => el.children.length === 0).map(el => norm(el.textContent)).filter(Boolean),
    error: button.getAttribute('data-error') === 'true'
  })) : [];
  const header = [...document.querySelectorAll('button')].map(el => norm(el.textContent))
    .filter(text => /%\\s*complete/i.test(text) || /review\\s+\\d+\\s+errors?/i.test(text) || text === 'Publish');
  const sections = [...document.querySelectorAll('[id^="free-lesson-section"]')];
  const inline = [];
  sections.forEach(section => {
    section.querySelectorAll('p, span, div').forEach(el => {
      if (el.children.length !== 0) return;
      const cls = (el.getAttribute('class') || '');
      const text = norm(el.textContent);
      if (!text || text.length > 200) return;
      if (/(^|\\s|-)(red|error|danger|destructive)(-|\\s|$)/i.test(cls) || /before publishing/i.test(text)) inline.push(text);
    });
  });
  return {
    title: {value: titleInput ? titleInput.value : null, counter: titleInput ? counterNear(titleInput) : null},
    date: dateInput ? dateInput.value : null,
    start_time: selectText('Start time'),
    duration: selectText('Duration'),
    timezone_text: details ? ((norm(details.textContent).match(/All times are in [A-Za-z_\\/]+/) || [null])[0]) : null,
    link: {add_button: buttons.includes('Add event link'), update_button: buttons.includes('Update event link')},
    outcomes,
    topic: {value: topic ? topic.value : null, counter: topic ? counterNear(topic) : null},
    instructors,
    header,
    inline_errors: inline
  };
}"""
READ_ONLY_SCRIPTS = frozenset({
    LESSONS_NAV_JS,
    LESSONS_LIST_READY_JS,
    LESSONS_LIST_JS,
    LESSON_ROUTE_READY_JS,
    LESSON_PUBLISHED_JS,
    LESSON_TEXT_COUNTS_JS,
    LESSON_SIGNUPS_READY_JS,
    LESSON_EDITOR_READY_JS,
    LESSON_EDITOR_JS,
})
SIGNUP_HISTOGRAM_UNAVAILABLE = (
    "signup timestamps are not exposed read-only: the Signups tab shows only coarse relative "
    "dates across paginated rows next to names and emails, and exact timestamps come only "
    "from an undocumented API that this tool does not call"
)


class ReadOnlyPage:
    """Page facade for lessons commands: navigation and registered read-only scripts only."""

    def __init__(self, page):
        self._page = page

    @property
    def url(self) -> str:
        return self._page.url

    def goto(self, url: str, **kwargs):
        validate_url(url)
        return self._page.goto(url, **kwargs)

    def evaluate(self, script: str, *args):
        if script not in READ_ONLY_SCRIPTS:
            raise MavenError("lessons commands only run registered read-only scripts")
        return self._page.evaluate(script, *args)

    def wait_for_function(self, script: str, **kwargs):
        if script not in READ_ONLY_SCRIPTS:
            raise MavenError("lessons commands only run registered read-only scripts")
        return self._page.wait_for_function(script, **kwargs)

    def wait_for_timeout(self, timeout: float):
        return self._page.wait_for_timeout(timeout)

    def __getattr__(self, name: str):
        raise MavenError(f"lessons commands are read-only; '{name}' is not available")


def _lessons_base(page) -> tuple[str, ReadOnlyPage]:
    dashboard = _dashboard_href(page)
    reader = ReadOnlyPage(page)
    _goto(reader, dashboard)
    try:
        reader.wait_for_function(LESSONS_NAV_JS, timeout=15000)
        href = reader.evaluate(LESSONS_NAV_JS)
    except MavenError:
        raise
    except Exception:
        href = None
    if not href:
        raise MavenError("Lightning Lessons link was not found on the dashboard")
    validate_url(href)
    return lessons_admin_base(href), reader


def _read_lesson_list(reader: ReadOnlyPage, base: str) -> tuple[list[dict], dict]:
    _goto(reader, base)
    _wait_for(reader, LESSONS_LIST_READY_JS, "Lightning Lessons list did not finish loading")
    reader.wait_for_timeout(1000)
    try:
        state = reader.evaluate(LESSONS_LIST_JS)
    except MavenError:
        raise
    except Exception:
        raise MavenError("Lightning Lessons list could not be read") from None
    return parse_lesson_list(state, base)


def list_lessons(page) -> dict:
    base, reader = _lessons_base(page)
    lessons, completeness = _read_lesson_list(reader, base)
    counts = {status: sum(1 for item in lessons if item["status"] == status)
              for status in ("draft", "upcoming", "past")}
    result = {
        "command": "lessons list",
        "source": "browser",
        "lessons_url": base,
        "lessons": lessons,
        "count": len(lessons),
        "counts": counts,
        "completeness": completeness,
        "observed_at": _now(),
    }
    assert_public_output(result)
    return result


def _resolve_lesson(page, lesson: str) -> tuple[str, str, ReadOnlyPage]:
    base, lesson_id = parse_lesson_ref(lesson)
    if base is None:
        base, reader = _lessons_base(page)
    else:
        reader = ReadOnlyPage(page)
    return base, lesson_id, reader


def _open_lesson(reader: ReadOnlyPage, base: str, lesson_id: str) -> dict:
    url = lesson_admin_url(base, lesson_id)
    _goto(reader, url)
    _wait_for(reader, LESSON_ROUTE_READY_JS, "lesson page did not finish loading")
    path = urlsplit(reader.url).path.rstrip("/")
    if f"/admin/lightning-lessons/{lesson_id}" not in path:
        raise MavenError("lesson page redirected to a different lesson")
    if path.endswith("/edit"):
        return {"published": False}
    try:
        data = reader.evaluate(LESSON_PUBLISHED_JS)
    except MavenError:
        raise
    except Exception:
        raise MavenError("lesson overview data could not be read") from None
    if data and data.get("slug") not in (None, lesson_id):
        raise MavenError("lesson overview data belongs to a different lesson")
    return data or {"published": False}


def _read_text_counts(reader: ReadOnlyPage) -> dict:
    reader.wait_for_timeout(1500)
    try:
        return reader.evaluate(LESSON_TEXT_COUNTS_JS) or {}
    except MavenError:
        raise
    except Exception:
        return {}


def show_lesson(page, lesson: str) -> dict:
    base, lesson_id, reader = _resolve_lesson(page, lesson)
    published = summarize_published(_open_lesson(reader, base, lesson_id))
    viewers_text = None
    if published["published"]:
        viewers_text = parse_recording_viewers(_read_text_counts(reader).get("viewers"))
    _goto(reader, f"{lesson_admin_url(base, lesson_id)}/edit")
    _wait_for(reader, LESSON_EDITOR_READY_JS, "lesson editor did not finish loading")
    reader.wait_for_timeout(1000)
    try:
        state = reader.evaluate(LESSON_EDITOR_JS)
    except MavenError:
        raise
    except Exception:
        raise MavenError("lesson editor could not be read") from None
    editor = summarize_editor(state)
    status = "draft" if not published["published"] else (published.get("phase") or "published")
    result = {
        "command": "lessons show",
        "source": "browser",
        "lesson": {"id": lesson_id, "admin_url": lesson_admin_url(base, lesson_id), "status": status},
        "editor": editor,
        "published": published | ({"recording_viewer_text_count": viewers_text} if published["published"] else {}),
        "observed_at": _now(),
    }
    assert_public_output(result)
    return result


def _stats_for(reader: ReadOnlyPage, base: str, lesson_id: str) -> dict:
    published = summarize_published(_open_lesson(reader, base, lesson_id))
    entry = {"id": lesson_id, "admin_url": lesson_admin_url(base, lesson_id)}
    if not published["published"]:
        return entry | {"status": "draft", "published": False}
    viewers_text = parse_recording_viewers(_read_text_counts(reader).get("viewers"))
    _goto(reader, f"{lesson_admin_url(base, lesson_id)}?tab=signups")
    signups_tab = None
    try:
        reader.wait_for_function(LESSON_SIGNUPS_READY_JS, timeout=15000)
        signups_tab = parse_signups_tab(_read_text_counts(reader).get("signups"))
    except MavenError:
        raise
    except Exception:
        signups_tab = None
    return entry | {
        "status": published.get("phase") or "published",
        "published": True,
        "start_date": published["start_date"],
        "signups": {
            "signup_count": published["signup_count"],
            "signups_tab_count": signups_tab,
        },
        "recording_viewers": {
            "recording_viewer_count": published["recording_viewer_count"],
            "overview_text_count": viewers_text,
        },
        "live_attendance": None,
        "signup_date_histogram": {"available": False, "reason": SIGNUP_HISTOGRAM_UNAVAILABLE},
    }


def lessons_stats(page, lesson: str | None, all_lessons: bool) -> dict:
    if bool(lesson) == bool(all_lessons):
        raise MavenError("choose exactly one of --lesson or --all")
    completeness = {"status": "complete"}
    if all_lessons:
        base, reader = _lessons_base(page)
        listed, completeness = _read_lesson_list(reader, base)
        targets = [item["id"] for item in listed if item["status"] != "draft"]
    else:
        base, lesson_id, reader = _resolve_lesson(page, lesson)
        targets = [lesson_id]
    entries = [_stats_for(reader, base, lesson_id) for lesson_id in targets]
    published = [item for item in entries if item.get("published")]
    def total(group: str, key: str) -> int | None:
        values = [item[group][key] for item in published]
        if not values or any(value is None for value in values):
            return None
        return sum(values)
    result = {
        "command": "lessons stats",
        "source": "browser",
        "lessons": entries,
        "count": len(entries),
        "totals": {
            "signup_count": total("signups", "signup_count"),
            "recording_viewer_count": total("recording_viewers", "recording_viewer_count"),
        },
        "notes": [
            "signup_count comes from the lesson page's embedded data; signups_tab_count is the "
            "Signups tab header and may differ; neither is reconciled here",
            "Maven admin shows no live-attendance count",
        ],
        "completeness": completeness,
        "observed_at": _now(),
    }
    assert_public_output(result)
    return result
