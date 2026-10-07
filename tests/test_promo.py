import io
import itertools
import json
import re
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from maven_skill import promo
from maven_skill.errors import MavenError
from maven_skill.promo import (
    PROMO_SCRIPTS,
    PROMO_TABLE_JS,
    PUBLIC_PRICE_JS,
    SETTINGS_READY_JS,
    PromoReader,
    annotate_png,
    button_kind,
    check_table,
    classify_handler,
    classify_icon,
    course_from_list,
    find_unique_row,
    list_promo_codes,
    locate_pause,
    locate_toggle,
    parse_course_ref,
    parse_promo_table,
    public_link,
    render_list,
    render_locate,
    svg_subpaths,
    verdict_for,
)


ADMIN = "https://maven.com/acme/admin/courses/demo-course"
SETTINGS = ADMIN + "/settings"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
HEADERS = ["Code", "Amount off", "Percent off", "Redemptions", "Actions"]

# Icon geometry as rendered by the Maven admin UI (UI assets, not business data).
PAUSE_D = (
    "M3.60002 12.9V3.1H5.65002V12.9H3.60002ZM3.50002 1.9C2.89251 1.9 2.40002 2.39249 2.40002 3V13C2.40002 "
    "13.6075 2.89251 14.1 3.50002 14.1H5.75002C6.35754 14.1 6.85002 13.6075 6.85002 13V3C6.85002 2.39249 "
    "6.35754 1.9 5.75002 1.9H3.50002ZM10.35 12.9V3.1H12.4V12.9H10.35ZM10.25 1.9C9.64251 1.9 9.15002 2.39249 "
    "9.15002 3V13C9.15002 13.6075 9.64251 14.1 10.25 14.1H12.5C13.1075 14.1 13.6 13.6075 13.6 13V3C13.6 "
    "2.39249 13.1075 1.9 12.5 1.9H10.25Z"
)
PLAY_D = (
    "M4.46448 1.53974C4.63542 1.44446 4.82869 1.39652 5.02435 1.40084C5.21955 1.40516 5.41008 1.46136 "
    "5.57637 1.56365C5.57675 1.56389 5.57714 1.56412 5.57752 1.56436L14.5662 7.06128C14.7278 7.15787 14.8617 "
    "7.29455 14.955 7.4581C15.0492 7.62319 15.0987 7.80997 15.0987 8.00002C15.0987 8.19008 15.0492 8.37686 "
    "14.955 8.54195C14.8617 8.7055 14.7278 8.84217 14.5662 8.93877L5.57752 14.4357C5.57714 14.4359 5.57677 "
    "14.4362 5.57639 14.4364C5.41009 14.5387 5.21956 14.5949 5.02435 14.5992C4.82869 14.6035 4.63542 14.5556 "
    "4.46448 14.4603C4.29354 14.365 4.15111 14.2259 4.05189 14.0572C3.95266 13.8885 3.90024 13.6964 3.90002 "
    "13.5007L3.90002 2.50002C3.90024 2.30432 3.95266 2.11156 4.05189 1.94287C4.15111 1.77419 4.29354 1.63502 "
    "4.46448 1.53974ZM14.2563 7.57502L13.9434 8.08663C13.9458 8.08835 13.9483 8.08996 13.9509 8.09148L14.2563 "
    "7.57502ZM13.8012 8.00002L5.10002 2.67895V13.3211L13.8012 8.00002Z"
)
LINK_DS = [
    "M11.4696 6.6967L13.3257 4.84054C13.7087 4.45721 14.1635 4.15308 14.664 3.94555C15.1645 3.73801 15.7011 "
    "3.63112 16.2429 3.631L16.5077 13.3258C16.1247 13.7089 15.6699 14.0127 15.1695 14.22",
    "M12.5302 17.3033L10.674 19.1595C10.2911 19.5428 9.8363 19.8469 9.33576 20.0544C8.83521 20.262 8.29868 "
    "20.3689 7.75682 20.369L13.3257 10.6742",
]
TRASH_DS = [
    "M13.4998 3.5L2.49976 3.50001",
    "M6.5 6.5V10.5",
    "M9.5 6.5V10.5",
    "M12.5 3.5V13C12.5 13.1326 12.4473 13.2598 12.3536 13.3536C12.2598 13.4473 12.1326 13.5 12 13.5H4C3.86739 "
    "13.5 3.74021 13.4473 3.64645 13.3536C3.55268 13.2598 3.5 13.1326 3.5 13V3.5",
    "M10.5 3.5V2.5C10.5 2.23478 10.3946 1.98043 10.2071 1.79289C10.0196 1.60536 9.76522 1.5 9.5 1.5H6.5C6.23478 "
    "1.5 5.98043 1.60536 5.79289 1.79289C5.60536 1.98043 5.5 2.23478 5.5 2.5V3.5",
]

