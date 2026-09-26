import threading
import time
import tkinter as tk
import tkinter.font as tkfont

from src.gui import fonts
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav
from src.tools.scanner import wifi_monitor

MUTED = "#888888"
BRIGHT = "#ffffff"
ACCENT = "#5ba3ec"
STRONG = "#00cc66"
MEDIUM = "#e6b422"
WEAK = "#cc3333"

COL_GAP = "   "
ICON_BASE = 50

BSSID_W = 17
MIN_SSID = 12
MIN_SIG = 4
MIN_SEC = 5
MIN_CHAN = 4
MIN_FREQ = 8

POLL_MS = 2000


class WifiView(BaseView):
    name = "wifi"
    description = "Available WiFi networks"

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "wifi", self.master)

        tk.Label(
            header,
            text="Wifi",
            font=fonts.view_font_bold(22),
            fg="#ffffff",
            bg="#000000",
        ).pack(anchor="center")

        self.iface_frame = tk.Frame(header, bg="#000000")
        self.iface_frame.pack(anchor="center")

        self.monitor_frame = tk.Frame(header, bg="#000000")
        self.monitor_frame.pack(anchor="center")

        self.stats_label = tk.Label(
            header,
            text="",
            font=fonts.view_font(10),
            fg=MUTED,
            bg="#000000",
        )
        self.stats_label.pack(anchor="center")

        self._unlock_btn = tk.Label(
            header,
            text="  Unlock channel  ",
            font=fonts.view_font(10),
            fg=ACCENT,
            bg="#222222",
            relief=tk.RAISED,
            bd=1,
            padx=12,
            pady=3,
        )
        self._unlock_btn.bind("<Button-1>", lambda e: self._unlock_channel())
        self._unlock_btn.bind("<Enter>", lambda e: self._unlock_btn.config(bg="#333333"))
        self._unlock_btn.bind("<Leave>", lambda e: self._unlock_btn.config(bg="#222222"))

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000",
            fg=BRIGHT,
            font=fonts.view_font(16),
            borderwidth=0,
            highlightthickness=0,
            pady=10,
            state=tk.DISABLED,
            cursor="",
            wrap=tk.NONE,
            spacing1=8,
            spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("stale", foreground=WEAK)
        self.text.tag_configure("sig_strong", foreground=STRONG)
        self.text.tag_configure("sig_medium", foreground=MEDIUM)
        self.text.tag_configure("sig_weak", foreground=WEAK)

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        self._ifaces = []
        self._selected_iface = None
        self._last_hash = None
        self._poll_id = None
        self._resize_id = None
        self._on_network_click = None
        self._fb_nets = []
        self._fb_scanning = False
        self._fb_last = 0.0

    def _on_resize(self, event):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._last_hash = None
        self._resize_id = self.after(200, self._poll)

    def on_activate(self):
        self._last_hash = None
        self.after(100, self._poll)

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _render_ifaces(self):
        for child in self.iface_frame.winfo_children():
            child.destroy()

        tk.Label(
            self.iface_frame,
            text="Interfaces:",
            font=fonts.view_font(11),
            fg=MUTED,
            bg="#000000",
        ).pack(side=tk.LEFT, padx=(0, 4))

        options = [None] + list(self._ifaces)
        for iface in options:
            label = "All" if iface is None else iface
            selected = iface == self._selected_iface
            btn = tk.Label(
                self.iface_frame,
                text=f"  {label}  ",
                font=fonts.view_font_bold(11) if selected else fonts.view_font(11),
                fg=ACCENT if selected else MUTED,
                bg="#000000",
            )
            btn.pack(side=tk.LEFT, padx=2)
            btn.bind("<Button-1>", lambda e, i=iface: self._select_iface(i))
            btn.bind("<Enter>", lambda e, b=btn: b.config(font=fonts.view_font_under(11), fg=BRIGHT))
            btn.bind("<Leave>", lambda e, b=btn, i=iface: b.config(
                font=fonts.view_font_bold(11) if i == self._selected_iface else fonts.view_font(11),
                fg=ACCENT if i == self._selected_iface else MUTED))

        self._render_monitor()

    def _render_monitor(self):
        for child in self.monitor_frame.winfo_children():
            child.destroy()
        iface = self._selected_iface
        if not iface:
            return
        on = wifi_monitor.is_iface_enabled(iface)
        tk.Label(
            self.monitor_frame,
            text=f"{iface}   Monitor mode:",
            font=fonts.view_font(11),
            fg=MUTED,
            bg="#000000",
        ).pack(side=tk.LEFT, padx=(0, 4))
        sw = tk.Label(
            self.monitor_frame,
            text="  ON  " if on else "  OFF  ",
            font=fonts.view_font_bold(11),
            fg=STRONG if on else MUTED,
            bg="#000000",
        )
        sw.pack(side=tk.LEFT)
        sw.bind("<Button-1>", lambda e, i=iface: self._toggle_monitor(i))
        sw.bind("<Enter>", lambda e, b=sw: b.config(fg=BRIGHT))
        sw.bind("<Leave>", lambda e, b=sw, i=iface: b.config(
            fg=STRONG if wifi_monitor.is_iface_enabled(i) else MUTED))

    def _toggle_monitor(self, iface):
        if wifi_monitor.is_iface_enabled(iface):
            wifi_monitor.disable_iface(iface)
        else:
            if not wifi_monitor.capture_supported():
                return
            wifi_monitor.enable_iface(iface)
        self._last_hash = None
        self._render_ifaces()
        self._poll()

    def _select_iface(self, iface):
        if self._selected_iface == iface:
            iface = None
        self._selected_iface = iface
        self._render_ifaces()
        self._last_hash = None
        self._fb_last = 0.0
        self._poll()

    def _poll(self):
        if wifi_monitor.is_running():
            all_nets = wifi_monitor.get_networks()
        else:
            now = time.time()
            if not self._fb_scanning and now - self._fb_last > 10:
                self._fb_scanning = True
                self._fb_last = now
                threading.Thread(target=self._fb_run, daemon=True).start()
            all_nets = self._fb_nets

        self._update_ifaces(all_nets)
        self._update_stats()
        self._update_unlock_btn()

        if self._selected_iface:
            nets = [n for n in all_nets if self._selected_iface in n.get("devices", [])]
        else:
            nets = all_nets

        current_hash = hash(tuple(
            (n["ssid"], n["bssid"], n["signal"] // 10, n["security"], n.get("stale")) for n in nets))
        if current_hash != self._last_hash:
            self._last_hash = current_hash
            self._render(nets)

        self._poll_id = self.after(POLL_MS, self._poll)

    def _fb_run(self):
        try:
            self._fb_nets = wifi_monitor.scan_networks_fallback(None)
        except Exception:
            self._fb_nets = []
        self._fb_scanning = False

    def _update_ifaces(self, all_nets):
        ifaces = set(wifi_monitor.wifi_interfaces())
        svc = wifi_monitor.get_service()
        for i in svc.ifaces:
            ifaces.add(i)
        ifaces = sorted(ifaces)
        if ifaces != self._ifaces:
            self._ifaces = ifaces
            if self._selected_iface not in (None, *self._ifaces):
                self._selected_iface = None
            self._render_ifaces()

    def _update_stats(self):
        if wifi_monitor.is_running():
            s = wifi_monitor.get_stats()
            self.stats_label.config(
                text=f"{s['networks']} networks  |  {s['probes']} clients  |  "
                     f"{s['handshakes']} handshakes  "
                     f"(beacons {s['beacons_seen']}, data {s['data_seen']})")
        else:
            self.stats_label.config(
                text=f"Scan-only mode  |  {len(self._fb_nets)} networks")

    def _update_unlock_btn(self):
        if not wifi_monitor.monitor_supported():
            self._unlock_btn.pack_forget()
            return
        if wifi_monitor.is_locked():
            ch = wifi_monitor.locked_channel()
            self._unlock_btn.config(text=f"  Unlock channel {ch}  ")
            self._unlock_btn.pack(anchor="center", pady=(4, 0))
        else:
            self._unlock_btn.pack_forget()

    def _unlock_channel(self):
        wifi_monitor.unlock_channel()
        self._update_unlock_btn()

    def _render(self, nets):
        scroll_pos = self.text.yview()[0]
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not nets:
            self._render_message()
            self.text.configure(state=tk.DISABLED)
            return

        w_ssid = MIN_SSID
        w_sig = MIN_SIG
        w_sec = MIN_SEC
        w_chan = MIN_CHAN
        w_freq = MIN_FREQ
        for n in nets:
            w_ssid = max(w_ssid, len(n["ssid"]))
            w_sig = max(w_sig, len(f"{n['signal']}%"))
            w_sec = max(w_sec, len(n["security"]))
            w_chan = max(w_chan, len(str(n["chan"])))
            w_freq = max(w_freq, len(n["freq"]))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        bssid_px = col_w(BSSID_W)
        row_px = (icons.scaled(ICON_BASE) + gap_px + col_w(w_ssid) + gap_px + bssid_px + gap_px +
                  col_w(w_sig) + gap_px + col_w(w_sec) + gap_px +
                  col_w(w_chan) + gap_px + col_w(w_freq))

        w = self.text.winfo_width()
        if w > row_px:
            pad_chars = int((w - row_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += col_w(w_ssid) + gap_px
        tabs.append(t)
        t += bssid_px + gap_px
        tabs.append(t)
        t += col_w(w_sig) + gap_px
        tabs.append(t)
        t += col_w(w_sec) + gap_px
        tabs.append(t)
        t += col_w(w_chan) + gap_px
        tabs.append(t)

        self.text.configure(tabs=tabs)

        for n in nets:
            self._insert_line(n, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)

    def _render_message(self):
        font = tkfont.Font(font=self.text.cget("font"))
        if not wifi_monitor.monitor_supported():
            msg = "Scanning WiFi networks (scan-only: passive probes unavailable)..."
        elif not wifi_monitor.is_running():
            msg = "WiFi monitor off (no client probes). Scanning via system..."
        else:
            msg = "Scanning for WiFi networks..."
        w = self.text.winfo_width()
        char_w = font.measure(" ")
        pad = " " * max(0, int((w - font.measure(msg)) // 2 // char_w))
        self.text.insert(tk.END, pad + msg, "muted")

    @staticmethod
    def _signal_tag(signal):
        if signal >= 70:
            return "sig_strong"
        if signal >= 40:
            return "sig_medium"
        return "sig_weak"

    def _insert_line(self, n, center_pad):
        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon("wifi.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")

        self.text.insert(tk.END, "\t", "bright")
        tag = f"wifi_{n['bssid'] or n['ssid']}"
        self.text.tag_configure(tag, underline=False)
        ssid_tag = "stale" if n.get("stale") else "bright"
        self.text.insert(tk.END, n["ssid"], (ssid_tag, tag))
        self.text.tag_bind(tag, "<Button-1>",
                           lambda e, net=n: self._on_network_click
                           and self._on_network_click(net))
        self.text.tag_bind(tag, "<Enter>",
                           lambda e, t=tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(tag, "<Leave>",
                           lambda e, t=tag: self.text.tag_configure(t, underline=False))
        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, n["bssid"], "muted")
        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, f"{n['signal']}%", self._signal_tag(n["signal"]))
        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, n["security"], "muted")
        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, str(n["chan"]), "muted")
        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, n["freq"], "muted")
        self.text.insert(tk.END, "\n", "bright")
