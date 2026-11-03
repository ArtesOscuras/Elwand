from src.gui import fonts, icons
import tkinter as tk
import tkinter.font as tkfont
from .base import BaseView
from .nav import build as build_nav
import src.sessions as sessions

MUTED = "#888888"
BRIGHT = "#ffffff"

COL_GAP = "   "
ICON_BASE = 50
MIN_NAME = 10
UPDATED_W = 19


class SessionView(BaseView):
    name = "sessions"
    description = "Work sessions"

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "sessions", self.master)

        tk.Label(
            header,
            text="Sessions",
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
            state=tk.DISABLED,
            cursor="",
            wrap=tk.NONE,
            spacing1=8,
            spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("small", foreground=MUTED,
                                font=fonts.view_font(10))

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555", width=10, borderwidth=0,
                            highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        self._on_session_click = None
        self._on_delete_session = None
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

    def refresh(self):
        """Force an immediate re-render (e.g. after a switch/delete)."""
        if self._poll_id:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        self._last_hash = None
        self._poll()

    @staticmethod
    def _updated(meta):
        ts = (meta.get("updated") or "").strip()
        return ts[:UPDATED_W]

    def _insert_line(self, meta, idx, center_pad):
        sid = meta.get("id", "")
        name = (meta.get("name") or sid or "?").strip()
        active = bool(meta.get("active"))
        updated = self._updated(meta)

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon("session.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")

        self.text.insert(tk.END, "\t", "bright")

        normal = (fonts.view_font_bold(16) if active
                  else fonts.view_font(16))
        hover = (fonts.view_font_bold_under(16) if active
                 else fonts.view_font_under(16))
        tag = f"sess_{idx}"
        self.text.tag_configure(tag, underline=False, font=normal)
        self.text.insert(tk.END, name, ("bright", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda e, s=sid: (
            self._on_session_click and self._on_session_click(s)))
        self.text.tag_bind(tag, "<Enter>", lambda e, t=tag, h=hover: (
            self.text.tag_configure(t, underline=True, font=h)))
        self.text.tag_bind(tag, "<Leave>", lambda e, t=tag, n=normal: (
            self.text.tag_configure(t, underline=False, font=n)))

        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, updated, "small")

        self.text.insert(tk.END, "\t", "bright")
        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"delsess_{idx}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>", lambda e, s=sid: (
                self._on_delete_session and self._on_delete_session(s), "break")[-1])

        self.text.insert(tk.END, "\n", "bright")

    def _poll(self):
        rows = sessions.list_sessions()
        current_hash = hash(tuple(
            (s.get("id"), s.get("name"), s.get("updated"), s.get("active"))
            for s in rows
        ))
        if current_hash == self._last_hash and self.text.index("end-1c") != "1.0":
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_name = MIN_NAME
        for s in rows:
            w_name = max(w_name, len((s.get("name") or s.get("id") or "").strip()))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        icon_px = icons.scaled(ICON_BASE)
        row_px = (icon_px + gap_px + col_w(w_name) + gap_px
                  + col_w(UPDATED_W) + gap_px + col_w(3))

        w = self.text.winfo_width()
        if w > row_px:
            pad_chars = int((w - row_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + icon_px + gap_px
        tabs.append(t)                      # name start
        t += col_w(w_name) + gap_px
        tabs.append(t)                      # updated start
        t += col_w(UPDATED_W) + gap_px
        tabs.append(t)                      # delete start

        self.text.configure(tabs=tabs)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not rows:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No sessions found.\n", "muted")
        else:
            for idx, meta in enumerate(rows):
                self._insert_line(meta, idx, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)

        self._poll_id = self.after(2000, self._poll)
