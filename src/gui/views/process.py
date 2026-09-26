import tkinter as tk
import tkinter.font as tkfont
from src.gui import fonts
from src.gui import icons
from src import process_registry
from .base import BaseView
from .nav import build as build_nav

MUTED = "#888888"
BRIGHT = "#ffffff"
RUNNING_COLOR = "#00cc66"

COL_GAP = "   "
ICON_BASE = 50


def _fmt_elapsed(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


class ProcessView(BaseView):
    name = "process"
    description = "Running background tools"

    MIN_NAME = 14
    MIN_DETAIL = 20

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "process", self.master)

        self._title_label = tk.Label(
            header, text="Process",
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
        self.text.tag_configure("running", foreground=RUNNING_COLOR)
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
        items = process_registry.list_active()

        w_name = self.MIN_NAME
        w_detail = self.MIN_DETAIL
        for p in items:
            w_name = max(w_name, len(p["name"]))
            w_detail = max(w_detail, len(p["detail"]))

        font = tkfont.Font(font=self.text.cget("font"))
        detail_font = tkfont.Font(font=fonts.view_font(10))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        max_detail_px = 0
        for p in items:
            max_detail_px = max(max_detail_px, detail_font.measure(p["detail"]))
        status_w = col_w(20)
        row_px = (icons.scaled(ICON_BASE) + gap_px + col_w(w_name) + gap_px
                  + max_detail_px + gap_px + status_w)

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
        t += max_detail_px + gap_px
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not items:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No processes running.\n", "muted")
        else:
            first = True
            for p in items:
                if not first:
                    self.text.insert(tk.END, center_pad, "bright")
                first = False
                self._insert_line(p)
                self.text.insert(tk.END, "\n", "bright")

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)
        self._poll_id = self.after(1000, self._poll)

    def _insert_line(self, p):
        icon = icons.icon(p.get("icon", "service.png"), size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, p["name"], "bright")
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, p["detail"], "muted_small")
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, " RUNNING ", "running")
        self.text.insert(tk.END, "  " + _fmt_elapsed(p["elapsed"]), "muted")
