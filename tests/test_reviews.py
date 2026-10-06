import json
import re

import pytest

from maven_skill import ops
from maven_skill.errors import MavenError
from maven_skill.ops import (
    REVIEW_CARDS_JS,
    REVIEWS_EMBEDDED_JS,
    REVIEWS_READY_JS,
    SURVEY_CARDS_JS,
    SURVEY_CARD_TEXT_JS,
    SURVEY_PAGE_READY_JS,
    SURVEYS_NAV_JS,
    SURVEYS_NAV_READY_JS,
    list_reviews,
    list_surveys,
)
from maven_skill.parse import (
    assert_review_output,
    merge_public_reviews,
    parse_course_survey_average,
    parse_review_card,
    parse_review_date,
    parse_survey_card,
    parse_testimonials,
    public_course_url,
    rating_summary,
    review_text,
    star_rating,
    survey_label_token,
    validate_survey_csv,
)


PUBLIC = "https://maven.com/acme/widgets"
ADMIN = "https://maven.com/acme/admin/courses/widgets"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
FULL = ["full"] * 5


def card(name="Ada", chips=("Live cohort", " Jul 2026 Live cohort"), headline="Engineer · Example Co",
         date="Sep 1, 2026", text="Built a tool that saves my team an hour a day.", stars=None):
    leaves = [{"tag": "p", "text": name}] if name else []
    leaves += [{"tag": "span", "text": chip} for chip in chips]
    if headline:
        leaves.append({"tag": "div", "text": headline})
    leaves.append({"tag": "p", "text": date})
    if text:
        leaves.append({"tag": "div", "text": text})
    return {"leaves": leaves, "stars": FULL if stars is None else stars}


def embedded(items=None, total=3, testimonials=None):
    return {
        "course": {"slug": "widgets", "name": "Widgets 101"},
        "rating_summary": {"sum": 52, "count": 6},
        "metadata": {"total": total, "pages": 1, "page": 1},
        "items": items if items is not None else [
            {"anonymous": False, "name": "Ada", "job_title": "Engineer", "company": "Example Co", "rating": 9,
             "review": "Built a tool that saves my team an hour a day.", "cohort_name": "Cohort 3",
             "cohort_type": "live", "cohort_start": "2026-07-13T19:00:00Z", "created_at": "2026-09-01T08:00:00Z"},
        ],
        "testimonials": testimonials if testimonials is not None else [
            {"author_name": "Bea", "author_description": "PM · Example Org",
             "quote": "<p>Shipped my first agent &amp; kept it running.</p>"},
        ],
    }


# --- URL handling ------------------------------------------------------------------

@pytest.mark.parametrize("value", [PUBLIC, PUBLIC + "/", ADMIN, ADMIN + "/surveys?cohort=3", PUBLIC + "?ref=x"])
def test_public_course_url_normalizes_public_and_admin_urls(value):
    assert public_course_url(value) == PUBLIC


@pytest.mark.parametrize("value", [
    "http://maven.com/acme/widgets",
    "https://example.com/acme/widgets",
    "https://maven.com/acme",
    "https://maven.com/admin/widgets",
    "https://maven.com/acme/widgets/extra",
    "",
])
def test_public_course_url_rejects_other_urls(value):
    with pytest.raises(MavenError):
        public_course_url(value)


# --- card parsing ------------------------------------------------------------------

def test_review_card_fields_in_observed_order():
    parsed = parse_review_card(card())
    assert parsed == {
        "name": "Ada",
        "headline": "Engineer · Example Co",
        "cohort": "Jul 2026 Live cohort",
        "date": "2026-09-01",
        "date_text": "Sep 1, 2026",
        "text": "Built a tool that saves my team an hour a day.",
        "star_icons": 5.0,
    }


def test_review_card_without_headline_or_chips_and_with_paragraphs():
    parsed = parse_review_card(card(headline=None, chips=(), date="July 6, 2031",
                                    text="First   line.\n\nSecond line\nstill second."))
    assert parsed["headline"] is None and parsed["cohort"] is None
    assert parsed["date"] == "2031-07-06"
    assert parsed["text"] == "First line.\n\nSecond line still second."


def test_review_card_without_date_or_text_is_unparsed():
    assert parse_review_card(card(date="soon")) is None
    assert parse_review_card(card(text=None)) is None


def test_review_card_redacts_emails():
    parsed = parse_review_card(card(text="Write to ada@example.com for the repo", headline="Mail bea@example.com"))
    assert not EMAIL_RE.search(json.dumps(parsed))
    assert "[email removed]" in parsed["text"]