# Synthetic handler sources shaped like the minified admin bundle.
TOGGLE_SRC = ('()=>((e,t)=>{let r={...e,active:t},a=M.mutateAsync(r);(0,o.vX)(a,{success:"".concat('
              't?"Restarted":"Paused"," ").concat(e.code)})})(e,!e.active)')
COPY_SRC = "()=>{(0,g.l)(t),k.track(u.XN.adminPromoCodeCopy,{...e})}"
DELETE_SRC = ('()=>(e=>{confirm("".concat("Are you sure you want to delete"," ").concat(e.code,"?"))'
              '&&I.mutateAsync(e.id)})(e)')


def pause_svg():
    return {"view_box": "0 0 16 16", "paths": [{"d": PAUSE_D, "fill_rule": "evenodd", "stroke": None, "fill": "currentColor"}]}


def play_svg():
    return {"view_box": "0 0 16 16", "paths": [{"d": PLAY_D, "fill_rule": "evenodd", "stroke": None, "fill": "#0D0D0C"}]}


def link_svg():
    return {"view_box": "0 0 24 24", "paths": [{"d": d, "fill_rule": None, "stroke": "currentColor", "fill": None} for d in LINK_DS]}


def trash_svg():
    return {"view_box": "0 0 16 16", "paths": [{"d": d, "fill_rule": None, "stroke": "currentColor", "fill": None} for d in TRASH_DS]}


def buttons(active=True, handlers=True):
    return [
        {"position": 0, "class": "", "svg": link_svg(), "handler": COPY_SRC if handlers else None},
        {"position": 1, "class": "pl-1", "svg": pause_svg() if active else play_svg(),
         "handler": TOGGLE_SRC if handlers else None},
        {"position": 2, "class": "", "svg": trash_svg(), "handler": DELETE_SRC if handlers else None},
    ]


def row(index, code, amount="-", percent="-", redemptions="-", active=True, handlers=True, greyed=None):
    greyed = (not active) if greyed is None else greyed
    return {
        "index": index,
        "cells": [code, amount, percent, redemptions, ""],
        "row_class": "text-gray-400" if greyed else "",
        "greyed": greyed,
        "html": f"<tr><td>{code}</td></tr>",
        "buttons": buttons(active, handlers),
    }


def table_state(rows=None, react=True, react_codes=None):
    rows = rows if rows is not None else [
        row(0, "FRIENDS50", amount="$100", redemptions="12"),
        row(1, "SPRING25", percent="25%", redemptions="1,204", active=False),
        row(2, "demo-pass", amount="$100"),
        row(3, "DEMO-PASS", amount="$100", active=False),
    ]
    state = {"tables": 1, "headers": list(HEADERS), "rows": rows}
    if react:
        codes = react_codes if react_codes is not None else [
            {"code": r["cells"][0], "active": not r["greyed"], "valid": True, "amount_off": None,
             "percent_off": None, "redemptions": None, "currency": "usd"} for r in rows
        ]
        state["react"] = {"available": True, "share_slug": None, "codes": codes}
    else:
        state["react"] = {"available": False, "reason": "promoCodes prop not found"}
    return state


# --- course reference ----------------------------------------------------------------

@pytest.mark.parametrize("value", [ADMIN, ADMIN + "/", SETTINGS + "?cohort=42", "acme/demo-course"])
def test_course_ref_normalizes_to_admin_url(value):
    assert parse_course_ref(value) == (ADMIN, None)


def test_course_ref_bare_slug_needs_discovery():
    assert parse_course_ref("demo-course") == (None, "demo-course")


