"""Read-only promo code commands: `promo-codes list` and `promo-codes locate-pause`.

Both commands read the course Settings page through PromoReader, a page facade that
exposes navigation, registered read-only scripts, and a row capture (scroll, element
screenshot, bounding boxes). It has no click, fill, type, hover, keyboard, or locator
surface. The middle Actions button of a promo code row is a one-click pause/resume
toggle without confirmation, so this module never interacts with any Actions button;
`locate-pause` only identifies the button and draws a box around it on a screenshot.
"""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from maven_skill.errors import MavenError
from maven_skill.parse import (
    SAFE_SLUG,
    assert_public_output,
    canonical_url,
    course_admin_path,
    public_course_url,
)
from maven_skill.session import validate_url


EXPECTED_HEADERS = ["Code", "Amount off", "Percent off", "Redemptions", "Actions"]
# Recorded as evidence only; identification uses geometry, never these constants alone.
PAUSE_ICON_PREFIX = "M3.60002 12.9V3.1H5.65002V12.9H3.60002Z"
PLAY_ICON_PREFIX = "M4.46448 1.53974"
SCHOOL_COURSE = re.compile(r"^(?P<school>[A-Za-z0-9_-]{1,64})/(?P<course>[A-Za-z0-9_-]{1,64})$")

SETTINGS_READY_JS = """() => {
  const norm = v => (v || '').replace(/\\s+/g, ' ').trim();
  if (!document.querySelector('input[name="code"]')) return false;
  return [...document.querySelectorAll('table')].some(t =>
    [...t.querySelectorAll('thead h5')].some(h => norm(h.textContent) === 'Code'));
}"""
PROMO_TABLE_JS = """() => {
  const norm = v => (v || '').replace(/\\s+/g, ' ').trim();
  const tables = [...document.querySelectorAll('table')].filter(t =>
    [...t.querySelectorAll('thead h5')].some(h => norm(h.textContent) === 'Code'));
  if (tables.length !== 1) return {tables: tables.length};
  const table = tables[0];
  const headers = [...table.querySelectorAll('thead h5')].map(h => norm(h.textContent));
  const keyOf = (el, prefix) => Object.keys(el).find(k => k.startsWith(prefix));
  const handlerOf = button => {
    try {
      const key = keyOf(button, '__reactProps$');
      const fn = key && button[key] ? button[key].onClick : null;
      return typeof fn === 'function' ? Function.prototype.toString.call(fn).slice(0, 4000) : null;
    } catch (e) { return null; }
  };
  const svgOf = button => {
    const svg = button.querySelector('svg');
    if (!svg) return null;
    return {
      view_box: svg.getAttribute('viewBox'),
      paths: [...svg.querySelectorAll('path')].map(p => ({
        d: (p.getAttribute('d') || '').slice(0, 3000),
        fill_rule: p.getAttribute('fill-rule'),
        stroke: p.getAttribute('stroke'),
        fill: p.getAttribute('fill')
      }))
    };
  };
  const rows = [...table.querySelectorAll('tbody > tr')].map((tr, index) => {
    const cells = [...tr.children].filter(c => c.tagName === 'TD');
    const actions = cells.length ? cells[cells.length - 1] : null;
    const buttons = actions ? [...actions.querySelectorAll('button')] : [];
    return {
      index,
      cells: cells.map(c => norm(c.textContent)),
      row_class: tr.getAttribute('class') || '',
      greyed: tr.classList.contains('text-gray-400'),
      html: tr.outerHTML.slice(0, 20000),
      buttons: buttons.map((b, position) => ({
        position,
        class: b.getAttribute('class') || '',
        aria_label: b.getAttribute('aria-label'),
        title: b.getAttribute('title'),
        text: norm(b.textContent),
        data_attributes: [...b.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name),
        svg: svgOf(b),
        handler: handlerOf(b)
      }))
    };
  });
  let react = {available: false, reason: 'promoCodes prop not found'};
  try {
    const key = keyOf(table, '__reactFiber$');
    let fiber = key ? table[key] : null;
    for (let i = 0; fiber && i < 15; i += 1) {
      const props = fiber.memoizedProps || {};
      if (Array.isArray(props.promoCodes)) {
        react = {
          available: true,
          share_slug: typeof props.courseSlugForShareLink === 'string' ? props.courseSlugForShareLink : null,
          codes: props.promoCodes.map(c => ({
            code: c.code, active: c.active, valid: c.valid, amount_off: c.amount_off,
            percent_off: c.percent_off, redemptions: c.redemptions, currency: c.currency
          }))
        };
        break;
      }
      fiber = fiber.return;
    }
  } catch (e) { react = {available: false, reason: 'promoCodes prop unreadable'}; }
  return {tables: 1, headers, rows, react};
}"""
PUBLIC_PRICE_JS = """() => {
  const norm = v => (v || '').replace(/\\s+/g, ' ').trim();
  const price = /^\\$\\s?[\\d,]+(?:\\.\\d\\d)?$/;
  const struck = new Set();
  document.querySelectorAll('s, del, strike, [class*="line-through"]').forEach(el => {
    const text = norm(el.innerText || el.textContent);
    if (price.test(text)) struck.add(text);
  });
  document.querySelectorAll('body *').forEach(el => {
    if (el.children.length !== 0) return;
    const text = norm(el.textContent);
    if (!price.test(text)) return;
    const line = (getComputedStyle(el).textDecorationLine || '');
    if (line.includes('line-through')) struck.add(text);
  });
  const body = document.body ? (document.body.innerText || '') : '';
  return {struck: [...struck].slice(0, 10), prices: (body.match(/\\$[\\d,]+(?:\\.\\d\\d)?/g) || []).slice(0, 12)};
}"""
PROMO_SCRIPTS = frozenset({SETTINGS_READY_JS, PROMO_TABLE_JS, PUBLIC_PRICE_JS})


