from src.gui import fonts
import os
import shutil
import tkinter as tk
import tkinter.font as tkfont
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav
from src.elwand_paths import evidence_dir as _evidence_dir

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"

COL_GAP = "   "
ICON_BASE = 50


def _get_evidence_dir():
    return str(_evidence_dir())


def _list_evidences():
    base = _get_evidence_dir()
    result = []
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            entry_path = os.path.join(base, entry)
            if os.path.isdir(entry_path):
                session_path = os.path.join(entry_path, "session.json")
                if os.path.isfile(session_path):
                    try:
                        import json
                        with open(session_path) as f:
                            meta = json.load(f)
                        req_count = meta.get("request_count", 0)
                    except Exception:
                        req_count = 0
                    result.append({"name": entry, "requests": req_count})
    return result


class EvidenceListView(BaseView):
    name = "evidences"
    description = "Recorded evidence sessions"

    MIN_NAME = 15

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "evidences", self.master)

        self._title_label = tk.Label(
            header,
            text="Evidence",
            font=fonts.view_font_bold(22),
            fg=BRIGHT,
            bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind(
            "<Button-1>",
            lambda e: self.master.activate_view("inventory"))
        self._title_label.bind(
            "<Enter>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold(22)))

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
        self.text.tag_configure("info", foreground=INFO)

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        self._last_hash = None
        self._poll_id = None
        self._resize_id = None

    def _on_resize(self, event):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._last_hash = None
        self._resize_id = self.after(200, self._poll)


    def on_activate(self):
        self.after(100, self._poll)

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        self._items = []

    def _insert_line(self, item, center_pad):
        name = item["name"]
        reqs = item["requests"]
        req_text = f"{reqs} requests"

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon("evidence.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        tag = f"e_{name}"
        self.text.tag_configure(tag, underline=False)
        self.text.insert(tk.END, name[:50] + "\u2026" if len(name) > 50 else name, ("bright", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda e, n=name: (
            self._on_item_click and self._on_item_click(n)))
        self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, req_text, "muted")
        self.text.insert(tk.END, "\t", "bright")

        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"del_{name}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>", lambda e, n=name: (
                self._delete_evidence(n), "break")[-1])

        self.text.insert(tk.END, "\n", "muted")

    @staticmethod
    def _delete_evidence(name):
        base = _get_evidence_dir()
        path = os.path.join(base, name)
        if os.path.isdir(path):
            shutil.rmtree(path)

    def _poll(self):
        items = _list_evidences()
        self._items = items

        current_hash = hash(tuple((i["name"], i["requests"]) for i in items))

        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_name = self.MIN_NAME
        w_reqs = 10
        for item in items:
            w_name = max(w_name, len(item["name"]))
            w_reqs = max(w_reqs, len(f"{item['requests']} requests"))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        row_content_px = icons.scaled(ICON_BASE) + gap_px + col_w(w_name) + gap_px + col_w(w_reqs) + gap_px + col_w(3)

        w = self.text.winfo_width()
        if w > row_content_px:
            pad_chars = int((w - row_content_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += col_w(w_name) + gap_px
        tabs.append(t)
        t += col_w(w_reqs) + gap_px
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not items:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No evidence sessions recorded yet.\n", "muted")
        else:
            for item in items:
                self._insert_line(item, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)

        self._poll_id = self.after(2000, self._poll)