@pytest.mark.parametrize("value", [
    "http://maven.com/acme/admin/courses/demo-course",
    "https://example.com/acme/admin/courses/demo-course",
    "https://maven.com/acme/demo-course",
    "acme/demo/course",
    "demo course",
    "",
])
def test_course_ref_rejects_other_values(value):
    with pytest.raises(MavenError):
        parse_course_ref(value)


def test_course_from_list_requires_one_match():
    courses = [{"url": ADMIN, "title": "Demo"}, {"url": "https://maven.com/acme/admin/courses/other", "title": "x"}]
    assert course_from_list(courses, "demo-course") == ADMIN
    with pytest.raises(MavenError):
        course_from_list(courses, "missing")
    with pytest.raises(MavenError):
        course_from_list(courses + [{"url": "https://maven.com/beta/admin/courses/demo-course"}], "demo-course")


def test_public_link_uses_landing_page_and_share_slug():
    assert public_link(ADMIN, "FRIENDS50") == "https://maven.com/acme/demo-course?promoCode=FRIENDS50"
    assert public_link(ADMIN, "FRIENDS50", "demo-landing") == "https://maven.com/acme/demo-landing?promoCode=FRIENDS50"
    assert public_link(ADMIN, "A&B") == "https://maven.com/acme/demo-course?promoCode=A%26B"
    assert public_link(ADMIN, "X", "../evil") == "https://maven.com/acme/demo-course?promoCode=X"


# --- icon geometry -------------------------------------------------------------------

def test_svg_subpaths_traces_straight_segments():
    subs = svg_subpaths("M1 2H3V5L1 2ZM0 0C1 1 2 2 3 3Z")
    assert subs[0]["points"] == [(1, 2), (3, 2), (3, 5), (1, 2)] and not subs[0]["curved"] and subs[0]["closed"]
    assert subs[1]["curved"]


@pytest.mark.parametrize("svg,kind", [
    (pause_svg(), "pause"),
    (play_svg(), "play"),
    (link_svg(), "link"),
    (trash_svg(), "trash"),
    (None, "unknown"),
    ({"view_box": "0 0 16 16", "paths": []}, "unknown"),
    ({"view_box": "0 0 24 24", "paths": pause_svg()["paths"]}, "unknown"),
    ({"view_box": "0 0 16 16", "paths": [{"d": "M3.6 12.9V3.1H5.65V12.9H3.6Z", "fill_rule": "evenodd"}]}, "unknown"),
    ({"view_box": "0 0 16 16", "paths": [{"d": "M3 3H13V5H3Z", "fill_rule": "evenodd"}]}, "unknown"),
    ({"view_box": "0 0 16 16", "paths": [{"d": "M3 8L12 3V13L3 8Z", "fill_rule": "evenodd"}]}, "unknown"),
])
def test_classify_icon(svg, kind):
    assert classify_icon(svg) == kind


# --- handler source ------------------------------------------------------------------

@pytest.mark.parametrize("source,kind", [
    (TOGGLE_SRC, "toggle"),
    (TOGGLE_SRC.replace('"', "'"), "toggle"),
    (COPY_SRC, "copy"),
    (DELETE_SRC, "delete"),
    (TOGGLE_SRC.replace("!e.active", "e.active"), "unknown"),
    (TOGGLE_SRC.replace('"Paused"', '"Stopped"'), "unknown"),
    ("()=>{}", "unknown"),
    (None, None),
    ("", None),
])
def test_classify_handler(source, kind):
    assert classify_handler(source) == kind


def test_button_kind_prefers_handler_and_flags_conflicts():
    assert button_kind({"svg": pause_svg(), "handler": TOGGLE_SRC}) == ("toggle", "handler")
    assert button_kind({"svg": trash_svg(), "handler": None}) == ("delete", "geometry")
    assert button_kind({"svg": pause_svg(), "handler": DELETE_SRC}) == ("conflict", "handler+geometry")
    assert button_kind({"svg": None, "handler": COPY_SRC}) == ("copy", "handler")


# --- table parsing -------------------------------------------------------------------