# --- page facade ---------------------------------------------------------------------

class PromoReader:
    """Settings-page facade: navigation, registered scripts, and row capture only."""

    def __init__(self, page):
        self._page = page

    @property
    def url(self) -> str:
        return self._page.url

    def goto(self, url: str, **kwargs):
        validate_url(url)
        return self._page.goto(url, **kwargs)

    def evaluate(self, script: str, *args):
        if script not in PROMO_SCRIPTS:
            raise MavenError("promo-codes commands only run registered read-only scripts")
        return self._page.evaluate(script, *args)

    def wait_for_function(self, script: str, **kwargs):
        if script not in PROMO_SCRIPTS:
            raise MavenError("promo-codes commands only run registered read-only scripts")
        return self._page.wait_for_function(script, **kwargs)

    def wait_for_timeout(self, timeout: float):
        return self._page.wait_for_timeout(timeout)

    def capture_row(self, index: int, code: str) -> dict:
        """Screenshot one promo table row and measure its Actions buttons; no interaction."""
        page = self._page
        tables = page.locator("table").filter(
            has=page.locator("thead h5", has_text=re.compile(r"^\s*Code\s*$"))
        )
        if tables.count() != 1:
            raise MavenError("Promo codes table was not unique when capturing the row")
        row = tables.first.locator("tbody > tr").nth(index)
        first_cell = " ".join((row.locator("td").first.inner_text(timeout=5000) or "").split())
        if first_cell != code:
            raise MavenError("Promo codes table changed while capturing the row")
        row.scroll_into_view_if_needed(timeout=5000)
        png = row.screenshot(type="png", timeout=10000)
        row_box = row.bounding_box()
        buttons = row.locator("td").last.locator("button")
        boxes = [buttons.nth(i).bounding_box() for i in range(buttons.count())]
        return {"png": png, "row_box": row_box, "button_boxes": boxes}

    @contextmanager
    def cookieless(self):
        """A fresh browser context without cookies, for reading the public landing page."""
        browser = self._page.context.browser
        if browser is None:
            raise MavenError("browser handle is unavailable for the public link check")
        context = browser.new_context()
        try:
            page = context.new_page()
            yield PromoReader(page)
        finally:
            context.close()

    def __getattr__(self, name: str):
        raise MavenError(f"promo-codes commands are read-only; '{name}' is not available")


# --- course reference ----------------------------------------------------------------

