import os
import tkinter as tk
from tkinter import ttk
from src.gui import fonts, windowing, theme
from src.elwand_paths import lst_dir as _lst_dir, rules_dir as _rules_dir

MUTED = "#888888"
BRIGHT = "#ffffff"
BG = "#111111"
FG = "#ffffff"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"


class _LogStream:
    """File-like object that forwards each written line to a dialog output."""

    def __init__(self, dialog, color="error"):
        self._dialog = dialog
        self._color = color
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if not line:
                continue
            try:
                if not self._dialog.winfo_exists():
                    return
                self._dialog.after(
                    0, lambda l=line, c=self._color: self._dialog._log(l, c))
            except (tk.TclError, RuntimeError):
                return

    def flush(self):
        pass


class DicmaDialog(tk.Toplevel):
    def __init__(self, parent, active_tab=None):
        super().__init__(parent)
        self.title("DICMA — Dictionary Maker")
        self.configure(bg=BG)

        self.transient(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)

        self._nb = ttk.Notebook(self)
        self._nb.grid(row=0, column=0, sticky="ew", padx=0, pady=(5, 0))

        self._tab_users = tk.Frame(self._nb, bg=BG)
        self._tab_neighbours = tk.Frame(self._nb, bg=BG)
        self._tab_passwords = tk.Frame(self._nb, bg=BG)
        self._tab_rules = tk.Frame(self._nb, bg=BG)

        self._nb.add(self._tab_users, text="Users")
        self._nb.add(self._tab_neighbours, text="Related Words")
        self._nb.add(self._tab_passwords, text="Passwords")
        self._nb.add(self._tab_rules, text="Rules")
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._tab_outputs = {}
        self._tab_progress = {}
        self._tab_progress_labels = {}

        self._btn_frame = tk.Frame(self, bg=BG)
        self._btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=15)
        self._btn_frame.columnconfigure(0, weight=1)

        self._start_btn = self._make_button(self._btn_frame, "Generate")
        self._start_btn.grid(row=0, column=1, padx=(0, 6))

        self._close_btn = self._make_button(self._btn_frame, "Close")
        self._close_btn.grid(row=0, column=2, padx=(0, 0))

        self._start_btn.bind("<Button-1>", lambda e: self._on_start())
        self._close_btn.bind("<Button-1>", lambda e: self._on_close())

        self._build_users_tab()
        self._build_neighbours_tab()
        self._build_passwords_tab()
        self._build_rules_tab()

        self._running = False

        if active_tab is not None:
            self._nb.select(active_tab)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        windowing.min_size(self, 760, 1)
        self.update_idletasks()
        w = windowing.px(760)
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - windowing.px(20))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.wait_visibility()
        self.grab_set()

    def _make_button(self, parent, text):
        return theme.button(parent, text)

    def _make_entry(self, parent, var, width=30):
        return theme.entry(parent, textvariable=var, width=width)

    def _make_label(self, parent, text):
        return tk.Label(parent, text=text, fg=MUTED, bg=BG,
                        font=fonts.view_font_bold(10), anchor="w")

    def _make_llm_selector(self, parent):
        """Provider + model selectors fed from the configured providers.

        Returns (provider_var, model_var). The model list follows the selected
        provider and defaults to that provider's active model.
        """
        from src.llm.config import load as _llm_load
        cfg = _llm_load()
        providers = list(cfg.get("providers", {}).keys())
        active = cfg.get("active_provider", "")

        provider_var = tk.StringVar(
            value=active or (providers[0] if providers else ""))

        prow = tk.Frame(parent, bg=BG)
        prow.pack(fill=tk.X, pady=(0, 4))
        tk.Label(prow, text="Provider", fg=MUTED, bg=BG,
                 font=fonts.view_font(10), width=9, anchor="w").pack(side=tk.LEFT)
        first = provider_var.get()
        menu = tk.OptionMenu(
            prow, provider_var, first,
            *[p for p in providers if p != first])
        menu.config(bg=theme.PANEL, fg=FG, font=fonts.view_font(10),
                    borderwidth=0, highlightthickness=1,
                    highlightcolor="#333333", highlightbackground="#333333",
                    activebackground=theme.BTN_HOVER, activeforeground=FG)
        menu["menu"].config(bg=theme.PANEL, fg=FG, font=fonts.view_font(10))
        menu.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        mrow = tk.Frame(parent, bg=BG)
        mrow.pack(fill=tk.X)
        tk.Label(mrow, text="Model", fg=MUTED, bg=BG,
                 font=fonts.view_font(10), width=9, anchor="w").pack(side=tk.LEFT)
        model_var = tk.StringVar()
        combo = ttk.Combobox(mrow, textvariable=model_var,
                             font=fonts.view_font(10))
        combo.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        def _refresh_models(*_):
            pid = provider_var.get()
            pcfg = _llm_load()
            models = pcfg.get("providers", {}).get(pid, {}).get("models", [])
            combo["values"] = models
            am = pcfg.get("active_models", {}).get(pid, "")
            model_var.set(am or (models[0] if models else ""))

        provider_var.trace_add("write", lambda *a: _refresh_models())
        _refresh_models()
        return provider_var, model_var

    def _log(self, text, color="info"):
        if not self.winfo_exists():
            return
        names = ["users", "neighbours", "passwords", "rules"]
        idx = self._nb.index(self._nb.select())
        name = names[idx] if idx < len(names) else "users"
        w = self._tab_outputs.get(name)
        if w and w.winfo_exists():
            w.config(state=tk.NORMAL)
            w.insert(tk.END, text + "\n", color)
            w.see(tk.END)
            w.config(state=tk.DISABLED)

    def _on_close(self):
        self._running = False
        self._destroyed = True
        self.destroy()

    def _make_output(self, tab, name, with_progress=False, height=4):
        out = theme.output(tab, height=height)
        out.tag_configure("info", foreground=BRIGHT)
        scroll = theme.scrollbar(tab, out)
        self._tab_outputs[name] = out

        if with_progress:
            prog = ttk.Progressbar(tab, mode="determinate")
            prog_label = tk.Label(tab, text="", fg=MUTED, bg=BG,
                                  font=fonts.view_font(9), anchor="w")
            self._tab_progress[name] = prog
            self._tab_progress_labels[name] = prog_label
            return out, scroll, prog, prog_label
        return out, scroll

    def _on_tab_changed(self, event=None):
        # ttk.Notebook moves focus into the new tab (ActivateTab -> focusFirst ->
        # traverseTo), landing on the first focusable widget — the "Output file"
        # entry. Keep focus on the notebook and drop any stray selection.
        for entry in (getattr(self, "_users_out_entry", None),
                      getattr(self, "_neigh_out_entry", None),
                      getattr(self, "_pass_out_entry", None),
                      getattr(self, "_rules_out_entry", None)):
            if entry is not None:
                try:
                    entry.selection_clear()
                except tk.TclError:
                    pass
        try:
            self._nb.focus_set()
        except tk.TclError:
            pass

    def _run_captured(self, fn, stdout=None):
        """Run fn() with stdout/stderr routed to this dialog's Output pane.

        Keeps the DICMA engine from printing to the terminal: engine errors
        (stderr) and verbose lines (stdout) appear in the Output box instead.
        `stdout` may be a custom stream (e.g. a progress writer)."""
        import sys
        old = (sys.stdout, sys.stderr)
        sys.stdout = stdout if stdout is not None else _LogStream(self, "muted")
        sys.stderr = _LogStream(self, "error")
        try:
            fn()
        finally:
            sys.stdout, sys.stderr = old

    def _resize_to_content(self):
        """Shrink/grow the window height to fit the current content.

        The notebook is as tall as its tallest tab, so the window ends right
        where the buttons end. Used after toggling sub-frames that change a
        tab's height (e.g. the Passwords LLM section)."""
        if not self.winfo_exists():
            return
        self.update_idletasks()
        self.geometry(f"{windowing.px(760)}x{self.winfo_reqheight()}")

    def _set_progress_visible(self, name, visible):
        """Show/hide a tab's progress bar + label and resize to fit.

        The progress widgets are hidden when idle so the output box reaches
        down to the buttons instead of leaving an empty reserved strip."""
        for w in (self._tab_progress.get(name),
                  self._tab_progress_labels.get(name)):
            if w is None:
                continue
            if visible:
                w.grid()
            else:
                w.grid_remove()
        self._resize_to_content()

    # ------------------------------------------------------------------ Users

    def _build_users_tab(self):
        tab = self._tab_users
        tab.columnconfigure(1, weight=1)

        self._make_label(tab, "Output file").grid(
            row=0, column=0, sticky="w", padx=(15, 0), pady=(15, 0))

        out_frame = tk.Frame(tab, bg=BG)
        out_frame.grid(row=0, column=1, sticky="ew", padx=(6, 15), pady=(15, 0))
        out_frame.columnconfigure(0, weight=1)

        default_out = os.path.join(str(_lst_dir()), "dicma_users.txt")
        self._users_out_var = tk.StringVar(value=default_out)
        self._users_out_entry = self._make_entry(out_frame, self._users_out_var)
        self._users_out_entry.grid(row=0, column=0, sticky="ew")

        self._users_browse_btn = self._make_button(out_frame, "Browse")
        self._users_browse_btn.grid(row=0, column=1, padx=(6, 0))
        self._users_browse_btn.bind(
            "<Button-1>",
            lambda e: self._browse_output(self._users_out_var),
        )

        inv_frame = tk.Frame(tab, bg=BG)
        inv_frame.grid(row=1, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(15, 0))

        tk.Label(
            inv_frame, text="Add from inventory:", fg=MUTED, bg=BG,
            font=fonts.view_font(10),
        ).pack(side=tk.LEFT)

        from src.machines.people_db import load_people
        people = load_people()
        self._people = people
        people_names = []
        for p in people:
            full = f"{p['first_name']} {p['last_name']}".strip()
            if not full:
                full = p.get("username", "") or f"(id:{p['id']})"
            if full:
                people_names.append(full)

        self._users_combo = theme.combo(inv_frame, values=people_names, width=22)
        self._users_combo.pack(side=tk.LEFT, padx=(6, 6))
        if people_names:
            self._users_combo.current(0)

        add_btn = self._make_button(inv_frame, "Add")
        add_btn.pack(side=tk.LEFT)
        add_btn.bind("<Button-1>", lambda e: self._users_add_selected())

        add_all_btn = self._make_button(inv_frame, "Add All")
        add_all_btn.pack(side=tk.LEFT, padx=(6, 0))
        add_all_btn.bind("<Button-1>", lambda e: self._users_add_all())

        clear_btn = self._make_button(inv_frame, "Clear")
        clear_btn.pack(side=tk.LEFT, padx=(6, 0))
        clear_btn.bind("<Button-1>", lambda e: self._users_clear())

        names_frame = tk.Frame(tab, bg=BG)
        names_frame.grid(row=2, column=0, columnspan=2, sticky="nsew",
                         padx=15, pady=(10, 0))
        names_frame.columnconfigure(0, weight=1)
        names_frame.rowconfigure(0, weight=1)

        self._users_names_text = tk.Text(
            names_frame, bg="#000000", fg=FG,
            insertbackground=FG, font=fonts.view_font(10),
            wrap=tk.WORD, cursor="",
            borderwidth=0,
            relief=tk.FLAT,
            highlightbackground="#333333", highlightthickness=1,
            height=10,
        )
        self._users_names_text.grid(row=0, column=0, sticky="nsew")

        names_scroll = theme.scrollbar(names_frame, self._users_names_text)
        names_scroll.grid(row=0, column=1, sticky="ns")

        opts_frame = tk.Frame(tab, bg=BG)
        opts_frame.grid(row=3, column=0, columnspan=2, sticky="w",
                        padx=15, pady=(10, 0))
        self._users_light_var = tk.BooleanVar(value=False)
        self._users_light_cb = theme.Toggle(
            opts_frame, "Light mode", variable=self._users_light_var)
        self._users_light_cb.pack(side=tk.LEFT)

        self._make_label(tab, "Output").grid(
            row=4, column=0, sticky="w", padx=(15, 0), pady=(8, 0))
        out, out_scroll = self._make_output(tab, "users", height=7)
        out.grid(row=5, column=0, columnspan=2, sticky="nsew",
                 padx=15, pady=(4, 15))
        out_scroll.grid(row=5, column=2, sticky="ns")
        tab.rowconfigure(5, weight=1)

    def _browse_output(self, var):
        path = windowing.ask_save_file(
            self, title="Save output as",
            initialdir=str(_lst_dir()),
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def _get_text_lines(self, widget):
        text = widget.get("1.0", tk.END)
        return [n.strip() for n in text.splitlines() if n.strip()]

    def _get_words(self, widget):
        """Words from a text box, split on newlines and commas."""
        text = widget.get("1.0", tk.END)
        words = []
        for chunk in text.replace(",", "\n").splitlines():
            chunk = chunk.strip()
            if chunk:
                words.append(chunk)
        return words

    def _set_text_lines(self, widget, lines):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", "\n".join(lines))

    def _append_to_text(self, widget, items):
        current = set(self._get_text_lines(widget))
        added = 0
        for n in items:
            n = " ".join(n.strip().split())
            if n and n not in current:
                current.add(n)
                added += 1
        if added:
            self._set_text_lines(widget, sorted(current))

    def _users_add_selected(self):
        name = self._users_combo.get().strip()
        if name:
            self._append_to_text(self._users_names_text, [name])

    def _users_add_all(self):
        all_names = []
        for p in self._people:
            full = f"{p['first_name']} {p['last_name']}".strip()
            if not full:
                full = p.get("username", "")
            if full:
                all_names.append(full)
        names_list = [" ".join(n.strip().split()) for n in all_names if n.strip()]
        self._append_to_text(self._users_names_text, names_list)

    def _users_clear(self):
        self._users_names_text.delete("1.0", tk.END)

    def _neigh_clear(self):
        self._neigh_words_text.delete("1.0", tk.END)

    # ----------------------------------------------------------- Related Words

    ALPHA = "#a0a0ff"

    def _build_neighbours_tab(self):
        tab = self._tab_neighbours
        tab.columnconfigure(1, weight=1)

        self._make_label(tab, "Output file").grid(
            row=0, column=0, sticky="w", padx=(15, 0), pady=(15, 0))

        out_frame = tk.Frame(tab, bg=BG)
        out_frame.grid(row=0, column=1, sticky="ew", padx=(6, 15), pady=(15, 0))
        out_frame.columnconfigure(0, weight=1)

        default_out = os.path.join(str(_lst_dir()), "dicma_related.txt")
        self._neigh_out_var = tk.StringVar(value=default_out)
        self._neigh_out_entry = self._make_entry(out_frame, self._neigh_out_var)
        self._neigh_out_entry.grid(row=0, column=0, sticky="ew")

        neigh_browse_btn = self._make_button(out_frame, "Browse")
        neigh_browse_btn.grid(row=0, column=1, padx=(6, 0))
        neigh_browse_btn.bind(
            "<Button-1>",
            lambda e: self._browse_output(self._neigh_out_var),
        )

        inv_frame = tk.Frame(tab, bg=BG)
        inv_frame.grid(row=1, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(15, 0))

        tk.Label(
            inv_frame, text="Add from person:", fg=MUTED, bg=BG,
            font=fonts.view_font(10),
        ).pack(side=tk.LEFT)

        from src.machines.people_db import load_people
        people = load_people()
        self._neigh_people = people
        people_names = []
        for p in people:
            full = f"{p['first_name']} {p['last_name']}".strip()
            if not full:
                full = p.get("username", "") or f"(id:{p['id']})"
            if full:
                people_names.append(full)

        self._neigh_combo = theme.combo(inv_frame, values=people_names, width=22)
        self._neigh_combo.pack(side=tk.LEFT, padx=(6, 6))
        if people_names:
            self._neigh_combo.current(0)

        neigh_add_btn = self._make_button(inv_frame, "Add")
        neigh_add_btn.pack(side=tk.LEFT)
        neigh_add_btn.bind("<Button-1>", lambda e: self._neigh_add_selected())

        neigh_add_all_btn = self._make_button(inv_frame, "Add All")
        neigh_add_all_btn.pack(side=tk.LEFT, padx=(6, 0))
        neigh_add_all_btn.bind("<Button-1>", lambda e: self._neigh_add_all())

        clear_btn = self._make_button(inv_frame, "Clear")
        clear_btn.pack(side=tk.LEFT, padx=(6, 0))
        clear_btn.bind("<Button-1>", lambda e: self._neigh_clear())

        words_frame = tk.Frame(tab, bg=BG)
        words_frame.grid(row=4, column=0, columnspan=2, sticky="nsew",
                         padx=15, pady=(10, 0))
        words_frame.columnconfigure(0, weight=1)
        words_frame.rowconfigure(0, weight=1)

        self._neigh_words_text = tk.Text(
            words_frame, bg="#000000", fg=FG,
            insertbackground=FG, font=fonts.view_font(10),
            wrap=tk.WORD, cursor="",
            borderwidth=0,
            relief=tk.FLAT,
            highlightbackground="#333333", highlightthickness=1,
            height=7,
        )
        self._neigh_words_text.grid(row=0, column=0, sticky="nsew")
        self._neigh_words_text.bind("<<Modified>>", lambda e: self._update_total_label())
        # Use KeyRelease to trigger total update
        self._neigh_words_text.bind("<KeyRelease>", lambda e: self.after(100, self._update_total_label))

        words_scroll = theme.scrollbar(words_frame, self._neigh_words_text)
        words_scroll.grid(row=0, column=1, sticky="ns")

        levels_frame = tk.Frame(tab, bg=BG)
        levels_frame.grid(row=3, column=0, columnspan=2, sticky="ew",
                          padx=15, pady=(10, 0))

        tk.Label(
            levels_frame, text="n1:", fg=MUTED, bg=BG,
            font=fonts.view_font(10),
        ).pack(side=tk.LEFT)
        self._neigh_n1_var = tk.StringVar(value="50")
        self._make_entry(levels_frame, self._neigh_n1_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12))

        tk.Label(
            levels_frame, text="n2:", fg=MUTED, bg=BG,
            font=fonts.view_font(10),
        ).pack(side=tk.LEFT)
        self._neigh_n2_var = tk.StringVar(value="0")
        self._make_entry(levels_frame, self._neigh_n2_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12))

        tk.Label(
            levels_frame, text="n3:", fg=MUTED, bg=BG,
            font=fonts.view_font(10),
        ).pack(side=tk.LEFT)
        self._neigh_n3_var = tk.StringVar(value="0")
        self._make_entry(levels_frame, self._neigh_n3_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12))

        self._neigh_total_label = tk.Label(
            levels_frame, text="", fg=MUTED, bg=BG,
            font=fonts.view_font(10),
        )
        self._neigh_total_label.pack(side=tk.LEFT)

        for var in (self._neigh_n1_var, self._neigh_n2_var, self._neigh_n3_var):
            var.trace_add("write", lambda *a: self._update_total_label())

        llm_label = tk.Frame(tab, bg=BG)
        llm_label.grid(row=5, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(12, 0))
        tk.Label(
            llm_label, text="LLM provider", fg=MUTED, bg=BG,
            font=fonts.view_font_bold(10),
        ).pack(anchor="w")

        llm_frame = tk.Frame(tab, bg=BG)
        llm_frame.grid(row=6, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(4, 0))
        self._neigh_provider_var, self._neigh_model_var = self._make_llm_selector(llm_frame)

        self._make_label(tab, "Output").grid(
            row=7, column=0, sticky="w", padx=(15, 0), pady=(8, 0))
        out, out_scroll, prog, prog_label = self._make_output(
            tab, "neighbours", with_progress=True, height=6)
        out.grid(row=8, column=0, columnspan=2, sticky="nsew",
                 padx=15, pady=(4, 0))
        out_scroll.grid(row=8, column=2, sticky="ns")
        prog.grid(row=9, column=0, columnspan=2, sticky="ew",
                  padx=15, pady=(4, 0))
        prog_label.grid(row=10, column=0, columnspan=2, sticky="ew",
                        padx=15, pady=(2, 15))
        prog.grid_remove()
        prog_label.grid_remove()
        tab.rowconfigure(8, weight=1)

    def _update_total_label(self):
        try:
            n1 = int(self._neigh_n1_var.get())
            n2 = int(self._neigh_n2_var.get())
            n3 = int(self._neigh_n3_var.get())
        except ValueError:
            self._neigh_total_label.config(text="")
            return
        words = len(self._get_text_lines(self._neigh_words_text))
        if n3 > 0:
            per_word = n1 * n2 * n3
        elif n2 > 0:
            per_word = n1 * n2
        else:
            per_word = n1
        total = per_word * words if words > 0 else per_word
        self._neigh_total_label.config(text=f"≈{total:,} words")

    def _neigh_get_interests(self, person):
        raw = (person.get("interests") or "").strip()
        if not raw:
            return []
        interests = []
        for part in raw.replace(",", " ").replace(";", " ").split():
            part = part.strip().lower()
            if part and len(part) >= 2:
                interests.append(part)
        return interests

    def _neigh_add_selected(self):
        name = self._neigh_combo.get().strip()
        if not name:
            return
        for p in self._neigh_people:
            full = f"{p['first_name']} {p['last_name']}".strip()
            if not full:
                full = p.get("username", "")
            if full == name:
                interests = self._neigh_get_interests(p)
                if interests:
                    self._append_to_text(self._neigh_words_text, interests)
                else:
                    self._log(f"No interests found for: {name}", "info")
                return

    def _neigh_add_all(self):
        all_interests = set()
        for p in self._neigh_people:
            for i in self._neigh_get_interests(p):
                all_interests.add(i)
        if all_interests:
            self._append_to_text(self._neigh_words_text, sorted(all_interests))

    # -------------------------------------------------------------- Passwords

    def _build_passwords_tab(self):
        tab = self._tab_passwords
        tab.columnconfigure(1, weight=1)

        self._make_label(tab, "Output file").grid(
            row=0, column=0, sticky="w", padx=(15, 0), pady=(15, 0))

        out_frame = tk.Frame(tab, bg=BG)
        out_frame.grid(row=0, column=1, sticky="ew", padx=(6, 15), pady=(15, 0))
        out_frame.columnconfigure(0, weight=1)

        default_out = os.path.join(str(_lst_dir()), "dicma_passwords.txt")
        self._pass_out_var = tk.StringVar(value=default_out)
        self._pass_out_entry = self._make_entry(out_frame, self._pass_out_var)
        self._pass_out_entry.grid(row=0, column=0, sticky="ew")

        pass_browse_btn = self._make_button(out_frame, "Browse")
        pass_browse_btn.grid(row=0, column=1, padx=(6, 0))
        pass_browse_btn.bind("<Button-1>", lambda e: self._browse_output(self._pass_out_var))

        self._make_label(tab, "Dictionary").grid(
            row=1, column=0, sticky="w", padx=(15, 0), pady=(15, 0))

        dict_frame = tk.Frame(tab, bg=BG)
        dict_frame.grid(row=1, column=1, sticky="ew", padx=(6, 15), pady=(15, 0))
        dict_frame.columnconfigure(0, weight=1)

        self._pass_dict_var = tk.StringVar()
        self._pass_dict_entry = self._make_entry(dict_frame, self._pass_dict_var)
        self._pass_dict_entry.grid(row=0, column=0, sticky="ew")

        pass_dict_btn = self._make_button(dict_frame, "Browse")
        pass_dict_btn.grid(row=0, column=1, padx=(6, 0))
        pass_dict_btn.bind("<Button-1>", lambda e: self._browse_pass_dict())

        tk.Label(
            tab,             text="Leave empty to use built-in patterns (rockyou-based).",
            fg=MUTED, bg=BG, font=fonts.view_font(9), anchor="w",
        ).grid(row=2, column=1, sticky="w", padx=(6, 15))

        src_frame = tk.Frame(tab, bg=BG)
        src_frame.grid(row=3, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(15, 0))

        tk.Label(src_frame, text="Passwords:", fg=MUTED, bg=BG,
                 font=fonts.view_font(10)).pack(side=tk.LEFT)

        from src.machines.credential_db import load_passwords
        from src.machines.people_db import load_people
        pw_list = sorted(set(p for p in load_passwords() if p))
        people_list_raw = []
        for p in load_people():
            full = f"{p['first_name']} {p['last_name']}".strip()
            if not full:
                full = p.get("username", "")
            if full:
                people_list_raw.append(p)

        self._pass_people = people_list_raw
        pass_values = pw_list or []
        self._pass_pw_combo = theme.combo(src_frame, values=pass_values, width=22)
        self._pass_pw_combo.pack(side=tk.LEFT, padx=(6, 6))
        if pass_values:
            self._pass_pw_combo.current(0)

        pw_add = self._make_button(src_frame, "Add")
        pw_add.pack(side=tk.LEFT)
        pw_add.bind("<Button-1>", lambda e: self._pass_add_pw())

        tk.Label(src_frame, text="Interests:", fg=MUTED, bg=BG,
                 font=fonts.view_font(10)).pack(side=tk.LEFT, padx=(12, 0))

        people_names = [f"{p['first_name']} {p['last_name']}".strip() or p.get("username", "")
                        for p in people_list_raw if f"{p['first_name']} {p['last_name']}".strip() or p.get("username")]
        self._pass_combo = theme.combo(src_frame, values=people_names, width=22)
        self._pass_combo.pack(side=tk.LEFT, padx=(6, 6))
        if people_names:
            self._pass_combo.current(0)

        pass_add_btn = self._make_button(src_frame, "Add")
        pass_add_btn.pack(side=tk.LEFT)
        pass_add_btn.bind("<Button-1>", lambda e: self._pass_add_interests())

        pass_add_all_btn = self._make_button(src_frame, "Add All")
        pass_add_all_btn.pack(side=tk.LEFT, padx=(6, 0))
        pass_add_all_btn.bind("<Button-1>", lambda e: self._pass_add_all_interests())

        clear_btn = self._make_button(src_frame, "Clear")
        clear_btn.pack(side=tk.LEFT, padx=(6, 0))
        clear_btn.bind("<Button-1>", lambda e: self._pass_clear())

        words_frame = tk.Frame(tab, bg=BG)
        words_frame.grid(row=4, column=0, columnspan=2, sticky="nsew",
                         padx=15, pady=(10, 0))
        words_frame.columnconfigure(0, weight=1)
        words_frame.rowconfigure(0, weight=1)

        self._pass_words_text = tk.Text(
            words_frame, bg="#000000", fg=FG,
            insertbackground=FG, font=fonts.view_font(10),
            wrap=tk.WORD, cursor="",
            borderwidth=0, relief=tk.FLAT,
            highlightbackground="#333333", highlightthickness=1,
            height=5,
        )
        self._pass_words_text.grid(row=0, column=0, sticky="nsew")
        words_scroll = theme.scrollbar(words_frame, self._pass_words_text)
        words_scroll.grid(row=0, column=1, sticky="ns")

        self._pass_llm_var = tk.BooleanVar(value=False)
        self._pass_llm_cb = theme.Toggle(
            tab, "Enable related words expansion",
            variable=self._pass_llm_var, command=self._pass_toggle_llm,
        )
        self._pass_llm_cb.grid(row=5, column=0, columnspan=2, sticky="w",
                               padx=15, pady=(10, 0))

        self._pass_llm_frame = tk.Frame(tab, bg=BG)
        self._pass_llm_frame.grid(row=6, column=0, columnspan=2, sticky="ew",
                                  padx=15, pady=(4, 0))
        self._pass_llm_frame.grid_remove()

        llm_inner = tk.Frame(self._pass_llm_frame, bg=BG)
        llm_inner.pack(fill=tk.X)

        levels_inner = tk.Frame(llm_inner, bg=BG)
        levels_inner.pack(fill=tk.X, pady=(0, 4))
        tk.Label(levels_inner, text="n1:", fg=MUTED, bg=BG,
                 font=fonts.view_font(10)).pack(side=tk.LEFT)
        self._pass_n1_var = tk.StringVar(value="50")
        self._make_entry(levels_inner, self._pass_n1_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12))
        tk.Label(levels_inner, text="n2:", fg=MUTED, bg=BG,
                 font=fonts.view_font(10)).pack(side=tk.LEFT)
        self._pass_n2_var = tk.StringVar(value="0")
        self._make_entry(levels_inner, self._pass_n2_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12))
        tk.Label(levels_inner, text="n3:", fg=MUTED, bg=BG,
                 font=fonts.view_font(10)).pack(side=tk.LEFT)
        self._pass_n3_var = tk.StringVar(value="0")
        self._make_entry(levels_inner, self._pass_n3_var, width=6).pack(
            side=tk.LEFT, padx=(4, 0))

        self._pass_provider_var, self._pass_model_var = self._make_llm_selector(llm_inner)

        opts_frame = tk.Frame(tab, bg=BG)
        opts_frame.grid(row=7, column=0, columnspan=2, sticky="w",
                        padx=15, pady=(10, 0))
        self._pass_light_var = tk.BooleanVar(value=False)
        self._pass_light_cb = theme.Toggle(
            opts_frame, "Light mode", variable=self._pass_light_var)
        self._pass_light_cb.pack(side=tk.LEFT)
        self._pass_full_var = tk.BooleanVar(value=False)
        self._pass_full_cb = theme.Toggle(
            opts_frame, "Full mode", variable=self._pass_full_var)
        self._pass_full_cb.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(opts_frame, text="(large output!)", fg=ERR_COLOR, bg=BG,
                 font=fonts.view_font(8)).pack(side=tk.LEFT, padx=(4, 0))

        self._make_label(tab, "Output").grid(
            row=8, column=0, sticky="w", padx=(15, 0), pady=(8, 0))
        out, out_scroll, prog, prog_label = self._make_output(
            tab, "passwords", with_progress=True)
        out.grid(row=9, column=0, columnspan=2, sticky="nsew",
                 padx=15, pady=(4, 0))
        out_scroll.grid(row=9, column=2, sticky="ns")
        prog.grid(row=10, column=0, columnspan=2, sticky="ew",
                  padx=15, pady=(4, 0))
        prog_label.grid(row=11, column=0, columnspan=2, sticky="ew",
                        padx=15, pady=(2, 15))
        prog.grid_remove()
        prog_label.grid_remove()

    def _pass_toggle_llm(self):
        if self._pass_llm_var.get():
            self._pass_llm_frame.grid()
        else:
            self._pass_llm_frame.grid_remove()
        self._resize_to_content()

    def _pass_add_pw(self):
        pw = self._pass_pw_combo.get().strip()
        if pw:
            self._append_to_text(self._pass_words_text, [pw])

    def _pass_add_interests(self):
        name = self._pass_combo.get().strip()
        if not name:
            return
        for p in self._pass_people:
            full = f"{p['first_name']} {p['last_name']}".strip()
            if not full:
                full = p.get("username", "")
            if full == name:
                interests = self._neigh_get_interests(p)
                if interests:
                    self._append_to_text(self._pass_words_text, interests)
                else:
                    self._log(f"No interests found for: {name}", "info")
                return

    def _pass_add_all_interests(self):
        all_i = set()
        for p in self._pass_people:
            for i in self._neigh_get_interests(p):
                all_i.add(i)
        if all_i:
            self._append_to_text(self._pass_words_text, sorted(all_i))

    def _pass_clear(self):
        self._pass_words_text.delete("1.0", tk.END)

    # ------------------------------------------------------------------ Rules

    def _build_rules_tab(self):
        tab = self._tab_rules
        tab.columnconfigure(1, weight=1)

        self._make_label(tab, "Output file").grid(
            row=0, column=0, sticky="w", padx=(15, 0), pady=(15, 0))

        out_frame = tk.Frame(tab, bg=BG)
        out_frame.grid(row=0, column=1, sticky="ew", padx=(6, 15), pady=(15, 0))
        out_frame.columnconfigure(0, weight=1)

        default_out = os.path.join(str(_rules_dir()), "dicma_rules.rule")
        self._rules_out_var = tk.StringVar(value=default_out)
        self._rules_out_entry = self._make_entry(out_frame, self._rules_out_var)
        self._rules_out_entry.grid(row=0, column=0, sticky="ew")

        rules_browse_btn = self._make_button(out_frame, "Browse")
        rules_browse_btn.grid(row=0, column=1, padx=(6, 0))
        rules_browse_btn.bind("<Button-1>", lambda e: self._browse_rules_output())

        self._make_label(tab, "Dictionary").grid(
            row=1, column=0, sticky="w", padx=(15, 0), pady=(15, 0))

        dict_frame = tk.Frame(tab, bg=BG)
        dict_frame.grid(row=1, column=1, sticky="ew", padx=(6, 15), pady=(15, 0))
        dict_frame.columnconfigure(0, weight=1)

        self._rules_dict_var = tk.StringVar()
        self._rules_dict_entry = self._make_entry(dict_frame, self._rules_dict_var)
        self._rules_dict_entry.grid(row=0, column=0, sticky="ew")

        dict_browse_btn = self._make_button(dict_frame, "Browse")
        dict_browse_btn.grid(row=0, column=1, padx=(6, 0))
        dict_browse_btn.bind("<Button-1>", lambda e: self._browse_dict())

        tk.Label(
            tab, text="Leave empty to use built-in patterns (rockyou-based).",
            fg=MUTED, bg=BG, font=fonts.view_font(9), anchor="w",
        ).grid(row=2, column=1, sticky="w", padx=(6, 15))

        opts_frame = tk.Frame(tab, bg=BG)
        opts_frame.grid(row=3, column=0, columnspan=2, sticky="w",
                        padx=15, pady=(15, 0))
        self._rules_light_var = tk.BooleanVar(value=False)
        self._rules_light_cb = theme.Toggle(
            opts_frame, "Light mode", variable=self._rules_light_var)
        self._rules_light_cb.pack(side=tk.LEFT)
        self._rules_full_var = tk.BooleanVar(value=False)
        self._rules_full_cb = theme.Toggle(
            opts_frame, "Full mode", variable=self._rules_full_var)
        self._rules_full_cb.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(opts_frame, text="(many rules!)", fg=ERR_COLOR, bg=BG,
                 font=fonts.view_font(8)).pack(side=tk.LEFT, padx=(4, 0))

        self._make_label(tab, "Output").grid(
            row=4, column=0, sticky="w", padx=(15, 0), pady=(12, 0))
        out, out_scroll = self._make_output(tab, "rules")
        out.grid(row=5, column=0, columnspan=2, sticky="nsew",
                 padx=15, pady=(4, 15))
        out_scroll.grid(row=5, column=2, sticky="ns")

    def _browse_rules_output(self):
        path = windowing.ask_save_file(
            self, title="Save rules as",
            initialdir=str(_rules_dir()),
            defaultextension=".rule",
            filetypes=[("Rule files", "*.rule"), ("All files", "*.*")],
        )
        if path:
            self._rules_out_var.set(path)

    def _browse_dict(self):
        path = windowing.ask_open_file(
            self, title="Select dictionary",
            initialdir=str(_lst_dir()),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._rules_dict_var.set(path)

    def _browse_pass_dict(self):
        path = windowing.ask_open_file(
            self, title="Select dictionary",
            initialdir=str(_lst_dir()),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._pass_dict_var.set(path)

    # -------------------------------------------------------------- Start

    def _on_start(self):
        if self._running:
            return
        tab_idx = self._nb.index(self._nb.select())
        if tab_idx == 0:
            self._start_users()
        elif tab_idx == 1:
            self._start_neighbours()
        elif tab_idx == 2:
            self._start_passwords()
        elif tab_idx == 3:
            self._start_rules()

    def _on_done(self, tab_name=None):
        self._running = False
        if not self.winfo_exists():
            return
        self._start_btn.config(text="Generate", fg=FG)
        self._start_btn.bind("<Enter>", lambda e: self._start_btn.config(bg="#333333"))
        self._start_btn.bind("<Leave>", lambda e: self._start_btn.config(bg="#222222"))
        name = tab_name or "neighbours"
        prog = self._tab_progress.get(name)
        if prog:
            prog.configure(value=100)
        prog_label = self._tab_progress_labels.get(name)
        if prog_label:
            prog_label.config(text="")
        if prog is not None:
            self._set_progress_visible(name, False)

    def _start_users(self):
        import threading
        names = self._get_text_lines(self._users_names_text)
        if not names:
            self._log("No names provided.", "error")
            return
        out_path = self._users_out_var.get().strip()
        if not out_path:
            self._log("Please specify an output file.", "error")
            return
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self._log(f"Cannot create output directory: {e}", "error")
                return
        light = self._users_light_var.get()
        self._log(f"Generating usernames from {len(names)} name(s)...", "info")
        self._log(f"  Output: {out_path}", "info")
        if light:
            self._log(f"  Mode: light", "info")
        self._running = True
        self._start_btn.config(text="Generating...", fg=MUTED)

        def _run():
            from src.tools.dicma import engine as dicma
            dicma.LIGHT_MODE = light
            dicma.OUTPUT_FILE_BULEAN = True
            dicma.VERBOSE = False
            names_str = ", ".join(names)

            def _work():
                dicma.process_input_user(names_str, out_path)
            try:
                self._run_captured(_work)
                self.after(0, lambda: self._log(
                    f"Dictionary saved to: {out_path}", "success"))
            except Exception as e:
                self.after(0, lambda e=e: self._log(f"Error: {e}", "error"))
            self.after(0, lambda: self.winfo_exists() and self._on_done("users"))

        threading.Thread(target=_run, daemon=True).start()

    def _start_neighbours(self):
        import threading
        words = self._get_words(self._neigh_words_text)
        if not words:
            self._log("No words provided.", "error")
            return
        out_path = self._neigh_out_var.get().strip()
        if not out_path:
            self._log("Please specify an output file.", "error")
            return
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self._log(f"Cannot create output directory: {e}", "error")
                return
        try:
            n1 = int(self._neigh_n1_var.get())
            n2 = int(self._neigh_n2_var.get())
            n3 = int(self._neigh_n3_var.get())
        except ValueError:
            self._log("Invalid neighbour count values.", "error")
            return
        if n1 <= 0:
            self._log("n1 must be at least 1.", "error")
            return
        if n3 > 0 and n2 <= 0:
            self._log("n2 must be at least 1 when n3 is set.", "error")
            return

        self._update_total_label()

        provider_id = self._neigh_provider_var.get().strip()
        model = self._neigh_model_var.get().strip()
        if not provider_id or not model:
            self._log("Select a provider and model.", "error")
            return

        self._log(f"Finding related words for {len(words)} word(s)...", "info")
        self._log(f"  n1={n1} n2={n2} n3={n3}  provider={provider_id} model={model}", "info")
        self._log(f"  Output: {out_path}", "info")
        self._running = True
        self._start_btn.config(text="Generating...", fg=MUTED)

        prog = self._tab_progress.get("neighbours")
        prog_label = self._tab_progress_labels.get("neighbours")
        if prog:
            prog.configure(mode="determinate", maximum=100, value=0)
        if prog_label:
            prog_label.config(text="")
        self._set_progress_visible("neighbours", True)

        if n3 > 0:
            phase_weights = (40, 30, 30)
        elif n2 > 0:
            phase_weights = (50, 50, 0)
        else:
            phase_weights = (100, 0, 0)

        class _ProgressWriter:
            def __init__(self, dialog, word_count, weights, prog, prog_label):
                self._dialog = dialog
                self._buf = ""
                self._word_count = word_count
                self._weights = (weights[0], weights[1], weights[2])
                self._phase = 0
                self._completed = 0
                self._cur_word_pct = 0.0
                self._prog = prog
                self._prog_label = prog_label
                self._last_total_text = ""

            def _calc_pct(self):
                base = sum(self._weights[:self._phase])
                phase_weight = self._weights[self._phase]
                return int(base + (self._completed + self._cur_word_pct) * phase_weight)

            def _update(self, text):
                if not self._dialog.winfo_exists():
                    return
                pct = self._calc_pct()
                p = self._prog
                pl = self._prog_label
                if p and pl and p.winfo_exists() and pl.winfo_exists():
                    self._dialog.after(0, lambda pct=pct, t=text: (
                        p.configure(value=min(pct, 100)),
                        pl.config(text=t),
                    ))
                if text and text != self._last_total_text:
                    self._last_total_text = text
                    self._dialog.after(0, lambda t=text: self._dialog._log(t, "info"))

            def write(self, s):
                self._buf += s
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    import re
                    m_total = re.search(r"Total:\s*(\d+)/(\d+)", line)
                    m_batch = re.search(r"L([23])\s+batch:\s*(\d+)/(\d+)", line)
                    m_done = re.search(r"L(\d)\s+done", line)
                    if m_total:
                        cur = int(m_total.group(1))
                        target = int(m_total.group(2))
                        if target > 0:
                            self._cur_word_pct = cur / target
                            self._update(line)
                    elif m_batch:
                        level = int(m_batch.group(1))
                        cur = int(m_batch.group(2))
                        target = int(m_batch.group(3))
                        phase = level - 1
                        if self._phase != phase:
                            self._phase = phase
                            self._completed = 0
                        self._completed = cur
                        self._cur_word_pct = 0.0
                        if target > 0:
                            self._cur_word_pct = cur / target
                        self._update(line)
                    elif m_done:
                        level = int(m_done.group(1))
                        phase = level - 1
                        if "L1" in line:
                            self._completed += 1
                            self._cur_word_pct = 0.0
                        self._update(line)
                    else:
                        self._dialog.after(
                            0, lambda l=line: self._dialog._log(l, "muted"))

            def flush(self):
                pass

        log_writer = _ProgressWriter(self, len(words), phase_weights, prog, prog_label)

        def _run():
            def _work():
                from src.llm.client import LLMClient
                from src.llm.config import load as _llm_load
                from src.tools.dicma import engine as dicma
                client = LLMClient(config=_llm_load(), provider_id=provider_id)
                complete = lambda m, **kw: client.raw_complete(
                    m, model=model, **kw)
                dicma.RAISE_ON_ERROR = True
                dicma.VERBOSE = True
                expanded = dicma.ml_expand_words(complete, words, n1, n2, n3)
                result = dicma.merge_with_inputs(expanded, words)
                dicma.save_list_to_file(result, out_path)
                self.after(0, lambda: self._log(
                    f"Saved {len(result)} words ({len(words)} seed words first) "
                    f"to: {out_path}", "success"))
            try:
                self._run_captured(_work, stdout=log_writer)
            except Exception as e:
                self.after(0, lambda e=e: self._log(f"Error: {e}", "error"))
            self.after(0, lambda: self.winfo_exists() and self._on_done("neighbours"))

        threading.Thread(target=_run, daemon=True).start()

    def _start_passwords(self):
        import threading
        words = self._get_words(self._pass_words_text)
        if not words:
            self._log("No words provided.", "error")
            return
        out_path = self._pass_out_var.get().strip()
        if not out_path:
            self._log("Please specify an output file.", "error")
            return
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self._log(f"Cannot create output directory: {e}", "error")
                return
        light = self._pass_light_var.get()
        full = self._pass_full_var.get()
        use_llm = self._pass_llm_var.get()
        dict_path = self._pass_dict_var.get().strip()

        self._running = True
        self._start_btn.config(text="Generating...", fg=MUTED)

        prog = self._tab_progress.get("passwords")
        prog_label = self._tab_progress_labels.get("passwords")
        if prog:
            prog.configure(mode="determinate", maximum=100, value=0)
        if prog_label:
            prog_label.config(text="")
        self._set_progress_visible("passwords", True)

        self._log(f"Generating passwords from {len(words)} word(s)...", "info")
        self._log(f"  Output: {out_path}", "info")
        if light:
            self._log(f"  Mode: light", "info")
        if full:
            self._log(f"  Mode: full (large output!)", "info")
        if dict_path:
            self._log(f"  Dict: {dict_path}", "info")

        if not use_llm:
            self._log(f"  LLM expansion: off", "info")

            def _run():
                from src.tools.dicma import engine as dicma
                dicma.LIGHT_MODE = light
                dicma.FULL_MODE = full
                dicma.OUTPUT_FILE_BULEAN = True
                dicma.VERBOSE = False
                dicma._NO_MULTIPROC = True

                def _work():
                    if dict_path:
                        dicma.extract_patterns(dict_path)
                    self.after(0, lambda: self._update_progress("passwords", 50, "Passworifying..."))
                    dicma.process_passwd(words, out_path)
                try:
                    self._run_captured(_work)
                    self.after(0, lambda: self._log(
                        f"Dictionary saved to: {out_path}", "success"))
                except Exception as e:
                    self.after(0, lambda e=e: self._log(f"Error: {e}", "error"))
                self.after(0, lambda: self.winfo_exists() and self._on_done("passwords"))

            threading.Thread(target=_run, daemon=True).start()
            return

        n1, n2, n3 = self._parse_pass_n()
        if n1 is None:
            return
        provider_id = self._pass_provider_var.get().strip()
        model = self._pass_model_var.get().strip()
        if not provider_id or not model:
            self._log("Select a provider and model.", "error")
            self._on_done("passwords")
            return

        if n3 > 0:
            phase_weights = (20, 15, 15, 50)
        elif n2 > 0:
            phase_weights = (25, 25, 0, 50)
        else:
            phase_weights = (50, 0, 0, 50)

        self._log(f"  LLM: n1={n1} n2={n2} n3={n3} model={model}", "info")

        class _PassProgressWriter:
            def __init__(self, dialog, word_count, weights, prog, prog_label):
                self._dialog = dialog
                self._buf = ""
                self._word_count = word_count
                self._weights = weights
                self._phase = 0
                self._completed = 0
                self._cur_word_pct = 0.0
                self._prog = prog
                self._prog_label = prog_label
                self._last_total_text = ""

            def _calc_pct(self):
                base = sum(self._weights[:self._phase])
                phase_weight = self._weights[self._phase]
                return int(base + (self._completed + self._cur_word_pct) * phase_weight)

            def _update(self, text):
                if not self._dialog.winfo_exists():
                    return
                pct = self._calc_pct()
                p = self._prog
                pl = self._prog_label
                if p and pl and p.winfo_exists() and pl.winfo_exists():
                    self._dialog.after(0, lambda pct=pct, t=text: (
                        p.configure(value=min(pct, 100)),
                        pl.config(text=t),
                    ))
                if text and text != self._last_total_text:
                    self._last_total_text = text
                    self._dialog.after(0, lambda t=text: self._dialog._log(t, "info"))

            def write(self, s):
                self._buf += s
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    import re
                    m_total = re.search(r"Total:\s*(\d+)/(\d+)", line)
                    m_batch = re.search(r"L([23])\s+batch:\s*(\d+)/(\d+)", line)
                    m_done = re.search(r"L(\d)\s+done", line)
                    if m_total:
                        cur, target = int(m_total.group(1)), int(m_total.group(2))
                        if target > 0:
                            self._cur_word_pct = cur / target
                            self._update(line)
                    elif m_batch:
                        level = int(m_batch.group(1))
                        cur = int(m_batch.group(2))
                        target = int(m_batch.group(3))
                        phase = level - 1
                        if self._phase != phase:
                            self._phase = phase
                            self._completed = 0
                        self._completed = cur
                        self._cur_word_pct = 0.0
                        if target > 0:
                            self._cur_word_pct = cur / target
                        self._update(line)
                    elif m_done:
                        if "L1" in line:
                            self._completed += 1
                            self._cur_word_pct = 0.0
                        self._update(line)
                    else:
                        self._dialog.after(
                            0, lambda l=line: self._dialog._log(l, "muted"))

            def flush(self):
                pass

        log_writer = _PassProgressWriter(self, len(words), phase_weights, prog, prog_label)

        def _run():
            def _work():
                from src.llm.client import LLMClient
                from src.llm.config import load as _llm_load
                from src.tools.dicma import engine as dicma
                client = LLMClient(config=_llm_load(), provider_id=provider_id)
                complete = lambda m, **kw: client.raw_complete(
                    m, model=model, **kw)
                dicma.RAISE_ON_ERROR = True
                dicma.VERBOSE = True
                expanded = dicma.ml_expand_words(complete, words, n1, n2, n3)
                all_words = dicma.merge_with_inputs(expanded, words)
                self.after(0, lambda: self._log(
                    f"LLM expanded to {len(all_words)} words. Passworifying...", "info"))
                self.after(0, lambda: self._update_progress(
                    "passwords", 50, "Passworifying..."))
                dicma.LIGHT_MODE = light
                dicma.FULL_MODE = full
                dicma.OUTPUT_FILE_BULEAN = True
                dicma.VERBOSE = False
                dicma._NO_MULTIPROC = True
                if dict_path:
                    dicma.extract_patterns(dict_path)
                dicma.process_passwd(all_words, out_path)
                self.after(0, lambda: self._log(
                    f"Dictionary saved to: {out_path}", "success"))
            try:
                self._run_captured(_work, stdout=log_writer)
            except Exception as e:
                self.after(0, lambda e=e: self._log(f"Error: {e}", "error"))
            self.after(0, lambda: self.winfo_exists() and self._on_done("passwords"))

        threading.Thread(target=_run, daemon=True).start()

    def _parse_pass_n(self):
        try:
            n1 = int(self._pass_n1_var.get())
            n2 = int(self._pass_n2_var.get())
            n3 = int(self._pass_n3_var.get())
        except ValueError:
            self._log("Invalid neighbour count values.", "error")
            self._on_done("passwords")
            return None, None, None
        if n1 <= 0:
            self._log("n1 must be at least 1.", "error")
            self._on_done("passwords")
            return None, None, None
        if n3 > 0 and n2 <= 0:
            self._log("n2 must be at least 1 when n3 is set.", "error")
            self._on_done("passwords")
            return None, None, None
        return n1, n2, n3

    def _update_progress(self, tab, value, text):
        if not self.winfo_exists():
            return
        prog = self._tab_progress.get(tab)
        pl = self._tab_progress_labels.get(tab)
        if prog and pl:
            prog.configure(value=value)
            pl.config(text=text)

    def _start_rules(self):
        import threading
        out_path = self._rules_out_var.get().strip()
        if not out_path:
            self._log("Please specify an output file.", "error")
            return
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self._log(f"Cannot create output directory: {e}", "error")
                return
        light = self._rules_light_var.get()
        full = self._rules_full_var.get()
        dict_path = self._rules_dict_var.get().strip()

        self._log(f"Generating hashcat rules...", "info")
        self._log(f"  Output: {out_path}", "info")
        if light:
            self._log(f"  Mode: light", "info")
        if full:
            self._log(f"  Mode: full (many rules!)", "info")
        if dict_path:
            self._log(f"  Dict: {dict_path}", "info")
        else:
            self._log(f"  Dict: built-in patterns", "info")
        self._running = True
        self._start_btn.config(text="Generating...", fg=MUTED)

        def _run():
            from src.tools.dicma import engine as dicma
            dicma.VERBOSE = False

            def _work():
                if dict_path:
                    self.after(0, lambda: self._log(
                        "Extracting patterns from dictionary...", "info"))
                    suffixes, prefixes, numbers, symbols = dicma.extract_patterns(dict_path)
                    all_suf = list(dict.fromkeys(suffixes + numbers + symbols))
                    all_pre = list(dict.fromkeys(prefixes + numbers + symbols))
                else:
                    all_suf = list(dict.fromkeys(
                        dicma.BASIC_SUFIXS + dicma.NUMERIC_PATTERNS + dicma.SYMBOLIC_PATTERNS))
                    all_pre = list(dict.fromkeys(
                        dicma.BASIC_PREFIXS + dicma.NUMERIC_PATTERNS + dicma.SYMBOLIC_PATTERNS))
                rules = dicma.generate_rules(all_suf, all_pre, light=light, full=full)
                dicma.save_list_to_file(rules, out_path)
                self.after(0, lambda: self._log(
                    f"{len(rules)} rules saved to: {out_path}", "success"))
            try:
                self._run_captured(_work)
            except Exception as e:
                self.after(0, lambda e=e: self._log(f"Error: {e}", "error"))
            self.after(0, lambda: self.winfo_exists() and self._on_done("rules"))

        threading.Thread(target=_run, daemon=True).start()