def test_parse_table_reports_status_amounts_and_duplicates():
    parsed = parse_promo_table(table_state())
    codes = parsed["codes"]
    assert [c["status"] for c in codes] == ["active", "paused", "active", "paused"]
    assert (codes[0]["amount_off"], codes[0]["percent_off"], codes[0]["redemptions"]) == ("$100", None, 12)
    assert (codes[1]["amount_off"], codes[1]["percent_off"], codes[1]["redemptions"]) == (None, "25%", 1204)
    assert codes[2]["redemptions"] == 0
    assert [c["duplicate"] for c in codes] == [False, False, True, True]
    assert parsed["duplicates"] == ["DEMO-PASS", "demo-pass"]
    assert parsed["react_data"] == "aligned"
    assert codes[1]["signals"] == {"icon": "paused", "row_greyed": "paused", "react_active": "paused"}


def test_status_is_unknown_when_signals_disagree():
    rows = [row(0, "FRIENDS50", greyed=True), row(1, "SPRING25")]
    react = [{"code": "FRIENDS50", "active": True}, {"code": "SPRING25", "active": False}]
    codes = parse_promo_table(table_state(rows, react_codes=react))["codes"]
    assert [c["status"] for c in codes] == ["unknown", "unknown"]


def test_react_data_is_optional_and_paired_by_row():
    rows = [row(0, "FRIENDS50"), row(1, "SPRING25", active=False)]
    parsed = parse_promo_table(table_state(rows, react=False))
    assert parsed["react_data"] == "unavailable"
    assert [c["status"] for c in parsed["codes"]] == ["active", "paused"]
    assert parsed["codes"][0]["signals"]["react_active"] is None
    swapped = [{"code": "SPRING25", "active": False}, {"code": "FRIENDS50", "active": True}]
    parsed = parse_promo_table(table_state(rows, react_codes=swapped))
    assert parsed["react_data"] == "misaligned"
    assert [c["status"] for c in parsed["codes"]] == ["active", "paused"]
    parsed = parse_promo_table(table_state(rows, react_codes=swapped[:1]))
    assert parsed["react_data"] == "misaligned"


def test_status_unknown_without_a_single_toggle_icon():
    broken = row(0, "FRIENDS50")
    broken["buttons"][1]["svg"] = trash_svg()
    assert parse_promo_table(table_state([broken], react=False))["codes"][0]["status"] == "unknown"


@pytest.mark.parametrize("state", [
    None,
    {"tables": 0},
    {"tables": 2},
    {"tables": 1, "headers": ["Code", "Amount", "Percent off", "Redemptions", "Actions"], "rows": []},
])
def test_check_table_refuses_unexpected_layouts(state):
    with pytest.raises(MavenError):
        check_table(state)


def test_find_unique_row_is_case_insensitive_and_strict():
    rows = table_state()["rows"]
    assert find_unique_row(rows, "friends50")["index"] == 0
    with pytest.raises(MavenError, match="not found"):
        find_unique_row(rows, "MISSING")
    with pytest.raises(MavenError, match="not unique"):
        find_unique_row(rows, "Demo-Pass")


# --- locate-pause checks -------------------------------------------------------------

def locate(r, active=True, alignment="aligned"):
    data = {"code": r["cells"][0], "active": active}
    report = locate_toggle(r, data, alignment)
    return report, verdict_for(report)


def test_all_four_checks_give_high_confidence():
    report, verdict = locate(row(0, "FRIENDS50"))
    assert (verdict, report["confidence"], report["target_position"]) == ("ready_to_pause", "high", 1)
    assert all(check["result"] is True for check in report["checks"].values())


def test_missing_handler_source_gives_medium_confidence():
    report, verdict = locate(row(0, "FRIENDS50", handlers=False), alignment="unavailable")
    assert (verdict, report["confidence"]) == ("ready_to_pause", "medium")
    assert report["checks"]["E2_handler"]["result"] is None
    assert [b["basis"] for b in report["buttons"]] == ["geometry"] * 3


def test_identification_does_not_rely_on_position():
    r = row(0, "FRIENDS50")
    r["buttons"] = [r["buttons"][1], r["buttons"][0], r["buttons"][2]]
    report, verdict = locate(r)
    assert verdict == "ready_to_pause" and report["target_position"] == 0