def parse_course_ref(value: str) -> tuple[str | None, str | None]:
    """Return (course admin URL or None, bare course slug or None)."""
    text = (value or "").strip()
    if text.startswith("https://") or text.startswith("http://"):
        parsed = urlsplit(text)
        if parsed.scheme != "https" or parsed.hostname != "maven.com":
            raise MavenError("course must be a https://maven.com course admin URL")
        path = course_admin_path(text)
        school = path.split("/")[1] if path.count("/") >= 3 else ""
        if not SAFE_SLUG.fullmatch(school) or not path.startswith(f"/{school}/admin/courses/"):
            raise MavenError("course must be a Maven course admin URL")
        slug = path.rsplit("/", 1)[-1]
        if not SAFE_SLUG.fullmatch(slug):
            raise MavenError("course slug is not a safe token")
        return f"https://maven.com{path}", None
    pair = SCHOOL_COURSE.fullmatch(text)
    if pair:
        return f"https://maven.com/{pair.group('school')}/admin/courses/{pair.group('course')}", None
    if SAFE_SLUG.fullmatch(text):
        return None, text
    raise MavenError("course must be a course admin URL, <school>/<course>, or a course slug")


def course_from_list(courses: list[dict], slug: str) -> str:
    matches = []
    for course in courses:
        path = urlsplit(course.get("url") or "").path.rstrip("/")
        if path.endswith(f"/admin/courses/{slug}"):
            matches.append(course["url"])
    if len(matches) != 1:
        raise MavenError("course slug did not match exactly one course in the courses list")
    return matches[0]


def settings_url(admin_url: str) -> str:
    return f"https://maven.com{course_admin_path(admin_url)}/settings"


def public_link(admin_url: str, code: str, share_slug: str | None = None) -> str:
    base = public_course_url(admin_url)
    if share_slug and SAFE_SLUG.fullmatch(share_slug):
        school = urlsplit(base).path.split("/")[1]
        base = f"https://maven.com/{school}/{share_slug}"
    return f"{base}?promoCode={quote(code, safe='')}"


# --- SVG geometry --------------------------------------------------------------------

PATH_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def svg_subpaths(d: str) -> list[dict]:
    """Split a path into subpaths. Only absolute M/L/H/V/Z are traced; anything else marks curved."""
    subpaths: list[dict] = []
    current = None
    command = None
    x = y = 0.0
    tokens = PATH_TOKEN.findall(d or "")
    i = 0

    def number() -> float | None:
        nonlocal i
        if i < len(tokens) and not tokens[i].isalpha():
            value = float(tokens[i])
            i += 1
            return value
        return None

    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            command = token
            i += 1
            if command in "Zz":
                if current is not None:
                    current["closed"] = True
                    current = None
                continue
        if command is None:
            i += 1
            continue
        if command == "M":
            nx, ny = number(), number()
            if nx is None or ny is None:
                break
            x, y = nx, ny
            current = {"points": [(x, y)], "curved": False, "closed": False}
            subpaths.append(current)
            command = "L"
        elif command == "L":
            nx, ny = number(), number()
            if nx is None or ny is None:
                break
            x, y = nx, ny
            if current is not None:
                current["points"].append((x, y))
        elif command == "H":
            nx = number()
            if nx is None:
                break
            x = nx
            if current is not None:
                current["points"].append((x, y))
        elif command == "V":
            ny = number()
            if ny is None:
                break
            y = ny
            if current is not None:
                current["points"].append((x, y))
        else:
            if current is None:
                current = {"points": [], "curved": True, "closed": False}
                subpaths.append(current)
            current["curved"] = True
            while number() is not None:
                pass
    return subpaths


def _vertices(sub: dict) -> list[tuple[float, float]]:
    points = []
    for point in sub["points"]:
        rounded = (round(point[0], 3), round(point[1], 3))
        if not points or points[-1] != rounded:
            points.append(rounded)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points


def _is_bar(sub: dict) -> tuple[float, float] | None:
    """A closed axis-aligned rectangle clearly taller than wide; returns its x range."""
    if sub["curved"]:
        return None
    pts = _vertices(sub)
    if len(pts) != 4:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if x0 != x1 and y0 != y1:
            return None
    xs = sorted({p[0] for p in pts})
    ys = sorted({p[1] for p in pts})
    if len(xs) != 2 or len(ys) != 2:
        return None
    width, height = xs[1] - xs[0], ys[1] - ys[0]
    if width <= 0 or height < 2 * width:
        return None
    return xs[0], xs[1]


