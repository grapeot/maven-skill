from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from playwright.sync_api import sync_playwright


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Navigation requires an HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URLs are not allowed")
    if parsed.hostname != "maven.com" and not parsed.hostname.endswith(".maven.com"):
        raise ValueError("Navigation is limited to maven.com")
    return url


def private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Session:
    def __init__(self, data_dir: Path, port: int):
        if not 1024 <= port <= 65535:
            raise ValueError("CDP port must be between 1024 and 65535")
        self.root = data_dir.expanduser().resolve()
        self.profile = self.root / "browser-profile"
        self.port = port
        self.endpoint = f"http://127.0.0.1:{port}"

    def endpoint_ready(self) -> bool:
        try:
            with build_opener(ProxyHandler({})).open(
                f"{self.endpoint}/json/version", timeout=2
            ) as response:
                return bool(json.load(response).get("webSocketDebuggerUrl"))
        except (OSError, ValueError):
            return False

    def verify_browser(self, browser) -> None:
        cdp = browser.new_browser_cdp_session()
        try:
            args = cdp.send("Browser.getBrowserCommandLine")["arguments"]
            expected = f"--user-data-dir={self.profile}"
            if expected not in args:
                raise ValueError("CDP port belongs to a different browser profile")
        finally:
            cdp.detach()

    def connect(self, playwright):
        browser = playwright.chromium.connect_over_cdp(self.endpoint, timeout=10000)
        self.verify_browser(browser)
        return browser

    def open(self, url: str) -> dict:
        validate_url(url)
        if self.endpoint_ready():
            return {**self.status(), "reused": True}
        # An occupied port must never cause attachment to another application's browser.
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", self.port)) == 0:
                raise ValueError("CDP port is already occupied")
        for directory in (self.root, self.profile, self.root / "downloads"):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        executable = os.environ.get("MAVEN_CHROME_EXECUTABLE")
        if not executable:
            executable = (
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                if sys.platform == "darwin"
                else shutil.which("google-chrome") or shutil.which("chromium")
            )
        if not executable or not Path(executable).is_file():
            raise ValueError("Chrome executable not found; set MAVEN_CHROME_EXECUTABLE")
        log_path = self.root / "browser.log"
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(log_path, 0o600)
        with os.fdopen(fd, "ab") as log:
            process = subprocess.Popen(
                [executable, f"--remote-debugging-port={self.port}",
                 "--remote-debugging-address=127.0.0.1",
                 f"--user-data-dir={self.profile}", "--enable-automation",
                 "--no-first-run", "--no-default-browser-check", url],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True,
            )
        for _ in range(100):
            if self.endpoint_ready():
                with sync_playwright() as p:
                    browser = self.connect(p)
                    cdp = browser.new_browser_cdp_session()
                    cdp.send("Browser.setDownloadBehavior", {
                        "behavior": "allow", "downloadPath": str(self.root / "downloads")
                    })
                    cdp.detach()
                return {**self.status(), "reused": False, "pid": process.pid}
            if process.poll() is not None:
                raise ValueError(f"Chrome exited with code {process.returncode}; see private browser.log")
            time.sleep(0.2)
        raise TimeoutError("Chrome CDP startup timed out; see private browser.log")

    def status(self) -> dict:
        if not self.endpoint_ready():
            return {"browser_connected": False, "authentication": "not_checked"}
        with sync_playwright() as p:
            browser = self.connect(p)
            return {"browser_connected": True, "authentication": "not_checked",
                    "cdp_url": self.endpoint,
                    "pages": [page.url for ctx in browser.contexts for page in ctx.pages],
                    "profile": str(self.profile)}

    def save(self, close: bool = False) -> dict:
        with sync_playwright() as p:
            browser = self.connect(p)
            context = browser.contexts[0]
            state = context.storage_state(indexed_db=True)
            target = self.root / "auth-state.json"
            private_json(target, state)
            if close:
                cdp = browser.new_browser_cdp_session()
                cdp.send("Browser.close")
            return {"saved": True, "state_path": str(target), "closed": close}

    def page(self, url: str | None = None) -> dict:
        if url:
            validate_url(url)
        with sync_playwright() as p:
            browser = self.connect(p)
            context = browser.contexts[0]
            pages = [page for page in context.pages if
                     urlsplit(page.url).hostname == "maven.com" or
                     (urlsplit(page.url).hostname or "").endswith(".maven.com")]
            if not pages and not url:
                raise ValueError("No Maven page is open; navigate to Maven first")
            page = pages[-1] if pages else context.new_page()
            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {"url": page.url, "title": page.title(),
                    "text": page.locator("body").inner_text(timeout=10000)[:30000],
                    "controls": page.locator("a, button, input, select").evaluate_all(
                        "els => els.slice(0, 300).map(e => ({tag:e.tagName, "
                        "text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,200), "
                        "href:e.getAttribute('href'), type:e.getAttribute('type')}))"
                    )}