def test_wrong_handler_on_toggle_gives_no_confidence():
    r = row(0, "FRIENDS50")
    r["buttons"][1]["handler"] = DELETE_SRC
    report, verdict = locate(r)
    assert (verdict, report["confidence"]) == ("not_ready", "none")
    assert report["checks"]["E2_handler"]["result"] is False


def test_other_buttons_must_be_copy_and_delete():
    r = row(0, "FRIENDS50")
    r["buttons"][2]["handler"] = COPY_SRC
    r["buttons"][2]["svg"] = link_svg()
    report, verdict = locate(r)
    assert verdict == "not_ready" and report["checks"]["E3_exclusive"]["result"] is False


def test_button_count_must_be_three():
    r = row(0, "FRIENDS50")
    r["buttons"] = r["buttons"][:2]
    report, verdict = locate(r)
    assert verdict == "not_ready" and "expected exactly 3" in report["reason"]
    assert report["target_position"] is None


def test_paused_code_reports_already_paused():
    report, verdict = locate(row(0, "SPRING25", active=False), active=False)
    assert verdict == "already_paused"
    assert report["confidence"] == "high"
    assert report["checks"]["E1_icon"]["result"] is True
    assert report["checks"]["E4_state"]["result"] is False


def test_conflicting_state_is_not_ready():
    report, verdict = locate(row(0, "FRIENDS50"), active=False)
    assert report["status"] == "unknown" and verdict == "not_ready"


# --- annotation ----------------------------------------------------------------------

def png_bytes(width=400, height=40):
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def test_annotation_boxes_the_button_at_device_scale():
    row_box = {"x": 100, "y": 50, "width": 200, "height": 20}
    button_box = {"x": 250, "y": 52, "width": 10, "height": 10}
    image = Image.open(io.BytesIO(annotate_png(png_bytes(400, 40), row_box, button_box, "boxed")))
    pad = 16
    # 2x device scale: button starts at (250-100)*2 = 300 px; outline sits 4 px outside it.
    assert image.getpixel((pad + 300 - 4, pad + 4 + 5)) == (220, 0, 0)
    assert image.getpixel((pad + 10, pad + 10)) == (255, 255, 255)
    plain = Image.open(io.BytesIO(annotate_png(png_bytes(400, 40), row_box, None, "nothing")))
    assert plain.getpixel((pad + 300 - 4, pad + 4 + 5)) == (255, 255, 255)


# --- page facade ---------------------------------------------------------------------

class FakeLocator:
    """Locator stand-in that records methods; it has no click, hover, or fill."""

    def __init__(self, page, path):
        self.page = page
        self.path = path

    def _record(self, name):
        self.page.calls.append(("locator", name, self.path))

    def filter(self, **kwargs):
        self._record("filter")
        return FakeLocator(self.page, self.path + ".filter")

    def locator(self, selector, **kwargs):
        self._record("locator")
        return FakeLocator(self.page, self.path + f">{selector}")

    @property
    def first(self):
        return FakeLocator(self.page, self.path + ".first")

    @property
    def last(self):
        return FakeLocator(self.page, self.path + ".last")

    def nth(self, index):
        return FakeLocator(self.page, self.path + f".nth({index})")

    def count(self):
        self._record("count")
        return 3 if self.path.endswith(">button") else 1

    def inner_text(self, **kwargs):
        self._record("inner_text")
        return self.page.row_code

    def scroll_into_view_if_needed(self, **kwargs):
        self._record("scroll_into_view_if_needed")

    def screenshot(self, **kwargs):
        self._record("screenshot")
        return png_bytes(400, 40)

    def bounding_box(self):
        self._record("bounding_box")
        match = re.search(r">button\.nth\((\d)\)$", self.path)
        if match:
            return {"x": 230 + 20 * int(match.group(1)), "y": 52, "width": 16, "height": 16}
        return {"x": 100, "y": 50, "width": 200, "height": 20}