def _is_play_triangle(sub: dict) -> bool:
    """A straight-edged triangle with a vertical left edge and an apex to its right."""
    if sub["curved"]:
        return False
    pts = _vertices(sub)
    if len(pts) != 3:
        return False
    for apex in pts:
        others = [p for p in pts if p != apex]
        if len(others) == 2 and others[0][0] == others[1][0] and apex[0] > others[0][0]:
            low, high = sorted(p[1] for p in others)
            return low < apex[1] < high
    return False


def _straight_line(sub: dict) -> str | None:
    if sub["curved"]:
        return None
    pts = _vertices(sub)
    if len(pts) != 2:
        return None
    (x0, y0), (x1, y1) = pts
    if abs(y0 - y1) <= 0.05 and abs(x0 - x1) > 1:
        return "horizontal"
    if abs(x0 - x1) <= 0.05 and abs(y0 - y1) > 1:
        return "vertical"
    return None


def classify_icon(svg: dict | None) -> str:
    """Return pause, play, link, trash, or unknown from the icon geometry."""
    if not svg or not svg.get("paths"):
        return "unknown"
    view_box = " ".join((svg.get("view_box") or "").split())
    paths = svg["paths"]
    stroked = all((p.get("stroke") or "") and not p.get("fill_rule") for p in paths)
    if view_box == "0 0 16 16" and len(paths) == 1 and paths[0].get("fill_rule") == "evenodd":
        subs = svg_subpaths(paths[0].get("d") or "")
        bars = sorted(r for r in (_is_bar(s) for s in subs) if r)
        triangles = [s for s in subs if _is_play_triangle(s)]
        disjoint = len(bars) >= 2 and all(a[1] < b[0] for a, b in zip(bars, bars[1:]))
        if len(bars) == 2 and disjoint and not triangles:
            return "pause"
        if triangles and not bars:
            return "play"
        return "unknown"
    if view_box == "0 0 24 24" and len(paths) == 2 and stroked:
        if all(svg_subpaths(p.get("d") or "") and all(s["curved"] for s in svg_subpaths(p.get("d") or ""))
               for p in paths):
            return "link"
        return "unknown"
    if view_box == "0 0 16 16" and len(paths) >= 4 and stroked:
        lines = [_straight_line(s) for p in paths for s in svg_subpaths(p.get("d") or "")]
        if lines.count("horizontal") >= 1 and lines.count("vertical") >= 2:
            return "trash"
    return "unknown"


# --- handler source ------------------------------------------------------------------

PAUSED_LITERAL = re.compile(r"[\"'`]Paused[\"'`]")
NEGATED_ACTIVE = re.compile(r"!\s*[\w$]+\.active\b")


def classify_handler(source: str | None) -> str | None:
    """Return toggle, copy, delete, or unknown from onClick source; None when unavailable."""
    if not source:
        return None
    if "active:" in source and PAUSED_LITERAL.search(source) and NEGATED_ACTIVE.search(source):
        return "toggle"
    if "PromoCodeCopy" in source:
        return "copy"
    if "confirm(" in source and re.search(r"delete", source, re.IGNORECASE):
        return "delete"
    return "unknown"


GEOMETRY_FOR = {"copy": "link", "delete": "trash", "toggle": ("pause", "play")}


def button_kind(button: dict) -> tuple[str, str]:
    """Return (kind, basis): kind from the handler when readable, else from geometry."""
    icon = classify_icon(button.get("svg"))
    handler = classify_handler(button.get("handler"))
    if handler is None:
        by_icon = {"link": "copy", "trash": "delete", "pause": "toggle", "play": "toggle"}
        return by_icon.get(icon, "unknown"), "geometry"
    expected = GEOMETRY_FOR.get(handler)
    if expected is not None and icon != "unknown" and icon not in (
        expected if isinstance(expected, tuple) else (expected,)
    ):
        return "conflict", "handler+geometry"
    return handler, "handler"


# --- table parsing -------------------------------------------------------------------

def _amount(text: str) -> str | None:
    text = " ".join((text or "").split())
    return None if text in ("", "-") else text


def _redemptions(text: str) -> int | None:
    text = " ".join((text or "").split()).replace(",", "")
    if text in ("", "-"):
        return 0
    return int(text) if text.isdigit() else None


def check_table(state: dict | None) -> None:
    if not state or state.get("tables") != 1:
        raise MavenError("Promo codes table was not found exactly once on the Settings page")
    if state.get("headers") != EXPECTED_HEADERS:
        raise MavenError("Promo codes table headers changed; refusing to read the page")


