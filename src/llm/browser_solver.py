"""Browser-based anti-bot challenge solver (Akamai, Cloudflare, etc.).

Reuses the host's installed Chromium-family browser via the existing CDP
infrastructure to execute JavaScript challenges, harvests the resulting
"solved" cookies, and makes them available for replay through curl_cffi.

The solver is challenge-type agnostic: `detect_protection()` classifies the
blocking layer, and `SOLVED_PREDICATES` maps each type to a predicate that
recognises a solved state. Adding a new provider (DataDome, PerimeterX, ...)
means adding a detection rule and a solved predicate.
"""

import json
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlparse

from src.elwand_paths import antibot_profile_dir
from src.tools.webrecorder.browser_finder import find_browsers
from src.tools.webrecorder.cdp import CDPClient

_SOLVER_PORT = 9333
_COOKIE_TTL = 40 * 60
_SOLVE_TIMEOUT = 15


# ─── Detection ──────────────────────────────────────────────

def detect_protection(status_code, headers=None, cookies=None):
    """Classify the active anti-bot layer, or None if nothing is blocking.

    Only returns a type when the response appears to be a *challenge* (i.e. we
    have not been let through yet), not when a known cookie is already solved.
    """
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    ck = {str(k): str(v) for k, v in (cookies or {}).items()}
    server = h.get("server", "").lower()

    # Akamai Bot Manager — unsolved `_abck` cookie (sensor). The `AkamaiGHost`
    # server header alone means a hard "Access Denied" edge block (IP/UA/geo),
    # which is not solvable by a browser, so it is intentionally not detected.
    abck = ck.get("_abck", "")
    if abck:
        parts = abck.split("~")
        if len(parts) < 2 or parts[1] != "0":
            return "akamai"

    # PerimeterX (_pxhd/_px3 cookies, x-px-* headers).
    if any(name.startswith("_px") for name in ck) or any(name.startswith("x-px-") for name in h):
        return "perimeterx"

    # DataDome (x-datadome header or datadome* cookies).
    if "x-datadome" in h or any(name.startswith("datadome") for name in ck):
        return "datadome"

    # Cloudflare — only flag explicit challenge signals, not any Cloudflare
    # front (avoid false positives on sites that serve content with __cf_bm).
    if "challenge" in h.get("cf-mitigated", "").lower():
        if not ck.get("cf_clearance"):
            return "cloudflare"
    if "cloudflare" in server and status_code in (403, 503):
        if not ck.get("cf_clearance"):
            return "cloudflare"

    return None


def _akamai_solved(cookies):
    abck = cookies.get("_abck", "")
    parts = abck.split("~")
    return len(parts) >= 2 and parts[1] == "0"


def _cloudflare_solved(cookies):
    return bool(cookies.get("cf_clearance"))


SOLVED_PREDICATES = {
    "akamai": _akamai_solved,
    "cloudflare": _cloudflare_solved,
}


# ─── Cookie bank ────────────────────────────────────────────

class CookieBank:
    """Per-host cache of solved cookies with a time-to-live."""

    def __init__(self, ttl=_COOKIE_TTL):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._store = {}

    def get(self, host):
        with self._lock:
            entry = self._store.get(host)
            if not entry:
                return None
            expires, cookies = entry
            if time.time() > expires:
                self._store.pop(host, None)
                return None
            return dict(cookies)

    def set(self, host, cookies):
        with self._lock:
            self._store[host] = (time.time() + self._ttl, dict(cookies))

    def clear(self):
        with self._lock:
            self._store.clear()


cookie_bank = CookieBank()


# ─── Browser lifecycle ──────────────────────────────────────

def _launch_browser(browser_path, headless):
    args = [
        browser_path,
        f"--remote-debugging-port={_SOLVER_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={antibot_profile_dir()}",
        "--new-window", "about:blank",
        "--no-first-run", "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-restore-session-state",
        "--disable-features=WelcomePage,ChromeWhatsNewUI",
    ]
    if headless:
        args.append("--headless=new")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _kill_on_port(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1).close()
        subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"],
                       timeout=5, capture_output=True)
        time.sleep(0.5)
    except Exception:
        pass


def _get_cdp_url(port):
    for _ in range(20):
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2)
            data = json.loads(resp.read())
            for page in data:
                if page.get("type") == "page":
                    return page.get("webSocketDebuggerUrl")
        except Exception:
            time.sleep(0.25)
    return None


def _get_all_cookies(cdp):
    try:
        res = cdp.call("Network.getAllCookies", {})
        return res.get("cookies", []) if res else []
    except Exception:
        return []


def _filter_cookies(all_cookies, host):
    out = {}
    for c in all_cookies:
        domain = (c.get("domain") or "").lstrip(".")
        name = c.get("name")
        value = c.get("value", "")
        if not name:
            continue
        if host == domain or host.endswith("." + domain):
            out[name] = value
    return out


