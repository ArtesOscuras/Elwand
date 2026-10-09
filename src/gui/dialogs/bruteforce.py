import os
import tkinter as tk
from tkinter import ttk
from src.gui import fonts, windowing, theme
from src.machines import store
from src.tools.bruteforce import BruteForceEngine
from src.elwand_paths import lst_dir as _lst_dir

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
        self._tab_rdp = tk.Frame(self._nb, bg=BG)
        self._tab_ldap = tk.Frame(self._nb, bg=BG)
        self._tab_mssql = tk.Frame(self._nb, bg=BG)
        self._tab_mysql = tk.Frame(self._nb, bg=BG)
        self._tab_pgsql = tk.Frame(self._nb, bg=BG)

        self._nb.add(self._tab_ftp, text="FTP")
        self._nb.add(self._tab_ssh, text="SSH")
        self._nb.add(self._tab_smb, text="SMB")
        self._nb.add(self._tab_rdp, text="RDP")
        self._nb.add(self._tab_ldap, text="LDAP")
        self._nb.add(self._tab_mssql, text="MSSQL")
        self._nb.add(self._tab_mysql, text="MySQL")
        self._nb.add(self._tab_pgsql, text="PGSQL")

        self._build_tab(self._tab_ftp, "ftp", 21)
        self._build_tab(self._tab_ssh, "ssh", 22)
        self._build_tab(self._tab_smb, "smb", 445)
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
        output_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(5, 10))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self._output = theme.output(output_frame)
        self._output.tag_configure("info", foreground=INFO)
        self._output.tag_configure("bright", foreground=BRIGHT)
        self._output.grid(row=0, column=0, sticky="nsew")

        scrollbar = theme.scrollbar(output_frame, self._output)
        scrollbar.grid(row=0, column=1, sticky="ns")

        footer = tk.Frame(self, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))

        close_btn = theme.button(footer, "  Close  ", command=self._on_close)
        close_btn.pack(side=tk.RIGHT, padx=(10, 0))

        self._stop_btn = theme.button(footer, "  Stop  ", command=self._stop)
        self._stop_btn.pack(side=tk.RIGHT, padx=(10, 0))

        self._start_btn = theme.button(footer, "  Start  ", command=self._start)
        self._start_btn.pack(side=tk.RIGHT, padx=(10, 0))

        self._engine = None
        self._vars_by_tab = {"ftp": self._ftp_vars, "ssh": self._ssh_vars, "smb": self._smb_vars,
                            "ldap": self._ldap_vars, "rdp": self._rdp_vars,
                            "mssql": self._mssql_vars, "mysql": self._mysql_vars,
                            "pgsql": self._pgsql_vars}

        self._proto_idx = {"ftp": 0, "ssh": 1, "smb": 2, "rdp": 3,
                          "ldap": 4, "mssql": 5, "mysql": 6, "pgsql": 7}
        self._tab_widgets = {"ftp": self._tab_ftp, "ssh": self._tab_ssh, "smb": self._tab_smb,
                            "rdp": self._tab_rdp, "ldap": self._tab_ldap,
                            "mssql": self._tab_mssql, "mysql": self._tab_mysql,
                            "pgsql": self._tab_pgsql}

        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

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
            [("inventory", "From inventory"), ("file", "From file")],
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
        vars_ = self._vars_by_tab[proto]
        vars_["target"].set(target)
        vars_["port"].set(str(port))
        vars_["user_src"].set("inventory")
        vars_["pass_src"].set("inventory")
        self._start_btn.config(text="  Running...  ", fg=MUTED)
        self._clear_output()
        engine = BruteForceEngine(
            target=target, port=port, protocol=proto,
            users=users, passwords=passwords,
            on_result=self._log,
            on_progress=lambda tested, total: self._update_progress(tested, total),
            on_found=self._on_cred_found,
        )
        self._engine = engine
        engine.start()

    def _start(self):
        proto = self._get_active_proto()
        vars_ = self._vars_by_tab[proto]

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

        if user_src == "inventory":
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

        self._start_btn.config(text="  Running...  ", fg=MUTED)
        self._clear_output()

        engine = BruteForceEngine(
            target=target, port=port, protocol=proto,
            userlist=userlist, passlist=passlist,
            users=users, passwords=passwords,
            on_result=self._log,
            on_progress=lambda tested, total: self._update_progress(tested, total),
            on_found=self._on_cred_found,
        )
        self._engine = engine
        engine.start()

    def _stop(self):
        if self._engine:
            self._engine.stop()
            self._log("Stopped", "info")
        self._start_btn.config(text="  Start  ", fg=FG)

    def _on_cred_found(self, proto, target, port, user, pwd):
        from src.machines.credential_db import save_credential, save_user
        machine = store.get(target)
        dom = machine.domain if machine else ""
        save_credential(user, pwd, domain=dom, password_origin=f"{proto} bruteforce")
        save_user(user)

    def _update_progress(self, tested, total):
        pct = int(tested / max(total, 1) * 100)
        self._start_btn.config(text=f"  {pct}% ({tested}/{total})  ")

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
        self.destroy()