def react_alignment(rows: list[dict], react: dict | None) -> str:
    if not react or not react.get("available"):
        return "unavailable"
    codes = react.get("codes") or []
    if len(codes) != len(rows):
        return "misaligned"
    for row, data in zip(rows, codes):
        if not row["cells"] or row["cells"][0] != (data.get("code") or ""):
            return "misaligned"
    return "aligned"


def toggle_icon(buttons: list[dict]) -> str | None:
    icons = [classify_icon(b.get("svg")) for b in buttons]
    toggles = [icon for icon in icons if icon in ("pause", "play")]
    return toggles[0] if len(toggles) == 1 else None


def row_status(icon: str | None, greyed: bool, react_active) -> tuple[str, dict]:
    signals = {
        "icon": {"pause": "active", "play": "paused"}.get(icon or ""),
        "row_greyed": "paused" if greyed else "active",
        "react_active": None if not isinstance(react_active, bool) else ("active" if react_active else "paused"),
    }
    if signals["icon"] is None:
        return "unknown", signals
    values = {value for value in signals.values() if value is not None}
    return (values.pop() if len(values) == 1 else "unknown"), signals


def parse_promo_table(state: dict | None) -> dict:
    check_table(state)
    rows = state.get("rows") or []
    react = state.get("react") or {}
    alignment = react_alignment(rows, react)
    folded: dict[str, int] = {}
    for row in rows:
        if row.get("cells"):
            key = row["cells"][0].casefold()
            folded[key] = folded.get(key, 0) + 1
    codes = []
    for row in rows:
        cells = row.get("cells") or []
        data = (react.get("codes") or [])[row["index"]] if alignment == "aligned" else None
        if len(cells) != len(EXPECTED_HEADERS):
            codes.append({"index": row["index"], "code": cells[0] if cells else None, "status": "unknown",
                          "signals": {}, "duplicate": False, "note": "row does not have five cells"})
            continue
        icon = toggle_icon(row.get("buttons") or [])
        status, signals = row_status(icon, bool(row.get("greyed")), (data or {}).get("active"))
        codes.append({
            "index": row["index"],
            "code": cells[0],
            "amount_off": _amount(cells[1]),
            "percent_off": _amount(cells[2]),
            "redemptions": _redemptions(cells[3]),
            "status": status,
            "signals": signals,
            "duplicate": folded.get(cells[0].casefold(), 0) > 1,
        })
    duplicates = sorted({c["code"] for c in codes if c.get("duplicate") and c.get("code")},
                        key=lambda code: (code.casefold(), code))
    return {"codes": codes, "duplicates": duplicates, "react_data": alignment, "react": react}


# --- locate-pause --------------------------------------------------------------------

def _check(result, detail: str) -> dict:
    return {"result": result, "detail": detail}


