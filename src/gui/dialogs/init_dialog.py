from src.gui import fonts, windowing
import os
import platform
import sys
import threading
import tkinter as tk

SUCCESS = "#00cc66"
FAIL = "#f44747"
WARN = "#ce9178"
BRIGHT = "#ffffff"
MUTED = "#888888"
INFO = "#5ba3ec"

_checks_order = []

from src import info as _info
_info.set("platform", sys.platform)
_info.set("platform_name", platform.system())


def _has_list(name):
    from src.wordlist_download import is_installed
    try:
        return is_installed(name)
    except Exception:
        return False


def _has_rockyou():
    return _has_list("rockyou")


def _has_usernames():
    return _has_list("usernames")


def _checks():
    # --- System ---
    is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
    yield _check("root", "Root", lambda: is_root, kind="system", critical=False,
                 detail="yes" if is_root else "no")
    yield _check("python_version", f"Python {platform.python_version()}",
                 lambda: sys.version_info >= (3, 11),
                 kind="system", critical=True)
    yield _check("platform", f"Platform: {platform.system()}",
                 lambda: sys.platform in ("linux", "darwin"),
                 kind="system", critical=True,
                 detail=platform.system())

    # --- Python dependencies ---
    yield _check("scapy", "scapy", lambda: _has_module("scapy"), kind="python", critical=True)
    yield _check("zeroconf", "zeroconf", lambda: _has_module("zeroconf"), kind="python", critical=True)
    yield _check("impacket", "impacket", lambda: _has_module("impacket"), kind="python", critical=True)
    yield _check("websocket", "websocket-client", lambda: _has_module("websocket"), kind="python", critical=True)
    yield _check("pillow", "Pillow", lambda: _has_module("PIL"), kind="python", critical=True)
    yield _check("paramiko", "paramiko", lambda: _has_module("paramiko"), kind="python", critical=False)

    # --- Network interfaces ---
    yield _check("network_ifaces", "Network interfaces",
                 lambda: _check_interfaces(),
                 kind="system", critical=True,
                 detail=str(len(_list_interfaces())))

    # --- Binaries ---
    yield _check("nmap_bin", "nmap", lambda: _resolve_binary("nmap")[0], kind="binary", critical=False)
    yield _check("hashcat", "hashcat", lambda: _resolve_binary("hashcat")[0], kind="binary", critical=False)
    yield _check("hydra", "hydra", lambda: _resolve_binary("hydra")[0], kind="binary", critical=False)
    yield _check("whatweb", "whatweb", lambda: _resolve_binary("whatweb")[0], kind="binary", critical=False)
    yield _check("xfreerdp", "xfreerdp", lambda: _resolve_binary("xfreerdp")[0], kind="binary", critical=False)
    yield _check("tcpdump", "tcpdump", lambda: _resolve_binary("tcpdump")[0], kind="binary", critical=False)
    yield _check("browsers", "Chromium browser", lambda: _browser_check()[0], kind="binary", critical=False)

    # --- Wordlists ---
    yield _check("rockyou", "rockyou.txt wordlist",
                 lambda: _has_rockyou(),
                 kind="wordlist", critical=False,
                 detail="installed" if _has_rockyou() else "not installed (download lists)")
    yield _check("usernames", "usernames.txt wordlist",
                 lambda: _has_usernames(),
                 kind="wordlist", critical=False,
                 detail="installed" if _has_usernames() else "not installed (download lists)")


def _check(key, label, fn, kind="", critical=False, detail=""):
    return {"key": key, "label": label, "fn": fn, "kind": kind, "critical": critical, "detail": detail}


def _has_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _resolve_binary(name):
    from src.resolve_binary import resolve
    found = resolve(name)
    if found:
        from src.info import set as info_set
        info_set(f"{name}_path", found)
    return (True, found) if found else (False, "")


def _browser_check():
    from src.tools.webrecorder.browsers import find_browsers
    browsers = find_browsers()
    if browsers:
        return True, list(browsers.keys())[0]
    return False, ""


