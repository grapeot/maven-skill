import argparse
import json
import os
from pathlib import Path
import sys

from maven_skill.session import Session


def main() -> int:
    parser = argparse.ArgumentParser(prog="maven-skill")
    parser.add_argument("--data-dir", type=Path, default=os.getenv("MAVEN_DATA_DIR", ".local"))
    parser.add_argument("--port", type=int, default=os.getenv("MAVEN_CDP_PORT", "9337"))
    groups = parser.add_subparsers(dest="group", required=True)
    sessions = groups.add_parser("session").add_subparsers(dest="action", required=True)
    sessions.add_parser("open").add_argument("--url", default="https://maven.com/")
    for name in ("status", "save", "close"):
        sessions.add_parser(name)
    pages = groups.add_parser("page").add_subparsers(dest="action", required=True)
    pages.add_parser("snapshot")
    pages.add_parser("goto").add_argument("url")
    args = parser.parse_args()
    try:
        session = Session(args.data_dir, args.port)
        if args.group == "page":
            result = session.page(args.url if args.action == "goto" else None)
        elif args.action == "open":
            result = session.open(args.url)
        elif args.action == "status":
            result = session.status()
        else:
            result = session.save(close=args.action == "close")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Exception messages from browser protocols can contain URLs/tokens.
        print(json.dumps({"error": type(exc).__name__, "message":
                          str(exc) if isinstance(exc, (ValueError, TimeoutError))
                          else "Browser operation failed; inspect session status locally"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
