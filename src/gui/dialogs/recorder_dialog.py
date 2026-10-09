from src.gui import fonts, windowing, theme
import tkinter as tk
from tkinter import ttk

from src.machines import store
from src.machines import domain_db

BG = "#111111"
BG_WIDGET = "#000000"
FG = "#ffffff"
FG_DIM = "#888888"
SEL_BG = "#333333"
ERR_COLOR = "#f44747"


class _TargetSection:
    def __init__(self, parent, row, on_select=None):
        self._target_keys = []
        self._on_select = on_select

        mode_frame = tk.Frame(parent, bg=BG)
        mode_frame.grid(row=row, column=1, sticky="w", padx=15, pady=(10, 5))

        self._target_mode = tk.StringVar(value="machine")

        theme.Segmented(
            mode_frame,
            [("machine", "  Machine  "), ("domain", "  Domain  ")],
            self._target_mode, command=self._populate).pack(side=tk.LEFT)

        frame = tk.Frame(parent, bg=BG_WIDGET)
        frame.grid(row=row + 1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._listbox = theme.listbox(frame, height=3)
        self._listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = theme.scrollbar(frame, self._listbox)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._populate()

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


class WebRecorderDialog(tk.Toplevel):
    def __init__(self, parent, browsers, default_name=""):
        super().__init__(parent)
        self.result = None

        self.title("Web Recorder")
        windowing.size_dialog(self, 580, 660)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)
        self.rowconfigure(4, weight=1)
        self.rowconfigure(5, weight=0)
        self.rowconfigure(6, weight=1)
        self.rowconfigure(7, weight=0)
        self.rowconfigure(8, weight=0)

        tk.Label(
            self, text="Web Recorder Configuration", font=fonts.view_font_bold(16),
            fg=FG, bg=BG,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        tk.Label(
            self, text="Evidence name", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=1, column=0, sticky="w", padx=15, pady=(5, 0))
        tk.Label(
            self, text="(name for the evidence folder)", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG,
        ).grid(row=2, column=0, sticky="w", padx=15, pady=(0, 5))

        self._name_var = tk.StringVar(value=default_name)
        theme.entry(self, textvariable=self._name_var, width=40).grid(
            row=1, column=1, rowspan=2, sticky="ew", padx=15, pady=(5, 5))

        self._name_feedback = tk.Label(
            self, text="", font=fonts.view_font(9),
            fg=ERR_COLOR, bg=BG,
        )
        self._name_feedback.grid(row=2, column=1, sticky="w", padx=15, pady=(0, 0))

        tk.Label(
            self, text="Target", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=3, column=0, sticky="nw", padx=15, pady=(10, 5))

        self._url_var = tk.StringVar()

        def _on_target_change(value):
            if not value:
                return
            self._url_var.set(f"https://{value}/")

        self._target = _TargetSection(self, 3, on_select=_on_target_change)

        tk.Label(
            self, text="URL", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=5, column=0, sticky="w", padx=15, pady=(10, 0))
        theme.entry(self, textvariable=self._url_var, width=40).grid(
            row=5, column=1, sticky="ew", padx=15, pady=(10, 0))

        tk.Label(
            self, text="Browser", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=6, column=0, sticky="nw", padx=15, pady=(15, 5))

        frame = tk.Frame(self, bg=BG_WIDGET)
        frame.grid(row=6, column=1, sticky="nsew", padx=15, pady=(15, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._browser_listbox = theme.listbox(frame, height=4)
        self._browser_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = theme.scrollbar(frame, self._browser_listbox)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._browser_paths = []
        for path, label in sorted(browsers.items()):
            self._browser_listbox.insert(tk.END, f"  {label}  ({path})")
            self._browser_paths.append(path)
        if self._browser_paths:
            self._browser_listbox.selection_set(0)

        tk.Label(
            self, text="Scope", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=7, column=0, sticky="w", padx=15, pady=(15, 0))

        scope_frame = tk.Frame(self, bg=BG)
        scope_frame.grid(row=7, column=1, sticky="ew", padx=15, pady=(15, 0))

        self._scope_var = tk.BooleanVar(value=False)
        self._scope_check = theme.Toggle(
            scope_frame, "  Only capture matching domain",
            variable=self._scope_var)
        self._scope_check.pack(side=tk.LEFT)

        self._scope_domain_var = tk.StringVar()
        self._scope_domain_entry = theme.entry(
            scope_frame, textvariable=self._scope_domain_var, width=25)
        self._scope_domain_entry.pack(side=tk.LEFT, padx=(10, 0))

        self._scope_domain_var.trace_add("write", lambda *_: self._sync_scope())

        self._review_var = tk.BooleanVar(value=False)
        review_frame = tk.Frame(self, bg=BG)
        review_frame.grid(row=8, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 0))
        theme.Toggle(review_frame, "  Review requests",
                     variable=self._review_var).pack(side=tk.LEFT)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=9, column=0, columnspan=2, sticky="ew", padx=15, pady=(15, 15))

        cancel_btn = theme.button(btn_frame, "  Cancel  ", command=self.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))

        start_btn = theme.button(btn_frame, "  Start  ", command=self._start)
        start_btn.pack(side=tk.RIGHT)

        self._browser_listbox.bind("<Return>", lambda e: self._start())

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _sync_scope(self):
        domain = self._scope_domain_var.get().strip()
        self._name_var.set(domain)

    def _start(self):
        name = self._name_var.get().strip()
        if not name:
            self._name_feedback.config(text="Evidence name is required")
            return
        self._name_feedback.config(text="")
        target = self._url_var.get().strip()
        if not target:
            return
        sel = self._browser_listbox.curselection()
        if not sel:
            return
        browser = self._browser_paths[sel[0]]
        scope = None
        if self._scope_var.get():
            scope = self._scope_domain_var.get().strip() or name
        self.result = {
            "name": name,
            "target": target,
            "browser": browser,
            "scope": scope,
            "review_mode": self._review_var.get(),
        }
        self.destroy()
