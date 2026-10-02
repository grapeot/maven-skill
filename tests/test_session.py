import json
import stat
from pathlib import Path

import pytest

from maven_skill.session import Session, private_json, validate_url


@pytest.mark.parametrize("url", ["https://maven.com/", "https://app.maven.com/course"])
def test_navigation_allows_maven(url):
    assert validate_url(url) == url


@pytest.mark.parametrize("url", ["http://maven.com/", "https://maven.com.example.com/",
                               "https://example.com/", "https://alice:secret@example.com/"])
def test_navigation_rejects_unrelated_or_credential_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_state_is_private_and_atomic(tmp_path):
    path = tmp_path / "auth-state.json"
    path.write_text("old")
    path.chmod(0o644)
    private_json(path, {"cookies": [], "origins": []})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == {"cookies": [], "origins": []}
    assert not list(tmp_path.glob(".state-*"))


def test_wrong_profile_is_rejected_before_browser_use(tmp_path):
    class CDP:
        def send(self, method):
            return {"arguments": ["--user-data-dir=/different/profile"]}
        def detach(self):
            pass
    class Browser:
        def new_browser_cdp_session(self):
            return CDP()
    with pytest.raises(ValueError, match="different browser profile"):
        Session(tmp_path, 9337).verify_browser(Browser())


def test_string_port_is_accepted_and_invalid_port_is_rejected(tmp_path):
    assert Session(tmp_path, "9337").port == 9337
    with pytest.raises(ValueError):
        Session(tmp_path, "80")
    with pytest.raises(ValueError):
        Session(tmp_path, "nope")


def test_cli_port_default_is_int_and_business_commands_parse(monkeypatch):
    from maven_skill.cli import build_parser, resolve_port

    monkeypatch.delenv("MAVEN_CDP_PORT", raising=False)
    parser = build_parser()
    status = parser.parse_args(["session", "status"])
    assert resolve_port(status.port) == 9337
    export = parser.parse_args([
        "--auth-state", "state.json",
        "students", "export",
        "--course", "https://maven.com/example-school/admin/courses/example-course",
        "--cohort", "latest",
        "--output", "out.csv",
    ])
    assert export.auth_state == Path("state.json")
    assert export.cohort == "latest"
    with pytest.raises(SystemExit):
        parser.parse_args(["students", "export", "--course", "https://maven.com/example-school/admin/courses/example-course"])


def test_invalid_port_env_is_a_configuration_error(monkeypatch, capsys):
    from maven_skill.cli import main

    monkeypatch.setenv("MAVEN_CDP_PORT", "not-a-port")
    assert main(["session", "status"]) == 1
    error = capsys.readouterr().err
    assert "not-a-port" not in error
    assert "invalid" in error


def test_disconnected_status_does_not_claim_login(tmp_path, monkeypatch):
    session = Session(tmp_path, 9337)
    monkeypatch.setattr(session, "endpoint_ready", lambda: False)
    assert session.status() == {"browser_connected": False, "authentication": "not_checked"}
