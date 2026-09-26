from src.gui import fonts
import os
import time
import tkinter as tk
from datetime import datetime
from src.gui import icons
from src.elwand_paths import logs_dir
from .base import BaseView
from .nav import build as build_nav

_DBG_FILE = os.path.join(logs_dir(), "debugging_logs")


def _dbg(msg):
    try:
        os.makedirs(os.path.dirname(_DBG_FILE), exist_ok=True)
        with open(_DBG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except (PermissionError, OSError):
        pass


MUTED = "#888888"
BRIGHT = "#ffffff"
DISABLED_FG = "#444444"

COL_GAP = "   "
ICON_BASE = 50


class InventoryView(BaseView):
    name = "inventory"
    description = "Manage inventory"

    MIN_NAME = 14

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "inventory", self.master)

        tk.Label(
            header,
            text="Inventory",
            font=fonts.view_font_bold(22),
            fg="#ffffff",
            bg="#000000",
        ).pack(anchor="center")

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
            state=tk.NORMAL,
            cursor="",
            wrap=tk.NONE,
            spacing1=8,
            spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("disabled", foreground=DISABLED_FG)
        self.text.tag_configure("item_name", foreground=BRIGHT,
                                font=fonts.view_font(18))
        self.text.tag_configure("item_name_disabled", foreground=DISABLED_FG,
                                font=fonts.view_font(18))
        self.text.tag_configure("item_desc", foreground=MUTED,
                                font=fonts.view_font(12))
        self.text.tag_configure("item_desc_disabled", foreground=DISABLED_FG,
                                font=fonts.view_font(12))

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        self._items = [
            {"name": "Users", "action": "users",
             "desc": "Stored users found",
             "icon": "user.png", "enabled": True},
            {"name": "Groups", "action": "groups",
             "desc": "(not yet implemented)",
             "icon": "group.png", "enabled": False},
            {"name": "People", "action": "people",
             "desc": "People discovered (employees, contacts)",
             "icon": "people.png", "enabled": True},
            {"name": "Passwords", "action": "passwords",
             "desc": "Stored passwords found",
             "icon": "passwords.png", "enabled": True},
            {"name": "Hashes", "action": "hashes",
             "desc": "Stored hashes for cracking.",
             "icon": "hashes2.png", "enabled": True},
            {"name": "Handshakes", "action": "handshakes",
             "desc": "Captured WPA handshakes",
             "icon": "handshake.png", "enabled": True},
            {"name": "Tickets", "action": "tickets",
             "desc": "Kerberos tickets (not yet implemented).",
             "icon": "ticket.png", "enabled": False},
            {"name": "Credentials", "action": "credentials",
             "desc": "Valid users and password / hash_nt",
             "icon": "credential.png", "enabled": True},
            {"name": "Dictionarys", "action": "dictionarys",
             "desc": "Dictionary wordlists",
             "icon": "dictionary.png", "enabled": True},
            {"name": "Rules", "action": "rules_view",
             "desc": "Hashcat rules",
             "icon": "rules.png", "enabled": True},
            {"name": "Pocs", "action": "pocs",
             "desc": "Proof of Concept scripts",
             "icon": "poc.png", "enabled": True},
            {"name": "Evidences", "action": "evidences",
             "desc": "Collected evidence",
             "icon": "evidence.png", "enabled": True},
            {"name": "Reports", "action": "reports",
             "desc": "Generated reports",
             "icon": "report.png", "enabled": True},
        ]

        self._font18 = fonts.view_font(18)
        self._font16 = fonts.view_font(16)
        self._font12 = fonts.view_font(12)

        for item in self._items:
            icons.icon(item["icon"], size=icons.scaled(ICON_BASE))

        self._rendered = False
        self._poll_id = None
        self._resize_id = None

    def _on_resize(self, event):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._rendered = False
        self._resize_id = self.after(200, self._poll)

    def on_activate(self):
        _dbg(f"[inv] on_activate")
        self.after(10, self._poll)

    def on_deactivate(self):
        _dbg(f"[inv] on_deactivate")
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self):
        if not self._rendered:
            t0 = time.perf_counter()
            self._rendered = True
            self._render()
            _dbg(f"[inv] _render took {time.perf_counter() - t0:.3f}s")
        self._poll_id = self.after(2000, self._poll)

    def _render(self):
        t0 = time.perf_counter()
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        _dbg(f"[inv] _render clear took {time.perf_counter() - t0:.3f}s")

        w_name = self.MIN_NAME
        w_desc = 20
        for item in self._items:
            w_name = max(w_name, len(item["name"]))
            w_desc = max(w_desc, len(item["desc"]))

        name_px = self._font18.measure(" " * w_name)
        desc_px = self._font12.measure(" " * w_desc)
        gap_px = self._font16.measure(COL_GAP)
        char_w = self._font16.measure(" ")

        row_content_px = icons.scaled(ICON_BASE) + gap_px + name_px + gap_px + desc_px

        w = self.text.winfo_width()
        if w > row_content_px:
            pad_chars = int((w - row_content_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = self._font16.measure(center_pad)
        tabs = []
        t = center_px + icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += name_px + gap_px
        tabs.append(t)

        self.text.configure(tabs=tabs)

        for item in self._items:
            self._insert_item(item, center_pad)

        self.text.configure(state=tk.DISABLED)

    def _insert_item(self, item, center_pad):
        name = item["name"]
        action = item["action"]
        enabled = item["enabled"]
        icon_name = item["icon"]

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon(icon_name, size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        if enabled:
            tag = f"inv_{name}"
            self.text.tag_configure(tag, underline=False)
            self.text.insert(tk.END, name, ("item_name", tag))
            self.text.tag_bind(tag, "<Button-1>",
                               lambda e, a=action: self._on_item_click
                               and self._on_item_click(a))
            self.text.tag_bind(tag, "<Enter>",
                               lambda e, t=tag: self.text.tag_configure(
                                   t, underline=True))
            self.text.tag_bind(tag, "<Leave>",
                               lambda e, t=tag: self.text.tag_configure(
                                   t, underline=False))
            self.text.insert(tk.END, "\t", "bright")
            self.text.insert(tk.END, item["desc"], "item_desc")
        else:
            self.text.insert(tk.END, name, "item_name_disabled")
            self.text.insert(tk.END, "\t", "bright")
            self.text.insert(tk.END, item["desc"], "item_desc_disabled")

        self.text.insert(tk.END, "\n", "bright")
