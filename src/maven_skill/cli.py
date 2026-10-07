import argparse
import json
import os
from pathlib import Path
import sys

from maven_skill.errors import MavenError
from maven_skill.ops import (
    export_students,
    lessons_stats,
    list_cohorts,
    list_courses,
    list_lessons,
    list_reviews,
    list_surveys,
    run_business,
    show_lesson,
)
from maven_skill.promo import list_promo_codes, locate_pause, render_list, render_locate
from maven_skill.session import Session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maven-skill")
    parser.add_argument("--data-dir", type=Path, default=os.getenv("MAVEN_DATA_DIR", ".local"))
    parser.add_argument("--port", type=int)
    parser.add_argument("--auth-state", type=Path)
    groups = parser.add_subparsers(dest="group", required=True)
    sessions = groups.add_parser("session").add_subparsers(dest="action", required=True)
    sessions.add_parser("open").add_argument("--url", default="https://maven.com/")
    for name in ("status", "save", "close"):
        sessions.add_parser(name)
    pages = groups.add_parser("page").add_subparsers(dest="action", required=True)
    pages.add_parser("snapshot")
    pages.add_parser("goto").add_argument("url")
    courses = groups.add_parser("courses").add_subparsers(dest="action", required=True)
    courses.add_parser("list")
    cohorts = groups.add_parser("cohorts").add_subparsers(dest="action", required=True)
    cohorts.add_parser("list").add_argument("--course", required=True)
    students = groups.add_parser("students").add_subparsers(dest="action", required=True)
    export = students.add_parser("export")
    export.add_argument("--course", required=True)
    export.add_argument("--cohort", required=True)
    export.add_argument("--output", type=Path)
    lessons = groups.add_parser("lessons").add_subparsers(dest="action", required=True)
    lessons.add_parser("list")
    lessons.add_parser("show").add_argument("--lesson", required=True)
    stats = lessons.add_parser("stats").add_mutually_exclusive_group(required=True)
    stats.add_argument("--lesson")
    stats.add_argument("--all", action="store_true", dest="all_lessons")
    reviews = groups.add_parser("reviews").add_subparsers(dest="action", required=True)
    reviews.add_parser("list").add_argument("--course", required=True)
    surveys = reviews.add_parser("surveys")
    surveys.add_argument("--course", required=True)
    surveys.add_argument("--cohort")
    surveys.add_argument("--download", action="store_true")
    surveys.add_argument("--output-dir", type=Path)
    promo = groups.add_parser("promo-codes").add_subparsers(dest="action", required=True)
    promo_list = promo.add_parser("list")
    promo_list.add_argument("--course", required=True)
    promo_list.add_argument("--json", action="store_true", dest="as_json")
    locate = promo.add_parser("locate-pause")
    locate.add_argument("--course", required=True)
    locate.add_argument("--code", required=True)
    locate.add_argument("--output-dir", type=Path, required=True)
    locate.add_argument("--json", action="store_true", dest="as_json")
    return parser


def resolve_port(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    raw = os.getenv("MAVEN_CDP_PORT")
    if raw is None or raw.strip() == "":
        return 9337
    try:
        port = int(raw.strip())
    except (TypeError, ValueError):
        raise MavenError("CDP port configuration is invalid") from None
    if not 1024 <= port <= 65535:
        raise MavenError("CDP port configuration is invalid")
    return port


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        session = Session(args.data_dir, resolve_port(args.port))
        if args.group == "page":
            result = session.page(args.url if args.action == "goto" else None)
        elif args.group == "session" and args.action == "open":
            result = session.open(args.url)
        elif args.group == "session" and args.action == "status":
            result = session.status()
        elif args.group == "session":
            result = session.save(close=args.action == "close")
        elif args.group == "courses":
            result = run_business(session, args.auth_state, list_courses)
        elif args.group == "cohorts":
            result = run_business(
                session, args.auth_state, lambda page: list_cohorts(page, args.course)
            )
        elif args.group == "lessons" and args.action == "list":
            result = run_business(session, args.auth_state, list_lessons)
        elif args.group == "lessons" and args.action == "show":
            result = run_business(
                session, args.auth_state, lambda page: show_lesson(page, args.lesson)
            )
        elif args.group == "lessons":
            result = run_business(
                session,
                args.auth_state,
                lambda page: lessons_stats(page, args.lesson, args.all_lessons),
            )
        elif args.group == "reviews" and args.action == "list":
            result = run_business(
                session, args.auth_state, lambda page: list_reviews(page, args.course)
            )
        elif args.group == "promo-codes" and args.action == "list":
            result = run_business(
                session, args.auth_state, lambda page: list_promo_codes(page, args.course)
            )
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else render_list(result))
            return 0
        elif args.group == "promo-codes":
            result = run_business(
                session,
                args.auth_state,
                lambda page: locate_pause(page, args.course, args.code, args.output_dir),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else render_locate(result))
            return 3 if result["verdict"] == "not_ready" else 0
        elif args.group == "reviews":
            if args.output_dir is not None and not args.download:
                raise MavenError("--output-dir requires --download")
            result = run_business(
                session,
                args.auth_state,
                lambda page: list_surveys(
                    page, args.course, args.cohort, args.download, args.output_dir, session.root
                ),
            )
        else:
            result = run_business(
                session,
                args.auth_state,
                lambda page: export_students(
                    page, args.course, args.cohort, args.output, session.root
                ),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, (MavenError, ValueError, TimeoutError)) else (
            "Browser operation failed; inspect session status locally"
        )
        print(json.dumps({"error": type(exc).__name__, "message": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
