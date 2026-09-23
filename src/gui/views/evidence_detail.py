from src.gui import fonts
import json
import os
import tkinter as tk
from .base import BaseView
from src.elwand_paths import evidence_dir as _evidence_dir

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"


def _get_evidence_dir():
    return str(_evidence_dir())


def _load_evidence(name):
    base = _get_evidence_dir()
    session_path = os.path.join(base, name, "session.json")
    if not os.path.isfile(session_path):
        return None
    with open(session_path) as f:
        return json.load(f)


def _list_requests(name):
    base = _get_evidence_dir()
    target_dir = os.path.join(base, name)
    results = []
    if os.path.isdir(target_dir):
        for rdir in sorted(os.listdir(target_dir)):
            rpath = os.path.join(target_dir, rdir)
            if os.path.isdir(rpath):
                req_f = os.path.join(rpath, "request.json")
                resp_f = os.path.join(rpath, "response.json")
                body_f = os.path.join(rpath, "body.html")
                if os.path.isfile(req_f):
                    with open(req_f) as f:
                        req = json.load(f)
                else:
                    req = {}
                if os.path.isfile(resp_f):
                    with open(resp_f) as f:
                        resp = json.load(f)
                else:
                    resp = {}
                body = ""
                if os.path.isfile(body_f):
                    try:
                        with open(body_f) as f:
                            body = f.read()
                    except Exception:
                        pass
                results.append((req, resp, body))
    return results