class FakeContext:
    def __init__(self, browser):
        self.browser = browser
        self.closed = False

    def new_page(self):
        page = FakePage(public=self.browser.public_state)
        self.browser.public_pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, public_state):
        self.public_state = public_state
        self.contexts = []
        self.public_pages = []

    def new_context(self, **kwargs):
        assert kwargs == {}
        context = FakeContext(self)
        self.contexts.append(context)
        return context


class FakePage:
    def __init__(self, table=None, public=None, row_code="FRIENDS50"):
        self.url = "about:blank"
        self.calls = []
        self.table = table
        self.row_code = row_code
        self.public = public if public is not None else {"struck": ["$1,000"], "prices": ["$1,000", "$900"]}
        self.context = FakeContext(FakeBrowser(self.public))

    def goto(self, url, **kwargs):
        self.calls.append(("goto", url))
        self.url = url + ("?cohort=42" if url.endswith("/settings") else "")

    def evaluate(self, script, *args):
        self.calls.append(("evaluate", script))
        if script == PROMO_TABLE_JS:
            return self.table
        if script == PUBLIC_PRICE_JS:
            return self.public
        return None

    def wait_for_function(self, script, **kwargs):
        self.calls.append(("wait_for_function", script))
        return True

    def wait_for_timeout(self, timeout):
        self.calls.append(("wait_for_timeout", timeout))

    def locator(self, selector, **kwargs):
        self.calls.append(("locator", "root", selector))
        return FakeLocator(self, selector)

    def click(self, *args, **kwargs):
        self.calls.append(("click", args))

    def hover(self, *args, **kwargs):
        self.calls.append(("hover", args))

    def fill(self, *args, **kwargs):
        self.calls.append(("fill", args))

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fast_clock(monkeypatch):
    ticks = itertools.count(0, 3)
    monkeypatch.setattr(promo, "time", SimpleNamespace(monotonic=lambda: next(ticks)))


@pytest.mark.parametrize("name", [
    "click", "dblclick", "hover", "fill", "type", "press", "check", "tap", "focus", "dispatch_event",
    "keyboard", "mouse", "locator", "get_by_role", "get_by_text", "query_selector", "set_input_files",
])
def test_promo_reader_has_no_interaction_surface(name):
    page = FakePage()
    reader = PromoReader(page)
    with pytest.raises(MavenError, match="read-only"):
        getattr(reader, name)
    assert page.calls == []


def test_promo_reader_only_runs_registered_scripts_and_maven_urls():
    page = FakePage(table_state())
    reader = PromoReader(page)
    assert reader.evaluate(PROMO_TABLE_JS)["tables"] == 1
    with pytest.raises(MavenError, match="registered"):
        reader.evaluate("() => document.querySelector('button').click()")
    with pytest.raises(MavenError, match="registered"):
        reader.wait_for_function("() => true")
    with pytest.raises(ValueError):
        reader.goto("https://example.com/")


WRITE_PATTERNS = re.compile(
    r"\.click\(|dispatchEvent|\.submit\(|\.focus\(|\.value\s*=[^=]|innerHTML\s*=|textContent\s*=[^=]|"
    r"fetch\(|XMLHttpRequest|sendBeacon|setAttribute|removeAttribute|\.remove\(|localStorage|sessionStorage|"
    r"confirm\(|\.onClick\(",
)


def test_registered_scripts_are_read_only():
    assert PROMO_SCRIPTS == {SETTINGS_READY_JS, PROMO_TABLE_JS, PUBLIC_PRICE_JS}
    for script in PROMO_SCRIPTS:
        assert not WRITE_PATTERNS.search(script), script[:60]


def test_promo_module_has_no_interaction_calls():
    source = Path(promo.__file__).read_text()
    for pattern in (r"\.click\(", r"\.dblclick\(", r"\.hover\(", r"\.fill\(", r"\.type\(", r"\.press\(",
                    r"\.check\(", r"\.tap\(", r"dispatch_event", r"\.keyboard", r"\.mouse",
                    r"set_checked", r"select_option", r"_guarded_click"):
        assert not re.search(pattern, source), pattern


def assert_no_interaction(page):
    assert not [call for call in page.calls if call[0] in ("click", "hover", "fill")]
    allowed = {"root", "filter", "locator", "count", "inner_text", "scroll_into_view_if_needed",
               "screenshot", "bounding_box"}
    assert {call[1] for call in page.calls if call[0] == "locator"} <= allowed