@pytest.mark.parametrize("states,value", [
    (FULL, 5.0),
    (["full"] * 4 + ["half"], 4.5),
    (["full"] * 4 + ["empty"], 4.0),
    (["full"] * 4, None),
    (["full"] * 4 + ["unknown"], None),
    (None, None),
])
def test_star_rating(states, value):
    assert star_rating(states) == value


@pytest.mark.parametrize("text,iso", [
    ("Sep 1, 2031", "2031-09-01"), ("July 6, 2031", "2031-07-06"), ("June 3, 2030", "2030-06-03"),
    ("Sept 5, 2025", "2025-09-05"), ("2026-09-01", None), ("Live cohort", None),
])
def test_review_date(text, iso):
    assert parse_review_date(text) == iso


def test_review_text_keeps_full_length():
    long = "word " * 400
    assert len(review_text(long)) == len(long.strip())


# --- merge and summary -------------------------------------------------------------

def test_merge_prefers_embedded_rating_and_falls_back_to_star_icons():
    cards = [card(), card(name="Cy", text="Learned to scope projects.", stars=["full"] * 4 + ["half"]),
             card(name="Di", text="Great.", stars=["full"] * 4 + ["empty"])]
    reviews, completeness = merge_public_reviews(embedded(), cards)
    assert [item["name"] for item in reviews] == ["Ada", "Cy", "Di"]
    assert reviews[0]["rating"] == 4.5 and reviews[0]["rating_source"] == "embedded_data"
    assert reviews[0]["cohort_name"] == "Cohort 3"
    assert reviews[1]["rating"] == 4.5 and reviews[1]["rating_source"] == "star_icons"
    assert reviews[2]["rating"] == 4.0
    assert all(item["source"] == "public_review" for item in reviews)
    assert completeness == {"status": "complete", "declared_total": 3, "parsed": 3, "unparsed_cards": 0}


@pytest.mark.parametrize("cards,total", [
    ([card()], 3),
    ([card(), {"leaves": [{"tag": "p", "text": "Broken"}], "stars": FULL}], 1),
    ([card()], None),
])
def test_merge_reports_partial(cards, total):
    _, completeness = merge_public_reviews(embedded(total=total), cards)
    assert completeness["status"] == "partial"


def test_merge_dedupes_repeated_cards():
    reviews, _ = merge_public_reviews(embedded(total=1), [card(), card()])
    assert len(reviews) == 1


def test_merge_without_cards_uses_embedded_and_hides_anonymous_identity():
    items = [{"anonymous": True, "name": "Hidden Person", "job_title": "Secret", "company": "Corp",
              "rating": 10, "review": "Loved it.", "cohort_name": "Cohort 1", "created_at": "2024-05-21T00:00:00Z"}]
    reviews, completeness = merge_public_reviews(embedded(items=items, total=1), [])
    assert reviews[0]["name"] is None and reviews[0]["headline"] is None and reviews[0]["anonymous"] is True
    assert reviews[0]["rating"] == 5.0 and reviews[0]["date"] == "2024-05-21"
    assert "Hidden" not in json.dumps(reviews)
    assert completeness["status"] == "complete"


def test_testimonials_strip_html():
    assert parse_testimonials(embedded()["testimonials"]) == [{
        "source": "public_testimonial", "name": "Bea", "headline": "PM · Example Org",
        "text": "Shipped my first agent & kept it running.",
    }]
    assert parse_testimonials([{"author_name": "X", "quote": "<p></p>"}]) == []


def test_rating_summary_converts_ten_point_scale_and_cross_checks_page_text():
    summary = rating_summary(embedded(), "4.3 (6 ratings)")
    assert summary == {"average": 4.333, "scale": 5, "ratings_count": 6, "page_text_average": 4.3,
                       "page_text_count": 6, "counts_agree": True}
    assert rating_summary(None, None)["average"] is None
    assert rating_summary(embedded(), "5.0 (7 ratings)")["counts_agree"] is False


def test_review_output_guard():
    assert_review_output({"name": "Ada", "text": "fine"})
    for value in ({"text": "ada@example.com"}, ["https://us01web.zoom.us/j/1"]):
        with pytest.raises(MavenError, match="private"):
            assert_review_output(value)


