import os
import re
import sqlite3
import threading
import tkinter as tk
from collections import defaultdict
from tkinter import ttk
from src.gui import fonts, windowing
from src.machines import credential_db
from src.tools.hashcat import HashcatEngine
from src.elwand_paths import hashcat_db as _hashcat_db

BG = "#111111"
BG_WIDGET = "#000000"
FG = "#ffffff"
FG_DIM = "#888888"
SEL_BG = "#333333"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"
INFO_COLOR = "#5ba3ec"


class HashcatDialog(tk.Toplevel):
    def __init__(self, parent, active_tab=0):
        super().__init__(parent)
        self._engine = None
        self._cracked = []
        self._hash_items = []
        self._modes_by_type = {}
        self._hw = None
        self._detect_db = None
        self.result = None

        self.title("Hashcat")
        sh = self.winfo_screenheight()
        h = min(windowing.px(680), sh - windowing.px(60))
        w = windowing.px(800)
        x = (self.winfo_screenwidth() - w) // 2
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
        windowing.min_size(self, 700, 500)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222", foreground=FG_DIM,
                        font=fonts.view_font(10), padding=[14, 6])
        style.map("TNotebook.Tab", background=[("selected", BG)],
                  foreground=[("selected", FG)])

        self._nb = ttk.Notebook(self)
        self._nb.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self._tab_crack = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_crack, text="  Hashcat Wrdlst  ")
        self._build_crack_tab(self._tab_crack)

        self._tab_mask = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_mask, text="  Hashcat Mask  ")
        self._build_mask_tab(self._tab_mask)

        self._tab_add = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_add, text="  Add Hash  ")
        self._build_add_tab(self._tab_add)

        self._tab_detect = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_detect, text="  Detect  ")
        self._build_detect_tab(self._tab_detect)

        self._nb.select(active_tab)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._detect_hardware()

    # ─── Crack Tab ──────────────────────────────────────────────

    def _build_crack_tab(self, parent):
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(7, weight=1)

        row = 0

        tk.Label(
            parent, text="Hash", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 2))

        hash_frame = tk.Frame(parent, bg=BG_WIDGET)
        hash_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 2))
        hash_frame.columnconfigure(0, weight=1)
        hash_frame.rowconfigure(0, weight=1)

        self._hash_listbox = tk.Listbox(
            hash_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._hash_listbox.grid(row=0, column=0, sticky="nsew")

        hash_scroll = tk.Scrollbar(hash_frame, orient=tk.VERTICAL, command=self._hash_listbox.yview)
        hash_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        hash_scroll.grid(row=0, column=1, sticky="ns")
        self._hash_listbox.configure(yscrollcommand=hash_scroll.set)

        self._mode_var = tk.StringVar()
        self._hash_val_var = tk.StringVar()
        self._type_label_var = tk.StringVar()

        self._populate_hashes()
        self._hash_listbox.bind("<<ListboxSelect>>", self._on_hash_select)

        row += 1

        tk.Label(
            parent, text="Hash value", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 0))
        self._hash_val_entry = tk.Entry(
            parent, textvariable=self._hash_val_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._hash_val_entry.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 0))
        row += 1

        tk.Label(
            parent, text="Hash type", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 0))
        self._type_label = tk.Label(
            parent, textvariable=self._type_label_var,
            fg=SUCCESS, bg=BG, font=fonts.view_font(11), anchor="w",
        )
        self._type_label.grid(row=row, column=1, sticky="w", padx=15, pady=(5, 0))
        row += 1

        tk.Label(
            parent, text="Mode", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 10))
        self._mode_entry = tk.Entry(
            parent, textvariable=self._mode_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG, width=8,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mode_entry.grid(row=row, column=1, sticky="w", padx=15, pady=(5, 10))
        row += 1

        tk.Label(
            parent, text="Device", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(5, 5))

        self._hw_frame = tk.Frame(parent, bg=BG)
        self._hw_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))

        self._hw_label = tk.Label(
            self._hw_frame, text="Detecting hardware...", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        )
        self._hw_label.pack(side=tk.LEFT)

        self._hw_var = tk.StringVar(value="auto")
        self._hw_cpu_rb = None
        self._hw_gpu_rb = None
        row += 1

        tk.Label(
            parent, text="Wordlist", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 5))

        wl_frame = tk.Frame(parent, bg=BG)
        wl_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        wl_frame.columnconfigure(0, weight=1)

        self._wl_var = tk.StringVar()
        self._wl_path_label = tk.Label(wl_frame, textvariable=self._wl_var, fg=FG, bg=BG,
                                       font=fonts.view_font(9), anchor="w")
        self._wl_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_btn = tk.Label(wl_frame, text="  Browse...  ", bg="#222222", fg=FG,
                              font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=10, pady=4)
        browse_btn.pack(side=tk.LEFT)
        browse_btn.bind("<Button-1>", lambda e: self._browse_wordlist())
        browse_btn.bind("<Enter>", lambda e: browse_btn.config(bg="#333333"))
        browse_btn.bind("<Leave>", lambda e: browse_btn.config(bg="#222222"))
        row += 1

        tk.Label(
            parent, text="Rules file", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 5))

        rules_frame = tk.Frame(parent, bg=BG)
        rules_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        rules_frame.columnconfigure(0, weight=1)

        self._rules_var = tk.StringVar()
        self._rules_path_label = tk.Label(rules_frame, textvariable=self._rules_var, fg=FG, bg=BG,
                                          font=fonts.view_font(9), anchor="w")
        self._rules_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        rules_browse_btn = tk.Label(rules_frame, text="  Browse...  ", bg="#222222", fg=FG,
                                    font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=10, pady=4)
        rules_browse_btn.pack(side=tk.LEFT)
        rules_browse_btn.bind("<Button-1>", lambda e: self._browse_rules())
        rules_browse_btn.bind("<Enter>", lambda e: rules_browse_btn.config(bg="#333333"))
        rules_browse_btn.bind("<Leave>", lambda e: rules_browse_btn.config(bg="#222222"))
        row += 1

        tk.Label(
            parent, text="Output", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(5, 2))

        output_frame = tk.Frame(parent, bg=BG_WIDGET)
        output_frame.grid(row=row, column=1, sticky="nsew", padx=15, pady=(5, 2))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self._output_text = tk.Text(
            output_frame, bg=BG_WIDGET, fg=FG_DIM, insertbackground=FG,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self._output_text.grid(row=0, column=0, sticky="nsew")

        output_scroll = tk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self._output_text.yview)
        output_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                                width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        output_scroll.grid(row=0, column=1, sticky="ns")
        self._output_text.configure(yscrollcommand=output_scroll.set)

        self._output_text.tag_configure("success", foreground=SUCCESS)
        self._output_text.tag_configure("error", foreground=ERR_COLOR)
        self._output_text.tag_configure("info", foreground=INFO_COLOR)

        row += 1

        self._progress_var = tk.IntVar(value=0)
        self._progress_bar = ttk.Progressbar(
            parent, variable=self._progress_var, maximum=100,
        )
        self._progress_bar.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 2))
        row += 1

        self._progress_label = tk.Label(
            parent, text="Ready", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, anchor="w",
        )
        self._progress_label.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15)
        row += 1

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(8, 10))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        stop_btn = tk.Label(
            btn_frame, text="  Stop  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        stop_btn.pack(side=tk.RIGHT, padx=(5, 0))
        stop_btn.bind("<Button-1>", lambda e: self._stop())
        stop_btn.bind("<Enter>", lambda e: stop_btn.config(bg="#333333"))
        stop_btn.bind("<Leave>", lambda e: stop_btn.config(bg="#222222"))

        start_btn = tk.Label(
            btn_frame, text="  Start  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        start_btn.pack(side=tk.RIGHT, padx=(5, 0))
        start_btn.bind("<Button-1>", lambda e: self._start())
        start_btn.bind("<Enter>", lambda e: start_btn.config(bg="#333333"))
        start_btn.bind("<Leave>", lambda e: start_btn.config(bg="#222222"))

    # ─── Mask Tab ──────────────────────────────────────────────

    def _build_mask_tab(self, parent):
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)

        row = 0

        tk.Label(
            parent, text="Hash", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 2))

        hash_frame = tk.Frame(parent, bg=BG_WIDGET)
        hash_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 2))
        hash_frame.columnconfigure(0, weight=1)
        hash_frame.rowconfigure(0, weight=1)

        self._mask_hash_listbox = tk.Listbox(
            hash_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._mask_hash_listbox.grid(row=0, column=0, sticky="nsew")

        hash_scroll = tk.Scrollbar(hash_frame, orient=tk.VERTICAL,
                                   command=self._mask_hash_listbox.yview)
        hash_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        hash_scroll.grid(row=0, column=1, sticky="ns")
        self._mask_hash_listbox.configure(yscrollcommand=hash_scroll.set)
        self._mask_hash_listbox.bind("<<ListboxSelect>>", self._on_mask_hash_select)
        row += 1

        tk.Label(
            parent, text="Hash value", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(3, 0))
        self._mask_hash_val_entry = tk.Entry(
            parent, textvariable=self._hash_val_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mask_hash_val_entry.grid(row=row, column=1, sticky="ew", padx=15, pady=(3, 0))
        row += 1

        tk.Label(
            parent, text="Hash type", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(3, 0))
        self._mask_type_label = tk.Label(
            parent, textvariable=self._type_label_var,
            fg=SUCCESS, bg=BG, font=fonts.view_font(11), anchor="w",
        )
        self._mask_type_label.grid(row=row, column=1, sticky="w", padx=15, pady=(3, 0))
        row += 1

        tk.Label(
            parent, text="Mode", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(3, 5))
        self._mask_mode_entry = tk.Entry(
            parent, textvariable=self._mode_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG, width=8,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mask_mode_entry.grid(row=row, column=1, sticky="w", padx=15, pady=(3, 5))
        row += 1

        tk.Label(
            parent, text="Device", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(3, 3))
        self._mask_hw_frame = tk.Frame(parent, bg=BG)
        self._mask_hw_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(3, 3))
        self._mask_hw_placeholder = tk.Label(
            self._mask_hw_frame, text="Detecting hardware...",
            font=fonts.view_font(11), fg=FG_DIM, bg=BG,
        )
        self._mask_hw_placeholder.pack(side=tk.LEFT)
        row += 1

        tk.Label(
            parent, text="Mask", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 5))

        mask_entry_frame = tk.Frame(parent, bg=BG)
        mask_entry_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 5))
        mask_entry_frame.columnconfigure(0, weight=1)

        self._mask_var = tk.StringVar()
        self._mask_entry = tk.Entry(
            mask_entry_frame, textvariable=self._mask_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mask_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        help_label = tk.Label(
            mask_entry_frame, text=" ?l=a-z ?u=A-Z ?d=0-9 ?s=spc ?a=all",
            font=fonts.view_font(9), fg=FG_DIM, bg=BG,
        )
        help_label.pack(side=tk.RIGHT)
        self._mask_var.trace_add("write", self._on_mask_changed)
        row += 1

        tk.Label(
            parent, text="Quick masks", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(2, 3))

        quick_frame = tk.Frame(parent, bg=BG)
        quick_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(2, 3))

        quick_masks = [
            ("?l?l?l?l?l?l", "6 lower"),
            ("?l?l?l?l?l?l?l?l", "8 lower"),
            ("?l?l?l?l?d?d?d?d", "4 lower + 4 digits"),
            ("?u?l?l?l?l?l?l?l", "1 upper + 7 lower"),
            ("?u?l?l?l?l?l?d?d", "common password"),
            ("?d?d?d?d?d?d?d?d", "8 digits"),
            ("?a?a?a?a?a?a", "6 all-printable"),
        ]
        for mask, desc in quick_masks:
            qb = tk.Label(
                quick_frame, text=f" {desc} ", bg="#333333", fg=FG_DIM,
                font=fonts.view_font(8), relief=tk.FLAT, padx=6, pady=2,
            )
            qb.pack(side=tk.LEFT, padx=(0, 4), pady=2)
            qb.bind("<Button-1>", lambda e, m=mask: self._mask_var.set(m))
            qb.bind("<Enter>", lambda e, b=qb: b.config(fg=FG, bg="#444444"))
            qb.bind("<Leave>", lambda e, b=qb: b.config(fg=FG_DIM, bg="#333333"))
        row += 1

        tk.Label(
            parent, text="Custom charsets", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(8, 3))

        cs_frame = tk.Frame(parent, bg=BG)
        cs_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 3))
        cs_frame.columnconfigure(1, weight=1)

        self._mask_cs_vars = {}
        cs_hint = {"1": "e.g. ?l?d", "2": "e.g. ?u?d",
                   "3": "e.g. ?s", "4": "e.g. ?l?u?d"}
        for i, key in enumerate(["1", "2", "3", "4"]):
            tk.Label(
                cs_frame, text=f"-{key}", font=fonts.view_font(11),
                fg=FG_DIM, bg=BG,
            ).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=(1, 0))
            var = tk.StringVar()
            self._mask_cs_vars[key] = var
            tk.Entry(
                cs_frame, textvariable=var,
                bg=BG_WIDGET, fg=FG, insertbackground=FG,
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333",
                highlightbackground="#333333", width=20,
            ).grid(row=i, column=1, sticky="w", pady=(1, 0))
            tk.Label(
                cs_frame, text=cs_hint[key],
                font=fonts.view_font(8), fg=FG_DIM, bg=BG,
            ).grid(row=i, column=2, sticky="w", padx=(5, 0), pady=(1, 0))
        row += 1

        tk.Label(
            parent, text="Output", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(5, 2))

        output_frame = tk.Frame(parent, bg=BG_WIDGET)
        output_frame.grid(row=row, column=1, sticky="nsew", padx=15, pady=(5, 2))
        parent.rowconfigure(row, weight=1)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self._mask_output_text = tk.Text(
            output_frame, bg=BG_WIDGET, fg=FG_DIM, insertbackground=FG,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self._mask_output_text.grid(row=0, column=0, sticky="nsew")

        output_scroll = tk.Scrollbar(
            output_frame, orient=tk.VERTICAL,
            command=self._mask_output_text.yview,
        )
        output_scroll.configure(
            bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0,
        )
        output_scroll.grid(row=0, column=1, sticky="ns")
        self._mask_output_text.configure(yscrollcommand=output_scroll.set)

        self._mask_output_text.tag_configure("success", foreground=SUCCESS)
        self._mask_output_text.tag_configure("error", foreground=ERR_COLOR)
        self._mask_output_text.tag_configure("info", foreground=INFO_COLOR)
        row += 1

        self._mask_progress_var = tk.IntVar(value=0)
        self._mask_progress_bar = ttk.Progressbar(
            parent, variable=self._mask_progress_var, maximum=100,
        )
        self._mask_progress_bar.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 2),
        )
        row += 1

        self._mask_progress_label = tk.Label(
            parent, text="Ready", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, anchor="w",
        )
        self._mask_progress_label.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=15,
        )
        row += 1

        mask_btn_frame = tk.Frame(parent, bg=BG)
        mask_btn_frame.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(8, 10),
        )

        close_btn = tk.Label(
            mask_btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        stop_btn = tk.Label(
            mask_btn_frame, text="  Stop  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        stop_btn.pack(side=tk.RIGHT, padx=(5, 0))
        stop_btn.bind("<Button-1>", lambda e: self._stop())
        stop_btn.bind("<Enter>", lambda e: stop_btn.config(bg="#333333"))
        stop_btn.bind("<Leave>", lambda e: stop_btn.config(bg="#222222"))

        start_btn = tk.Label(
            mask_btn_frame, text="  Start  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        start_btn.pack(side=tk.RIGHT, padx=(5, 0))
        start_btn.bind("<Button-1>", lambda e: self._start_mask())
        start_btn.bind("<Enter>", lambda e: start_btn.config(bg="#333333"))
        start_btn.bind("<Leave>", lambda e: start_btn.config(bg="#222222"))

        self._populate_mask_hashes()

    def _populate_mask_hashes(self):
        items = credential_db.load_hashes()
        if not items:
            return
        self._mask_hash_listbox.delete(0, tk.END)
        for item in items:
            htype = item.get("type", "")
            mode = self._modes_by_type.get(htype, item.get("hascat_mode", ""))
            mode_str = f"  [{mode}] " if mode else "  "
            label = f"{mode_str}{htype:<30} {item.get('hash', '')[:30]}"
            self._mask_hash_listbox.insert(tk.END, label)
        self._mask_hash_listbox.selection_set(0)
        self._on_mask_hash_select()

    def _on_mask_hash_select(self, event=None):
        items = credential_db.load_hashes()
        sel = self._mask_hash_listbox.curselection()
        if not sel or sel[0] >= len(items):
            return
        item = items[sel[0]]
        htype = item.get("type", "")
        mode = self._modes_by_type.get(htype, item.get("hascat_mode", ""))
        self._mode_var.set(mode or "")
        self._hash_val_var.set(item.get("hash", ""))
        self._type_label_var.set(htype)

    def _on_mask_changed(self, *_):
        mask = self._mask_var.get()
        if mask:
            self._mask_progress_label.config(
                text=f"  Mask: {mask} ({mask.count('?')} chars)")
        else:
            self._mask_progress_label.config(text="  Ready")

    def _build_mask_hw_buttons(self, hw):
        self._mask_hw_placeholder.destroy()

        def _build_rb(text, value):
            return tk.Radiobutton(
                self._mask_hw_frame, text=text, variable=self._hw_var,
                value=value, bg=BG, fg=FG, selectcolor=BG,
                font=fonts.view_font(11), activebackground=BG,
                activeforeground=FG, indicatoron=False, relief=tk.FLAT,
            )

        auto_rb = _build_rb("  Auto  ", "auto")
        auto_rb.pack(side=tk.LEFT, padx=(0, 5))
        auto_rb.bind("<Enter>", lambda e: auto_rb.config(bg="#333333"))
        auto_rb.bind("<Leave>", lambda e: auto_rb.config(bg=BG))

        if hw.get("cpu", True):
            cpu_rb = _build_rb("  CPU  ", "1")
            cpu_rb.pack(side=tk.LEFT, padx=(0, 5))
            cpu_rb.bind("<Enter>", lambda e: cpu_rb.config(bg="#333333"))
            cpu_rb.bind("<Leave>", lambda e: cpu_rb.config(bg=BG))
            cpu_rb.select()

        if hw.get("gpu", True):
            gpu_rb = _build_rb("  GPU  ", "2")
            gpu_rb.pack(side=tk.LEFT, padx=(0, 5))
            gpu_rb.bind("<Enter>", lambda e: gpu_rb.config(bg="#333333"))
            gpu_rb.bind("<Leave>", lambda e: gpu_rb.config(bg=BG))

        auto_rb.select()

    def _start_mask(self):
        mode = self._mode_var.get().strip()
        if not mode:
            self._mask_write_output("Hashcat mode is required.\n", "error")
            return
        hash_val = self._hash_val_var.get().strip()
        if not hash_val:
            self._mask_write_output("No hash selected. Switch to Crack tab.\n", "error")
            return
        mask = self._mask_var.get().strip()
        if not mask:
            self._mask_write_output("Mask is required.\n", "error")
            return

        custom_charsets = {}
        for key, var in self._mask_cs_vars.items():
            val = var.get().strip()
            if val:
                custom_charsets[key] = val

        self._cracked = []
        self._mask_output_text.configure(state=tk.NORMAL)
        self._mask_output_text.delete("1.0", tk.END)
        self._mask_output_text.configure(state=tk.DISABLED)
        self._mask_progress_var.set(0)
        self._mask_progress_label.config(text=f"  Mask: {mask} ({mask.count('?')} chars)")

        backend = self._hw_var.get()
        if backend == "auto":
            backend = None

        engine = HashcatEngine(
            mode=mode,
            hash_value=hash_val,
            mask=mask,
            custom_charsets=custom_charsets,
            backend=backend,
            on_output=lambda t, c=None: self._mask_write_output(t, c),
            on_cracked=self._on_mask_cracked,
            on_done=self._on_mask_done,
            on_progress=self._on_mask_progress,
        )
        self._engine = engine
        engine.start()

    def _on_mask_done(self, cracked):
        self._engine = None
        def _update():
            if not self.winfo_exists():
                return
            self._mask_progress_var.set(100)
            if cracked:
                self._mask_write_output(
                    f"\n[+] Done. {len(cracked)} password(s) cracked.\n", "success")
                self._mask_progress_label.config(
                    text=f"  Done. {len(cracked)} cracked")
            else:
                self._mask_write_output(
                    "\n[-] Done. No passwords found.\n", "info")
                self._mask_progress_label.config(
                    text="  Done. No passwords found")
        self.after(0, _update)

    def _on_mask_progress(self, done, total, recovered):
        if not self.winfo_exists():
            return
        pct = int(done * 100 / max(total, 1))
        def _update():
            if not self.winfo_exists():
                return
            self._mask_progress_var.set(pct)
            parts = [f"  {done}/{total}"]
            if recovered:
                parts.append(f"  recovered: {recovered}")
            self._mask_progress_label.config(text="".join(parts))
        self.after(0, _update)

    def _mask_write_output(self, text, color=None):
        self.after(0, lambda: self._mask_do_write(text, color))

    def _mask_do_write(self, text, color=None):
        if not self.winfo_exists():
            return
        self._mask_output_text.configure(state=tk.NORMAL)
        is_at_bottom = self._mask_output_text.yview()[1] >= 1.0
        if color:
            self._mask_output_text.insert(tk.END, text, color)
        else:
            self._mask_output_text.insert(tk.END, text)
        if is_at_bottom:
            self._mask_output_text.see(tk.END)
        self._mask_output_text.configure(state=tk.DISABLED)

    # ─── Add Hash Tab ───────────────────────────────────────────

    def _build_add_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)

        self._add_sel_type = None

        tk.Label(
            parent, text="Type", font=fonts.view_font_bold(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        type_frame = tk.Frame(parent, bg=BG_WIDGET)
        type_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 5))
        type_frame.columnconfigure(0, weight=1)
        type_frame.rowconfigure(0, weight=1)

        self._add_type_list = tk.Listbox(
            type_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=4,
        )
        self._add_type_list.grid(row=0, column=0, sticky="nsew")
        self._add_type_list.bind("<<ListboxSelect>>", self._add_on_type_select)

        scrollbar = tk.Scrollbar(type_frame, orient=tk.VERTICAL, command=self._add_type_list.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._add_type_list.configure(yscrollcommand=scrollbar.set)

        self._add_type_names = []
        self._add_type_modes = {}
        self._add_type_examples = {}
        try:
            import sqlite3
            db_path = str(_hashcat_db())
            if os.path.isfile(db_path):
                conn = sqlite3.connect(db_path)
                rows = conn.execute(
                    'SELECT "Hash-Mode", "Hash-Name", "Example" '
                    'FROM DefaultMode ORDER BY "Hash-Mode"'
                ).fetchall()
                for mode, name, example in rows:
                    self._add_type_list.insert(tk.END, f"  {name}")
                    self._add_type_names.append(name)
                    self._add_type_modes[name] = str(mode) if mode != -1 else ""
                    self._add_type_examples[name] = example
                conn.close()
                if self._add_type_names:
                    self._add_type_list.selection_set(0)
        except Exception:
            pass

        self._add_example_label = tk.Label(
            parent, text="", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, wraplength=600,
        )
        self._add_example_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=15, pady=(2, 5))

        fields = [
            ("Hash", "hash", ""),
            ("Salt", "salt", ""),
            ("Peper", "peper", ""),
            ("Hashcat mode", "hascat_mode", ""),
            ("Origin", "origin_obteined", "Added manually by user"),
        ]

        row = 3
        for label, key, default in fields:
            tk.Label(
                parent, text=f"{label}:", font=fonts.view_font(11),
                fg=FG_DIM, bg=BG,
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(6, 0))
            var = tk.StringVar(value=default)
            tk.Entry(
                parent, textvariable=var,
                bg=BG_WIDGET, fg=FG, insertbackground=FG,
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15, pady=(6, 0))
            setattr(self, f"_add_{key}_var", var)
            row += 1

        self._add_feedback = tk.Label(
            parent, text="", font=fonts.view_font(11),
            fg=SUCCESS, bg=BG,
        )
        self._add_feedback.grid(row=row, column=0, columnspan=2, pady=(6, 0))
        row += 1

        add_btn_frame = tk.Frame(parent, bg=BG)
        add_btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(10, 10))

        close_btn = tk.Label(
            add_btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        add_btn = tk.Label(
            add_btn_frame, text="  Add  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.RIGHT)
        add_btn.bind("<Button-1>", lambda e: self._add_save())
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

    def _add_on_type_select(self, event):
        idx = self._add_type_list.curselection()
        if idx and idx[0] < len(self._add_type_names):
            name = self._add_type_names[idx[0]]
            self._add_sel_type = name
            self._add_hascat_mode_var.set(self._add_type_modes.get(name, ""))
            example = self._add_type_examples.get(name, "")
            if example:
                show = example if len(example) < 80 else example[:80] + "..."
                self._add_example_label.config(text=f"  Example: {show}")
            else:
                self._add_example_label.config(text="")

    def _add_save(self):
        if not self._add_sel_type:
            return
        credential_db.save_hash_entry(
            self._add_sel_type,
            self._add_hash_var.get().strip(),
            self._add_salt_var.get().strip(),
            self._add_peper_var.get().strip(),
            self._add_hascat_mode_var.get().strip(),
            self._add_origin_obteined_var.get().strip(),
        )
        self.result = True
        self._add_feedback.config(text="Done.")
        self.after(800, lambda: self._add_feedback.config(text=""))
        self._refresh_hash_list()

    # ─── Shared Methods ─────────────────────────────────────────

    def _refresh_hash_list(self):
        self._hash_items.clear()
        self._hash_listbox.delete(0, tk.END)
        self._modes_by_type.clear()
        self._populate_hashes()
        if hasattr(self, "_mask_hash_listbox"):
            self._populate_mask_hashes()

    def _populate_hashes(self):
        items = credential_db.load_hashes()
        if not items:
            return

        try:
            import sqlite3
            conn = sqlite3.connect(str(_hashcat_db()))
            rows = conn.execute(
                'SELECT "Hash-Name", "Hash-Mode" FROM DefaultMode'
            ).fetchall()
            for name, mode in rows:
                self._modes_by_type[name] = str(mode)
            conn.close()
        except Exception:
            pass

        for item in items:
            self._hash_items.append(item)
            htype = item.get("type", "")
            mode = self._modes_by_type.get(htype, item.get("hascat_mode", ""))
            mode_str = f"  [{mode}] " if mode else "  "
            label = f"{mode_str}{htype:<30} {item.get('hash', '')[:30]}"
            self._hash_listbox.insert(tk.END, label)
        if self._hash_items:
            self._hash_listbox.selection_set(0)
            self._on_hash_select()

    def _on_hash_select(self, event=None):
        sel = self._hash_listbox.curselection()
        if not sel or sel[0] >= len(self._hash_items):
            return
        item = self._hash_items[sel[0]]
        htype = item.get("type", "")
        mode = self._modes_by_type.get(htype, item.get("hascat_mode", ""))
        self._mode_var.set(mode or "")
        self._hash_val_var.set(item.get("hash", ""))
        self._type_label_var.set(htype)

    def _browse_wordlist(self):
        from tkinter import filedialog
        from src.elwand_paths import lst_dir
        f = filedialog.askopenfilename(
            title="Select wordlist",
            initialdir=str(lst_dir()),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            self._wl_var.set(f)

    def _browse_rules(self):
        from tkinter import filedialog
        from src.elwand_paths import rules_dir
        f = filedialog.askopenfilename(
            title="Select rules file",
            initialdir=str(rules_dir()),
            filetypes=[("Rule files", "*.rule"), ("All files", "*.*")])
        if f:
            self._rules_var.set(f)

    def _detect_hardware(self):
        threading.Thread(target=self._run_hw_detect, daemon=True).start()

    def _run_hw_detect(self):
        hw = HashcatEngine.detect_hardware()
        self.after(0, lambda: self._on_hw_detected(hw))

    def _on_hw_detected(self, hw):
        self._hw = hw
        self._hw_label.destroy()

        has_cpu = hw.get("cpu", True)
        has_gpu = hw.get("gpu", True)

        def _build_rb(text, value):
            rb = tk.Radiobutton(
                self._hw_frame, text=text, variable=self._hw_var, value=value,
                bg=BG, fg=FG, selectcolor=BG, font=fonts.view_font(11),
                activebackground=BG, activeforeground=FG,
                indicatoron=False, relief=tk.FLAT,
            )
            return rb

        self._hw_auto_rb = _build_rb("  Auto  ", "auto")
        self._hw_auto_rb.pack(side=tk.LEFT, padx=(0, 5))
        self._hw_auto_rb.bind("<Enter>", lambda e: self._hw_auto_rb.config(bg="#333333"))
        self._hw_auto_rb.bind("<Leave>", lambda e: self._hw_auto_rb.config(bg=BG))

        if has_cpu:
            self._hw_cpu_rb = _build_rb("  CPU  ", "1")
            self._hw_cpu_rb.pack(side=tk.LEFT, padx=(0, 5))
            self._hw_cpu_rb.bind("<Enter>", lambda e: self._hw_cpu_rb.config(bg="#333333"))
            self._hw_cpu_rb.bind("<Leave>", lambda e: self._hw_cpu_rb.config(bg=BG))
            self._hw_cpu_rb.select()

        if has_gpu:
            self._hw_gpu_rb = _build_rb("  GPU  ", "2")
            self._hw_gpu_rb.pack(side=tk.LEFT, padx=(0, 5))
            self._hw_gpu_rb.bind("<Enter>", lambda e: self._hw_gpu_rb.config(bg="#333333"))
            self._hw_gpu_rb.bind("<Leave>", lambda e: self._hw_gpu_rb.config(bg=BG))

        self._hw_auto_rb.select()

        if hasattr(self, "_mask_hw_placeholder"):
            self._build_mask_hw_buttons(hw)

    def _start(self):
        mode = self._mode_var.get().strip()
        if not mode:
            self._write_output("Hashcat mode is required.\n", "error")
            return
        hash_val = self._hash_val_var.get().strip()
        if not hash_val:
            self._write_output("Hash value is required.\n", "error")
            return
        wl = self._wl_var.get().strip()
        if not wl:
            self._write_output("Wordlist is required.\n", "error")
            return
        if not os.path.isfile(wl):
            self._write_output(f"Wordlist not found: {wl}\n", "error")
            return

        rules = self._rules_var.get().strip() or None
        if rules and not os.path.isfile(rules):
            self._write_output(f"Rules file not found: {rules}\n", "error")
            return

        self._cracked = []
        self._clear_output()
        self._progress_var.set(0)
        self._progress_label.config(text="Running...")

        backend = self._hw_var.get()
        if backend == "auto":
            backend = None

        engine = HashcatEngine(
            mode=mode,
            hash_value=hash_val,
            wordlist=wl,
            rules_file=rules,
            backend=backend,
            on_output=self._write_output,
            on_cracked=self._on_cracked,
            on_done=self._on_done,
            on_progress=self._on_progress,
        )
        self._engine = engine
        engine.start()

    def _stop(self):
        if self._engine:
            self._engine.stop()
            self._write_output("Stopped.\n", "info")
            self._mask_write_output("Stopped.\n", "info")

    def _on_cracked(self, hash_val, plain):
        self._cracked.append(plain)
        credential_db.save_password(plain)
        self.after(0, lambda: self._write_output(
            f"\n[+] Cracked: {plain}  (saved to inventory)\n", "success"))

    def _on_mask_cracked(self, hash_val, plain):
        self._cracked.append(plain)
        credential_db.save_password(plain)
        self.after(0, lambda: self._mask_write_output(
            f"\n[+] Cracked: {plain}  (saved to inventory)\n", "success"))

    def _on_done(self, cracked):
        self._engine = None
        def _update():
            if not self.winfo_exists():
                return
            self._progress_var.set(100)
            if cracked:
                self._write_output(
                    f"\n[+] Done. {len(cracked)} password(s) cracked.\n", "success")
                self._progress_label.config(text=f"  Done. {len(cracked)} cracked")
            else:
                self._write_output("\n[-] Done. No passwords found.\n", "info")
                self._progress_label.config(text="  Done. No passwords found")
        self.after(0, _update)

    def _on_progress(self, done, total, recovered):
        if not self.winfo_exists():
            return
        pct = int(done * 100 / max(total, 1))
        def _update():
            if not self.winfo_exists():
                return
            self._progress_var.set(pct)
            parts = [f"  {done}/{total}"]
            if recovered:
                parts.append(f"  recovered: {recovered}")
            self._progress_label.config(text="".join(parts))
        self.after(0, _update)

    def _write_output(self, text, color=None):
        self.after(0, lambda: self._do_write(text, color))

    def _do_write(self, text, color=None):
        if not self.winfo_exists():
            return
        self._output_text.configure(state=tk.NORMAL)
        is_at_bottom = self._output_text.yview()[1] >= 1.0
        if color:
            self._output_text.insert(tk.END, text, color)
        else:
            self._output_text.insert(tk.END, text)
        if is_at_bottom:
            self._output_text.see(tk.END)
        self._output_text.configure(state=tk.DISABLED)

    def _clear_output(self):
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.delete("1.0", tk.END)
        self._output_text.configure(state=tk.DISABLED)

    # ─── Detect Tab ─────────────────────────────────────────────

    def _build_detect_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=0)
        parent.rowconfigure(3, weight=0)

        tk.Label(
            parent, text="Paste text or load a file to detect hash types",
            font=fonts.view_font_bold(11), fg=FG, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        text_frame = tk.Frame(parent, bg=BG_WIDGET)
        text_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self._detect_text = tk.Text(
            text_frame, bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            wrap=tk.WORD, height=6,
        )
        self._detect_text.grid(row=0, column=0, sticky="nsew")

        detect_scroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                     command=self._detect_text.yview)
        detect_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                                width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        detect_scroll.grid(row=0, column=1, sticky="ns")
        self._detect_text.configure(yscrollcommand=detect_scroll.set)

        detect_btn_frame = tk.Frame(parent, bg=BG)
        detect_btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))

        load_btn = tk.Label(
            detect_btn_frame, text="  Load file...  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        load_btn.pack(side=tk.LEFT)
        load_btn.bind("<Button-1>", lambda e: self._detect_load_file())
        load_btn.bind("<Enter>", lambda e: load_btn.config(bg="#333333"))
        load_btn.bind("<Leave>", lambda e: load_btn.config(bg="#222222"))

        detect_btn = tk.Label(
            detect_btn_frame, text="  Detect  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        detect_btn.pack(side=tk.LEFT, padx=(10, 0))
        detect_btn.bind("<Button-1>", lambda e: self._detect_hashes())
        detect_btn.bind("<Enter>", lambda e: detect_btn.config(bg="#333333"))
        detect_btn.bind("<Leave>", lambda e: detect_btn.config(bg="#222222"))

        self._detect_count_label = tk.Label(
            parent, text="", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, anchor="w",
        )
        self._detect_count_label.grid(row=3, column=0, sticky="w", padx=15, pady=(0, 5))

        results_frame = tk.Frame(parent, bg=BG_WIDGET)
        results_frame.grid(row=4, column=0, sticky="nsew", padx=15, pady=(0, 5))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        self._detect_listbox = tk.Listbox(
            results_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False,
        )
        self._detect_listbox.grid(row=0, column=0, sticky="nsew")

        list_scroll = tk.Scrollbar(results_frame, orient=tk.VERTICAL,
                                   command=self._detect_listbox.yview)
        list_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self._detect_listbox.configure(yscrollcommand=list_scroll.set)

        self._detect_listbox.bind("<Double-Button-1>", lambda e: self._detect_save_selected())

        self._detect_results = []

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=5, column=0, sticky="ew", padx=15, pady=(10, 10))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        save_sel_btn = tk.Label(
            btn_frame, text="  Save selected  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        save_sel_btn.pack(side=tk.RIGHT)
        save_sel_btn.bind("<Button-1>", lambda e: self._detect_save_selected())
        save_sel_btn.bind("<Enter>", lambda e: save_sel_btn.config(bg="#333333"))
        save_sel_btn.bind("<Leave>", lambda e: save_sel_btn.config(bg="#222222"))

    def _build_detect_db(self):
        if self._detect_db is not None:
            return
        self._detect_db = {"prefix": [], "length": defaultdict(list), "structured": []}
        try:
            db_path = str(_hashcat_db())
            if not os.path.isfile(db_path):
                return
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                'SELECT "Hash-Mode", "Hash-Name", "Example" FROM DefaultMode'
            ).fetchall()
            conn.close()
        except Exception:
            return

        for mode, name, example in rows:
            if not example or example.startswith("http"):
                continue
            mode = str(mode) if mode != -1 else ""
            hash_part = example.split(":")[0]

            prefix = _extract_prefix(hash_part)
            if prefix:
                if prefix == "$2a$" or prefix == "$2b$" or prefix == "$2y$":
                    prefix = r"\$2[aby]\$"
                else:
                    prefix = re.escape(prefix)
                pref_re = re.compile(r"(?:^|\s)(" + prefix + r"\S+)")
                self._detect_db["prefix"].append((pref_re, mode, name, hash_part))
                continue

            fields = example.split(":")
            if len(fields) >= 3:
                pattern = _build_structured_pattern(fields)
                if pattern:
                    try:
                        compiled = re.compile(pattern)
                        self._detect_db["structured"].append((compiled, mode, name))
                    except re.error:
                        pass
                continue

            cs = _charset_type(hash_part)
            if cs:
                key = (len(hash_part), cs)
                self._detect_db["length"][key].append((mode, name))

    def _detect_hashes(self):
        self._build_detect_db()
        if not self._detect_db:
            return

        text = self._detect_text.get("1.0", tk.END).strip()
        if not text:
            self._detect_count_label.config(text="")
            self._detect_listbox.delete(0, tk.END)
            self._detect_results.clear()
            return

        results = []
        seen = set()

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            matched = False
            if ":" in line:
                for regex, mode, name in self._detect_db["structured"]:
                    if regex.match(line):
                        key = f"{mode}:{line[:40]}"
                        if key not in seen:
                            seen.add(key)
                            results.append((line, [(mode, name)]))
                        matched = True
                        break

            tokens = _extract_tokens(line) if not matched else []
            for token in tokens:
                if token in seen:
                    continue
                matches = self._match_token(token)
                if matches:
                    seen.add(token)
                    results.append((token, matches))

        self._detect_results = results
        self._detect_listbox.delete(0, tk.END)

        if results:
            self._detect_count_label.config(
                text=f"  {len(results)} hash(es) found")
            for token, matches in results:
                for mode, name in matches:
                    display = token if len(token) <= 40 else token[:37] + "..."
                    mode_str = f"[{mode}]" if mode else "[?]"
                    self._detect_listbox.insert(
                        tk.END, f"  {mode_str:<8} {name:<28} {display}")
        else:
            self._detect_count_label.config(text="  No hashes detected")

    def _match_token(self, token):
        matches = []
        for pref_re, mode, name, _example in self._detect_db["prefix"]:
            if pref_re.match(token) or pref_re.search(token):
                matches.append((mode, name))
        if matches:
            return matches
        for charset in ("hex", "crypt", "b64"):
            cs = _charset_type_max(token, charset)
            if cs:
                key = (len(token), cs)
                matches.extend(self._detect_db["length"].get(key, []))
                if matches:
                    break
        return matches

    def _detect_load_file(self):
        from tkinter import filedialog
        f = filedialog.askopenfilename(
            title="Load file for hash detection",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not f:
            return
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            return
        self._detect_text.delete("1.0", tk.END)
        self._detect_text.insert("1.0", content)

    def _detect_save_selected(self):
        sel = self._detect_listbox.curselection()
        if not sel or not self._detect_results:
            return
        line_idx = sel[0]
        current = 0
        for token, matches in self._detect_results:
            count = len(matches)
            if current + count > line_idx:
                match_idx = line_idx - current
                mode, name = matches[match_idx]
                credential_db.save_hash_entry(
                    hash_type=name,
                    hash_value=token,
                    hascat_mode=mode,
                    origin="detected",
                )
                self._detect_count_label.config(
                    text=f"  Saved: [{mode}] {name}")
                self._refresh_hash_list()
                self.after(1500, lambda: self._detect_count_label.config(
                    text=f"  {len(self._detect_results)} hash(es) found"))
                return
            current += count

    def _on_close(self):
        self._stop()
        self.destroy()


# ─── Hash Detection Helpers ─────────────────────────────────────

_HEX_RE = re.compile(r"^[a-fA-F0-9]+$")
_CRYPT_RE = re.compile(r"^[./0-9A-Za-z]+$")
_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")
_TOKEN_RE = re.compile(
    r"\b[a-fA-F0-9]{16,}\b"
    r"|\b[./0-9A-Za-z]{13,}\b"
    r"|\b[A-Za-z0-9+/=]{20,}\b"
)


def _extract_prefix(s):
    if s.startswith("$"):
        m = re.match(r"(\$[^$]+\$)", s)
        if m:
            return m.group(1)
    if s.startswith("{") and "}" in s:
        m = re.match(r"(\{[^}]+\})", s)
        if m:
            return m.group(1)
    return None


def _build_structured_pattern(fields):
    parts = []
    for i, f in enumerate(fields):
        f = f.strip()
        if not f:
            parts.append(r":?")
        elif _HEX_RE.match(f):
            n = len(f)
            if i == len(fields) - 1 and n >= 32:
                parts.append(r"[a-fA-F0-9]{32,}")
            else:
                parts.append(f"[a-fA-F0-9]{{{n}}}")
        elif _CRYPT_RE.match(f):
            parts.append(f"[./0-9A-Za-z]{{{len(f)}}}")
        else:
            parts.append(r"[^\s:]+")
    return r"^" + r":".join(parts) + r"$"


def _charset_type(s):
    if _HEX_RE.match(s):
        return "hex"
    if _CRYPT_RE.match(s):
        return "crypt"
    if _B64_RE.match(s):
        return "b64"
    return None


def _charset_type_max(s, default_cs):
    if default_cs == "hex" and _HEX_RE.match(s):
        return "hex"
    if default_cs == "crypt" and _CRYPT_RE.match(s):
        return "crypt"
    if default_cs == "b64" and _B64_RE.match(s):
        return "b64"
    return None


def _extract_tokens(line):
    if line.startswith("$") or line.startswith("{"):
        return [line]
    tokens = []
    for token in _TOKEN_RE.findall(line):
        if token and not _is_junk(token):
            tokens.append(token)
    return tokens


_JUNK_RE = re.compile(
    r"^(\d)\1{7,}$"             # all same digit  1111111111111111
    r"|^0+$"                     # all zeros      0000000000000000
    r"|^[a-fA-F](\d)\1{6,}$"    # hex with trailing repeated digit
)


def _is_junk(token):
    if not token:
        return True
    s = set(token.lower())
    if len(s) <= 2:
        return True
    if _JUNK_RE.match(token):
        return True
    return False