# --- command orchestration -----------------------------------------------------------

def test_list_reads_settings_without_interaction():
    page = FakePage(table_state())
    result = list_promo_codes(page, ADMIN + "/settings?cohort=42")
    assert result["command"] == "promo-codes list"
    assert result["settings_url"] == SETTINGS
    assert result["count"] == 4
    assert result["counts"] == {"active": 2, "paused": 2, "unknown": 0}
    assert result["duplicates"] == ["DEMO-PASS", "demo-pass"]
    assert ("goto", SETTINGS) in page.calls
    assert_no_interaction(page)
    assert not EMAIL_RE.search(json.dumps(result))
    text = render_list(result)
    assert "FRIENDS50" in text and "duplicate codes" in text and "2 paused" in text


def test_list_refuses_a_redirect_away_from_settings():
    page = FakePage(table_state())
    page.goto = lambda url, **kwargs: setattr(page, "url", "https://maven.com/acme/admin/courses/other/settings")
    with pytest.raises(MavenError, match="redirected"):
        list_promo_codes(page, ADMIN)


def test_list_with_bare_slug_uses_course_discovery(monkeypatch):
    from maven_skill import ops

    monkeypatch.setattr(ops, "_dashboard_href", lambda page: "https://maven.com/acme/admin")
    monkeypatch.setattr(ops, "_courses_href", lambda page, dashboard: "https://maven.com/acme/admin/courses")
    monkeypatch.setattr(ops, "_collect_course_links", lambda page: ([{"url": ADMIN, "title": "Demo"}], {}))
    page = FakePage(table_state())
    assert list_promo_codes(page, "demo-course")["course"] == ADMIN


def test_locate_pause_writes_private_artifacts(tmp_path):
    page = FakePage(table_state())
    out = tmp_path / "job"
    result = locate_pause(page, ADMIN, "friends50", out)
    assert (result["verdict"], result["confidence"], result["target_position"]) == ("ready_to_pause", "high", 1)
    assert result["code"] == "FRIENDS50" and result["redemptions"] == 12
    assert result["public_link"] == {
        "url": "https://maven.com/acme/demo-course?promoCode=FRIENDS50", "checked": True,
        "has_struck_price": True, "struck_prices": ["$1,000"], "prices": ["$1,000", "$900"],
    }
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    for name in ("row.png", "annotated.png", "evidence.json"):
        assert stat.S_IMODE((out / name).stat().st_mode) == 0o600
    evidence = json.loads((out / "evidence.json").read_text())
    assert evidence["verdict"] == "ready_to_pause"
    assert evidence["button_evidence"][1]["handler_excerpt"].startswith("()=>")
    assert evidence["button_evidence"][1]["box"] == {"x": 250, "y": 52, "width": 16, "height": 16}
    assert Image.open(out / "annotated.png").getpixel((16 + 300 - 4, 16 + 4 + 5)) == (220, 0, 0)
    assert all(context.closed for context in page.context.browser.contexts)
    assert_no_interaction(page)
    assert not EMAIL_RE.search(json.dumps(result))
    text = render_locate(result)
    assert text.startswith("VERDICT: ready_to_pause  confidence=high")
    assert "E2_handler: pass" in text and "struck price: True" in text


def test_locate_pause_reports_already_paused(tmp_path):
    page = FakePage(table_state(), public={"struck": [], "prices": ["$1,000"]}, row_code="SPRING25")
    result = locate_pause(page, "acme/demo-course", "SPRING25", tmp_path / "job")
    assert result["verdict"] == "already_paused"
    assert result["public_link"]["has_struck_price"] is False
    assert_no_interaction(page)


def test_locate_pause_refuses_duplicates_and_missing_codes_without_files(tmp_path):
    for code, message in (("demo-pass", "not unique"), ("MISSING", "not found")):
        page = FakePage(table_state())
        with pytest.raises(MavenError, match=message):
            locate_pause(page, ADMIN, code, tmp_path / code)
        assert not (tmp_path / code).exists()


