import ssl
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .wordlist import load_wordlist
from src import process_registry

TIMEOUT = 5
MAX_WORKERS = 20
SHOW_CODES = {200, 201, 204, 301, 302, 307, 400, 401, 403, 404, 405, 500, 502, 503}
ALL_CODES = list(SHOW_CODES)
USER_AGENT = "Elwand/1.0"

_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE


class FuzzEngine:
    def __init__(self, target, wordlist_path, method, target_ip=None, on_result=None, workers=None, on_progress=None, on_found=None, on_done=None, url_template=None, show_codes=None, hide_size_range=None, scheme="http"):
        self._target = target
        self._wordlist_path = wordlist_path
        self._method = method
        self._target_ip = target_ip
        self._url_template = url_template
        self._scheme = scheme
        self._show_codes = show_codes if show_codes is not None else SHOW_CODES
        self._hide_size_range = hide_size_range if hide_size_range is not None else None
        self._on_result = on_result
        self._on_progress = on_progress
        self._on_found = on_found
        self._on_done = on_done
        self._stop_flag = threading.Event()
        self._executor = None
        self._workers = workers or MAX_WORKERS

    def start(self):
        self._stop_flag.clear()
        pid = process_registry.register(
            "Fuzzer", detail=f"{self._method}  {self._target}")

        def _wrap():
            try:
                self._run()
            finally:
                process_registry.finish(pid)

        threading.Thread(target=_wrap, daemon=True).start()

    def stop(self):
        self._stop_flag.set()

    def _emit(self, text, color=None):
        if self._on_result:
            self._on_result(text, color)

    def _display_word(self, word):
        if self._method == "directory" and self._url_template:
            return self._url_template.replace("FUZZ", word).rsplit("/", 1)[-1]
        return word

    def _run(self):
        words = load_wordlist(self._wordlist_path)
        total = len(words)
        self._emit(f"\n[*] Loaded {total} words\n")

        self._executor = ThreadPoolExecutor(max_workers=self._workers)
        futures = {}
        for word in words:
            if self._stop_flag.is_set():
                break
            fut = self._executor.submit(self._do_request, word)
            futures[fut] = word

        done = 0
        found = 0
        for fut in as_completed(futures):
            if self._stop_flag.is_set():
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._emit("\n[*] Stopped.\n", "success")
                return
            word = futures[fut]
            done += 1
            try:
                status, length = fut.result()
                if status and status in self._show_codes:
                    skip = False
                    if self._hide_size_range:
                        lo, hi = self._hide_size_range
                        if lo <= length <= hi:
                            skip = True
                    if not skip:
                        found += 1
                        display = self._display_word(word)
                        self._emit(f"  [{status}] {display:<40} {length:>6} bytes\n", "success")
                        if self._on_found:
                            self._on_found(word, display)
            except Exception:
                pass
            if done % 50 == 0 and self._on_progress:
                self._on_progress(done, total, found)

        self._executor.shutdown(wait=False)
        if self._on_progress:
            self._on_progress(total, total, found)
        self._emit(f"\n[+] Done. {found} results from {total} requests.\n", "success")
        if self._on_done:
            self._on_done(found)

    def _do_request(self, word):
        req = self._build_request(word)
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context)
            body = resp.read(10240)
            return resp.status, len(body)
        except urllib.request.HTTPError as e:
            body = e.read(10240)
            return e.code, len(body)
        except Exception:
            return None, 0

    def _build_request(self, word):
        method = self._method
        target = self._target
        s = self._scheme
        if method == "directory":
            if self._url_template:
                url = self._url_template.replace("FUZZ", word)
            else:
                url = f"{s}://{target}/{word}/"
            return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        elif method == "vhost":
            ip = self._target_ip or target
            req = urllib.request.Request(
                f"{s}://{ip}/",
                headers={"User-Agent": USER_AGENT, "Host": f"{word}.{target}"},
            )
            return req
        else:
            url = f"{s}://{word}.{target}/"
            return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
