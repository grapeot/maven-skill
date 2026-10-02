import json
import stat

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


def test_disconnected_status_does_not_claim_login(tmp_path, monkeypatch):
    session = Session(tmp_path, 9337)
    monkeypatch.setattr(session, "endpoint_ready", lambda: False)
    assert session.status() == {"browser_connected": False, "authentication": "not_checked"}