# --- surveys parsing ---------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ({"text": "Cohort 7 Completed July 6, 2031 5 / 5 Share 6 responses", "button": "6 responses"},
     {"label": "Cohort 7", "status": "completed", "completed_date": "2031-07-06", "average_rating": 5.0,
      "rating_scale": 5, "responses": 6, "downloadable": True}),
    ({"text": "Cohort 1 Completed May 2, 2030 4.6 / 5 Share 10 responses", "button": "10 responses"},
     {"label": "Cohort 1", "status": "completed", "completed_date": "2030-05-02", "average_rating": 4.6,
      "rating_scale": 5, "responses": 10, "downloadable": True}),
    ({"text": "Self-paced cohort Completed Sep 9, 2030 Share No responses yet", "button": "No responses yet",
      "disabled": True},
     {"label": "Self-paced cohort", "status": "completed", "completed_date": "2030-09-09", "average_rating": None,
      "rating_scale": 5, "responses": 0, "downloadable": False}),
    ({"text": "Cohort 8 Reminder email will send on Mon, Oct 7, 9:00AM (PDT) Share No responses yet",
      "button": "No responses yet", "disabled": True},
     {"label": "Cohort 8", "status": "pending", "completed_date": None, "average_rating": None,
      "rating_scale": 5, "responses": 0, "downloadable": False}),
])
def test_survey_card(raw, expected):
    assert parse_survey_card(raw) == expected


@pytest.mark.parametrize("raw", [
    {"text": "Course interest survey Sending out a pre-launch survey Share 322 responses Edit", "button": "322 responses"},
    {"text": "Cohort 2 Completed July 14, 2024 Share", "button": "Share"},
    {"text": "Cohort 2 ada@example.com Share 4 responses", "button": "4 responses"},
])
def test_survey_card_skips_non_cohort_cards(raw):
    assert parse_survey_card(raw) is None


def test_course_survey_average_and_label_token():
    assert parse_course_survey_average("Average rating for 9 cohorts\n4.88\n\n/ 5") == {
        "cohorts": 9, "average_rating": 4.88, "scale": 5}
    assert parse_course_survey_average(None) is None
    assert survey_label_token("Self-paced cohort") == "self-paced-cohort"
    assert survey_label_token("!!!") == "cohort"


SURVEY_CSV = (
    "Cohort,Student Name,Student Title,Student Company,Student Email,How would you rate this course?,"
    "Leave a public review,Write a private note\n"
    "Cohort 3,Ada Example,Engineer,Example Co,ada@example.com,5.0,Great,\n"
    "Cohort 3,Bea Example,PM,Example Org,bea@example.com,4.5,,Slow week 2\n"
    "Cohort 3,Cy Example,,,cy@example.com,5.0,Loved it,Thanks\n"
).encode()


def test_survey_csv_aggregates_without_identities():
    checked = validate_survey_csv(SURVEY_CSV, 3)
    assert checked["rating_column"] == "How would you rate this course?"
    assert checked["counts"] == {"page_responses": 3, "csv_rows": 3, "ratings": 3,
                                 "public_reviews": 2, "private_notes": 2}
    assert checked["rating"] == {"average": 4.833, "scale": 5, "histogram": {"5": 2, "4.5": 1}}
    dumped = json.dumps(checked)
    assert not EMAIL_RE.search(dumped) and "Ada" not in dumped and "Slow" not in dumped


@pytest.mark.parametrize("payload,rows,match", [
    (b"<!DOCTYPE html><html></html>", 0, "HTML"),
    (SURVEY_CSV, 4, "row count"),
    (b"Cohort,Name\nCohort 3,Ada\n", 1, "rating column"),
    (SURVEY_CSV.replace(b"4.5", b"great"), 3, "not numeric"),
    (SURVEY_CSV.replace(b"4.5", b"9"), 3, "0-5"),
    (b"\xff\xfe", 0, "UTF-8"),
])
def test_survey_csv_rejects_bad_exports(payload, rows, match):
    with pytest.raises(MavenError, match=match):
        validate_survey_csv(payload, rows)


# --- browser flows with fake pages -------------------------------------------------

class FakeLocator:
    def __init__(self, page, label):
        self.page = page
        self.label = label

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self.page.show_more else 0

    def inner_text(self, timeout=None):
        return self.label

    def get_attribute(self, name):
        return None

    def get_by_role(self, role, name=None, exact=False):
        return FakeLocator(self.page, name)

    def click(self, timeout=None):
        self.page.calls.append(("click", self.label))
        self.page.clicked(self.label)