def locate_toggle(row: dict, data: dict | None, alignment: str) -> dict:
    """Identify the pause/resume toggle in one row with four independent checks."""
    buttons = row.get("buttons") or []
    greyed = bool(row.get("greyed"))
    react_active = (data or {}).get("active") if alignment == "aligned" else None
    icon = toggle_icon(buttons)
    status, signals = row_status(icon, greyed, react_active)
    report = {"status": status, "signals": signals, "button_count": len(buttons), "target_position": None,
              "buttons": [], "checks": {}, "confidence": "none"}
    for button in buttons:
        kind, basis = button_kind(button)
        report["buttons"].append({
            "position": button.get("position"),
            "icon": classify_icon(button.get("svg")),
            "handler": classify_handler(button.get("handler")) or "unavailable",
            "kind": kind,
            "basis": basis,
        })
    if len(buttons) != 3:
        report["reason"] = f"Actions cell has {len(buttons)} buttons; expected exactly 3"
        return report
    candidates = [i for i, b in enumerate(report["buttons"]) if b["icon"] in ("pause", "play")]
    if len(candidates) != 1:
        report["reason"] = "could not single out one pause/resume icon among the three buttons"
        return report
    target = candidates[0]
    report["target_position"] = target
    mine = report["buttons"][target]
    others = [b for i, b in enumerate(report["buttons"]) if i != target]
    wanted_icon = "play" if status == "paused" else "pause"
    checks = report["checks"]
    checks["E1_icon"] = _check(
        mine["icon"] == wanted_icon,
        f"icon geometry is {mine['icon']} (expected {wanted_icon}: "
        + ("two vertical bars" if wanted_icon == "pause" else "right-pointing triangle") + ")",
    )
    if mine["handler"] == "unavailable":
        checks["E2_handler"] = _check(None, "onClick source unavailable")
    else:
        checks["E2_handler"] = _check(
            mine["handler"] == "toggle",
            "onClick toggles active and reports Paused" if mine["handler"] == "toggle"
            else f"onClick looks like {mine['handler']}",
        )
    other_kinds = sorted(b["kind"] for b in others)
    checks["E3_exclusive"] = _check(
        other_kinds == ["copy", "delete"],
        "other buttons are " + " and ".join(f"{b['kind']} ({b['basis']})" for b in others),
    )
    if status == "active":
        if react_active is True:
            checks["E4_state"] = _check(True, "row not greyed and React data active=true (index-aligned)")
        else:
            checks["E4_state"] = _check(None, f"row not greyed; React active unavailable ({alignment})")
    else:
        checks["E4_state"] = _check(
            False, "row is paused, so this toggle would resume the code" if status == "paused"
            else "status signals disagree"
        )
    hard = [checks["E1_icon"]["result"], checks["E3_exclusive"]["result"]]
    soft = [checks["E2_handler"]["result"], checks["E4_state"]["result"]]
    if status == "active":
        if all(hard) and all(value is True for value in soft):
            report["confidence"] = "high"
        elif all(hard) and all(value is not False for value in soft):
            report["confidence"] = "medium"
    elif status == "paused":
        # Identification of the (resume) toggle only; E4 fails by definition.
        if all(hard) and checks["E2_handler"]["result"] is True:
            report["confidence"] = "high"
        elif all(hard) and checks["E2_handler"]["result"] is None:
            report["confidence"] = "medium"
    return report


def verdict_for(report: dict) -> str:
    if report["status"] == "paused":
        return "already_paused"
    if report["status"] == "active" and report["confidence"] in ("high", "medium"):
        return "ready_to_pause"
    return "not_ready"


def find_unique_row(rows: list[dict], code: str) -> dict:
    wanted = (code or "").strip().casefold()
    matches = [row for row in rows if row.get("cells") and row["cells"][0].casefold() == wanted]
    if not matches:
        raise MavenError("promo code was not found in the Promo codes table")
    if len(matches) > 1:
        raise MavenError(f"promo code is not unique: {len(matches)} rows match case-insensitively")
    return matches[0]


def annotate_png(png: bytes, row_box: dict | None, button_box: dict | None, label: str) -> bytes:
    """Draw a box around the target button on the row screenshot (no DOM changes)."""
    from PIL import Image, ImageDraw

    image = Image.open(io.BytesIO(png)).convert("RGB")
    pad, strip = 16, 30
    canvas = Image.new("RGB", (image.width + 2 * pad, image.height + 2 * pad + strip), "white")
    canvas.paste(image, (pad, pad))
    draw = ImageDraw.Draw(canvas)
    if row_box and button_box and row_box.get("width"):
        scale = image.width / row_box["width"]
        x0 = (button_box["x"] - row_box["x"]) * scale + pad - 4
        y0 = (button_box["y"] - row_box["y"]) * scale + pad - 4
        x1 = x0 + button_box["width"] * scale + 8
        y1 = y0 + button_box["height"] * scale + 8
        draw.rectangle([x0, y0, x1, y1], outline=(220, 0, 0), width=3)
    draw.text((pad, image.height + 2 * pad + 8), label, fill=(220, 0, 0))
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".promo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


# --- page orchestration --------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(state: dict | None) -> tuple:
    if not state or state.get("tables") != 1:
        return (None,)
    rows = state.get("rows") or []
    return (len(rows), tuple(tuple(r.get("cells") or []) for r in rows),
            tuple(bool(r.get("greyed")) for r in rows), bool((state.get("react") or {}).get("available")))


