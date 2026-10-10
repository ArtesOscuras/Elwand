import time
import tkinter as tk

from src.gui import fonts, theme
from .base import BaseView
from src.tools.scanner import wifi_monitor

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"


class WifiDetailView(BaseView):
    name = "wifi_detail"
    description = "WiFi network detail view"

    def __init__(self, parent, network, **kwargs):
        self._network = dict(network or {})
        self._bssid = self._network.get("bssid", "")
        self._ssid = self._network.get("ssid", "")
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
            font=fonts.view_font_bold(22), fg=BRIGHT, bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind(
            "<Enter>", lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>", lambda e: self._title_label.config(font=fonts.view_font_bold(22)))
        self._on_back_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=(220, 20), pady=(0, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame, bg="#000000", fg=BRIGHT, cursor="",
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("stale", foreground="#cc3333")
        self.text.tag_configure("info", foreground=INFO)
        self.text.tag_configure("success", foreground=SUCCESS)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))

        inner = tk.Frame(btn_frame, bg="#000000")
        inner.pack(anchor="center")

        self._lock_btn = theme.button(inner, "  Lock channel  ",
                                      command=self._toggle_lock)
        self._lock_btn.pack(side=tk.LEFT, padx=(0, 10))

        op_btn = theme.button(inner, "  Wifi operator  ",
                              command=self._open_wifi_operator)
        op_btn.pack(side=tk.LEFT, padx=(0, 10))

        back_btn = theme.button(inner, "  \u2190 Back  ",
                                command=lambda: self._on_back_click and self._on_back_click())
        back_btn.pack(side=tk.LEFT)

        self._poll_id = None

    def on_activate(self):
        self._poll()

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _open_wifi_operator(self):
        top = self.winfo_toplevel()
        fn = getattr(top, "_cmd_use_wifioperator", None)
        if callable(fn):
            fn([])

    def _toggle_lock(self):
        chan = self._network.get("chan")
        if not chan:
            return
        if wifi_monitor.is_locked() and wifi_monitor.locked_channel() == chan:
            wifi_monitor.unlock_channel()
        else:
            wifi_monitor.lock_channel(chan)
        self._update_lock_btn()

    def _update_lock_btn(self):
        if not wifi_monitor.monitor_supported():
            self._lock_btn.pack_forget()
            return
        chan = self._network.get("chan")
        if not chan:
            self._lock_btn.config(text="  No channel  ", fg=MUTED)
            return
        if wifi_monitor.is_locked() and wifi_monitor.locked_channel() == chan:
            self._lock_btn.config(text="  Unlock channel  ", fg=INFO)
        else:
            self._lock_btn.config(text=f"  Lock channel {chan}  ", fg=BRIGHT)

    @staticmethod
    def _pmf_label(pmf):
        return {
            "required": "required (802.11w)",
            "capable": "capable (802.11w)",
            "no": "no",
        }.get(pmf, "-")

    def _poll(self):
        self._refresh()
        self._poll_id = self.after(2000, self._poll)

    def _refresh(self):
        net = self._network
        for n in wifi_monitor.get_networks():
            if self._bssid and n.get("bssid") == self._bssid:
                net = n
                self._network = n
                self._ssid = n.get("ssid", self._ssid)
                break

        title = self._ssid
        if not title or title == "(hidden)":
            title = f"(hidden) {self._bssid}"
        self._title_label.config(text=title)

        probes = wifi_monitor.probes_for(
            ssid=self._ssid if self._ssid != "(hidden)" else None,
            bssid=self._bssid)

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        rows = [
            ("SSID", net.get("ssid", "") or "-"),
            ("BSSID", net.get("bssid", "") or "-"),
            ("Signal", f"{net.get('signal', 0)}%" if net.get("signal") else "-"),
            ("Security", net.get("security", "") or "-"),
            ("PMF", self._pmf_label(net.get("pmf"))),
            ("Channel", str(net.get("chan", "") or "-")),
            ("Frequency", net.get("freq", "") or "-"),
            ("Interface", net.get("device", "") or "-"),
        ]
        if net.get("signal_dbm") is not None:
            rows.append(("Live signal", f"{net.get('signal_dbm')} dBm"))
        label_w = max(len(r[0]) for r in rows) + 2
        value_tag = "stale" if net.get("stale") else "bright"
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value}\n", value_tag)

        self.text.insert(tk.END, "\nProbes:\n", "info")
        if wifi_monitor.is_running():
            svc = wifi_monitor.get_service()
            self.text.insert(tk.END, f"  monitoring on {svc.iface or '...'}\n", "muted")
            if probes:
                self.text.insert(tk.END, f"  {len(probes)} client(s) probing this network\n", "muted")
                for p in probes:
                    self._insert_probe(p)
            else:
                self.text.insert(tk.END, "  No probes captured yet.\n", "muted")
        elif wifi_monitor.is_macos():
            self.text.insert(tk.END, "  Probe capture requires root permissions in Mac OS.\n", "muted")
        elif not wifi_monitor.capture_supported():
            self.text.insert(tk.END, "  Probe capture requires Linux with a monitor-mode adapter.\n", "muted")
        else:
            self.text.insert(tk.END, "  Probe capture requires root (WiFi Monitor off).\n", "muted")

        self.text.configure(state=tk.DISABLED)
        self._update_lock_btn()

    def _insert_probe(self, p):
        ts = time.strftime("%H:%M:%S", time.localtime(p.get("last_seen", 0)))
        sig = p.get("signal")
        sig_text = f"{sig} dBm" if sig is not None else "n/a"
        mac_tag = "stale" if p.get("stale") else "bright"
        self.text.insert(tk.END, f"  {p['mac']}", mac_tag)
        self.text.insert(tk.END, f"  {sig_text}", "muted")
        self.text.insert(tk.END, f"  {ts}\n", "muted")