def _list_interfaces():
    from src.network_iface import interfaces, ifaddresses, AF_INET
    result = []
    for iface in interfaces():
        if iface == "lo0":
            continue
        addrs = ifaddresses(iface).get(AF_INET)
        if addrs:
            result.append(iface)
    return result


def _check_interfaces():
    return len(_list_interfaces()) > 0


def run_checks():
    results = []
    for item in _checks():
        try:
            result = item["fn"]()
            results.append({"key": item["key"], "label": item["label"],
                           "ok": result, "kind": item.get("kind", ""),
                           "critical": item["critical"], "detail": item.get("detail", "")})
        except Exception as e:
            results.append({"key": item["key"], "label": item["label"],
                           "ok": False, "kind": item.get("kind", ""),
                           "critical": item["critical"], "detail": item.get("detail", ""),
                           "error": str(e)})
    return results


class InitDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Elwand — Initialization Check")
        windowing.size_dialog(self, 780, 620)
        self.configure(bg="#111111")
        self.resizable(False, False)

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#111111")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5), padx=15)

        tk.Label(
            header,
            text="System Checks",
            font=fonts.view_font_bold(18),
            fg=BRIGHT,
            bg="#111111",
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Checking dependencies and system capabilities...",
            font=fonts.view_font(10),
            fg=MUTED,
            bg="#111111",
        ).pack(anchor="w", pady=(2, 0))

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(5, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000",
            fg=BRIGHT,
            font=fonts.view_font(11),
            borderwidth=0,
            highlightthickness=0,
            state=tk.DISABLED,
            cursor="",
            wrap=tk.WORD,
            pady=8,
            padx=10,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("success", foreground=SUCCESS)
        self.text.tag_configure("fail", foreground=FAIL)
        self.text.tag_configure("warn", foreground=WARN)
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)
        self.text.tag_configure("bold", font=fonts.view_font_bold(11))

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))

        btn_inner = tk.Frame(btn_frame, bg="#111111")
        btn_inner.pack(expand=True)

        self._dl_btn = tk.Label(
            btn_inner, text="  Download lists  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        self._dl_btn.pack(side=tk.LEFT, padx=(0, 10))
        self._dl_btn.bind("<Button-1>", lambda e: self._start_download())
        self._dl_btn.bind("<Enter>", lambda e: self._dl_btn.config(bg="#333333"))
        self._dl_btn.bind("<Leave>", lambda e: self._dl_btn.config(bg="#222222"))
        self._dl_btn.pack_forget()

        self._ok_btn = tk.Label(
            btn_inner, text="  Continue  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        self._ok_btn.pack(side=tk.LEFT)
        self._ok_btn.bind("<Button-1>", lambda e: self.destroy())
        self._ok_btn.bind("<Enter>", lambda e: self._ok_btn.config(bg="#333333"))
        self._ok_btn.bind("<Leave>", lambda e: self._ok_btn.config(bg="#222222"))

        self._failed_critical = False
        self._total = 0
        self._done = 0

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Return>", lambda e: self.destroy())
        self.after(50, self._start_checks)

    def _start_checks(self):
        threading.Thread(target=self._run_checks, daemon=True).start()

    def _run_checks(self):
        results = run_checks()
        self._total = len(results)
        self._done = 0
        self._failed_critical = False
        self._last_kind = None

        for r in results:
            self._done += 1
            self._show_result(r)

        self.after(0, self._finish)

    def _show_result(self, r):
        def _insert():
            if not self.winfo_exists():
                return
            self.text.configure(state=tk.NORMAL)
            key = r["key"]
            label = r["label"]
            ok = r["ok"]
            critical = r["critical"]
            kind = r.get("kind", "")

            if kind and kind != self._last_kind:
                self._last_kind = kind
                self.text.insert(tk.END, "\n", "bright")
                self.text.insert(tk.END, f"  \u2500\u2500 {kind.upper()} \u2500\u2500\n", "info")
                self.text.insert(tk.END, "\n", "bright")

            line = f"  [{self._done}/{self._total}] "
            self.text.insert(tk.END, line, "muted")

            if ok:
                marker = "[OK]"
                tag = "success"
            elif critical:
                marker = "[FAIL]"
                tag = "fail"
                self._failed_critical = True
            else:
                marker = "[WARN]"
                tag = "warn"

            self.text.insert(tk.END, f"{marker} ", tag)
            self.text.insert(tk.END, f"{label}", "bright")
            if r.get("detail"):
                self.text.insert(tk.END, f" : {r['detail']}", "info")
            self.text.insert(tk.END, "\n")
            if r.get("kind"):
                self.text.insert(tk.END, f"        ({r['kind']})\n", "muted")

            if "error" in r:
                self.text.insert(tk.END, f"        {r['error']}\n", "fail")

            self.text.see(tk.END)
            self.text.configure(state=tk.DISABLED)

            from src.info import set as info_set
            info_set(key, ok)

        self.after(0, _insert)

    def _start_download(self):
        self._dl_btn.config(text="  Downloading...  ")
        self._dl_btn.unbind("<Button-1>")
        self._log("\n", "bright")
        self._log("  Downloading wordlists...\n", "info")
        threading.Thread(target=self._run_download, daemon=True).start()

    def _run_download(self):
        from src.wordlist_download import download, any_missing, is_installed
        missing = any_missing()
        if not missing:
            self.after(0, lambda: self._log("  All lists already installed.\n", "muted"))
            self.after(200, self._start_checks)
            return

        failed = []
        for name in missing:
            self.after(0, lambda n=name: self._log(
                f"\n  [{n}.txt]\n", "info"))
            try:
                last_pct = [-1]
                def progress(pct):
                    if pct - last_pct[0] >= 25:
                        last_pct[0] = pct
                        self.after(0, lambda p=pct, n=name: self._log(
                            f"  {n}.txt ... {p}%\n", "muted"))
                download(name, on_progress=progress)
                if is_installed(name):
                    self.after(0, lambda n=name: self._log(
                        f"  {n}.txt  Done. ✓\n", "success"))
                else:
                    raise RuntimeError("verification failed")
            except Exception as e:
                failed.append(name)
                self.after(0, lambda n=name, e=str(e): self._log(
                    f"  {n}.txt  Failed: {e}\n", "fail"))

        if failed:
            self.after(0, lambda: self._log(
                f"\n  {len(missing) - len(failed)}/{len(missing)} lists installed.\n", "muted"))
            self.after(0, lambda: (
                self._dl_btn.config(text="  Retry download  "),
                self._dl_btn.bind("<Button-1>", lambda e: self._start_download()),
            ))
        else:
            self.after(0, lambda: self._log(
                f"\n  {len(missing)} list(s) installed.\n", "success"))
            self.after(200, lambda: (
                self.text.configure(state=tk.NORMAL),
                self.text.delete("1.0", tk.END),
                self.text.configure(state=tk.DISABLED),
            ))
            self.after(600, self._start_checks)

    def _log(self, text, tag=None):
        if not self.winfo_exists():
            return
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, text, tag if tag else "bright")
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def _finish(self):
        if not self.winfo_exists():
            return
        def _ui():
            self.text.configure(state=tk.NORMAL)
            self.text.insert(tk.END, "\n")
            self.text.insert(tk.END, "\u2500" * 58 + "\n", "muted")
            if self._failed_critical:
                self.text.insert(tk.END, "  WARNING: Critical dependencies missing!\n", "fail")
                self.text.insert(tk.END, "  Some features will not work properly.\n", "warn")
            else:
                passed = self._total
                self.text.insert(tk.END, f"  All {passed} checks complete.", "success")
            self.text.insert(tk.END, "\n")
            self.text.see(tk.END)
            self.text.configure(state=tk.DISABLED)

            from src.wordlist_download import any_missing
            try:
                missing = bool(any_missing())
            except Exception:
                missing = False
            if missing:
                self._dl_btn.pack(side=tk.LEFT, padx=(0, 10),
                                   before=self._ok_btn)
            else:
                self._dl_btn.pack_forget()

        self.after(0, _ui)