def read_settings(reader: PromoReader, admin_url: str) -> tuple[str, dict]:
    from maven_skill.ops import _goto

    url = settings_url(admin_url)
    _goto(reader, url)
    if canonical_url(reader.url) != canonical_url(url):
        raise MavenError("Settings page redirected away from the course settings")
    try:
        reader.wait_for_function(SETTINGS_READY_JS, timeout=45000)
    except MavenError:
        raise
    except Exception:
        raise MavenError("Promo codes table did not load on the Settings page") from None
    reader.wait_for_timeout(2000)
    state = None
    started = time.monotonic()
    for _ in range(8):
        try:
            current = reader.evaluate(PROMO_TABLE_JS)
        except MavenError:
            raise
        except Exception:
            raise MavenError("Promo codes table could not be read") from None
        if state is not None and _signature(current) == _signature(state):
            state = current
            break
        state = current
        if time.monotonic() - started > 15:
            break
        reader.wait_for_timeout(1000)
    return url, state


def resolve_admin_url(page, course: str, allow_discovery: bool) -> str:
    admin_url, slug = parse_course_ref(course)
    if admin_url:
        validate_url(admin_url)
        return admin_url
    if not allow_discovery:
        raise MavenError("locate-pause needs the course admin URL or <school>/<course>, not a bare slug")
    from maven_skill.ops import _collect_course_links, _courses_href, _dashboard_href, _goto

    dashboard = _dashboard_href(page)
    courses_url = _courses_href(page, dashboard)
    _goto(page, courses_url)
    courses, _ = _collect_course_links(page)
    found = course_from_list(courses, slug)
    admin_url, _ = parse_course_ref(found)
    return admin_url


def list_promo_codes(page, course: str) -> dict:
    admin_url = resolve_admin_url(page, course, allow_discovery=True)
    reader = PromoReader(page)
    url, state = read_settings(reader, admin_url)
    parsed = parse_promo_table(state)
    codes = parsed["codes"]
    result = {
        "command": "promo-codes list",
        "source": "browser",
        "course": admin_url,
        "settings_url": url,
        "codes": codes,
        "count": len(codes),
        "counts": {status: sum(1 for c in codes if c["status"] == status)
                   for status in ("active", "paused", "unknown")},
        "duplicates": parsed["duplicates"],
        "react_data": parsed["react_data"],
        "notes": [
            "status combines the toggle icon geometry, the greyed row class, and (when readable) "
            "the page's React data matched by row index; any disagreement reports unknown",
            "Maven allows duplicate code strings; pair data by row, never by code text",
            "redemptions shown as '-' on the page are reported as 0",
        ],
        "observed_at": _now(),
    }
    assert_public_output(result)
    return result


def public_check(reader: PromoReader, link: str) -> dict:
    try:
        with reader.cookieless() as public:
            public.goto(link, wait_until="domcontentloaded", timeout=30000)
            state = {"struck": [], "prices": []}
            started = time.monotonic()
            while time.monotonic() - started < 15:
                public.wait_for_timeout(1000)
                state = public.evaluate(PUBLIC_PRICE_JS) or state
                if state.get("struck") or (state.get("prices") and time.monotonic() - started >= 8):
                    break
    except MavenError:
        raise
    except Exception:
        return {"url": link, "checked": False, "has_struck_price": None, "struck_prices": [], "prices": []}
    return {
        "url": link,
        "checked": True,
        "has_struck_price": bool(state.get("struck")),
        "struck_prices": state.get("struck") or [],
        "prices": state.get("prices") or [],
    }


