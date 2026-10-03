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
    run_business,
    show_lesson,
)
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