def _solve_with_browser(browser_path, url, host, predicate, timeout, headless):
    _kill_on_port(_SOLVER_PORT)
    proc = _launch_browser(browser_path, headless)
    try:
        cdp_url = _get_cdp_url(_SOLVER_PORT)
        if not cdp_url:
            return None
        cdp = CDPClient(cdp_url)
        try:
            cdp.send("Page.enable", {})
            cdp.send("Network.enable", {})
            cdp.send("Page.navigate", {"url": url})
            deadline = time.time() + timeout
            while time.time() < deadline:
                cookies = _filter_cookies(_get_all_cookies(cdp), host)
                if predicate is None:
                    if cookies and _abck_flags_settled(cookies):
                        return cookies
                elif predicate(cookies):
                    return cookies
                time.sleep(0.5)
            return None
        finally:
            try:
                cdp.close()
            except Exception:
                pass
    finally:
        try:
            proc.kill()
        except Exception:
            pass
    return None


def _abck_flags_settled(cookies):
    abck = cookies.get("_abck", "")
    if not abck:
        return False
    return _akamai_solved(cookies)


# ─── Public API ─────────────────────────────────────────────

def solve(url, challenge_type=None, timeout=_SOLVE_TIMEOUT, headless=True):
    """Solve the anti-bot challenge on `url`, returning solved cookies or None."""
    host = urlparse(url).hostname
    if not host:
        return None
    if challenge_type and challenge_type not in SOLVED_PREDICATES:
        return None
    predicate = SOLVED_PREDICATES.get(challenge_type) if challenge_type else None
    browsers = find_browsers()
    if not browsers:
        return None
    modes = [True, False] if headless else [False]
    for browser_path, _label in sorted(browsers.items()):
        for mode in modes:
            cookies = _solve_with_browser(browser_path, url, host, predicate, timeout, mode)
            if cookies:
                return cookies
    return None


def browser_fetch(url, timeout=_SOLVE_TIMEOUT):
    """Fetch `url` through a real browser and return the rendered HTML.

    Used as a last-resort fallback when replaying solved cookies still fails
    (Akamai/Cloudflare configs that bind the cookie to the TLS fingerprint).
    """
    host = urlparse(url).hostname
    browsers = find_browsers()
    if not browsers:
        return None
    for browser_path, _label in sorted(browsers.items()):
        for mode in (True, False):
            rendered = _browser_fetch_once(browser_path, url, host, timeout, mode)
            if rendered:
                return rendered
    return None


def _eval(cdp, expression):
    try:
        res = cdp.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if res and res.get("result", {}).get("value") is not None:
            return res["result"]["value"]
    except Exception:
        pass
    return None


def _wait_navigation(cdp, timeout):
    """Wait until the navigation has left about:blank and finished loading."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        href = _eval(cdp, "location.href")
        state = _eval(cdp, "document.readyState")
        if href and not href.startswith("about:") and state == "complete":
            return True
        time.sleep(0.3)
    return False


def _wait_network_idle(cdp, timeout):
    """Wait until no new resources have started for a short settle window."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        prev = _eval(cdp, "performance.getEntriesByType('resource').length")
        time.sleep(1.5)
        now = _eval(cdp, "performance.getEntriesByType('resource').length")
        if prev is not None and now is not None and prev == now:
            return True
    return False


def _wait_body_content(cdp, timeout, min_chars=200):
    """Best-effort wait until the rendered body has visible text.

    Returns when the body text reaches `min_chars`, or when it stops growing
    (a short, server-rendered page), or when the timeout expires.
    """
    deadline = time.time() + timeout
    prev = None
    while time.time() < deadline:
        n = _eval(cdp, "document.body ? document.body.innerText.trim().length : 0")
        if n is not None and n >= min_chars:
            return True
        if n is not None and n > 0:
            if prev is not None and n == prev:
                return True
            prev = n
        time.sleep(0.5)
    return False


def _browser_fetch_once(browser_path, url, host, timeout, headless):
    _kill_on_port(_SOLVER_PORT)
    proc = _launch_browser(browser_path, headless)
    try:
        cdp_url = _get_cdp_url(_SOLVER_PORT)
        if not cdp_url:
            return None
        cdp = CDPClient(cdp_url)
        try:
            cdp.send("Page.enable", {})
            cdp.send("Network.enable", {})
            cdp.send("Page.navigate", {"url": url})
            _wait_navigation(cdp, timeout)
            _wait_network_idle(cdp, timeout)
            _wait_body_content(cdp, min(timeout, 10))
            time.sleep(1.0)
            text = _eval(cdp, (
                "document.documentElement ? document.documentElement.outerHTML "
                ": (document.body ? document.body.innerHTML : '')"
            ))
            if not text:
                return None
            low = text.lower()
            if "access denied" in low or "<title>attention required" in low:
                return None
            return str(text)
        finally:
            try:
                cdp.close()
            except Exception:
                pass
    finally:
        try:
            proc.kill()
        except Exception:
            pass
    return None