def locate_pause(page, course: str, code: str, output_dir: Path) -> dict:
    if not code or not code.strip():
        raise MavenError("--code is required")
    admin_url = resolve_admin_url(page, course, allow_discovery=False)
    reader = PromoReader(page)
    url, state = read_settings(reader, admin_url)
    parsed = parse_promo_table(state)
    rows = state.get("rows") or []
    row = find_unique_row(rows, code)
    entry = parsed["codes"][row["index"]]
    data = None
    if parsed["react_data"] == "aligned":
        data = (parsed["react"].get("codes") or [])[row["index"]]
    report = locate_toggle(row, data, parsed["react_data"])
    verdict = verdict_for(report)

    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    capture = reader.capture_row(row["index"], row["cells"][0])
    target = report["target_position"]
    button_box = capture["button_boxes"][target] if target is not None and target < len(capture["button_boxes"]) else None
    label = {
        "ready_to_pause": "boxed: PAUSE toggle (one click pauses immediately, no confirmation)",
        "already_paused": "boxed: RESUME toggle (code is already paused; clicking would reactivate it)",
        "not_ready": "not identified with enough confidence; nothing boxed reliably",
    }[verdict]
    row_png = directory / "row.png"
    annotated = directory / "annotated.png"
    private_bytes(row_png, capture["png"])
    private_bytes(annotated, annotate_png(capture["png"], capture["row_box"],
                                          button_box if verdict != "not_ready" else None, label))

    link = public_link(admin_url, row["cells"][0], (parsed["react"] or {}).get("share_slug"))
    baseline = public_check(reader, link)

    summary = {
        "command": "promo-codes locate-pause",
        "source": "browser",
        "course": admin_url,
        "settings_url": url,
        "code": row["cells"][0],
        "row_index": row["index"],
        "verdict": verdict,
        "confidence": report["confidence"],
        "status": report["status"],
        "signals": report["signals"],
        "amount_off": entry.get("amount_off"),
        "percent_off": entry.get("percent_off"),
        "redemptions": entry.get("redemptions"),
        "button_count": report["button_count"],
        "target_position": target,
        "buttons": report["buttons"],
        "checks": report["checks"],
        "reason": report.get("reason"),
        "react_data": parsed["react_data"],
        "public_link": baseline,
        "artifacts": {
            "row_screenshot": _display(row_png),
            "annotated": _display(annotated),
            "evidence": _display(directory / "evidence.json"),
        },
        "notes": [
            "this command never clicks; the toggle pauses or resumes on a single click without "
            "confirmation, so a retry after an unclear result can reactivate the code",
            "after pausing, the public ?promoCode= link should stop showing a struck-through price",
        ],
        "observed_at": _now(),
    }
    evidence = summary | {
        "row_cells": row["cells"],
        "row_class": row.get("row_class"),
        "row_html": row.get("html"),
        "button_evidence": [
            {
                "position": b.get("position"),
                "class": b.get("class"),
                "aria_label": b.get("aria_label"),
                "title": b.get("title"),
                "data_attributes": b.get("data_attributes"),
                "svg": b.get("svg"),
                "handler_excerpt": (b.get("handler") or "")[:1500] or None,
                "box": capture["button_boxes"][i] if i < len(capture["button_boxes"]) else None,
            }
            for i, b in enumerate(row.get("buttons") or [])
        ],
        "known_icon_prefixes": {"pause": PAUSE_ICON_PREFIX, "play": PLAY_ICON_PREFIX},
        "react_row": data,
        "row_box": capture["row_box"],
    }
    private_bytes(directory / "evidence.json",
                  json.dumps(evidence, ensure_ascii=False, indent=2).encode())
    assert_public_output(summary)
    return summary


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


# --- text rendering ------------------------------------------------------------------

def render_list(result: dict) -> str:
    rows = [("CODE", "AMOUNT_OFF", "PERCENT_OFF", "REDEMPTIONS", "STATUS", "DUP")]
    for c in result["codes"]:
        rows.append((c.get("code") or "?", c.get("amount_off") or "-", c.get("percent_off") or "-",
                     "?" if c.get("redemptions") is None else str(c["redemptions"]),
                     c["status"], "dup" if c.get("duplicate") else ""))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = [f"course: {result['course']}"]
    lines += ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)).rstrip() for r in rows]
    counts = result["counts"]
    lines.append(f"{result['count']} codes: {counts['active']} active, {counts['paused']} paused, "
                 f"{counts['unknown']} unknown; react data: {result['react_data']}")
    if result["duplicates"]:
        lines.append("duplicate codes (case-insensitive): " + ", ".join(result["duplicates"]))
    return "\n".join(lines)


def render_locate(result: dict) -> str:
    lines = [
        f"VERDICT: {result['verdict']}  confidence={result['confidence']}  status={result['status']}",
        f"code: {result['code']}  row={result['row_index']}  redemptions={result['redemptions']}  "
        f"amount_off={result['amount_off'] or '-'}  percent_off={result['percent_off'] or '-'}",
        f"target button position: {result['target_position']} of {result['button_count']} (0-based, for reference only)",
    ]
    for name, check in result["checks"].items():
        mark = {True: "pass", False: "FAIL", None: "unavailable"}[check["result"]]
        lines.append(f"  {name}: {mark} - {check['detail']}")
    if result.get("reason"):
        lines.append(f"reason: {result['reason']}")
    public = result["public_link"]
    lines.append(f"public link: {public['url']}  struck price: {public['has_struck_price']}  "
                 f"{' '.join(public['struck_prices'])}")
    for key, value in result["artifacts"].items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
