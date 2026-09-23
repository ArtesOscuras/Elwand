import base64
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlparse

from src.tools.scanner.identifier import _dbg
from src.machines import store
from src.machines import machine_db
from src.machines import domain_db
from .browsers import find_browsers, BrowserSelector
from .cdp import CDPClient
from .evidence import save_session_meta, update_session_count, save_request, target_dir

from src.elwand_paths import chrome_profile_dir as _chrome_profile_dir

DEBUG_PORT = 9222
USER_DATA_DIR = str(_chrome_profile_dir())


class Recorder:
    def __init__(self, target, browser_path, on_log=None, evidence_name=None, scope=None,
                 review_mode=False, on_review_request=None):
        self._target = target
        self._browser_path = browser_path
        self._on_log = on_log
        self._evidence_name = evidence_name or target
        self._scope = scope
        self._review_mode = review_mode
        self._on_review_request = on_review_request
        self._browser_proc = None
        self._cdp = None
        self._stop_flag = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _log(self, text, color=None):
        if self._on_log:
            self._on_log(text, color)

    @staticmethod
    def _short_url(url):
        if len(url) > 80:
            return url[:80] + "..."
        return url

    @staticmethod
    def _should_fetch_body(method):
        return method in ("POST", "PUT", "PATCH")

    def _try_fetch_post_data(self, r, rid, stage):
        if not self._should_fetch_body(r.get("method", "")):
            return
        if r.get("postData"):
            return
        try:
            result = self._cdp.call("Network.getRequestPostData", {"requestId": rid})
            if result and result.get("postData"):
                r["postData"] = result.get("postData", "")
                _dbg(f"[webrecorder] postData fetched [{stage}] rid={rid} method={r['method']} len={len(r['postData'])}")
            else:
                _dbg(f"[webrecorder] postData empty [{stage}] rid={rid} method={r['method']} url={r.get('url','')[:80]}")
        except Exception as e:
            _dbg(f"[webrecorder] postData error [{stage}] rid={rid}: {e}")

    def _run(self):
        url = self._target if "://" in self._target else f"http://{self._target}"
        tdir = target_dir(self._evidence_name)
        _dbg(f"[webrecorder] target={self._target} evidence={self._evidence_name} browser={self._browser_path}")

        self._log(f"\nStarting webrecorder: {self._target}\n", "info")

        try:
            import urllib.request
            try:
                old = urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
                old.close()
                self._log(f"Port {DEBUG_PORT} busy, killing previous instance...\n", "warning")
                subprocess.run(["pkill", "-f", f"remote-debugging-port={DEBUG_PORT}"],
                               timeout=5, capture_output=True)
            except Exception:
                pass

            self._browser_proc = subprocess.Popen([
                self._browser_path,
                f"--remote-debugging-port={DEBUG_PORT}",
                "--remote-allow-origins=*",
                f"--user-data-dir={USER_DATA_DIR}",
                "--new-window", "about:blank",
                "--no-first-run", "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--disable-restore-session-state",
                "--disable-features=WelcomePage,ChromeWhatsNewUI",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            time.sleep(2)

            cdp_url = self._get_cdp_url()
            _dbg(f"[webrecorder] cdp_url={cdp_url}")
            if not cdp_url:
                self._log(f"Could not connect to browser CDP on port {DEBUG_PORT}\n", "error")
                return

            self._cdp = CDPClient(cdp_url)

            meta = save_session_meta(tdir, self._evidence_name, os.path.basename(self._browser_path))
            self._log(f"Recording to {tdir}\n")
            self._log(f"Browser active — navigate freely. Use 'webrecorder stop' when done.\n")

            requests = {}
            extra_info = {}
            index = 0
            navigations = []
            certs = []

            cdp_commands = [
                ("Network.enable", {"maxTotalBufferSize": 100000000,
                                     "maxResourceBufferSize": 50000000,
                                     "maxPostDataSize": 65536}),
                ("Network.setCacheDisabled", {"cacheDisabled": True}),
                ("Page.enable", {}),
                ("Security.enable", {}),
            ]
            for cmd, cmd_params in cdp_commands:
                self._cdp.send(cmd, cmd_params)

            if self._review_mode:
                _dbg("[review] sending Fetch.enable (Document/XHR/Fetch, both stages)")
                self._cdp.send("Fetch.enable", {
                    "patterns": [
                        {"urlPattern": "*", "requestStage": "Request", "resourceType": "Document"},
                        {"urlPattern": "*", "requestStage": "Request", "resourceType": "XHR"},
                        {"urlPattern": "*", "requestStage": "Request", "resourceType": "Fetch"},
                        {"urlPattern": "*", "requestStage": "Response", "resourceType": "Document"},
                        {"urlPattern": "*", "requestStage": "Response", "resourceType": "XHR"},
                        {"urlPattern": "*", "requestStage": "Response", "resourceType": "Fetch"},
                    ],
                })
                self._log("Review mode enabled (Document, XHR, Fetch)\n", "info")

            self._cdp.send("Page.navigate", {"url": url})

            for event in self._cdp.events():
                if self._stop_flag.is_set():
                    break

                method = event.get("method")
                params = event.get("params", {})
                req_id = params.get("requestId", "")

                if method == "Network.requestWillBeSent":
                    redirect = params.get("redirectResponse")
                    if redirect:
                        redirect_url = redirect.get("url", "")
                        redirect_status = redirect.get("status", 302)
                        for rid, r in list(requests.items()):
                            if r["url"] == redirect_url:
                                r["status"] = redirect_status
                                r["redirectStatus"] = redirect_status
                                r["respHeaders"] = dict(redirect.get("headers", {}))
                                r["mimeType"] = redirect.get("mimeType", "")
                                set_cookie = r["respHeaders"].get("set-cookie") or r["respHeaders"].get("Set-Cookie") or ""
                                r["respCookies"] = self._parse_cookies(set_cookie)

                                index += 1
                                save_request(tdir, index,
                                             {"url": r["url"], "method": r["method"],
                                              "headers": r["headers"], "postData": r.get("postData", ""),
                                              "cookies": r.get("cookies", []),
                                              "timing": r.get("timing", 0)},
                                             {"status": r["status"],
                                              "headers": r["respHeaders"],
                                              "mimeType": r.get("mimeType", ""),
                                              "cookies": r.get("respCookies", [])},
                                             b"")
                                self._log(f"  [{r['status']}] {r['method']} {self._short_url(r['url'])} (redirect)\n", "info")
                                del requests[rid]
                                update_session_count(tdir, index)
                                self._save_url_to_inventory(r["url"])
                                _dbg(f"[webrecorder] redirect saved [{r['method']}] {r['url'][:80]} status={r['status']} postData_len={len(r.get('postData',''))}")
                                break

                    req = params.get("request", {})
                    requests[req_id] = {
                        "url": req.get("url", ""),
                        "method": req.get("method", "GET"),
                        "headers": dict(req.get("headers", {})),
                        "postData": req.get("postData", ""),
                        "cookies": [],
                        "timing": params.get("wallTime", 0),
                        "respHeaders": {},
                        "respCookies": [],
                        "status": 0,
                        "mimeType": "",
                        "redirectStatus": 0,
                    }
                    self._save_url_to_inventory(requests[req_id]["url"])

                elif method == "Network.requestWillBeSentExtraInfo":
                    if req_id in requests:
                        headers = dict(params.get("headers", {}))
                        cookie_header = headers.get("Cookie") or headers.get("cookie") or ""
                        requests[req_id]["cookies"] = self._parse_cookies(cookie_header)
                    extra_info.setdefault(req_id, {})
                    extra_info[req_id]["reqHeaders"] = dict(params.get("headers", {}))

                elif method == "Network.responseReceived":
                    resp = params.get("response", {})
                    if req_id in requests:
                        r = requests[req_id]
                        r["status"] = resp.get("status", 0)
                        r["respHeaders"] = dict(resp.get("headers", {}))
                        r["mimeType"] = resp.get("mimeType", "")
                        sec = resp.get("securityDetails")
                        if sec:
                            _dbg(f"[webrecorder] securityDetails for {r['url']}: {json.dumps(sec, default=str)[:500]}")
                            if sec.get("subjectName"):
                                self._save_cert(tdir, certs, {
                                "subject": sec.get("subjectName", ""),
                                "issuer": sec.get("issuer", ""),
                                "validFrom": sec.get("validFrom", 0),
                                "validTo": sec.get("validTo", 0),
                                "protocol": sec.get("protocol", ""),
                                "sanList": sec.get("sanList", []),
                            })

                elif method == "Network.responseReceivedExtraInfo":
                    if req_id in requests:
                        headers = dict(params.get("headers", {}))
                        set_cookie = headers.get("set-cookie") or headers.get("Set-Cookie") or ""
                        requests[req_id]["respHeaders"].update(headers)
                        if set_cookie:
                            requests[req_id]["respCookies"] = self._parse_cookies(set_cookie)

                elif method == "Network.loadingFinished":
                    if req_id in requests:
                        r = requests[req_id]
                        redirect_status = r.get("redirectStatus", 0)
                        body = b""
                        if redirect_status not in (301, 302, 303, 307, 308):
                            try:
                                result = self._cdp.call("Network.getResponseBody",
                                                        {"requestId": req_id})
                                if result:
                                    body_raw = result.get("body", "")
                                    if result.get("base64Encoded"):
                                        body = base64.b64decode(body_raw)
                                    else:
                                        body = body_raw.encode(errors="replace")
                            except Exception:
                                pass

                        if self._should_fetch_body(r["method"]) and not r["postData"]:
                            self._try_fetch_post_data(r, req_id, "loadingFinished")

                        index += 1
                        save_request(tdir, index,
                                     {"url": r["url"], "method": r["method"],
                                      "headers": r["headers"], "postData": r.get("postData", ""),
                                      "cookies": r.get("cookies", []),
                                      "timing": r.get("timing", 0)},
                                     {"status": r.get("status", 0),
                                      "headers": r.get("respHeaders", {}),
                                      "mimeType": r.get("mimeType", ""),
                                      "cookies": r.get("respCookies", [])},
                                     body)

                        self._log(f"  [{r.get('status', '?')}] {r['method']} {self._short_url(r['url'])}\n", "success")
                        del requests[req_id]
                        update_session_count(tdir, index)
                        self._save_url_to_inventory(r["url"])

                elif method == "Network.loadingFailed":
                    if req_id in requests:
                        r = requests[req_id]
                        r["status"] = 0
                        r["error"] = params.get("errorText", "unknown")

                        index += 1
                        save_request(tdir, index,
                                     {"url": r["url"], "method": r["method"],
                                      "headers": r["headers"], "postData": r.get("postData", ""),
                                      "cookies": r.get("cookies", []),
                                      "error": r["error"]},
                                     {"status": 0,
                                      "headers": {},
                                      "mimeType": "",
                                      "cookies": [],
                                      "error": r["error"]},
                                     b"")

                        self._log(f"  [FAIL] {r['method']} {self._short_url(r['url'])} — {r['error']}\n", "error")
                        del requests[req_id]
                        update_session_count(tdir, index)
                        self._save_url_to_inventory(r["url"])

                elif method == "Network.requestServedFromCache":
                    req = params.get("request", {})
                    cached_id = req_id
                    if cached_id not in requests:
                        requests[cached_id] = {
                            "url": req.get("url", ""),
                            "method": req.get("method", "GET"),
                            "headers": dict(req.get("headers", {})),
                            "postData": "",
                            "cookies": [],
                            "timing": params.get("wallTime", 0),
                            "respHeaders": {},
                            "respCookies": [],
                            "status": 200,
                            "mimeType": "",
                        }
                    r = requests[cached_id]
                    r["status"] = 200
                    r["respHeaders"] = {"x-served-from": "cache"}
                    index += 1
                    save_request(tdir, index,
                                 {"url": r["url"], "method": r["method"],
                                  "headers": r["headers"], "postData": r.get("postData", ""),
                                  "cookies": r.get("cookies", []),
                                  "timing": r.get("timing", 0)},
                                 {"status": 200,
                                  "headers": {"x-served-from": "cache"},
                                  "mimeType": r.get("mimeType", ""),
                                  "cookies": []},
                                 b"")
                    self._log(f"  [200] {r['method']} {self._short_url(r['url'])} (cached)\n", "info")
                    del requests[cached_id]
                    update_session_count(tdir, index)
                    self._save_url_to_inventory(r["url"])

                elif method == "Page.frameNavigated":
                    frame = params.get("frame", {})
                    nav_url = frame.get("url", "")
                    if nav_url and nav_url != "about:blank":
                        navigations.append({"url": nav_url, "time": time.time()})
                        with open(os.path.join(tdir, "session.json")) as f:
                            meta = json.load(f)
                        meta["navigations"] = navigations
                        with open(os.path.join(tdir, "session.json"), "w") as f:
                            json.dump(meta, f, indent=2)

                elif method == "Security.certificateError":
                    cert_info = {
                        "eventId": params.get("eventId"),
                        "errorType": params.get("errorType", ""),
                        "requestURL": params.get("requestURL", ""),
                    }
                    certs.append(cert_info)

                elif method == "Fetch.requestPaused":
                    _dbg(f"[review] requestPaused: url={params.get('request',{}).get('url','')[:60]} stage={'Response' if 'responseStatusCode' in params else 'Request'} resourceType={params.get('resourceType','')}")
                    if self._on_review_request:
                        req = params.get("request", {})
                        iid = params.get("requestId", "")
                        frame_id = params.get("frameId", "")
                        req_url = req.get("url", "")
                        req_method = req.get("method", "GET")
                        req_headers = dict(req.get("headers", {}))
                        req_body = req.get("postData", "")
                        res_type = params.get("resourceType", "")
                        net_id = params.get("networkId", "")
                        stage = "Response" if "responseStatusCode" in params else "Request"
                        resp_status = params.get("responseStatusCode")
                        resp_status_text = params.get("responseStatusText", "")
                        resp_headers_list = params.get("responseHeaders", [])
                        resp_headers = {h["name"]: h["value"] for h in resp_headers_list} if resp_headers_list else {}
                        resp_body = ""
                        resp_body_raw = None
                        resp_was_base64 = False
                        if stage == "Response":
                            try:
                                result = self._cdp.call("Fetch.getResponseBody", {"requestId": iid})
                                if result:
                                    raw = result.get("body", "")
                                    resp_was_base64 = result.get("base64Encoded", False)
                                    resp_body_raw = raw
                                    if resp_was_base64:
                                        resp_body = base64.b64decode(raw).decode(errors="replace")
                                    else:
                                        resp_body = raw
                            except Exception as e:
                                _dbg(f"[review] getResponseBody error: {e}")
                        send_it = threading.Event()
                        _s = stage
                        _rt = res_type
                        _fid = frame_id
                        _tdir = tdir
                        _resp_status = resp_status
                        _resp_text = resp_status_text
                        _resp_headers = resp_headers
                        _resp_body_orig = resp_body
                        _resp_body_raw = resp_body_raw
                        _resp_was_base64 = resp_was_base64

                        def on_send(url=None, method=None, headers=None, body=None):
                            try:
                                if _s == "Response":
                                    if body is None:
                                        self._cdp.send("Fetch.continueRequest", {"requestId": iid})
                                    elif _rt == "Document":
                                        self._cdp.send("Fetch.continueRequest", {"requestId": iid})
                                        _dbg(f"[review] Document modified, setDocumentContent len={len(body)}")
                                        time.sleep(0.1)
                                        self._cdp.send("Page.setDocumentContent", {"frameId": _fid, "html": body})
                                    else:
                                        body_bytes = body.encode("utf-8")
                                        body_enc = base64.b64encode(body_bytes).decode()
                                        f_params = {"requestId": iid,
                                                     "responseCode": _resp_status or 200,
                                                     "responsePhrase": _resp_text or "OK",
                                                     "body": body_enc}
                                        merged = dict(_resp_headers or {})
                                        if headers:
                                            merged.update(headers)
                                        clean = {}
                                        for k, v in merged.items():
                                            kl = k.lower()
                                            if kl not in ("content-encoding", "transfer-encoding"):
                                                clean[k] = v
                                        clean["Content-Length"] = str(len(body_bytes))
                                        f_params["responseHeaders"] = [{"name": k, "value": v} for k, v in clean.items()]
                                        _dbg(f"[review] fulfill: {len(clean)} headers, Content-Length={clean['Content-Length']}")
                                        self._cdp.send("Fetch.fulfillRequest", f_params)
                                        time.sleep(0.2)
                                        _dbg(f"[review] fulfill: {len(clean)} headers={list(clean.keys())}, body_len={len(body_enc)}")
                                        try:
                                            with open(os.path.join(_tdir, "body_original.txt"), "w", encoding="utf-8") as f:
                                                f.write(_resp_body_orig or "")
                                            with open(os.path.join(_tdir, "body_modified.txt"), "w", encoding="utf-8") as f:
                                                f.write(body)
                                        except Exception:
                                            pass
                                else:
                                    cr_params = {"requestId": iid}
                                    if url is not None:
                                        cr_params["url"] = url
                                    if method is not None:
                                        cr_params["method"] = method
                                    if headers:
                                        cr_params["headers"] = [{"name": k, "value": v} for k, v in headers.items()]
                                    if body is not None:
                                        cr_params["postData"] = body
                                    self._cdp.send("Fetch.continueRequest", cr_params)
                            except Exception as e:
                                _dbg(f"[review] on_send error: {e}")
                                pass
                            send_it.set()

                        _dbg(f"[review] calling on_review_request")
                        self._on_review_request(req_url, req_method, req_headers,
                                                req_body, res_type, net_id, stage, on_send,
                                                resp_status, resp_status_text, resp_headers,
                                                resp_body)
                        _dbg(f"[review] back from on_review_request")
                        send_it.wait()
                        _dbg(f"[review] send_it done")

            self._save_certs_list(tdir, certs)
            update_session_count(tdir, index)
            if not self._stop_flag.is_set():
                self._log(f"\nBrowser closed — recording stopped. {index} requests saved to {tdir}\n", "warning")
            else:
                self._log(f"\nRecording complete. {index} requests saved to {tdir}\n", "success")

        except Exception as e:
            _dbg(f"[webrecorder] error: {e}")
            self._log(f"Recorder error: {e}\n", "error")
        finally:
            if self._cdp:
                try:
                    self._cdp.close()
                except Exception:
                    pass
            self._cdp = None

    def _get_cdp_url(self):
        for _ in range(10):
            try:
                resp = urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=2)
                data = json.loads(resp.read())
                for page in data:
                    if page.get("type") == "page":
                        return page.get("webSocketDebuggerUrl")
            except Exception:
                time.sleep(0.5)
        return None

    def _save_url_to_inventory(self, url):
        parsed = urlparse(url)
        host = parsed.hostname
        path = parsed.path or "/"
        if not host:
            return
        if self._scope:
            scope_host = self._scope
            if not (host == scope_host or host.endswith("." + scope_host)):
                return
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            machine = store.get(host)
            if not machine:
                machine = store.add_or_update(ip=host, method="webrecorder")
                machine.device_type = "device unknown"
                machine_db.save_machine_info(machine)
            machine_db.save_directory(machine.id, path)
        else:
            if not domain_db.exists(host):
                try:
                    info = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
                    ip = info[0][4][0] if info else None
                except Exception:
                    ip = None
                if ip:
                    machine = store.get(ip)
                    if not machine:
                        machine = store.add_or_update(ip=ip, method="webrecorder")
                        machine.device_type = "device unknown"
                        machine_db.save_machine_info(machine)
                else:
                    machine = None
                domain_db.init_or_update(host, machine.id if machine else 0,
                                         machine.ip if machine else "", "webrecorder")
                if machine:
                    machine_db.save_domain(machine.id, host, "webrecorder")
            domain_db.save_directory(host, path)

    @staticmethod
    def _parse_cookies(text):
        if not text:
            return []
        result = []
        for part in text.split(";"):
            part = part.strip()
            if "=" in part:
                key, val = part.split("=", 1)
                result.append({"name": key.strip(), "value": val.strip()})
        return result

    @staticmethod
    def _save_cert(tdir, certs, cert_info):
        key = cert_info.get("subject", "")
        for c in certs:
            if c.get("subject") == key:
                return
        if key:
            certs.append(cert_info)

    @staticmethod
    def _save_certs_list(tdir, certs):
        _dbg(f"[webrecorder] _save_certs_list called, certs={len(certs)}")
        if not certs:
            return
        path = os.path.join(tdir, "session.json")
        if os.path.isfile(path):
            with open(path) as f:
                meta = json.load(f)
            meta["certificates"] = certs
            with open(path, "w") as f:
                json.dump(meta, f, indent=2)
            _dbg(f"[webrecorder] certificates saved to session.json")

    def kill_browser(self):
        if self._browser_proc:
            try:
                self._browser_proc.kill()
            except Exception:
                pass
            self._browser_proc = None
