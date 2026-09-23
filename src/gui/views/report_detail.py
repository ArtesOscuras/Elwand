import os
import tkinter as tk
from src.gui import fonts
from src.gui.markdown import MarkdownRenderer
from .base import BaseView
from src.elwand_paths import reports_dir

BRIGHT = "#ffffff"
MUTED = "#888888"


class ReportView(BaseView):
    name = "report"
    description = "Report view"

    def __init__(self, parent, fname, **kwargs):
        self._fname = fname
        super().__init__(parent, **kwargs)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 10))

        self._title_label = tk.Label(
            header, text=self._fname,
            font=fonts.view_font_bold(22),
            fg="#ffffff", bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind(
            "<Enter>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold(22)))
        self._on_back_click = None
        self._on_edit_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew",
                        padx=(100, 100), pady=(0, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT, cursor="",
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD, spacing1=3, spacing3=3,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self._md = MarkdownRenderer(self.text, 13, named=True)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))

        inner = tk.Frame(btn_frame, bg="#000000")
        inner.pack(anchor="center")

        edit_btn = tk.Label(
            inner, text="  Edit  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        edit_btn.pack(side=tk.LEFT, padx=(0, 10))
        edit_btn.bind("<Button-1>",
                      lambda e: self._on_edit_click
                      and self._on_edit_click())
        edit_btn.bind("<Enter>", lambda e: edit_btn.config(bg="#333333"))
        edit_btn.bind("<Leave>", lambda e: edit_btn.config(bg="#222222"))

        back_btn = tk.Label(
            inner, text="  \u2190 Back  ", bg="#222222", fg="#ffffff",
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

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _refresh(self):
        path = os.path.join(str(reports_dir()), self._fname)
        content = ""
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (PermissionError, OSError):
                content = ""
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self._md.render(content)
        self.text.configure(state=tk.DISABLED)
        self.text.yview_moveto(0)
