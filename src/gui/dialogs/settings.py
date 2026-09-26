import json
import tkinter as tk
from tkinter import ttk
from src.gui import fonts, windowing
from src import llm
from src import settings as _app_settings

BG = "#111111"
BG_WIDGET = "#000000"
FG = "#ffffff"
FG_DIM = "#888888"
SEL_BG = "#333333"
SUCCESS = "#00cc66"
ERR = "#f44747"
INFO = "#5ba3ec"


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Elwand — Settings")
        sh = self.winfo_screenheight()
        h = max(680, min(int(sh * 0.85), sh - 40))
        w = max(850, int(self.winfo_screenwidth() * 0.75))
        x = (self.winfo_screenwidth() - w) // 2
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
        windowing.min_size(self, 800, 660)
        self.configure(bg=BG)
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222",
                        foreground=FG_DIM, font=fonts.view_font(10),
                        padding=[14, 6])
        style.map("TNotebook.Tab", background=[("selected", BG)],
                  foreground=[("selected", FG)])

        self._nb = ttk.Notebook(self)
        self._nb.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 10))

        self._tab_models = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_models, text="  Models  ")
        self._build_models_tab(self._tab_models)

        self._tab_prompts = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_prompts, text="  Prompts  ")
        self._build_prompts_tab(self._tab_prompts)

        self._tab_safety = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_safety, text="  Safety  ")
        self._build_safety_tab(self._tab_safety)

        self._tab_console = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_console, text="  Console  ")
        self._build_console_tab(self._tab_console)

        self._nb.select(0)

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ─── Prompts Tab ─────────────────────────────────────────

    def _build_prompts_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0)

        tk.Label(
            parent, text="System Prompts",
            font=fonts.view_font_bold(11), fg=FG, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        prompts_frame = tk.Frame(parent, bg=BG_WIDGET)
        prompts_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        prompts_frame.columnconfigure(0, weight=1)
        prompts_frame.rowconfigure(0, weight=1)

        self._prompts_text = tk.Text(
            prompts_frame, bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            wrap=tk.WORD, pady=8, padx=12,
        )
        self._prompts_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(prompts_frame, orient=tk.VERTICAL,
                                 command=self._prompts_text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._prompts_text.configure(yscrollcommand=scrollbar.set)

        self._prompts_text.tag_configure("section", foreground=INFO)
        self._prompts_text.tag_configure("muted", foreground=FG_DIM)

        self._refresh_prompts()

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 10))

        save_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=SUCCESS,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        save_btn.pack()
        save_btn.bind("<Button-1>", lambda e: self._prompts_save())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#333333"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#222222"))

    def _refresh_prompts(self):
        prompts = self._config.get("prompts", {})
        self._prompts_text.delete("1.0", tk.END)
        for key, text in prompts.items():
            self._prompts_text.insert(tk.END, f"\u2500\u2500 {key} \u2500\u2500\n", "section")
            self._prompts_text.insert(tk.END, f"{text}\n\n")

    def _prompts_save(self):
        content = self._prompts_text.get("1.0", "end-1c")
        prompts = {}
        sections = content.split("\u2500\u2500 ")
        for sec in sections:
            if not sec.strip():
                continue
            parts = sec.split(" \u2500\u2500\n", 1)
            if len(parts) != 2:
                continue
            key = parts[0].strip()
            text = parts[1].strip()
            if key:
                prompts[key] = text
        self._config["prompts"] = prompts
        llm.config.save(self._config)
        self._refresh_prompts()

    # ─── Safety Tab ──────────────────────────────────────────

    def _build_safety_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)

        tk.Label(
            parent, text="Agent Safety",
            font=fonts.view_font_bold(11), fg=FG, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        content = tk.Frame(parent, bg=BG_WIDGET)
        content.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        content.columnconfigure(1, weight=1)

        tk.Label(
            content, text="  Agent can execute POCs",
            font=fonts.view_font(11), fg=FG, bg=BG_WIDGET,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(12, 6))

        self._poc_exec_var = tk.BooleanVar(
            value=_app_settings.get("agent_exec_pocs", False))
        self._poc_toggle = tk.Label(
            content, text="", bg=BG_WIDGET,
            font=fonts.view_font_bold(11),
            cursor="", padx=8, pady=4,
        )
        self._poc_toggle.grid(row=0, column=1, sticky="e", padx=15, pady=(12, 6))
        self._poc_toggle.bind("<Button-1>", lambda e: self._toggle_poc_exec())
        self._refresh_poc_toggle()

        tk.Label(
            content, text="  Agent has default access to shells",
            font=fonts.view_font(11), fg=FG, bg=BG_WIDGET,
        ).grid(row=1, column=0, sticky="w", padx=15, pady=(6, 6))

        self._shell_access_var = tk.BooleanVar(
            value=_app_settings.get("agent_default_shell_access", False))
        self._shell_access_toggle = tk.Label(
            content, text="", bg=BG_WIDGET,
            font=fonts.view_font_bold(11),
            cursor="", padx=8, pady=4,
        )
        self._shell_access_toggle.grid(row=1, column=1, sticky="e", padx=15, pady=(6, 6))
        self._shell_access_toggle.bind("<Button-1>", lambda e: self._toggle_shell_access())
        self._refresh_shell_access_toggle()

        tk.Label(
            content, text="  Agent can run nmap",
            font=fonts.view_font(11), fg=FG, bg=BG_WIDGET,
        ).grid(row=2, column=0, sticky="w", padx=15, pady=(6, 12))

        self._nmap_var = tk.BooleanVar(
            value=_app_settings.get("agent_nmap", False))
        self._nmap_toggle = tk.Label(
            content, text="", bg=BG_WIDGET,
            font=fonts.view_font_bold(11),
            cursor="", padx=8, pady=4,
        )
        self._nmap_toggle.grid(row=2, column=1, sticky="e", padx=15, pady=(6, 12))
        self._nmap_toggle.bind("<Button-1>", lambda e: self._toggle_nmap())
        self._refresh_nmap_toggle()

    def _refresh_poc_toggle(self):
        on = self._poc_exec_var.get()
        self._poc_toggle.config(
            text="  ON  " if on else " OFF ",
            fg="#cc3333" if on else "#00cc66",
        )

    def _toggle_poc_exec(self):
        current = self._poc_exec_var.get()
        self._poc_exec_var.set(not current)
        _app_settings.set("agent_exec_pocs", not current)
        _app_settings.save()
        self._refresh_poc_toggle()

    def _refresh_shell_access_toggle(self):
        on = self._shell_access_var.get()
        self._shell_access_toggle.config(
            text="  ON  " if on else " OFF ",
            fg="#cc3333" if on else "#00cc66",
        )

    def _toggle_shell_access(self):
        current = self._shell_access_var.get()
        self._shell_access_var.set(not current)
        _app_settings.set("agent_default_shell_access", not current)
        _app_settings.save()
        self._refresh_shell_access_toggle()

    def _refresh_nmap_toggle(self):
        on = self._nmap_var.get()
        self._nmap_toggle.config(
            text="  ON  " if on else " OFF ",
            fg="#cc3333" if on else "#00cc66",
        )

    def _toggle_nmap(self):
        current = self._nmap_var.get()
        self._nmap_var.set(not current)
        _app_settings.set("agent_nmap", not current)
        _app_settings.save()
        self._refresh_nmap_toggle()

    # ─── Console Tab ─────────────────────────────────────────

    def _build_console_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)

        tk.Label(
            parent, text="Console",
            font=fonts.view_font_bold(11), fg=FG, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        content = tk.Frame(parent, bg=BG_WIDGET)
        content.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        content.columnconfigure(1, weight=1)

        tk.Label(
            content, text="  Markdown interpretation",
            font=fonts.view_font(11), fg=FG, bg=BG_WIDGET,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(12, 12))

        self._md_var = tk.BooleanVar(
            value=_app_settings.get("console_markdown", True))
        self._md_toggle = tk.Label(
            content, text="", bg=BG_WIDGET,
            font=fonts.view_font_bold(11),
            cursor="", padx=8, pady=4,
        )
        self._md_toggle.grid(row=0, column=1, sticky="e", padx=15, pady=(12, 12))
        self._md_toggle.bind("<Button-1>", lambda e: self._toggle_markdown())
        self._refresh_md_toggle()

    def _refresh_md_toggle(self):
        on = self._md_var.get()
        self._md_toggle.config(
            text="  ON  " if on else " OFF ",
            fg="#00cc66" if on else "#888888",
        )

    def _toggle_markdown(self):
        current = self._md_var.get()
        self._md_var.set(not current)
        _app_settings.set("console_markdown", not current)
        _app_settings.save()
        self._refresh_md_toggle()
        console = getattr(getattr(self, "master", None), "console", None)
        if console is not None:
            try:
                console.restore_segments(console.get_segments())
            except Exception:
                pass

    # ─── Models Tab ──────────────────────────────────────────

    def _build_models_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0)

        self._config = llm.config.load()

        tk.Label(
            parent, text="Models Configuration",
            font=fonts.view_font_bold(11), fg=FG, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        list_frame = tk.Frame(parent, bg=BG_WIDGET)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._prov_text = tk.Text(
            list_frame, bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, cursor="", wrap=tk.WORD, pady=8, padx=12,
        )
        self._prov_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=self._prov_text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._prov_text.configure(yscrollcommand=scrollbar.set)

        self._prov_text.tag_configure("active", foreground=SUCCESS)
        self._prov_text.tag_configure("bright", foreground=FG)
        self._prov_text.tag_configure("muted", foreground=FG_DIM)
        self._prov_text.tag_configure("info", foreground=INFO)
        self._prov_text.tag_configure("error", foreground=ERR)

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 10))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        add_btn = tk.Label(
            btn_frame, text="  Add provider  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.RIGHT, padx=(5, 0))
        add_btn.bind("<Button-1>", lambda e: self._open_provider_dialog(is_new=True))
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

        edit_btn = tk.Label(
            btn_frame, text="  Edit / Set active  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        edit_btn.pack(side=tk.RIGHT, padx=(5, 0))
        edit_btn.bind("<Button-1>", lambda e: self._open_provider_dialog())
        edit_btn.bind("<Enter>", lambda e: edit_btn.config(bg="#333333"))
        edit_btn.bind("<Leave>", lambda e: edit_btn.config(bg="#222222"))

        save_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        save_btn.pack(side=tk.RIGHT, padx=(5, 0))

        def _main_save():
            llm.config.save(self._config)
            self._refresh_providers()

        save_btn.bind("<Button-1>", lambda e: _main_save())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#333333"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#222222"))

        self._prov_entries = []
        self._refresh_providers()

    def _refresh_providers(self):
        self._prov_text.configure(state=tk.NORMAL)
        self._prov_text.delete("1.0", tk.END)
        self._prov_entries = []

        providers = self._config.get("providers", {})
        active = self._config.get("active_provider", "")
        active_models = self._config.get("active_models", {})

        if not providers:
            self._prov_text.insert(tk.END, "\n  No providers configured.\n", "muted")
            self._prov_text.configure(state=tk.DISABLED)
            self._prov_view = providers
            return

        self._prov_view = providers

        for pid, p in providers.items():
            is_active = pid == active
            marker = "\u25cf" if is_active else "\u25cb"
            tag_marker = f"p_{pid}_marker"
            tag_name = f"p_{pid}_name"

            self._prov_text.tag_configure(tag_marker, foreground=SUCCESS if is_active else FG_DIM,
                                          underline=False)
            self._prov_text.tag_configure(tag_name, foreground=FG, underline=False)

            self._prov_text.insert(tk.END, f"  {marker}  ", (tag_marker,))
            self._prov_text.insert(tk.END, f"{pid}", (tag_name,))
            if is_active:
                self._prov_text.insert(tk.END, "  \u2190 active", "active")
            self._prov_text.insert(tk.END, "\n")

            url = p.get("base_url", "") or "(no URL set)"
            self._prov_text.insert(tk.END, f"      {url}\n", "muted")

            models = p.get("models", [])
            am = active_models.get(pid, "")
            active_model = am or (models[0] if models else "")
            if active_model:
                self._prov_text.insert(tk.END, f"      Model: {active_model}\n", "info")
            else:
                self._prov_text.insert(tk.END, "      Model: (none)\n", "muted")

            self._prov_text.insert(tk.END, "\n")
            self._prov_entries.append(pid)

            self._prov_text.tag_bind(tag_name, "<Enter>",
                                     lambda e, t=tag_name: self._prov_text.tag_configure(t, underline=True))
            self._prov_text.tag_bind(tag_name, "<Leave>",
                                     lambda e, t=tag_name: self._prov_text.tag_configure(t, underline=False))
            self._prov_text.tag_bind(tag_name, "<Button-1>",
                                     lambda e, p=pid: self._open_provider_dialog(preselected=p))

            self._prov_text.tag_bind(tag_marker, "<Enter>",
                                     lambda e, t=tag_marker: self._prov_text.tag_configure(t, underline=True))
            self._prov_text.tag_bind(tag_marker, "<Leave>",
                                     lambda e, t=tag_marker: self._prov_text.tag_configure(t, underline=False))
            self._prov_text.tag_bind(tag_marker, "<Button-1>",
                                     lambda e, p=pid: self._set_active(p))

        self._prov_text.configure(state=tk.DISABLED)

    def _set_active(self, pid):
        if pid not in self._config.get("providers", {}):
            return
        self._config["active_provider"] = pid
        llm.config.save(self._config)
        self._refresh_providers()

    # ─── Provider Edit Dialog ────────────────────────────────

    def _open_provider_dialog(self, is_new=False, preselected=None):
        open_provider_dialog(self, self._config, self._refresh_providers,
                             is_new=is_new, preselected=preselected)


def open_provider_dialog(parent, config, refresh_cb=None, is_new=False, preselected=None):
    dialog = tk.Toplevel(parent)
    dialog.title("New Provider" if is_new else "Edit Provider")
    dialog.configure(bg=BG)
    dialog.transient(parent)

    dialog.columnconfigure(0, weight=0)
    dialog.columnconfigure(1, weight=1)

    style = ttk.Style()
    style.configure("TCombobox",
                     fieldbackground=BG_WIDGET,
                     foreground=FG,
                     insertcolor=FG,
                     selectbackground=SEL_BG,
                     selectforeground=FG,
                     arrowsize=12)

    providers = config.get("providers", {})
    active = config.get("active_provider", "")
    active_models = config.get("active_models", {})

    row = 0

    if not is_new:
        tk.Label(
            dialog, text="Provider:", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 3))
        pids = list(providers.keys())
        sel = preselected or active
        if not pids:
            pid_var = tk.StringVar(value="")
        else:
            init = sel if sel in pids else pids[0]
            pid_var = tk.StringVar(value=init)
        option = tk.OptionMenu(dialog, pid_var, pid_var.get(),
                                *([p for p in pids if p != pid_var.get()] if pids else []))
        option.config(bg=BG_WIDGET, fg=FG, font=fonts.view_font(11),
                       borderwidth=0, highlightthickness=1,
                       highlightcolor="#333333", highlightbackground="#333333",
                       activebackground=SEL_BG, activeforeground=FG)
        option["menu"].config(bg=BG_WIDGET, fg=FG, font=fonts.view_font(11))
        option.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 3))
        row += 1
    else:
        pid_var = None

    tk.Label(
        dialog, text="Name:", font=fonts.view_font(11),
        fg=FG_DIM, bg=BG,
    ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
    name_var = tk.StringVar()
    tk.Entry(
        dialog, textvariable=name_var, bg=BG_WIDGET, fg=FG,
        insertbackground=FG, font=fonts.view_font(11),
        borderwidth=1, relief=tk.FLAT,
        highlightthickness=1, highlightcolor="#333333",
        highlightbackground="#333333",
    ).grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))
    row += 1

    tk.Label(
        dialog, text="Base URL:", font=fonts.view_font(11),
        fg=FG_DIM, bg=BG,
    ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
    url_var = tk.StringVar()
    url_entry = tk.Entry(
        dialog, textvariable=url_var, bg=BG_WIDGET, fg=FG,
        insertbackground=FG, font=fonts.view_font(11),
        borderwidth=1, relief=tk.FLAT,
        highlightthickness=1, highlightcolor="#333333",
        highlightbackground="#333333",
    )
    url_entry.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))
    row += 1

    tk.Label(
        dialog, text="API Key:", font=fonts.view_font(11),
        fg=FG_DIM, bg=BG,
    ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
    key_var = tk.StringVar()
    key_entry = tk.Entry(
        dialog, textvariable=key_var, show="*",
        bg=BG_WIDGET, fg=FG, insertbackground=FG,
        font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
        highlightthickness=1, highlightcolor="#333333",
        highlightbackground="#333333",
    )
    key_entry.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))
    row += 1

    tk.Label(
        dialog, text="Models:", font=fonts.view_font(11),
        fg=FG_DIM, bg=BG,
    ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))

    model_var = tk.StringVar()
    model_combo = ttk.Combobox(
        dialog, textvariable=model_var,
        font=fonts.view_font(11),
    )
    model_combo.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))

    detect_btn = tk.Label(
        dialog, text=" Detect ", bg="#222222", fg=FG,
        font=fonts.view_font(9), relief=tk.RAISED, bd=1,
        padx=8, pady=3,
    )
    detect_btn.grid(row=row, column=2, padx=(5, 15), pady=(5, 3))
    detect_btn.bind("<Enter>", lambda e: detect_btn.config(bg="#333333"))
    detect_btn.bind("<Leave>", lambda e: detect_btn.config(bg="#222222"))

    def _ollama_context_length(base, model):
        if not model or not base:
            return None
        if "11434" not in base and "ollama" not in base.lower():
            return None
        try:
            import urllib.request
            root = base.rstrip("/")
            if root.endswith("/v1"):
                root = root[:-3].rstrip("/")
            payload = json.dumps({"name": model}).encode("utf-8")
            req = urllib.request.Request(
                root + "/api/show", data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
            info = data.get("model_info") or {}
            for k, v in info.items():
                if isinstance(k, str) and k.lower().endswith("context_length") and isinstance(v, int) and v > 0:
                    return v
            return None
        except Exception:
            return None

    def _run_detect():
        url = url_var.get().strip()
        key = key_var.get().strip()
        if not url:
            return
        feedback.config(text="Detecting models...", fg=SUCCESS)
        detect_btn.config(text=" ... ", fg=FG_DIM)
        def _run():
            try:
                from openai import OpenAI
                client = OpenAI(base_url=url, api_key=key or "none")
                api_models = client.models.list()
                ids = [m.id for m in api_models.data]
                ctx = _ollama_context_length(url, ids[0] if ids else None)
                dialog.after(0, lambda: _on_detect(ids, ctx))
            except Exception as e:
                dialog.after(0, lambda err=str(e): _on_error(err))
        def _on_detect(ids, ctx=None):
            try:
                model_combo['values'] = ids
                if ids and model_var.get() not in ids:
                    model_var.set(ids[0])
                if ctx and not ctx_limit_var.get().strip():
                    ctx_limit_var.set(str(ctx))
                feedback.config(text=f"Found {len(ids)} model(s).", fg=SUCCESS)
                detect_btn.config(text=" Detect ", fg=FG)
            except tk.TclError:
                pass
        def _on_error(err):
            try:
                feedback.config(text=f"Detection failed: {err}", fg=ERR)
                detect_btn.config(text=" Detect ", fg=FG)
                dialog.after(4000, lambda: feedback.config(text="", fg=SUCCESS))
            except tk.TclError:
                pass
        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _on_focus_out(event):
        if event.widget is url_entry or event.widget is key_entry:
            _run_detect()

    url_entry.bind("<FocusOut>", _on_focus_out)
    key_entry.bind("<FocusOut>", _on_focus_out)

    detect_btn.bind("<Button-1>", lambda e: _run_detect())

    row += 1

    tk.Label(
        dialog, text="Context limit (tokens):", font=fonts.view_font(11),
        fg=FG_DIM, bg=BG,
    ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
    ctx_limit_var = tk.StringVar()
    tk.Entry(
        dialog, textvariable=ctx_limit_var, bg=BG_WIDGET, fg=FG,
        insertbackground=FG, font=fonts.view_font(11),
        borderwidth=1, relief=tk.FLAT,
        highlightthickness=1, highlightcolor="#333333",
        highlightbackground="#333333",
    ).grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))
    row += 1

    feedback = tk.Label(
        dialog, text="", font=fonts.view_font(9),
        fg=SUCCESS, bg=BG,
    )
    feedback.grid(row=row, column=0, columnspan=2, pady=(8, 0))
    row += 1

    btn_inner = tk.Frame(dialog, bg=BG)
    btn_inner.grid(row=row, column=0, columnspan=2, sticky="ew",
                   padx=15, pady=(10, 10))

    tk.Label(
        btn_inner, text="  Close  ", bg="#222222", fg=FG,
        font=fonts.view_font(10), relief=tk.RAISED, bd=1,
        padx=15, pady=6,
    ).pack(side=tk.RIGHT, padx=(5, 0))
    close_btn = btn_inner.winfo_children()[-1]
    close_btn.bind("<Button-1>", lambda e: dialog.destroy())
    close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
    close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

    save_btn = tk.Label(
        btn_inner, text="  Save  ", bg="#222222", fg=FG,
        font=fonts.view_font(10), relief=tk.RAISED, bd=1,
        padx=15, pady=6,
    )
    save_btn.pack(side=tk.RIGHT)
    save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#333333"))
    save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#222222"))

    if not is_new:
        del_btn = tk.Label(
            btn_inner, text="  Delete  ", bg="#222222", fg=ERR,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        del_btn.pack(side=tk.RIGHT, padx=(5, 0))
        del_btn.bind("<Enter>", lambda e: del_btn.config(bg="#333333"))
        del_btn.bind("<Leave>", lambda e: del_btn.config(bg="#222222"))

        def _delete():
            pid = pid_var.get().strip()
            if pid not in providers:
                return
            if len(providers) <= 1:
                feedback.config(text="Cannot delete the last provider.")
                dialog.after(1500, lambda: feedback.config(text=""))
                return
            del providers[pid]
            if config["active_provider"] == pid:
                remaining = list(providers.keys())
                config["active_provider"] = remaining[0]
                am = config.get("active_models", {})
                if pid in am:
                    del am[pid]
            config["providers"] = providers
            llm.config.save(config)
            refresh_cb and refresh_cb()
            feedback.config(text=f"Deleted '{pid}'.")
            dialog.after(800, dialog.destroy)

        del_btn.bind("<Button-1>", lambda e: _delete())

    def _load_provider():
        if is_new:
            name_var.set("")
            url_var.set("")
            key_var.set("")
            model_var.set("")
            ctx_limit_var.set("")
            model_combo['values'] = []
            return
        pid = pid_var.get().strip()
        p = providers.get(pid, {})
        name_var.set(pid)
        url_var.set(p.get("base_url", ""))
        key_var.set(p.get("api_key", ""))
        ctx = p.get("context_limit", "")
        ctx_limit_var.set(str(ctx) if ctx else "")
        model_list = p.get("models", [])
        model_combo['values'] = model_list
        am = active_models.get(pid, "")
        if am:
            model_var.set(am)
        elif model_list:
            model_var.set(model_list[0])
        else:
            model_var.set("")

    def _save():
        name = name_var.get().strip()
        if not name:
            return
        if is_new:
            if name in providers:
                feedback.config(text="Name already exists.")
                dialog.after(1500, lambda: feedback.config(text=""))
                return
            new_key = name
        else:
            old_key = pid_var.get().strip()
            new_key = name
            if new_key != old_key:
                if new_key in providers:
                    feedback.config(text="Name already exists.")
                    dialog.after(1500, lambda: feedback.config(text=""))
                    return
                providers[new_key] = providers.pop(old_key)
                if config["active_provider"] == old_key:
                    config["active_provider"] = new_key
                am = active_models
                if old_key in am:
                    am[new_key] = am.pop(old_key)
                    config["active_models"] = am
        combo_models = list(model_combo['values'])
        selected = model_var.get().strip()
        if selected and selected not in combo_models:
            combo_models.append(selected)
        providers[new_key] = {
            "base_url": url_var.get().strip(),
            "api_key": key_var.get().strip(),
            "models": combo_models,
        }
        ctx_raw = ctx_limit_var.get().strip()
        if ctx_raw:
            try:
                ctx_int = int(ctx_raw)
                if ctx_int > 0:
                    providers[new_key]["context_limit"] = ctx_int
            except ValueError:
                pass
        if selected:
            active_models[new_key] = selected
            config["active_models"] = active_models
        config["providers"] = providers
        if is_new:
            config.setdefault("active_provider", new_key)
        else:
            config["active_provider"] = new_key
        llm.config.save(config)
        refresh_cb and refresh_cb()
        feedback.config(text="Saved.")
        dialog.after(800, dialog.destroy)

    if not is_new:
        pid_var.trace_add("write", lambda *_: _load_provider())
        _load_provider()
        if url_var.get().strip():
            _run_detect()

    save_btn.bind("<Button-1>", lambda e: _save())

    windowing.min_size(dialog, 540, 1)
    dialog.update_idletasks()
    dialog.wait_visibility()
    dialog.grab_set()
