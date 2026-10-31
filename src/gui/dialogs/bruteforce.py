import os
import queue
import time
import tkinter as tk
from tkinter import ttk
from src.gui import fonts, windowing, theme
from src.machines import store
from src.tools.bruteforce import BruteForceEngine, KerberosEngine
from src.tools.bruteforce.people_users import usernames_from_people
from src.elwand_paths import lst_dir as _lst_dir
from src.gui.dialogs.target_section import TargetSection

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"
BG = "#111111"
FG = "#ffffff"


class BruteforceDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Bruteforce")
        windowing.size_dialog(self, 820, 670)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        import shutil
        self._has_xfreerdp = shutil.which("xfreerdp") is not None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        self._notebook_frame = tk.Frame(self, bg=BG)
        self._notebook_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(5, 0))

        self._nb = ttk.Notebook(self._notebook_frame)
        self._nb.pack(fill=tk.X)

        self._tab_ftp = tk.Frame(self._nb, bg=BG)
        self._tab_ssh = tk.Frame(self._nb, bg=BG)
        self._tab_smb = tk.Frame(self._nb, bg=BG)
        self._tab_kerberos = tk.Frame(self._nb, bg=BG)
        self._tab_rdp = tk.Frame(self._nb, bg=BG)
        self._tab_ldap = tk.Frame(self._nb, bg=BG)
        self._tab_mssql = tk.Frame(self._nb, bg=BG)
        self._tab_mysql = tk.Frame(self._nb, bg=BG)
        self._tab_pgsql = tk.Frame(self._nb, bg=BG)

        self._nb.add(self._tab_ftp, text="FTP")
        self._nb.add(self._tab_ssh, text="SSH")
        self._nb.add(self._tab_smb, text="SMB")
        self._nb.add(self._tab_kerberos, text="Kerberos")
        self._nb.add(self._tab_rdp, text="RDP")
        self._nb.add(self._tab_ldap, text="LDAP")
        self._nb.add(self._tab_mssql, text="MSSQL")
        self._nb.add(self._tab_mysql, text="MySQL")
        self._nb.add(self._tab_pgsql, text="PGSQL")

        self._build_tab(self._tab_ftp, "ftp", 21)
        self._build_tab(self._tab_ssh, "ssh", 22)
        self._build_tab(self._tab_smb, "smb", 445)
        self._build_kerberos_tab()
        self._build_tab(self._tab_rdp, "rdp", 3389)
        self._build_tab(self._tab_ldap, "ldap", 389)
        self._build_tab(self._tab_mssql, "mssql", 1433)
        self._build_tab(self._tab_mysql, "mysql", 3306)
        self._build_tab(self._tab_pgsql, "pgsql", 5432)

        if not self._has_xfreerdp:
            self._rdp_warn = tk.Label(self._tab_rdp, text="xfreerdp not found in PATH. Install freerdp to enable RDP brute force.",
                                      fg=ERR_COLOR, bg=BG, font=fonts.view_font(10), wraplength=500)
            self._rdp_warn.grid(row=9, column=0, columnspan=2, padx=15, pady=(10, 0))
        else:
            self._rdp_warn = None

        output_frame = tk.Frame(self, bg=BG)
        output_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(5, 2))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self._output = theme.output(output_frame)
        self._output.tag_configure("info", foreground=INFO)
        self._output.tag_configure("bright", foreground=BRIGHT)
        self._output.grid(row=0, column=0, sticky="nsew")

        scrollbar = theme.scrollbar(output_frame, self._output)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._progress_var = tk.IntVar(value=0)
        self._progress_bar = ttk.Progressbar(
            self, variable=self._progress_var, maximum=100)
        self._progress_bar.grid(row=2, column=0, sticky="ew", padx=15,
                                pady=(5, 2))

        self._progress_label = tk.Label(
            self, text="Ready", font=fonts.view_font(9),
            fg=MUTED, bg=BG, anchor="w")
        self._progress_label.grid(row=3, column=0, sticky="ew", padx=15)

        footer = tk.Frame(self, bg=BG)
        footer.grid(row=4, column=0, sticky="ew", padx=15, pady=(10, 15))

        close_btn = theme.button(footer, "  Close  ", command=self._on_close)
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self._clear_btn = theme.button(footer, "  Clear  ", command=self._clear)
        self._clear_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self._stop_btn = theme.button(footer, "  Stop  ", command=self._stop)
        self._stop_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self._start_btn = theme.button(footer, "  Start  ", command=self._start)
        self._start_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self._engine = None
        self._found_count = 0
        self._vars_by_tab = {"ftp": self._ftp_vars, "ssh": self._ssh_vars, "smb": self._smb_vars,
                            "kerberos": self._kerberos_vars,
                            "ldap": self._ldap_vars, "rdp": self._rdp_vars,
                            "mssql": self._mssql_vars, "mysql": self._mysql_vars,
                            "pgsql": self._pgsql_vars}

        self._proto_idx = {"ftp": 0, "ssh": 1, "smb": 2, "kerberos": 3,
                          "rdp": 4, "ldap": 5, "mssql": 6, "mysql": 7,
                          "pgsql": 8}
        self._tab_widgets = {"ftp": self._tab_ftp, "ssh": self._tab_ssh, "smb": self._tab_smb,
                            "kerberos": self._tab_kerberos,
                            "rdp": self._tab_rdp, "ldap": self._tab_ldap,
                            "mssql": self._tab_mssql, "mysql": self._tab_mysql,
                            "pgsql": self._tab_pgsql}

        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Worker -> main-thread event queue. Engine callbacks only enqueue here
        # (never touch tkinter); _drain applies them on the Tk thread.
        self._ui_q = queue.Queue()
        self._last_progress_at = 0.0
        self._drain_id = self.after(100, self._drain)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_tab(self, tab, proto, default_port):
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)

        row = 0

        # --- Target ---
        tk.Label(tab, text="Target:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=row, column=0, sticky="nw", padx=15, pady=(15, 5))

        mach_frame = tk.Frame(tab, bg="#000000")
        mach_frame.grid(row=row, column=1, sticky="nsew", padx=15, pady=(15, 5))
        mach_frame.columnconfigure(0, weight=1)
        mach_frame.rowconfigure(0, weight=1)

        machine_list = theme.listbox(mach_frame, height=5)
        machine_list.grid(row=0, column=0, sticky="nsew")
        mach_scroll = theme.scrollbar(mach_frame, machine_list)
        mach_scroll.grid(row=0, column=1, sticky="ns")

        self._populate_machines(machine_list)
        target_var = tk.StringVar()
        machine_list.bind("<<ListboxSelect>>", lambda e: self._on_machine_select(machine_list, target_var))

        tk.Entry(tab, textvariable=target_var, bg="#000000", fg=FG, insertbackground=FG,
                 font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                 highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=row + 1, column=1, sticky="ew", padx=15, pady=(2, 5))
        row += 2

        # --- Port ---
        tk.Label(tab, text="Port:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 5))
        port_var = tk.StringVar(value=str(default_port))
        tk.Entry(tab, textvariable=port_var, bg="#000000", fg=FG, insertbackground=FG,
                 font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT, width=8,
                 highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=row, column=1, sticky="w", padx=15, pady=(5, 5))
        row += 1

        # --- Users ---
        user_src = tk.StringVar(value="inventory")
        user_path = tk.StringVar()

        tk.Label(tab, text="Users:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=row, column=0, sticky="nw", padx=15, pady=(5, 5))

        user_row = tk.Frame(tab, bg=BG)
        user_row.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        theme.Segmented(
            user_row,
            [("inventory", "From inventory"),
             ("people", "From people with dicma"),
             ("file", "From file")],
            user_src).pack(side=tk.LEFT)

        user_browse_btn = theme.button(
            user_row, "  Browse...  ",
            command=lambda: self._browse_file(user_path), padx=10, pady=4)
        user_browse_btn.pack(side=tk.LEFT, padx=(10, 0))
        row += 1

        user_path_label = tk.Label(tab, textvariable=user_path, fg=BRIGHT, bg=BG,
                                   font=fonts.view_font(9), anchor="w", justify="left")
        user_path_label.grid(row=row, column=1, sticky="ew", padx=15, pady=(0, 5))

        def _toggle_user(*_):
            if user_src.get() == "file":
                if not user_path.get():
                    self._browse_file(user_path)
                user_browse_btn.enable()
            else:
                user_browse_btn.disable()
                user_path.set("")
        user_src.trace_add("write", _toggle_user)
        _toggle_user()
        row += 1

        # --- Passwords ---
        pass_src = tk.StringVar(value="inventory")
        pass_path = tk.StringVar()

        tk.Label(tab, text="Passwords:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=row, column=0, sticky="nw", padx=15, pady=(5, 5))

        pass_row = tk.Frame(tab, bg=BG)
        pass_row.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        theme.Segmented(
            pass_row,
            [("inventory", "From inventory"), ("file", "From file")],
            pass_src).pack(side=tk.LEFT)

        pass_browse_btn = theme.button(
            pass_row, "  Browse...  ",
            command=lambda: self._browse_file(pass_path), padx=10, pady=4)
        pass_browse_btn.pack(side=tk.LEFT, padx=(10, 0))
        row += 1

        pass_path_label = tk.Label(tab, textvariable=pass_path, fg=BRIGHT, bg=BG,
                                   font=fonts.view_font(9), anchor="w", justify="left")
        pass_path_label.grid(row=row, column=1, sticky="ew", padx=15, pady=(0, 5))

        def _toggle_pass(*_):
            if pass_src.get() == "file":
                if not pass_path.get():
                    self._browse_file(pass_path)
                pass_browse_btn.enable()
            else:
                pass_browse_btn.disable()
                pass_path.set("")
        pass_src.trace_add("write", _toggle_pass)
        _toggle_pass()
        row += 1

        setattr(self, f"_{proto}_vars", {
            "target": target_var, "port": port_var,
            "user_src": user_src, "user_path": user_path,
            "pass_src": pass_src, "pass_path": pass_path,
        })

    def _build_kerberos_tab(self):
        tab = self._tab_kerberos
        tab.columnconfigure(1, weight=1)

        row = 0
        self._kerb_target = TargetSection(
            tab, row, mode="both", label="DC / KDC",
            on_select=self._on_kerb_target_change)
        row += 2

        tk.Label(tab, text="Domain:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=row, column=0, sticky="w",
                                       padx=15, pady=(5, 5))
        domain_var = tk.StringVar()
        theme.entry(tab, textvariable=domain_var, width=30).grid(
            row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        row += 1

        tk.Label(tab, text="Mode:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=row, column=0, sticky="w",
                                       padx=15, pady=(5, 5))
        mode_var = tk.StringVar(value="userenum")
        theme.Segmented(
            tab, [("userenum", "User enumeration"),
                  ("bruteuser", "Bruteforce password")],
            mode_var, command=self._toggle_kerberos_mode).grid(
                row=row, column=1, sticky="w", padx=15, pady=(5, 5))
        row += 1

        # --- Userenum group ---
        ue = tk.Frame(tab, bg=BG)
        ue.grid(row=row, column=0, columnspan=2, sticky="ew",
                padx=15, pady=(5, 5))
        ue.columnconfigure(1, weight=1)

        tk.Label(ue, text="Users:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=0, column=0, sticky="w")
        ue_row = tk.Frame(ue, bg=BG)
        ue_row.grid(row=0, column=1, sticky="ew")
        user_src = tk.StringVar(value="inventory")
        user_path = tk.StringVar()
        theme.Segmented(
            ue_row,
            [("inventory", "From inventory"),
             ("people", "From people with dicma"),
             ("file", "From file")],
            user_src).pack(side=tk.LEFT)
        user_browse = theme.button(
            ue_row, "  Browse...  ",
            command=lambda: self._browse_file(user_path), padx=10, pady=4)
        user_browse.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(ue, textvariable=user_path, fg=BRIGHT, bg=BG,
                 font=fonts.view_font(9), anchor="w", justify="left").grid(
                     row=1, column=1, sticky="ew", pady=(2, 0))

        def _toggle_user(*_):
            if user_src.get() == "file":
                if not user_path.get():
                    self._browse_file(user_path)
                user_browse.enable()
            else:
                user_browse.disable()
                user_path.set("")
        user_src.trace_add("write", _toggle_user)
        _toggle_user()

        # --- Bruteuser group ---
        bu = tk.Frame(tab, bg=BG)
        bu.grid(row=row, column=0, columnspan=2, sticky="ew",
                padx=15, pady=(5, 5))
        bu.columnconfigure(1, weight=1)

        tk.Label(bu, text="User:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=0, column=0, sticky="w")
        single_user_var = tk.StringVar()
        theme.entry(bu, textvariable=single_user_var, width=30).grid(
            row=0, column=1, sticky="ew")

        tk.Label(bu, text="Passwords:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).grid(row=1, column=0, sticky="w", pady=(5, 0))
        bu_row = tk.Frame(bu, bg=BG)
        bu_row.grid(row=1, column=1, sticky="ew", pady=(5, 0))
        pass_src = tk.StringVar(value="inventory")
        pass_path = tk.StringVar()
        theme.Segmented(
            bu_row, [("inventory", "From inventory"), ("file", "From file")],
            pass_src).pack(side=tk.LEFT)
        pass_browse = theme.button(
            bu_row, "  Browse...  ",
            command=lambda: self._browse_file(pass_path), padx=10, pady=4)
        pass_browse.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(bu, textvariable=pass_path, fg=BRIGHT, bg=BG,
                 font=fonts.view_font(9), anchor="w", justify="left").grid(
                     row=2, column=1, sticky="ew", pady=(2, 0))

        def _toggle_pass(*_):
            if pass_src.get() == "file":
                if not pass_path.get():
                    self._browse_file(pass_path)
                pass_browse.enable()
            else:
                pass_browse.disable()
                pass_path.set("")
        pass_src.trace_add("write", _toggle_pass)
        _toggle_pass()

        self._kerb_userenum_frame = ue
        self._kerb_bruteuser_frame = bu

        # --- Options ---
        row += 1
        opts = tk.Frame(tab, bg=BG)
        opts.grid(row=row, column=0, columnspan=2, sticky="w",
                  padx=15, pady=(5, 5))
        tk.Label(opts, text="Threads:", font=fonts.view_font_bold(11),
                 fg=MUTED, bg=BG).pack(side=tk.LEFT)
        workers_var = tk.StringVar(value="200")
        theme.entry(opts, textvariable=workers_var, width=5).pack(
            side=tk.LEFT, padx=(6, 18))
        safe_var = tk.BooleanVar(value=False)
        theme.Toggle(opts, "Safe mode", variable=safe_var).pack(side=tk.LEFT)

        self._kerberos_vars = {
            "domain": domain_var,
            "mode": mode_var,
            "user_src": user_src,
            "user_path": user_path,
            "single_user": single_user_var,
            "pass_src": pass_src,
            "pass_path": pass_path,
            "workers": workers_var,
            "safe": safe_var,
        }
        self._toggle_kerberos_mode()
        self._on_kerb_target_change(None)

    def _domain_for_machine(self, ip):
        """Best-known domain for a machine (its SMB domain or an associated one)."""
        m = store.get(ip)
        if m is None:
            return ""
        if getattr(m, "domain", ""):
            return m.domain
        try:
            from src.machines import machine_db
            domains = machine_db.load_domains(m.id)
        except Exception:
            domains = []
        if domains:
            first = domains[0]
            return first[0] if isinstance(first, (tuple, list)) else first
        return ""

    def _on_kerb_target_change(self, value):
        """Fill the Domain field from the selected DC/KDC machine."""
        target = getattr(self, "_kerb_target", None)
        vars_ = getattr(self, "_kerberos_vars", None)
        if target is None or vars_ is None:
            return
        sel = target.selected()
        if not sel:
            return
        kind, val, _label, _ip = sel
        if kind == "domain":
            vars_["domain"].set((val or "").upper())
            return
        domain = self._domain_for_machine(val)
        if domain:
            vars_["domain"].set(domain.upper())

    def _toggle_kerberos_mode(self):
        vars_ = getattr(self, "_kerberos_vars", None)
        if not vars_:
            return
        if vars_["mode"].get() == "bruteuser":
            self._kerb_userenum_frame.grid_remove()
            self._kerb_bruteuser_frame.grid()
        else:
            self._kerb_bruteuser_frame.grid_remove()
            self._kerb_userenum_frame.grid()

    def _browse_file(self, path_var):
        initial = str(_lst_dir())
        f = windowing.ask_open_file(
            self, title="Select wordlist", initialdir=initial,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            path_var.set(f)

    def _populate_machines(self, lb):
        for m in store.get_all_sorted():
            if m.ip not in ("127.0.0.1", "::1") and not m.ip.startswith("127."):
                label = f"  {m.ip:<16} {m.hostname or ''}"
                lb.insert(tk.END, label)

    def _on_machine_select(self, lb, target_var):
        sel = lb.curselection()
        if sel:
            text = lb.get(sel[0]).strip()
            ip = text.split()[0]
            target_var.set(ip)

    def _populate_lst_files(self, lb):
        lst_dir = str(_lst_dir())
        if os.path.isdir(lst_dir):
            for fname in sorted(os.listdir(lst_dir)):
                if os.path.isfile(os.path.join(lst_dir, fname)):
                    lb.insert(tk.END, f"  {fname}")
        lb.selection_set(0)

    def _on_lst_select(self, lb, var):
        sel = lb.curselection()
        if sel:
            text = lb.get(sel[0]).strip()
            var.set(f"lst/{text}")

    def _on_tab_changed(self, event=None):
        proto = self._get_active_proto()
        if proto is None:
            return
        if proto == "rdp" and not self._has_xfreerdp:
            self._start_btn.config(text="  xfreerdp required  ")
            self._start_btn.disable()
        else:
            self._start_btn.config(text="  Start  ")
            self._start_btn.enable()

    def _get_active_proto(self):
        for proto, idx in self._proto_idx.items():
            if idx == self._nb.index(self._nb.select()):
                return proto
        return None

    def select_tab(self, proto):
        if proto in self._proto_idx:
            self._nb.select(self._proto_idx[proto])

    def auto_start(self, target, port, proto, users, passwords):
        self.select_tab(proto)
        if proto == "kerberos":
            # Console/agent wiring for Kerberos is not implemented yet; just
            # open the tab so the user can fill in the realm/DC.
            return
        vars_ = self._vars_by_tab[proto]
        vars_["target"].set(target)
        vars_["port"].set(str(port))
        vars_["user_src"].set("inventory")
        vars_["pass_src"].set("inventory")
        self._begin_run()
        engine = BruteForceEngine(
            target=target, port=port, protocol=proto,
            users=users, passwords=passwords,
            on_result=lambda t, c=None: self._ui_q.put(("log", t, c)),
            on_progress=self._queue_progress,
            on_found=self._on_cred_found,
        )
        self._engine = engine
        engine.start()

    def _start(self):
        proto = self._get_active_proto()
        vars_ = self._vars_by_tab[proto]

        if proto == "kerberos":
            self._start_kerberos(vars_)
            return

        target = vars_["target"].get().strip()
        if not target:
            self._log("Target is required", "error")
            return
        try:
            port = int(vars_["port"].get().strip())
        except ValueError:
            self._log("Invalid port", "error")
            return

        user_src = vars_["user_src"].get()
        pass_src = vars_["pass_src"].get()

        if user_src == "people":
            users = usernames_from_people()
            if not users:
                self._log("No usernames generated from People (DICMA)", "error")
                return
            self._log(f"Using {len(users)} users from People (DICMA)", "info")
            userlist = None
        elif user_src == "inventory":
            from src.machines.credential_db import load_usernames
            users = load_usernames()
            if not users:
                self._log("No users in inventory", "error")
                return
            self._log(f"Using {len(users)} users from inventory", "info")
            userlist = None
        else:
            userlist = vars_["user_path"].get().strip()
            if not userlist:
                self._log("User list file is required", "error")
                return
            users = None

        if pass_src == "inventory":
            from src.machines.credential_db import load_passwords
            passwords = load_passwords()
            if not passwords:
                self._log("No passwords in inventory", "error")
                return
            self._log(f"Using {len(passwords)} passwords from inventory", "info")
            passlist = None
        else:
            passlist = vars_["pass_path"].get().strip()
            if not passlist:
                self._log("Password list file is required", "error")
                return
            passwords = None

        self._begin_run()

        engine = BruteForceEngine(
            target=target, port=port, protocol=proto,
            userlist=userlist, passlist=passlist,
            users=users, passwords=passwords,
            on_result=lambda t, c=None: self._ui_q.put(("log", t, c)),
            on_progress=self._queue_progress,
            on_found=self._on_cred_found,
        )
        self._engine = engine
        engine.start()

    def _start_kerberos(self, vars_):
        domain = vars_["domain"].get().strip()
        sel = self._kerb_target.selected()
        kdc = sel[1] if sel else ""
        if not domain:
            self._log("Domain (realm) is required", "error")
            return
        if not kdc:
            self._log("Select a DC / KDC (machine or domain)", "error")
            return
        mode = vars_["mode"].get()
        try:
            workers = int(vars_["workers"].get().strip() or "200")
        except ValueError:
            self._log("Invalid thread count", "error")
            return
        safe = bool(vars_["safe"].get())

        users = userlist = None
        passwords = passlist = None
        single_user = ""

        if mode == "userenum":
            if vars_["user_src"].get() == "people":
                users = usernames_from_people()
                if not users:
                    self._log("No usernames generated from People (DICMA)",
                              "error")
                    return
                self._log(f"Using {len(users)} users from People (DICMA)",
                          "info")
            elif vars_["user_src"].get() == "inventory":
                from src.machines.credential_db import load_usernames
                users = load_usernames()
                if not users:
                    self._log("No users in inventory", "error")
                    return
                self._log(f"Using {len(users)} users from inventory", "info")
            else:
                userlist = vars_["user_path"].get().strip()
                if not userlist:
                    self._log("User list file is required", "error")
                    return
        else:
            single_user = vars_["single_user"].get().strip()
            if not single_user:
                self._log("Username is required", "error")
                return
            if vars_["pass_src"].get() == "inventory":
                from src.machines.credential_db import load_passwords
                passwords = load_passwords()
                if not passwords:
                    self._log("No passwords in inventory", "error")
                    return
                self._log(f"Using {len(passwords)} passwords from inventory",
                          "info")
            else:
                passlist = vars_["pass_path"].get().strip()
                if not passlist:
                    self._log("Password list file is required", "error")
                    return

        self._begin_run()

        def _on_found(user, pwd):
            # Saved on the engine thread; only the log line goes to the UI.
            self._found_count += 1
            from src.machines.credential_db import save_credential, save_user
            save_credential(user, pwd, domain=domain,
                            password_origin="kerberos bruteforce")
            save_user(user, origin="kerberos bruteforce", domain=domain)
            self._ui_q.put(("log",
                            f"[+] VALID LOGIN: {user}@{domain}:{pwd}",
                            "success"))

        def _on_valid_user(username, state, detail):
            self._found_count += 1
            from src.machines.credential_db import save_user
            save_user(username, origin="kerberos userenum", domain=domain)
            self._ui_q.put(("log",
                            f"[+] VALID USERNAME: {username}  ({detail})",
                            "success"))

        engine = KerberosEngine(
            domain=domain, kdc=kdc, mode=mode,
            users=users, userlist=userlist, user=single_user,
            passwords=passwords, passlist=passlist,
            workers=workers, safe=safe,
            on_result=lambda t, c=None: self._ui_q.put(("log", t, c)),
            on_progress=self._queue_progress,
            on_found=_on_found,
            on_valid_user=_on_valid_user,
        )
        self._engine = engine
        engine.start()

    def _begin_run(self):
        self._clear_output()
        self._found_count = 0
        self._last_progress_at = 0.0
        self._progress_var.set(0)
        self._progress_label.config(text="Starting…")

    def _clear(self):
        self._clear_output()
        self._found_count = 0
        self._progress_var.set(0)
        self._progress_label.config(text="Ready")

    def _queue_progress(self, tested, total):
        """Throttle progress to ~10 updates/s (runs on the engine thread)."""
        now = time.time()
        if now - self._last_progress_at >= 0.1 or tested >= total:
            self._last_progress_at = now
            self._ui_q.put(("progress", tested, total))

    def _drain(self):
        """Apply queued worker events on the Tk main thread."""
        self._drain_id = None
        if not self.winfo_exists():
            return
        progress = None
        try:
            for _ in range(200):
                try:
                    item = self._ui_q.get_nowait()
                except queue.Empty:
                    break
                if item[0] == "progress":
                    # Coalesce: only the latest progress of this batch is drawn.
                    progress = (item[1], item[2])
                elif item[0] == "log":
                    self._log(item[1], item[2])
            if progress is not None:
                self._update_progress(*progress)
        except tk.TclError:
            return
        try:
            self._drain_id = self.after(100, self._drain)
        except tk.TclError:
            pass

    def _stop(self):
        if self._engine:
            self._engine.stop()
            self._log("Stopped", "info")

    def _on_cred_found(self, proto, target, port, user, pwd):
        self._found_count += 1
        from src.machines.credential_db import save_credential, save_user
        machine = store.get(target)
        dom = machine.domain if machine else ""
        save_credential(user, pwd, domain=dom, password_origin=f"{proto} bruteforce")
        save_user(user)

    def _update_progress(self, tested, total):
        pct = int(tested / max(total, 1) * 100)
        self._progress_var.set(max(0, min(100, pct)))
        self._progress_label.config(
            text=f"  {tested}/{total}  found: {self._found_count}")

    def _log(self, text, color=None):
        self._output.configure(state=tk.NORMAL)
        tag = color or None
        self._output.insert(tk.END, text + "\n", tag)
        self._output.see(tk.END)
        self._output.configure(state=tk.DISABLED)

    def _clear_output(self):
        self._output.configure(state=tk.NORMAL)
        self._output.delete("1.0", tk.END)
        self._output.configure(state=tk.DISABLED)

    def _on_close(self):
        self._stop()
        if self._drain_id:
            try:
                self.after_cancel(self._drain_id)
            except tk.TclError:
                pass
            self._drain_id = None
        self.destroy()
