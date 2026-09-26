import tkinter as tk
import tkinter.font as tkfont
from src.gui import fonts
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav

MUTED = "#888888"
BRIGHT = "#ffffff"
ON_COLOR = "#00cc66"
OFF_COLOR = "#cc3333"
INFO = "#5ba3ec"

COL_GAP = "   "
ICON_BASE = 50

_STATIC_SERVICES = [
    {
        "key": "mdns",
        "name": "mDNS Listener",
        "desc": "Passive listener for device discovery",
        "icon": "service.png",
    },
    {
        "key": "revershell",
        "name": "Revershell Listener",
        "desc": "Listener for incoming reverse shell connections",
        "icon": "service.png",
    },
]


def _services():
    """Static services plus one monitor-mode switch per WiFi interface."""
    from src.tools.scanner import wifi_monitor
    svcs = [dict(s) for s in _STATIC_SERVICES]
    for iface in wifi_monitor.wifi_interfaces():
        svcs.append({
            "key": f"wifi:{iface}",
            "name": f"{iface} Monitor mode",
            "desc": "Captures nearby networks and client probes",
            "icon": "wifi.png",
        })
    return svcs


class ServicesView(BaseView):
    name = "services"
    description = "Background services"

    MIN_NAME = 18

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "services", self.master)

        self._title_label = tk.Label(
            header, text="Services",
            font=fonts.view_font_bold(22), fg=BRIGHT, bg="#000000",
        )
        self._title_label.pack(anchor="center")

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT,
            font=fonts.view_font(16), borderwidth=0, highlightthickness=0,
            pady=10, state=tk.DISABLED, cursor="",
            wrap=tk.NONE, spacing1=12, spacing3=12,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("on", foreground=ON_COLOR)
        self.text.tag_configure("off", foreground=OFF_COLOR)
        self.text.tag_configure("muted_small", foreground=MUTED, font=fonts.view_font(10))

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                  command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        self._on_toggle = None
        self._check_state = None

        self._states = {}
        self._poll_id = None
        self._resize_id = None

    def _on_resize(self, event):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._resize_id = self.after(200, self._poll)

    def on_activate(self):
        self.after(100, self._poll)

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self):
        svcs = _services()
        states = self._check_state() if self._check_state else {}
        for svc in svcs:
            self._states[svc["key"]] = bool(states.get(svc["key"], False))

        w_name = self.MIN_NAME
        for svc in svcs:
            w_name = max(w_name, len(svc["name"]))

        font = tkfont.Font(font=self.text.cget("font"))
        desc_font = tkfont.Font(font=fonts.view_font(10))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        max_desc_px = 0
        for svc in svcs:
            max_desc_px = max(max_desc_px, desc_font.measure(svc["desc"]))
        switch_w = col_w(8)
        row_px = icons.scaled(ICON_BASE) + gap_px + col_w(w_name) + gap_px + max_desc_px + gap_px + switch_w + 20

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
        t += col_w(w_name) + gap_px
        tabs.append(t)
        t += max_desc_px + gap_px
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, center_pad, "bright")

        first = True
        for svc in svcs:
            if not first:
                self.text.insert(tk.END, center_pad, "bright")
            first = False
            self._insert_line(svc)
            self.text.insert(tk.END, "\n", "bright")

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)
        self._poll_id = self.after(2000, self._poll)

    def _insert_line(self, svc):
        on = self._states.get(svc["key"], False)

        icon = icons.icon(svc.get("icon", "service.png"), size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, svc["name"], "bright")
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, svc["desc"], "muted_small")
        self.text.insert(tk.END, "\t", "bright")

        state_text = "  ON  " if on else " OFF "
        state_tag = f"toggle_{svc['key']}"
        self.text.tag_configure(state_tag, foreground=ON_COLOR if on else OFF_COLOR)
        self.text.insert(tk.END, state_text, ("on" if on else "off", state_tag))

        self.text.tag_bind(state_tag, "<Button-1>",
                           lambda e, k=svc["key"]: self._toggle(k))
        self.text.tag_bind(state_tag, "<Enter>",
                           lambda e, t=state_tag: self.text.tag_configure(
                               t, underline=True))
        self.text.tag_bind(state_tag, "<Leave>",
                           lambda e, t=state_tag: self.text.tag_configure(
                               t, underline=False))

    def _toggle(self, key):
        current = self._states.get(key, False)
        new_state = not current
        self._states[key] = new_state
        if self._on_toggle:
            self._on_toggle(key, new_state)
        self._poll()