class FakeReviewPage:
    def __init__(self, pages_of_cards, total, url=PUBLIC):
        self.url = "about:blank"
        self.final_url = url
        self.calls = []
        self.pages_of_cards = pages_of_cards
        self.loaded = 1
        self.dialog = False
        self.total = total

    @property
    def show_more(self):
        return self.loaded < len(self.pages_of_cards)

    def goto(self, url, **kwargs):
        self.calls.append(("goto", url))
        self.url = self.final_url

    def wait_for_function(self, script, **kwargs):
        self.calls.append(("wait_for_function", script[:30]))
        return True

    def wait_for_timeout(self, timeout):
        pass

    def evaluate(self, script, *args):
        self.calls.append(("evaluate", script[:30]))
        if script == REVIEWS_READY_JS:
            return True
        if script == REVIEWS_EMBEDDED_JS:
            return embedded(total=self.total)
        if script == REVIEW_CARDS_JS:
            if args and args[0] == "dialog" and not self.dialog:
                return None
            cards = [item for page in self.pages_of_cards[: self.loaded] for item in page]
            return {"cards": cards, "show_more": self.show_more, "summary_text": "4.3 (6 ratings)"}
        raise AssertionError("unexpected script")

    def get_by_role(self, role, name=None, exact=False):
        return FakeLocator(self, name)

    def clicked(self, label):
        assert label == "Show more reviews"
        if not self.dialog:
            self.dialog = True
        self.loaded += 1


def test_list_reviews_pages_through_show_more_with_guarded_clicks():
    pages = [[card()], [card(name="Cy", text="Second page.")], [card(name="Di", text="Third page.")]]
    page = FakeReviewPage(pages, total=3)
    result = list_reviews(page, ADMIN)
    assert result["course"] == PUBLIC
    assert result["count"] == 3
    assert result["completeness"]["status"] == "complete"
    assert result["completeness"]["show_more_remaining"] is False
    assert [call for call in page.calls if call[0] == "click"] == [("click", "Show more reviews")] * 2
    assert result["testimonial_count"] == 1
    assert result["rating_summary"]["ratings_count"] == 6
    assert not EMAIL_RE.search(json.dumps(result))


def test_list_reviews_single_page_does_not_click():
    page = FakeReviewPage([[card()]], total=1)
    result = list_reviews(page, PUBLIC)
    assert result["count"] == 1 and result["completeness"]["status"] == "complete"
    assert not [call for call in page.calls if call[0] == "click"]


def test_list_reviews_refuses_redirect():
    page = FakeReviewPage([[card()]], total=1, url="https://maven.com/acme/other")
    with pytest.raises(MavenError, match="redirected"):
        list_reviews(page, PUBLIC)


def test_guarded_click_refuses_write_controls():
    page = FakeReviewPage([[card()]], total=1)
    with pytest.raises(MavenError, match="write"):
        ops._guarded_click(FakeLocator(page, "Publish review"))
    assert not page.calls


def survey_state():
    return {
        "cards": [
            {"index": 0, "button": "322 responses", "disabled": False,
             "text": "Course interest survey Sending out a pre-launch survey Share 322 responses Edit"},
            {"index": 1, "button": "3 responses", "disabled": False,
             "text": "Cohort 3 Completed July 6, 2031 4.83 / 5 Share 3 responses"},
            {"index": 2, "button": "No responses yet", "disabled": True,
             "text": "Cohort 4 Reminder email will send on Mon, Oct 7, 9:00AM (PDT) Share No responses yet"},
        ],
        "average_text": "Average rating for 2 cohorts\n4.83\n/ 5",
    }


class FakeSurveyButton:
    def __init__(self, page, index):
        self.page = page
        self.index = index

    def evaluate(self, script):
        assert script == SURVEY_CARD_TEXT_JS
        return survey_state()["cards"][self.index]["text"]

    def inner_text(self, timeout=None):
        return survey_state()["cards"][self.index]["button"]

    def get_attribute(self, name):
        return None

    def click(self, timeout=None):
        self.page.calls.append(("click", self.index))


class FakeButtons:
    def __init__(self, page):
        self.page = page

    def nth(self, index):
        return FakeSurveyButton(self.page, index)


class FakeDownload:
    def __init__(self, payload):
        self.payload = payload

    def save_as(self, path):
        with open(path, "wb") as stream:
            stream.write(self.payload)


