import os
import tkinter as tk
import tkinter.font as tkfont
from src.gui import fonts
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav
from src.elwand_paths import lst_dir

MUTED = "#888888"
BRIGHT = "#ffffff"

COL_GAP = "   "
ICON_BASE = 50
MIN_NAME = 12


class DictionarysView(BaseView):
    name = "dictionarys"
    description = "Dictionary files"

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))
        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "dictionarys", self.master)

        self._title_label = tk.Label(
            header, text="Dictionarys",
            font=fonts.view_font_bold(22), fg=BRIGHT, bg="#000000",
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
            text_frame, bg="#000000", fg=BRIGHT,
            font=fonts.view_font(16), borderwidth=0, highlightthickness=0,
            pady=10, state=tk.DISABLED, cursor="",
            wrap=tk.NONE, spacing1=8, spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, pady=(15, 15))

        back_btn = tk.Label(
            btn_frame, text="  \u2190 Back  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.RIGHT, padx=(10, 0))
        back_btn.bind("<Button-1>",
                       lambda e: self.master.activate_view("inventory"))
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

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

    def _list_files(self):
        try:
            d = str(lst_dir())
            files = sorted(f for f in os.listdir(d)
                          if os.path.isfile(os.path.join(d, f)))
            return d, files
        except OSError:
            return str(lst_dir()), []

    def _poll(self):
        d, files = self._list_files()
        current_hash = hash(tuple(files))
        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_name = MIN_NAME
        for f in files:
            w_name = max(w_name, len(f))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        w_size = 8
        row_px = icons.scaled(ICON_BASE) + gap_px + col_w(w_name) + gap_px + col_w(w_size) + gap_px + 20

        w = self.text.winfo_width()
        if w > row_px:
            pad_chars = int((w - row_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = [center_px + icons.scaled(ICON_BASE) + gap_px]
        tabs.append(tabs[0] + col_w(w_name) + gap_px)
        tabs.append(tabs[1] + col_w(w_size) + gap_px)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not files:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No dictionaries found.\n", "muted")
        else:
            for f in files:
                path = os.path.join(d, f)
                size_bytes = os.path.getsize(path) if os.path.isfile(path) else 0
                if size_bytes >= 1024 * 1024:
                    size_str = f"{size_bytes / (1024 * 1024):.1f}M"
                elif size_bytes >= 1024:
                    size_str = f"{size_bytes / 1024:.0f}K"
                else:
                    size_str = f"{size_bytes}B"

                self.text.insert(tk.END, center_pad, "bright")

                dic_icon = icons.icon("dictionary.png", size=icons.scaled(ICON_BASE))
                if dic_icon:
                    self.text.image_create(tk.END, image=dic_icon)
                else:
                    self.text.insert(tk.END, "?")

                self.text.insert(tk.END, "\t", "bright")

                tag = f"dict_{f}"
                self.text.tag_configure(tag, underline=False)
                self.text.insert(tk.END, f, ("bright", tag))
                self.text.tag_bind(tag, "<Button-1>",
                                   lambda e, p=f: (
                                       self._on_item_click
                                       and self._on_item_click(p)))
                self.text.tag_bind(tag, "<Enter>",
                                   lambda e, t=tag: self.text.tag_configure(
                                       t, underline=True))
                self.text.tag_bind(tag, "<Leave>",
                                   lambda e, t=tag: self.text.tag_configure(
                                       t, underline=False))

                self.text.insert(tk.END, "\t", "bright")
                self.text.insert(tk.END, size_str, "muted")

                del_img = icons.delete_icon()
                if del_img:
                    self.text.insert(tk.END, "\t", "bright")
                    self.text.image_create(tk.END, image=del_img)
                    del_tag = f"deld_{f}"
                    self.text.tag_add(del_tag, "end-2c", "end-1c")
                    self.text.tag_bind(del_tag, "<Button-1>",
                                       lambda e, p=path: (
                                           os.remove(p),
                                           "break")[-1])

                self.text.insert(tk.END, "\n", "bright")

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)
        self._poll_id = self.after(2000, self._poll)
