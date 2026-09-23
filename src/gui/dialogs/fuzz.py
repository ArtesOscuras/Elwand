from src.gui import fonts
import os
import random
import re
import socket
import string
import tkinter as tk
import urllib.request
import ssl
from tkinter import ttk
from urllib.parse import urlparse

from src.tools.fuzz import FuzzEngine
from src.tools.fuzz.engine import ALL_CODES
from src.machines import store
from src.machines import machine_db
from src.machines import domain_db

BG = "#111111"
BG_WIDGET = "#000000"
FG = "#ffffff"
FG_DIM = "#888888"
SEL_BG = "#333333"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"
INFO_COLOR = "#5ba3ec"


class _TargetSection:
    def __init__(self, parent, row, mode="both", on_select=None):
        self._target_keys = []
        self._on_select = on_select
        self._mode = mode

        tk.Label(
            parent, text="Target", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 5))

        mode_frame = tk.Frame(parent, bg=BG)
        if mode != "domains":
            mode_frame.grid(row=row, column=1, sticky="w", padx=15, pady=(10, 5))
        else:
            mode_frame.grid(row=row, column=1, sticky="w", padx=15, pady=(10, 5))

        self._target_mode = tk.StringVar(value="machine" if mode == "both" else "domain")

        if mode == "both":
            machine_radio = tk.Radiobutton(
                mode_frame, text="  Machine  ", variable=self._target_mode, value="machine",
                bg=BG, fg=FG, selectcolor=BG, font=fonts.view_font(10),
                activebackground=BG, activeforeground=FG,
                indicatoron=False, relief=tk.FLAT,
                command=self._populate,
            )
            machine_radio.pack(side=tk.LEFT, padx=(0, 5))

            domain_radio = tk.Radiobutton(
                mode_frame, text="  Domain  ", variable=self._target_mode, value="domain",
                bg=BG, fg=FG, selectcolor=BG, font=fonts.view_font(10),
                activebackground=BG, activeforeground=FG,
                indicatoron=False, relief=tk.FLAT,
                command=self._populate,
            )
            domain_radio.pack(side=tk.LEFT)

        frame = tk.Frame(parent, bg=BG_WIDGET)
        frame.grid(row=row + 1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=self._listbox.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=scrollbar.set)

        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._populate()
        self._listbox.bind("<Return>", lambda e: self._start if hasattr(self, '_start') else None)

    def _on_list_select(self, event):
        if self._on_select:
            target = self.selected()
            if target:
                self._on_select(target[1])

    def _populate(self):
        self._listbox.delete(0, tk.END)
        self._target_keys = []

        if self._target_mode.get() == "machine":
            machines = store.get_all_sorted()
            for m in machines:
                if m.ip in ("127.0.0.1", "::1") or m.ip.startswith("127."):
                    continue
                label = f"{m.ip:<18}{m.hostname or ''}".rstrip()
                self._listbox.insert(tk.END, f"  {label}")
                self._target_keys.append(("machine", m.ip, m.hostname, m.ip))
        else:
            domains = domain_db.list_all()
            domains.sort()
            for d in domains:
                self._listbox.insert(tk.END, f"  {d}")
                self._target_keys.append(("domain", d, d, None))

        if self._target_keys:
            self._listbox.selection_set(0)
            self._on_list_select(None)

    def selected(self):
        sel = self._listbox.curselection()
        if not sel:
            return None
        return self._target_keys[sel[0]]


