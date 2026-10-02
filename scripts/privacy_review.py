"""Inspect publishable Git files; never print sensitive matches."""
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, capture_output=True,
    )
    files = sorted(set(p.decode() for p in result.stdout.split(b"\0") if p))
    secret_values = set()
    state = root / ".local/auth-state.json"
    if state.exists():
        payload = json.loads(state.read_text())
        secret_values.update(c["value"] for c in payload.get("cookies", []) if len(c["value"]) >= 12)
    failures = []
    for name in files:
        path = root / name
        if not path.is_file():
            continue
        if name.startswith((".local/", "data/", "downloads/", "logs/", ".venv/")):
            failures.append((name, "private_runtime_path"))
            continue
        text = path.read_text(errors="replace")
        if any(secret in text for secret in secret_values):
            failures.append((name, "live_credential_value"))
        if re.search(r"/(?:Users|home)/[A-Za-z0-9_.-]+/", text):
            failures.append((name, "personal_machine_path"))
        if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text):
            failures.append((name, "private_key"))
        for email in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
            if email.rsplit("@", 1)[1] not in ("example.com", "example.net", "example.org", "example.test"):
                failures.append((name, "non_example_email"))
    print(json.dumps({"files_reviewed": len(files), "failures": failures, "passed": not failures}))
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