class FakeExpect:
    def __init__(self, payload):
        self.value = FakeDownload(payload)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSurveyPage:
    def __init__(self, payload=SURVEY_CSV):
        self.url = "about:blank"
        self.calls = []
        self.payload = payload

    def goto(self, url, **kwargs):
        self.calls.append(("goto", url))
        self.url = url

    def wait_for_function(self, script, **kwargs):
        assert script in (SURVEYS_NAV_READY_JS, SURVEY_PAGE_READY_JS)
        return True

    def wait_for_timeout(self, timeout):
        pass

    def evaluate(self, script, *args):
        if script == SURVEYS_NAV_JS:
            return [f"{ADMIN}/surveys?cohort=3"]
        if script == SURVEY_CARDS_JS:
            return survey_state()
        raise AssertionError("unexpected script")

    def get_by_role(self, role, name=None, exact=False):
        return FakeButtons(self)

    def expect_download(self, timeout=None):
        return FakeExpect(self.payload)


def test_list_surveys_without_download_is_aggregate_only_and_never_clicks(tmp_path):
    page = FakeSurveyPage()
    result = list_surveys(page, ADMIN, None, False, None, tmp_path)
    assert result["surveys_url"] == f"{ADMIN}/surveys?cohort=3"
    assert [item["label"] for item in result["cohorts"]] == ["Cohort 3", "Cohort 4"]
    assert result["total_responses"] == 3
    assert result["skipped_cards"] == 1
    assert result["course_average"] == {"cohorts": 2, "average_rating": 4.83, "scale": 5}
    assert result["downloads"] == []
    assert "index" not in result["cohorts"][0]
    assert not [call for call in page.calls if call[0] == "click"]
    assert not list(tmp_path.iterdir())


def test_list_surveys_download_writes_private_csv_and_receipt(tmp_path):
    import stat

    page = FakeSurveyPage()
    result = list_surveys(page, ADMIN, "3", True, tmp_path / "out", tmp_path / "data")
    assert [call for call in page.calls if call[0] == "click"] == [("click", 1)]
    [download] = result["downloads"]
    assert download["cohort"] == "Cohort 3"
    assert download["counts"]["csv_rows"] == 3
    files = list((tmp_path / "out").iterdir())
    assert len(files) == 1 and files[0].name.startswith("survey-widgets-cohort-3-")
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    receipts = list((tmp_path / "data" / "receipts").iterdir())
    assert [path.name.startswith("survey-export-") for path in receipts] == [True]
    dumped = json.dumps(result)
    assert not EMAIL_RE.search(dumped) and "Ada" not in dumped and "Slow week" not in dumped


def test_list_surveys_removes_invalid_download(tmp_path):
    page = FakeSurveyPage(payload=b"<html>login</html>")
    with pytest.raises(MavenError, match="HTML"):
        list_surveys(page, ADMIN, "Cohort 3", True, tmp_path, tmp_path / "data")
    assert not list(tmp_path.glob("survey-*.csv"))


def test_list_surveys_rejects_unknown_cohort(tmp_path):
    with pytest.raises(MavenError, match="cohort"):
        list_surveys(FakeSurveyPage(), ADMIN, "Cohort 9", False, None, tmp_path)


WRITE_PATTERNS = re.compile(
    r"\.click\(|dispatchEvent|\.submit\(|\.focus\(|\.value\s*=[^=]|innerHTML\s*=|textContent\s*=[^=]|"
    r"fetch\(|XMLHttpRequest|sendBeacon|setAttribute|removeAttribute|\.remove\(|localStorage|sessionStorage",
)


def test_review_scripts_are_read_only():
    for script in (REVIEWS_READY_JS, REVIEWS_EMBEDDED_JS, REVIEW_CARDS_JS, SURVEYS_NAV_JS,
                   SURVEYS_NAV_READY_JS, SURVEY_CARDS_JS, SURVEY_PAGE_READY_JS, SURVEY_CARD_TEXT_JS):
        assert not WRITE_PATTERNS.search(script), script[:60]
    assert "user_id" not in REVIEWS_EMBEDDED_JS and "image_url" not in REVIEWS_EMBEDDED_JS


# --- CLI ---------------------------------------------------------------------------

def test_cli_reviews_parsing():
    from maven_skill.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["reviews", "list", "--course", PUBLIC])
    assert (args.group, args.action, args.course) == ("reviews", "list", PUBLIC)
    args = parser.parse_args(["reviews", "surveys", "--course", ADMIN, "--download", "--cohort", "3"])
    assert args.download is True and args.cohort == "3" and args.output_dir is None
    with pytest.raises(SystemExit):
        parser.parse_args(["reviews", "list"])


def test_cli_output_dir_requires_download(capsys):
    from maven_skill import cli

    assert cli.main(["reviews", "surveys", "--course", ADMIN, "--output-dir", "x"]) == 1
    assert "--download" in capsys.readouterr().err
