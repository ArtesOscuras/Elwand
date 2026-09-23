import re
import html2text
import requests
import urllib3
from html.parser import HTMLParser

from src.llm.mcp import call as _mcp_call

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


MAX_RESPONSE_SIZE = 5 * 1024 * 1024
DEFAULT_TIMEOUT = 30

_EXA_MCP = "https://mcp.exa.ai/mcp"
_EXA_TOOL = "web_search_exa"

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)
_ELWAND_UA = "opencode/Elwand"

_DDG_URL = "https://lite.duckduckgo.com/lite/"


def _html_to_markdown(html):
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    return h.handle(html)


_SKIP_TAGS = {"nav", "footer", "aside", "script", "style", "noscript", "iframe", "object", "embed"}
_SKIP_CLASSES = {"cookie", "cookies", "consent", "gdpr", "banner", "popup", "sidebar", "cookie-banner", "cookie-consent", "cookie-notice"}
_SKIP_IDS = {"sidebar", "cookie-banner", "cookie-consent"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _HTMLCleaner(HTMLParser):
    def __init__(self):
        super().__init__()
        self._out = []
        self._skip_depth = 0

    def _should_skip(self, tag, attrs):
        if tag in _SKIP_TAGS:
            return True
        d = dict(attrs)
        cls = d.get("class", "").lower()
        if cls:
            for sc in _SKIP_CLASSES:
                if sc in cls:
                    return True
        if d.get("id", "").lower() in _SKIP_IDS:
            return True
        return False

    def handle_starttag(self, tag, attrs):
        if self._skip_depth > 0:
            if tag not in _VOID_TAGS:
                self._skip_depth += 1
            return
        if self._should_skip(tag, attrs):
            self._skip_depth = 1
            return
        if attrs:
            attr_str = "".join(f' {k}="{v}"' for k, v in attrs)
            self._out.append(f"<{tag}{attr_str}>")
        else:
            self._out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if self._skip_depth > 0:
            self._skip_depth -= 1
            return
        self._out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        self._out.append(data)

    def handle_startendtag(self, tag, attrs):
        if self._skip_depth > 0:
            return
        if self._should_skip(tag, attrs):
            return
        if attrs:
            attr_str = "".join(f' {k}="{v}"' for k, v in attrs)
            self._out.append(f"<{tag}{attr_str}/>")
        else:
            self._out.append(f"<{tag}/>")

    def handle_entityref(self, name):
        if self._skip_depth > 0:
            return
        self._out.append(f"&{name};")

    def handle_charref(self, name):
        if self._skip_depth > 0:
            return
        self._out.append(f"&#{name};")

    def get_html(self):
        return "".join(self._out)


def _strip_html_non_content(html):
    parser = _HTMLCleaner()
    parser.feed(html)
    parser.close()
    return parser.get_html()


_TEXT_TYPES = (
    "text/", "application/json", "application/xml",
    "application/javascript", "application/xhtml+xml",
    "application/ld+json", "application/rss+xml",
    "application/atom+xml",
)

_COOKIE_VALUE_MAX = 80
_SESSION_COOKIE_HINTS = ("session", "sess", "sid", "token", "csrf", "xsrf", "auth", "jwt", "connect.sid")
_LONG_COOKIE_RE = re.compile(r"([A-Za-z0-9_\-]+)=([^\s;,]{%d,})" % (_COOKIE_VALUE_MAX + 1))


def _is_session_cookie(name):
    n = name.lower()
    return any(h in n for h in _SESSION_COOKIE_HINTS)


def _truncate_cookies(header):
    """Truncate extremely long cookie values, keeping session cookies intact."""
    def _trunc(m):
        name, value = m.group(1), m.group(2)
        if _is_session_cookie(name):
            return m.group(0)
        return f"{name}={value[:32]}…({len(value)} chars)"
    return _LONG_COOKIE_RE.sub(_trunc, header)


def _curl_request(url, timeout, method, body, content_type, headers, cookies=None):
    from curl_cffi import requests as curl_requests
    req_headers = {"User-Agent": _CHROME_UA}
    if headers:
        req_headers.update({str(k): str(v) for k, v in headers.items()})
    if body and method == "POST":
        req_headers["Content-Type"] = content_type or "application/x-www-form-urlencoded"
    session = curl_requests.Session(impersonate="chrome")
    if cookies:
        for k, v in cookies.items():
            try:
                session.cookies.set(str(k), str(v))
            except Exception:
                pass
    resp = session.request(method, url, headers=req_headers, data=body,
                           timeout=timeout, verify=False)
    return resp, session


def _curl_resolve(url, timeout, method, body, content_type, headers, antibot=False):
    """Perform the request, applying anti-bot solving when requested.

    Returns (status_code, resp_headers, text, content_type, note).
    """
    from urllib.parse import urlparse
    resp, session = _curl_request(url, timeout, method, body, content_type, headers)
    note = ""
    if antibot:
        from src.llm.browser_solver import detect_protection, solve, cookie_bank, browser_fetch
        host = urlparse(url).hostname
        challenge = detect_protection(resp.status_code, dict(resp.headers), dict(session.cookies))
        if challenge:
            cookies = cookie_bank.get(host) or solve(url, challenge)
            if cookies:
                cookie_bank.set(host, cookies)
                resp, session = _curl_request(url, timeout, method, body, content_type, headers, cookies=cookies)
                challenge = detect_protection(resp.status_code, dict(resp.headers), dict(session.cookies))
            if challenge:
                rendered = browser_fetch(url)
                if rendered:
                    return resp.status_code, dict(resp.headers), rendered, "text/html", f"[rendered via browser: {challenge} challenge]"
    status_code = resp.status_code
    resp_headers = dict(resp.headers)
    content_type = resp_headers.get("content-type", "").lower()
    if not any(content_type.startswith(t) for t in _TEXT_TYPES):
        return status_code, resp_headers, f"[non-text content skipped: {content_type}]", content_type, note
    rbody = resp.content
    if len(rbody) > MAX_RESPONSE_SIZE:
        raise RuntimeError(f"Response too large (exceeds {MAX_RESPONSE_SIZE // (1024*1024)}MB limit)")
    try:
        text = rbody.decode("utf-8")
    except UnicodeDecodeError:
        text = rbody.decode("latin-1", errors="replace")
    return status_code, resp_headers, text, content_type, note


def _fetch_raw(url, timeout=DEFAULT_TIMEOUT, method="GET", body=None, content_type=None, headers=None, antibot=False):
    _status, resp_headers, text, ct, note = _curl_resolve(url, timeout, method, body, content_type, headers, antibot)
    if isinstance(text, str) and text.startswith("[non-text"):
        return text, ct, resp_headers
    if note:
        text = f"{note}\n\n{text}"
    return text, ct, resp_headers


def fetch_raw(url, timeout=DEFAULT_TIMEOUT, method="GET", body=None, content_type=None, headers=None, antibot=False):
    status_code, resp_headers, text, ct, note = _curl_resolve(url, timeout, method, body, content_type, headers, antibot)
    if isinstance(text, str) and text.startswith("[non-text"):
        return status_code, resp_headers, text, ct
    if note:
        text = f"{note}\n\n{text}"
    return status_code, resp_headers, text, ct


def fetch_url(url, format="markdown", timeout=DEFAULT_TIMEOUT, offset=1, limit=None,
              method="GET", body=None, content_type=None, headers=None, antibot=False):
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        raw_content, raw_ct, resp_headers = _fetch_raw(url, timeout, method=method, body=body, content_type=content_type, headers=headers, antibot=antibot)
    except Exception as e:
        return f"Error fetching URL: {e}"

    cookies = _truncate_cookies(resp_headers.get("Set-Cookie", resp_headers.get("set-cookie", "")).strip())
    if cookies:
        raw_content = f"Cookies: {cookies}\n\n{raw_content}"

    is_html = "text/html" in raw_ct or "<html" in raw_content[:200].lower()

    if format == "markdown":
        if is_html:
            raw_content = _strip_html_non_content(raw_content)
            raw_content = _html_to_markdown(raw_content)
    else:
        pass

    if offset > 1 or limit is not None:
        lines = raw_content.splitlines(keepends=True)
        total = len(lines)
        start = max(0, offset - 1)
        end = start + limit if limit else total
        sliced = lines[start:end]
        shown = len(sliced)
        shown_end = offset + shown - 1 if shown > 0 else offset
        header = f"[{total} lines total, showing lines {offset}-{shown_end}]"
        return header + "\n" + "".join(sliced)

    return raw_content


def web_search(query, num_results=10):
    result = _exa_search(query, num_results)
    if result is not None:
        return result
    import time
    html = _ddg_search(query)
    if html is None:
        return f"Search failed for '{query}'. Try again later."
    results = _parse_ddg_results(html, num_results)
    if not results:
        return f"No results found for '{query}'."
    lines = [f"Web search results for '{query}':"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        lines.append(f"   {r['url']}")
    return "\n".join(lines)


def _parse_exa_results(text):
    results = []
    for block in text.split("\n---"):
        block = block.strip()
        if not block:
            continue
        title = ""
        url = ""
        snippet_parts = []
        in_highlights = False
        for line in block.split("\n"):
            stripped = line.strip()
            if stripped.startswith("Title:"):
                title = stripped[6:].strip()
            elif stripped.startswith("URL:"):
                url = stripped[4:].strip()
            elif stripped.startswith("Published:") or stripped.startswith("Author:"):
                continue
            elif stripped.startswith("Highlights:"):
                in_highlights = True
            elif in_highlights:
                hl = stripped
                if hl.startswith(">"):
                    hl = hl[1:].strip()
                if hl == "...":
                    continue
                if hl:
                    snippet_parts.append(hl)
        if not title or not url:
            continue
        snippet = " ".join(snippet_parts[:3])
        snippet = snippet.replace("--", " ").replace("#", " ")
        if snippet.lower().startswith(title.lower()):
            snippet = snippet[len(title):].strip()
        snippet = " ".join(snippet.split())[:150].strip()
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _exa_search(query, num_results):
    text = _mcp_call(_EXA_MCP, _EXA_TOOL, {
        "query": query,
        "type": "auto",
        "numResults": num_results,
        "livecrawl": "fallback",
    })
    if not text:
        return None
    results = _parse_exa_results(text)
    if not results:
        return None
    lines = [f"Web search results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        if r["snippet"]:
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   {r['url']}\n")
        else:
            lines.append(f"{i}. {r['title']}\n   {r['url']}\n")
            lines.append(f"\n{i}. {r['title']}\n   {r['url']}")
    return "\n".join(lines)


def _ddg_search(query, retries=2):
    import time
    user_agents = [
        _CHROME_UA,
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        _ELWAND_UA,
    ]
    for attempt in range(retries):
        ua = user_agents[attempt % len(user_agents)]
        try:
            resp = requests.post(
                _DDG_URL,
                data={"q": query},
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
                timeout=15,
            )
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
            continue
        if resp.status_code in (200, 202) and hasattr(resp, "text"):
            html = resp.text
            if '<a rel="nofollow"' in html or "result-link" in html or "result-snippet" in html:
                return html
            if '<td class="result-snippet"' in html or '<td class=\'result-snippet\'>' in html:
                return html
            if resp.status_code == 202 and "anomaly-modal" in html:
                if attempt < retries - 1:
                    time.sleep(3)
                    continue
        if attempt < retries - 1:
            time.sleep(2)
    return None


def _parse_ddg_results(html, max_results):
    results = []
    links = re.findall(
        r'''<a[^>]*rel=["']nofollow["'][^>]*href=["'](https?://[^"']+)["'][^>]*>(.*?)</a>''',
        html,
        re.DOTALL,
    )
    snippets = re.findall(
        r"""<td class=["']result-snippet["']>(.*?)</td>""",
        html,
        re.DOTALL,
    )

    for i, (url, title) in enumerate(links):
        if len(results) >= max_results:
            break
        title = re.sub(r"<[^>]+>", "", title).strip()
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
        results.append({"title": title, "url": url, "snippet": snippet})

    return results