class _RequestDetailDialog(tk.Toplevel):
    def __init__(self, parent, req, resp, body):
        super().__init__(parent)
        self.title("Request Detail")
        self.geometry("900x650")
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#111111")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5), padx=15)

        method = req.get("method", "?")
        url = req.get("url", "")
        status = resp.get("status", "?")

        tk.Label(
            header, text=f"[{status}] {method} {url}",
            font=fonts.view_font_bold(13),
            fg=SUCCESS if status != 0 and status != "?" else "#f44747",
            bg="#111111",
            wraplength=850,
        ).pack(anchor="w")

        content_frame = tk.Frame(self, bg="#000000")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(5, 10))
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            content_frame,
            bg="#000000", fg=BRIGHT,
            font=fonts.view_font(11),
            borderwidth=0, highlightthickness=0,
            state=tk.NORMAL, cursor="",
            wrap=tk.WORD, pady=10, padx=10,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(content_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("section", foreground=INFO, font=fonts.view_font_bold(12))
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("code", foreground="#ce9178")

        self._populate(req, resp, body)

        self.text.configure(state=tk.DISABLED)

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=2, column=0, pady=(0, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack()
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _populate(self, req, resp, body):
        method = req.get("method", "?")
        url = req.get("url", "")
        status = resp.get("status", "?")

        self.text.insert(tk.END, "\u2500\u2500\u2500 Request \u2500\u2500\u2500\n", "section")
        self.text.insert(tk.END, f"Method:  {method}\n", "bright")
        self.text.insert(tk.END, f"URL:     {url}\n", "bright")

        headers = req.get("headers", {})
        if headers:
            self.text.insert(tk.END, "\nRequest Headers:\n", "section")
            for k, v in headers.items():
                self.text.insert(tk.END, f"  {k}: {v}\n", "muted")

        cookies = req.get("cookies", [])
        if cookies:
            self.text.insert(tk.END, "\nRequest Cookies:\n", "section")
            for c in cookies:
                self.text.insert(tk.END, f"  {c.get('name', '')} = {c.get('value', '')}\n", "muted")

        post_data = req.get("postData", "")
        if post_data:
            self.text.insert(tk.END, "\nRequest Body:\n", "section")
            self.text.insert(tk.END, f"{post_data}\n", "code")

        self.text.insert(tk.END, "\n\u2500\u2500\u2500 Response \u2500\u2500\u2500\n", "section")
        self.text.insert(tk.END, f"Status:     {status}\n", "bright")
        mime = resp.get("mimeType", "")
        if mime:
            self.text.insert(tk.END, f"MIME Type:  {mime}\n", "bright")

        resp_error = resp.get("error", "")
        if resp_error:
            self.text.insert(tk.END, f"Error:      {resp_error}\n", "#f44747")

        resp_headers = resp.get("headers", {})
        if resp_headers:
            self.text.insert(tk.END, "\nResponse Headers:\n", "section")
            for k, v in resp_headers.items():
                self.text.insert(tk.END, f"  {k}: {v}\n", "muted")

        resp_cookies = resp.get("cookies", [])
        if resp_cookies:
            self.text.insert(tk.END, "\nResponse Cookies:\n", "section")
            for c in resp_cookies:
                self.text.insert(tk.END, f"  {c.get('name', '')} = {c.get('value', '')}\n", "muted")

        if body:
            self.text.insert(tk.END, "\n\u2500\u2500\u2500 Response Body \u2500\u2500\u2500\n", "section")
            truncated = body[:50000]
            self.text.insert(tk.END, f"{truncated}\n", "code")
            if len(body) > 50000:
                self.text.insert(tk.END, f"\n... truncated ({len(body)} total bytes)\n", "muted")


class EvidenceDetailView(BaseView):
    name = "evidence_detail"
    description = "Evidence session detail"

    def __init__(self, parent, ev_name, **kwargs):
        self._ev_name = ev_name
        super().__init__(parent, **kwargs)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 10))

        self._title_label = tk.Label(
            header, text="",
            font=fonts.view_font_bold(22),
            fg="#ffffff", bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind("<Enter>", lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind("<Leave>", lambda e: self._title_label.config(font=fonts.view_font_bold(22)))
        self._on_back_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=(220, 20), pady=(0, 20))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT,
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, cursor="", wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)
        self.text.tag_configure("success", foreground=SUCCESS)
        self.text.tag_configure("error", foreground="#f44747")

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, pady=(0, 15))

        back_btn = tk.Label(
            btn_frame, text="  \u2190 Back  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.LEFT)
        back_btn.bind("<Button-1>",
                      lambda e: self._on_back_click
                      and self._on_back_click())
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

    def on_activate(self):
        self._refresh()

    def on_deactivate(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _refresh(self):
        meta = _load_evidence(self._ev_name)
        req_list = _list_requests(self._ev_name)

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        self._title_label.config(text=f"Evidence — {self._ev_name}")

        if not meta:
            self.text.insert(tk.END, "No session data found.\n", "muted")
            self.text.configure(state=tk.DISABLED)
            return

        rows = [
            ("Target", meta.get("target", "")),
            ("Browser", meta.get("browser", "")),
            ("Started", (meta.get("started_at", "") or "")[:19].replace("T", " ")),
            ("Ended", (meta.get("ended_at", "") or "")[:19].replace("T", " ")),
            ("Requests", str(meta.get("request_count", 0))),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value or '-'}\n", "bright")

        navs = meta.get("navigations", [])
        if navs:
            self.text.insert(tk.END, f"\nNavigations ({len(navs)}):\n", "info")
            for n in navs:
                self.text.insert(tk.END, f"  {n['url']}\n", "bright")

        certs = meta.get("certificates", [])
        if certs:
            self.text.insert(tk.END, f"\nCertificates ({len(certs)}):\n", "info")
            for c in certs:
                self.text.insert(tk.END, f"  Subject: {c.get('subject', '')}\n", "bright")
                self.text.insert(tk.END, f"  Issuer:  {c.get('issuer', '')}\n", "muted")
                protocol = c.get("protocol", "")
                if protocol:
                    self.text.insert(tk.END, f"  Protocol: {protocol}\n", "muted")
                sans = c.get("sanList", [])
                if sans:
                    self.text.insert(tk.END, f"  SAN: {', '.join(sans)}\n", "muted")
                self.text.insert(tk.END, "\n")

        cookies_req = {}
        cookies_resp = {}
        for req, resp, _body in req_list:
            for c in req.get("cookies", []):
                key = (c.get("name", ""), c.get("value", ""))
                if key[0]:
                    cookies_req[key] = c
            for c in resp.get("cookies", []):
                key = (c.get("name", ""), c.get("value", ""))
                if key[0]:
                    cookies_resp[key] = c
        if cookies_req or cookies_resp:
            self.text.insert(tk.END, f"\nCookies:\n", "info")
            all_names = sorted(set(c.get("name", "") for c in cookies_req.values())
                              | set(c.get("name", "") for c in cookies_resp.values()))
            for name in all_names:
                c = next((x for x in cookies_resp.values() if x.get("name") == name), None)
                c = c or next((x for x in cookies_req.values() if x.get("name") == name), None)
                if not c:
                    continue
                self.text.insert(tk.END, f"  {name:<20} ", "bright")
                val = c.get("value", "")
                if len(val) > 60:
                    val = val[:60] + "..."
                self.text.insert(tk.END, f"{val}\n", "muted")

        if req_list:
            self.text.insert(tk.END, f"\nCaptured requests ({len(req_list)}):\n", "info")
            for i, (req, resp, body) in enumerate(req_list):
                method = req.get("method", "?")
                url = req.get("url", "")
                display_url = url[:65] + "..." if len(url) > 65 else url
                status = resp.get("status", "?")
                tag_color = "success" if status != 0 and status != "?" else "error"
                tag_name = f"req_{i}"

                self.text.tag_configure(tag_name, underline=False)
                self.text.insert(tk.END, f"  [{status}] {method} {display_url}\n", (tag_color, tag_name))
                self.text.tag_bind(tag_name, "<Button-1>", lambda e, r=req, s=resp, b=body: (
                    _RequestDetailDialog(self, r, s, b)))
                self.text.tag_bind(tag_name, "<Enter>", lambda e, t=tag_name: self.text.tag_configure(t, underline=True))
                self.text.tag_bind(tag_name, "<Leave>", lambda e, t=tag_name: self.text.tag_configure(t, underline=False))

        self.text.configure(state=tk.DISABLED)