class _WordlistSection:
    def __init__(self, parent, row):
        tk.Label(
            parent, text="Wordlist", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 5))

        self._path = tk.StringVar()

        path_frame = tk.Frame(parent, bg=BG)
        path_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 5))

        path_label = tk.Label(path_frame, textvariable=self._path, fg=FG, bg=BG,
                              font=fonts.view_font(9), anchor="w")
        path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_btn = tk.Label(path_frame, text="  Browse...  ", bg="#222222", fg=FG,
                              font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=10, pady=4)
        browse_btn.pack(side=tk.LEFT)
        browse_btn.bind("<Button-1>", lambda e: self._browse())
        browse_btn.bind("<Enter>", lambda e: browse_btn.config(bg="#333333"))
        browse_btn.bind("<Leave>", lambda e: browse_btn.config(bg="#222222"))

    def _browse(self):
        from tkinter import filedialog
        from src.elwand_paths import lst_dir
        f = filedialog.askopenfilename(
            initialdir=str(lst_dir()),
            title="Select wordlist",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            self._path.set(f)

    def selected(self):
        return self._path.get() or None


class FuzzDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self._engine = None
        self._dir_results = []
        self._dir_url_template = None
        self._vhost_results = []
        self._dns_results = []

        self.title("Fuzz")
        self.geometry("800x700")
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=(15, 0))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222", foreground=FG,
                        padding=[20, 6], font=fonts.view_font(10))
        style.map("TNotebook.Tab", background=[("selected", "#333333")])

        self._tab_dir = tk.Frame(self._notebook, bg=BG)
        self._tab_vhost = tk.Frame(self._notebook, bg=BG)
        self._tab_dns = tk.Frame(self._notebook, bg=BG)

        self._notebook.add(self._tab_dir, text="Directory")
        self._notebook.add(self._tab_vhost, text="Vhost subdomain")
        self._notebook.add(self._tab_dns, text="DNS subdomain")
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._tab_dir.columnconfigure(0, weight=1)
        self._tab_dir.columnconfigure(1, weight=1)
        self._tab_vhost.columnconfigure(0, weight=1)
        self._tab_vhost.columnconfigure(1, weight=1)
        self._tab_dns.columnconfigure(0, weight=1)
        self._tab_dns.columnconfigure(1, weight=1)

        self._build_directory_tab()
        self._build_vhost_tab()
        self._build_dns_tab()
        self._build_output_section()
        self._build_buttons()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_directory_tab(self):
        tab = self._tab_dir

        self._url_var = tk.StringVar()

        def _on_target_change(value):
            if not value:
                return
            current = self._url_var.get()
            if "://" in current:
                prefix, rest = current.split("://", 1)
                if "/" in rest:
                    _, path = rest.split("/", 1)
                else:
                    path = "FUZZ"
                self._url_var.set(f"{prefix}://{value}/{path}")
            else:
                self._url_var.set(f"http://{value}/FUZZ")

        self._target_dir = _TargetSection(tab, 0, mode="both", on_select=_on_target_change)

        tk.Label(
            tab, text="URL", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=2, column=0, sticky="w", padx=15, pady=(10, 0))

        self._url_entry = tk.Entry(
            tab, textvariable=self._url_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._url_entry.grid(row=2, column=1, sticky="ew", padx=15, pady=(10, 0))

        self._wl_dir = _WordlistSection(tab, 3)

        thread_row = 4
        tk.Label(
            tab, text="Threads", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=thread_row, column=0, sticky="w", padx=15, pady=(10, 0))
        self._thread_dir_var = tk.StringVar(value="20")
        tk.Entry(
            tab, textvariable=self._thread_dir_var, width=6,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=thread_row, column=1, sticky="w", padx=15, pady=(10, 0))

        row = 5
        tk.Label(
            tab, text="Show codes", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 0))
        self._filter_dir_var = tk.StringVar(value=",".join(str(c) for c in ALL_CODES))
        tk.Entry(
            tab, textvariable=self._filter_dir_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 0))

        row += 1
        tk.Label(
            tab, text="Hide size range", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 0))
        self._range_dir_var = tk.StringVar()
        tk.Entry(
            tab, textvariable=self._range_dir_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 0))

        self._wildcard_dir_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            tab, text="Wildcard detection", variable=self._wildcard_dir_var,
            bg=BG, fg=FG, selectcolor=BG,
            font=fonts.view_font(10),
            activebackground=BG, activeforeground=FG,
        ).grid(row=row + 1, column=1, sticky="w", padx=15, pady=(10, 0))

    def _build_vhost_tab(self):
        tab = self._tab_vhost
        self._target_vhost = _TargetSection(tab, 0, mode="domains")

        self._wl_vhost = _WordlistSection(tab, 2)

        tk.Label(
            tab, text="Threads", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=3, column=0, sticky="w", padx=15, pady=(10, 0))
        self._thread_vhost_var = tk.StringVar(value="20")
        tk.Entry(
            tab, textvariable=self._thread_vhost_var, width=6,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=3, column=1, sticky="w", padx=15, pady=(10, 0))

        tk.Label(
            tab, text="Show codes", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=4, column=0, sticky="w", padx=15, pady=(10, 0))
        self._filter_vhost_var = tk.StringVar(value=",".join(str(c) for c in ALL_CODES))
        tk.Entry(
            tab, textvariable=self._filter_vhost_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=4, column=1, sticky="ew", padx=15, pady=(10, 0))

        tk.Label(
            tab, text="Hide size range", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=5, column=0, sticky="w", padx=15, pady=(10, 0))
        self._range_vhost_var = tk.StringVar()
        tk.Entry(
            tab, textvariable=self._range_vhost_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=5, column=1, sticky="ew", padx=15, pady=(10, 0))

        self._wildcard_vhost_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            tab, text="Wildcard detection", variable=self._wildcard_vhost_var,
            bg=BG, fg=FG, selectcolor=BG,
            font=fonts.view_font(10),
            activebackground=BG, activeforeground=FG,
        ).grid(row=6, column=1, sticky="w", padx=15, pady=(10, 0))

    def _build_dns_tab(self):
        tab = self._tab_dns
        self._target_dns = _TargetSection(tab, 0, mode="domains")

        self._wl_dns = _WordlistSection(tab, 2)

        tk.Label(
            tab, text="Threads", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=3, column=0, sticky="w", padx=15, pady=(10, 0))
        self._thread_dns_var = tk.StringVar(value="20")
        tk.Entry(
            tab, textvariable=self._thread_dns_var, width=6,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=3, column=1, sticky="w", padx=15, pady=(10, 0))

        tk.Label(
            tab, text="Show codes", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=4, column=0, sticky="w", padx=15, pady=(10, 0))
        self._filter_dns_var = tk.StringVar(value=",".join(str(c) for c in ALL_CODES))
        tk.Entry(
            tab, textvariable=self._filter_dns_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=4, column=1, sticky="ew", padx=15, pady=(10, 0))

        tk.Label(
            tab, text="Hide size range", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=5, column=0, sticky="w", padx=15, pady=(10, 0))
        self._range_dns_var = tk.StringVar()
        tk.Entry(
            tab, textvariable=self._range_dns_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=5, column=1, sticky="ew", padx=15, pady=(10, 0))

        self._wildcard_dns_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            tab, text="Wildcard detection", variable=self._wildcard_dns_var,
            bg=BG, fg=FG, selectcolor=BG,
            font=fonts.view_font(10),
            activebackground=BG, activeforeground=FG,
        ).grid(row=6, column=1, sticky="w", padx=15, pady=(10, 0))

    def _build_output_section(self):
        tk.Label(
            self, text="Output", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=1, column=0, sticky="nw", padx=15, pady=(10, 5))

        frame = tk.Frame(self, bg=BG_WIDGET)
        frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._output_text = tk.Text(
            frame, bg=BG_WIDGET, fg=FG_DIM, insertbackground=FG,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self._output_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=self._output_text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._output_text.configure(yscrollcommand=scrollbar.set)

        self._output_text.tag_configure("success", foreground=SUCCESS)
        self._output_text.tag_configure("error", foreground=ERR_COLOR)
        self._output_text.tag_configure("info", foreground=INFO_COLOR)

        self.rowconfigure(1, weight=1)

    def _build_buttons(self):
        row = 2
        self._progress_var = tk.IntVar(value=0)
        self._progress_bar = ttk.Progressbar(
            self, variable=self._progress_var, maximum=100,
        )
        self._progress_bar.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 2))

        row = 3
        self._progress_label = tk.Label(
            self,             text="Ready", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, anchor="w",
        )
        self._progress_label.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15)

        row = 4
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(10, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))
        self._close_btn = close_btn

        self._save_dir_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        self._save_dir_btn.bind("<Button-1>", lambda e: self._save_dir_results())
        self._save_dir_btn.bind("<Enter>", lambda e: self._save_dir_btn.config(bg="#333333"))
        self._save_dir_btn.bind("<Leave>", lambda e: self._save_dir_btn.config(bg="#222222"))

        self._save_vhost_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        self._save_vhost_btn.bind("<Button-1>", lambda e: self._save_vhost_results())
        self._save_vhost_btn.bind("<Enter>", lambda e: self._save_vhost_btn.config(bg="#333333"))
        self._save_vhost_btn.bind("<Leave>", lambda e: self._save_vhost_btn.config(bg="#222222"))

        self._save_dns_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        self._save_dns_btn.bind("<Button-1>", lambda e: self._save_dns_results())
        self._save_dns_btn.bind("<Enter>", lambda e: self._save_dns_btn.config(bg="#333333"))
        self._save_dns_btn.bind("<Leave>", lambda e: self._save_dns_btn.config(bg="#222222"))

        self._save_buttons = [self._save_dir_btn, self._save_vhost_btn, self._save_dns_btn]

        clear_btn = tk.Label(
            btn_frame, text="  Clear  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        clear_btn.pack(side=tk.RIGHT, padx=(5, 0))
        clear_btn.bind("<Button-1>", lambda e: self._clear())
        clear_btn.bind("<Enter>", lambda e: clear_btn.config(bg="#333333"))
        clear_btn.bind("<Leave>", lambda e: clear_btn.config(bg="#222222"))

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

    def _check_wildcard(self, method, target_val, url_template, target_ip,
                        show_codes, hide_size_range):
        word = ''.join(random.choices(string.ascii_lowercase, k=10))
        if method == "directory":
            url = url_template.replace("FUZZ", word)
            req = urllib.request.Request(
                url, headers={"User-Agent": "Elwand/1.0"})
        elif method == "vhost":
            ip = target_ip or target_val
            req = urllib.request.Request(
                f"http://{ip}/",
                headers={"User-Agent": "Elwand/1.0",
                         "Host": f"{word}.{target_val}"})
        else:
            req = urllib.request.Request(
                f"http://{word}.{target_val}/",
                headers={"User-Agent": "Elwand/1.0"})

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            resp = urllib.request.urlopen(req, timeout=5, context=ctx)
            body = resp.read(10240)
            status = resp.status
        except urllib.request.HTTPError as e:
            body = e.read(10240)
            status = e.code
        except Exception:
            return False, None, None

        detected = True
        if show_codes and status not in show_codes:
            detected = False
        if hide_size_range:
            lo, hi = hide_size_range
            if lo <= len(body) <= hi:
                detected = False
        return detected, status, len(body)

    def _start(self):
        tab = self._notebook.index(self._notebook.select())

        if tab == 0:
            target = self._target_dir.selected()
            wordlist = self._wl_dir.selected()
            if not target or not wordlist:
                return
            target_type, target_val, target_label, target_ip = target
            try:
                workers = int(self._thread_dir_var.get())
            except ValueError:
                workers = 20
            url_template = self._url_var.get()
            self._dir_url_template = url_template
            self._dir_results = []
            show_codes = self._parse_codes(self._filter_dir_var.get()) or None
            hide_size = self._parse_range(self._range_dir_var.get())

            self._write_output(f"\n[*] Starting directory fuzz: url={url_template} wordlist={os.path.basename(wordlist)} threads={workers} codes={show_codes}\n", "info")
            if self._wildcard_dir_var.get():
                self._write_output("[*] Checking wildcard...\n", "info")
                hit, status, size = self._check_wildcard(
                    "directory", target_val, url_template, target_ip,
                    show_codes, hide_size)
                if hit:
                    self._write_output(
                        f"[!] WILDCARD DETECTED — random path responded "
                        f"with status {status}, {size} bytes. "
                        f"Adjust show_codes or hide_size_range filters. "
                        f"Fuzzing aborted.\n", "error")
                    return
                self._write_output(
                    f"[*] Wildcard test passed (status {status}, {size} bytes).\n",
                    "info")
            self._engine = FuzzEngine(
                target=target_val, wordlist_path=wordlist, method="directory",
                url_template=url_template, on_result=self._write_output,
                workers=workers, on_progress=self._on_progress,
                on_found=self._on_found, show_codes=show_codes,
                hide_size_range=hide_size,
            )
        elif tab == 1:
            target = self._target_vhost.selected()
            wordlist = self._wl_vhost.selected()
            if not target or not wordlist:
                return
            target_type, target_val, target_label, target_ip = target
            try:
                workers = int(self._thread_vhost_var.get())
            except ValueError:
                workers = 20

            ip = target_ip if target_type == "machine" and target_ip else target_val
            self._vhost_results = []
            show_codes = self._parse_codes(self._filter_vhost_var.get()) or None
            hide_size = self._parse_range(self._range_vhost_var.get())

            self._write_output(f"\n[*] Starting vhost fuzz: target={target_label} wordlist={os.path.basename(wordlist)} threads={workers} codes={show_codes}\n", "info")
            if self._wildcard_vhost_var.get():
                self._write_output("[*] Checking wildcard...\n", "info")
                hit, status, size = self._check_wildcard(
                    "vhost", target_val, None, ip, show_codes, hide_size)
                if hit:
                    self._write_output(
                        f"[!] WILDCARD DETECTED — random vhost responded "
                        f"with status {status}, {size} bytes. "
                        f"Adjust show_codes or hide_size_range filters. "
                        f"Fuzzing aborted.\n", "error")
                    return
                self._write_output(
                    f"[*] Wildcard test passed (status {status}, {size} bytes).\n",
                    "info")
            self._engine = FuzzEngine(
                target=target_val, wordlist_path=wordlist, method="vhost",
                target_ip=ip, on_result=self._write_output, workers=workers,
                on_progress=self._on_progress,
                on_found=self._on_found, show_codes=show_codes,
                hide_size_range=hide_size,
            )
        else:
            target = self._target_dns.selected()
            wordlist = self._wl_dns.selected()
            if not target or not wordlist:
                return
            target_type, target_val, target_label, target_ip = target
            try:
                workers = int(self._thread_dns_var.get())
            except ValueError:
                workers = 20

            self._dns_results = []
            show_codes = self._parse_codes(self._filter_dns_var.get()) or None
            hide_size = self._parse_range(self._range_dns_var.get())

            self._write_output(f"\n[*] Starting dns fuzz: target={target_label} wordlist={os.path.basename(wordlist)} threads={workers} codes={show_codes}\n", "info")
            if self._wildcard_dns_var.get():
                self._write_output("[*] Checking wildcard...\n", "info")
                hit, status, size = self._check_wildcard(
                    "dns", target_val, None, None, show_codes, hide_size)
                if hit:
                    self._write_output(
                        f"[!] WILDCARD DETECTED — random subdomain responded "
                        f"with status {status}, {size} bytes. "
                        f"Adjust show_codes or hide_size_range filters. "
                        f"Fuzzing aborted.\n", "error")
                    return
                self._write_output(
                    f"[*] Wildcard test passed (status {status}, {size} bytes).\n",
                    "info")
            self._engine = FuzzEngine(
                target=target_val, wordlist_path=wordlist, method="dns",
                on_result=self._write_output, workers=workers,
                on_progress=self._on_progress,
                on_found=self._on_found, show_codes=show_codes,
                hide_size_range=hide_size,
            )
        self._engine.start()

    def _stop(self):
        if self._engine:
            self._engine.stop()

    def _on_progress(self, done, total, found):
        if not self.winfo_exists():
            return
        self.after(0, lambda: self._progress_var.set(int(done * 100 / max(total, 1))) if self.winfo_exists() else None)
        self.after(0, lambda: self._progress_label.config(
            text=f"  {done}/{total}  found: {found}"
        ) if self.winfo_exists() else None)

    def _on_found(self, word, display):
        tab = self._notebook.index(self._notebook.select())
        if tab == 0:
            if self._dir_url_template:
                full_url = self._dir_url_template.replace("FUZZ", word)
                self._dir_results.append((display, full_url))
        elif tab == 1:
            target = self._target_vhost.selected()
            if target:
                self._vhost_results.append((word, target))
        else:
            target = self._target_dns.selected()
            if target:
                self._dns_results.append((word, target))

    def _on_tab_changed(self, event):
        for btn in self._save_buttons:
            btn.pack_forget()
        tab = self._notebook.index(self._notebook.select())
        self._save_buttons[tab].pack(side=tk.LEFT, padx=(0, 5))

    def _save_dir_results(self):
        if not self._dir_results:
            return
        self._write_output(f"\n[*] Saving {len(self._dir_results)} directory results...\n", "info")
        for display, full_url in self._dir_results:
            parsed = urlparse(full_url)
            host = parsed.hostname
            path = parsed.path or "/"
            if not host:
                self._write_output(f"  [!] Cannot parse URL: {full_url}\n", "error")
                continue

            if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
                machine = store.get(host)
                if not machine:
                    machine = store.add_or_update(ip=host, method="manual")
                    machine.device_type = "device unknown"
                    machine_db.save_machine_info(machine)
                machine_db.save_directory(machine.id, path)
                self._write_output(f"  [+] {path} → machine #{machine.id} ({host})\n", "success")
            else:
                if not domain_db.exists(host):
                    try:
                        info = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
                        ip = info[0][4][0] if info else None
                    except Exception:
                        ip = None
                    if ip:
                        machine = store.get(ip)
                        if not machine:
                            machine = store.add_or_update(ip=ip, method="manual")
                            machine.device_type = "device unknown"
                            machine_db.save_machine_info(machine)
                        domain_db.init_or_update(host, machine.id, machine.ip, "fuzz")
                        machine_db.save_domain(machine.id, host, "fuzz")
                domain_db.save_directory(host, path)
                self._write_output(f"  [+] {path} → domain {host}\n", "success")
        self._write_output("[*] Done.\n", "info")

    def _save_vhost_results(self):
        if not self._vhost_results:
            return
        self._write_output(f"\n[*] Saving {len(self._vhost_results)} vhost results...\n", "info")
        for word, target in self._vhost_results:
            target_type, target_val, target_label, target_ip = target
            subdomain = f"{word}.{target_val}"
            domain_db.save_subdomain(target_val, subdomain, "vhost")
            self._write_output(f"  [+] {subdomain} → domain {target_val}\n", "success")
        self._write_output("[*] Done.\n", "info")

    def _save_dns_results(self):
        if not self._dns_results:
            return
        self._write_output(f"\n[*] Saving {len(self._dns_results)} dns results...\n", "info")
        for word, target in self._dns_results:
            target_type, target_val, target_label, target_ip = target
            subdomain = f"{word}.{target_val}"
            domain_db.save_subdomain(target_val, subdomain, "dns")
            self._write_output(f"  [+] {subdomain} → domain {target_val}\n", "success")
        self._write_output("[*] Done.\n", "info")

    def _clear(self):
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.delete("1.0", tk.END)
        self._output_text.configure(state=tk.DISABLED)
        self._progress_var.set(0)
        self._progress_label.config(text="Ready")

    @staticmethod
    def _parse_codes(text):
        codes = set()
        for part in text.split(","):
            part = part.strip()
            if part.isdigit():
                codes.add(int(part))
        return codes

    @staticmethod
    def _parse_range(text):
        text = text.strip()
        if not text:
            return None
        if "-" in text:
            parts = text.split("-", 1)
            if parts[0].isdigit() and parts[1].isdigit():
                return (int(parts[0]), int(parts[1]))
        if text.isdigit():
            n = int(text)
            return (n, n)
        return None

    def _on_close(self):
        self._stop()
        self.destroy()