def test_locate_pause_refuses_bare_slug_before_navigation(tmp_path):
    page = FakePage(table_state())
    with pytest.raises(MavenError, match="admin URL"):
        locate_pause(page, "demo-course", "FRIENDS50", tmp_path / "job")
    assert page.calls == []


def test_locate_pause_survives_a_failed_public_check(tmp_path):
    page = FakePage(table_state())

    def broken(**kwargs):
        raise RuntimeError("network down")
    page.context.browser.new_context = broken
    result = locate_pause(page, ADMIN, "FRIENDS50", tmp_path / "job")
    assert result["public_link"]["checked"] is False
    assert result["verdict"] == "ready_to_pause"


def test_locate_pause_not_ready_still_writes_evidence(tmp_path):
    state = table_state()
    state["rows"][0]["buttons"][1]["handler"] = DELETE_SRC
    page = FakePage(state)
    result = locate_pause(page, ADMIN, "FRIENDS50", tmp_path / "job")
    assert (result["verdict"], result["confidence"]) == ("not_ready", "none")
    assert (tmp_path / "job" / "evidence.json").exists()


# --- CLI -----------------------------------------------------------------------------

def test_cli_promo_parsing():
    from maven_skill.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["promo-codes", "list", "--course", "acme/demo-course", "--json"])
    assert (args.group, args.action, args.as_json) == ("promo-codes", "list", True)
    args = parser.parse_args(["promo-codes", "locate-pause", "--course", ADMIN, "--code", "FRIENDS50",
                              "--output-dir", "out"])
    assert (args.code, args.output_dir, args.as_json) == ("FRIENDS50", Path("out"), False)
    for argv in (["promo-codes", "locate-pause", "--course", ADMIN, "--code", "X"],
                 ["promo-codes", "locate-pause", "--course", ADMIN, "--output-dir", "out"],
                 ["promo-codes", "list"],
                 ["promo-codes", "pause", "--course", ADMIN]):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)


def fake_locate_result(verdict):
    return {
        "verdict": verdict, "confidence": "high", "status": "active", "code": "FRIENDS50", "row_index": 0,
        "redemptions": 0, "amount_off": "$100", "percent_off": None, "target_position": 1, "button_count": 3,
        "checks": {"E1_icon": {"result": True, "detail": "pause"}}, "reason": None,
        "public_link": {"url": "https://maven.com/acme/demo-course?promoCode=FRIENDS50", "checked": True,
                        "has_struck_price": True, "struck_prices": ["$1,000"], "prices": []},
        "artifacts": {"annotated": "out/annotated.png"},
    }


@pytest.mark.parametrize("verdict,code", [("ready_to_pause", 0), ("already_paused", 0), ("not_ready", 3)])
def test_cli_locate_exit_codes(monkeypatch, capsys, verdict, code):
    from maven_skill import cli

    monkeypatch.setattr(cli, "run_business", lambda session, auth_state, action: fake_locate_result(verdict))
    argv = ["promo-codes", "locate-pause", "--course", ADMIN, "--code", "FRIENDS50", "--output-dir", "out"]
    assert cli.main(argv) == code
    assert capsys.readouterr().out.startswith(f"VERDICT: {verdict}")
    assert cli.main(argv + ["--json"]) == code
    assert json.loads(capsys.readouterr().out)["verdict"] == verdict


def test_cli_list_prints_text_or_json(monkeypatch, capsys):
    from maven_skill import cli

    result = list_promo_codes(FakePage(table_state()), ADMIN)
    monkeypatch.setattr(cli, "run_business", lambda session, auth_state, action: result)
    assert cli.main(["promo-codes", "list", "--course", ADMIN]) == 0
    assert capsys.readouterr().out.startswith("course: " + ADMIN)
    assert cli.main(["promo-codes", "list", "--course", ADMIN, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 4


def test_cli_sanitizes_unexpected_promo_errors(monkeypatch, capsys):
    from maven_skill import cli

    def explode(session, auth_state, action):
        raise RuntimeError("Bearer secret-token for ada@example.com at /private/path")
    monkeypatch.setattr(cli, "run_business", explode)
    assert cli.main(["promo-codes", "list", "--course", ADMIN]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "secret-token" not in captured.err and "@" not in captured.err and "/private" not in captured.err
