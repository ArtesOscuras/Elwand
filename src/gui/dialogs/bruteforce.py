import os
import tkinter as tk
from tkinter import ttk
from src.gui import fonts
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
        self.geometry("820x670")
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        import shutil
        self._has_xfreerdp = shutil.which("xfreerdp") is not None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222", foreground=MUTED,
                        font=fonts.view_font(10), padding=[12, 4])
        style.map("TNotebook.Tab", background=[("selected", "#111111")],
                  foreground=[("selected", FG)])

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

        self._output = tk.Text(
            output_frame, bg="#000000", fg=BRIGHT,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self._output.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(output_frame, orient=tk.VERTICAL, command=self._output.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._output.configure(yscrollcommand=scrollbar.set)
        self._output.tag_configure("success", foreground=SUCCESS)
        self._output.tag_configure("error", foreground=ERR_COLOR)
        self._output.tag_configure("info", foreground=INFO)
        self._output.tag_configure("bright", foreground=BRIGHT)
        self._output.tag_configure("muted", foreground=MUTED)

        footer = tk.Frame(self, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))

        close_btn = tk.Label(
            footer, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(10, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        self._stop_btn = tk.Label(
            footer, text="  Stop  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=15, pady=6,
        )
        self._stop_btn.pack(side=tk.RIGHT, padx=(10, 0))
        self._stop_btn.bind("<Button-1>", lambda e: self._stop())
        self._stop_btn.bind("<Enter>", lambda e: self._stop_btn.config(bg="#333333"))
        self._stop_btn.bind("<Leave>", lambda e: self._stop_btn.config(bg="#222222"))

        self._start_btn = tk.Label(
            footer, text="  Start  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=15, pady=6,
        )
        self._start_btn.pack(side=tk.RIGHT, padx=(10, 0))
        self._start_btn.bind("<Button-1>", lambda e: self._start())
        self._start_btn.bind("<Enter>", lambda e: self._start_btn.config(bg="#333333"))
        self._start_btn.bind("<Leave>", lambda e: self._start_btn.config(bg="#222222"))

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

        machine_list = tk.Listbox(
            mach_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=5,
        )
        machine_list.grid(row=0, column=0, sticky="nsew")
        mach_scroll = tk.Scrollbar(mach_frame, orient=tk.VERTICAL, command=machine_list.yview)
        mach_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                               width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        mach_scroll.grid(row=0, column=1, sticky="ns")
        machine_list.configure(yscrollcommand=mach_scroll.set)

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
        tk.Radiobutton(user_row, text="From inventory", variable=user_src, value="inventory",
                       bg=BG, fg=MUTED, selectcolor=BG, font=fonts.view_font(10),
                       activebackground=BG, activeforeground=FG, highlightthickness=0).pack(side=tk.LEFT, padx=(0, 15))
        tk.Radiobutton(user_row, text="From file", variable=user_src, value="file",
                       bg=BG, fg=MUTED, selectcolor=BG, font=fonts.view_font(10),
                       activebackground=BG, activeforeground=FG, highlightthickness=0).pack(side=tk.LEFT)

        user_browse_btn = tk.Label(user_row, text="  Browse...  ", bg="#222222", fg=FG,
                                   font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=10, pady=4)
        user_browse_btn.pack(side=tk.LEFT, padx=(10, 0))
        user_browse_btn.bind("<Button-1>", lambda e: self._browse_file(user_path))
        user_browse_btn.bind("<Enter>", lambda e: user_browse_btn.config(bg="#333333"))
        user_browse_btn.bind("<Leave>", lambda e: user_browse_btn.config(bg="#222222"))
        row += 1

        user_path_label = tk.Label(tab, textvariable=user_path, fg=BRIGHT, bg=BG,
                                   font=fonts.view_font(9), anchor="w", justify="left")
        user_path_label.grid(row=row, column=1, sticky="ew", padx=15, pady=(0, 5))

        def _toggle_user(*_):
            if user_src.get() == "file":
                if not user_path.get():
                    self._browse_file(user_path)
                user_browse_btn.config(fg=FG, bg="#222222")
                user_browse_btn.bind("<Button-1>", lambda e: self._browse_file(user_path))
                user_browse_btn.bind("<Enter>", lambda e: user_browse_btn.config(bg="#333333"))
                user_browse_btn.bind("<Leave>", lambda e: user_browse_btn.config(bg="#222222"))
            else:
                user_browse_btn.config(fg="#555555", bg="#1a1a1a")
                user_browse_btn.unbind("<Button-1>")
                user_browse_btn.unbind("<Enter>")
                user_browse_btn.unbind("<Leave>")
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
        tk.Radiobutton(pass_row, text="From inventory", variable=pass_src, value="inventory",
                       bg=BG, fg=MUTED, selectcolor=BG, font=fonts.view_font(10),
                       activebackground=BG, activeforeground=FG, highlightthickness=0).pack(side=tk.LEFT, padx=(0, 15))
        tk.Radiobutton(pass_row, text="From file", variable=pass_src, value="file",
                       bg=BG, fg=MUTED, selectcolor=BG, font=fonts.view_font(10),
                       activebackground=BG, activeforeground=FG, highlightthickness=0).pack(side=tk.LEFT)

        pass_browse_btn = tk.Label(pass_row, text="  Browse...  ", bg="#222222", fg=FG,
                                   font=fonts.view_font(10), relief=tk.RAISED, bd=1, padx=10, pady=4)
        pass_browse_btn.pack(side=tk.LEFT, padx=(10, 0))
        pass_browse_btn.bind("<Button-1>", lambda e: self._browse_file(pass_path))
        pass_browse_btn.bind("<Enter>", lambda e: pass_browse_btn.config(bg="#333333"))
        pass_browse_btn.bind("<Leave>", lambda e: pass_browse_btn.config(bg="#222222"))
        row += 1

        pass_path_label = tk.Label(tab, textvariable=pass_path, fg=BRIGHT, bg=BG,
                                   font=fonts.view_font(9), anchor="w", justify="left")
        pass_path_label.grid(row=row, column=1, sticky="ew", padx=15, pady=(0, 5))

        def _toggle_pass(*_):
            if pass_src.get() == "file":
                if not pass_path.get():
                    self._browse_file(pass_path)
                pass_browse_btn.config(fg=FG, bg="#222222")
                pass_browse_btn.bind("<Button-1>", lambda e: self._browse_file(pass_path))
                pass_browse_btn.bind("<Enter>", lambda e: pass_browse_btn.config(bg="#333333"))
                pass_browse_btn.bind("<Leave>", lambda e: pass_browse_btn.config(bg="#222222"))
            else:
                pass_browse_btn.config(fg="#555555", bg="#1a1a1a")
                pass_browse_btn.unbind("<Button-1>")
                pass_browse_btn.unbind("<Enter>")
                pass_browse_btn.unbind("<Leave>")
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
        from tkinter import filedialog
        initial = str(_lst_dir())
        f = filedialog.askopenfilename(
            parent=self, title="Select wordlist", initialdir=initial,
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
            self._start_btn.config(fg="#553333", bg="#1a1a1a", text="  xfreerdp required  ")
            self._start_btn.unbind("<Button-1>")
            self._start_btn.unbind("<Enter>")
            self._start_btn.unbind("<Leave>")
        else:
            self._start_btn.config(fg=FG, bg="#222222", text="  Start  ")
            self._start_btn.bind("<Button-1>", lambda e: self._start())
            self._start_btn.bind("<Enter>", lambda e: self._start_btn.config(bg="#333333"))
            self._start_btn.bind("<Leave>", lambda e: self._start_btn.config(bg="#222222"))

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
