import os
import pty
import select
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
from src.gui import fonts, windowing
from src.shells import shell_db
from src.shells.ftp_shell import FTPConnectionThread
from src.shells.ssh_shell import SSHConnectionThread
from src.shells.sftp_shell import SFTPConnectionThread
from src.shells.winrm_shell import WinRMConnectionThread
from src.elwand_paths import logs_dir as _logs_dir

_DBG_FILE = os.path.join(_logs_dir(), "debugging_logs")
_DBG_LOCK = threading.Lock()


def _dbg(msg):
    line = f"{time.strftime('%H:%M:%S')}  {msg}\n"
    try:
        with _DBG_LOCK:
            os.makedirs(os.path.dirname(_DBG_FILE), exist_ok=True)
            with open(_DBG_FILE, "a") as f:
                f.write(line)
    except (PermissionError, OSError):
        pass


BG = "#111111"
FG = "#ffffff"
MUTED = "#888888"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"


class RemoteAccessDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Remote Access Call")
        windowing.size_dialog(self, 620, 520)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=(15, 5))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222", foreground=FG,
                        padding=[20, 6], font=fonts.view_font(10))
        style.map("TNotebook.Tab", background=[("selected", "#333333")])

        self._tab_ftp = tk.Frame(self._notebook, bg=BG)
        self._tab_ssh = tk.Frame(self._notebook, bg=BG)
        self._tab_winrm = tk.Frame(self._notebook, bg=BG)

        self._notebook.add(self._tab_ftp, text="FTP")
        self._notebook.add(self._tab_ssh, text="SSH")
        self._notebook.add(self._tab_winrm, text="WinRM")

        self._build_ftp_tab()
        self._build_ssh_tab()
        self._build_winrm_tab()
        self._build_buttons()

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _build_ftp_tab(self):
        tab = self._tab_ftp
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)

        tk.Label(
            tab, text="Protocol:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        self._ftp_proto = tk.StringVar(value="ftp")
        proto_frame = tk.Frame(tab, bg=BG)
        proto_frame.grid(row=0, column=1, sticky="w", padx=15, pady=(15, 5))
        ftp_rb = tk.Radiobutton(
            proto_frame, text="FTP", variable=self._ftp_proto, value="ftp",
            bg=BG, fg=FG, selectcolor=BG, font=fonts.view_font(10),
            activebackground=BG, activeforeground=FG, highlightthickness=0,
        )
        ftp_rb.pack(side=tk.LEFT, padx=(0, 15))
        sftp_rb = tk.Radiobutton(
            proto_frame, text="SFTP", variable=self._ftp_proto, value="sftp",
            bg=BG, fg=FG, selectcolor=BG, font=fonts.view_font(10),
            activebackground=BG, activeforeground=FG, highlightthickness=0,
        )
        sftp_rb.pack(side=tk.LEFT)

        tk.Label(
            tab, text="Machine:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=1, column=0, sticky="nw", padx=15, pady=(10, 0))

        mach_frame = tk.Frame(tab, bg="#000000")
        mach_frame.grid(row=1, column=1, sticky="nsew", padx=15, pady=(10, 0))
        mach_frame.columnconfigure(0, weight=1)
        mach_frame.rowconfigure(0, weight=1)

        self._machine_list = tk.Listbox(
            mach_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._machine_list.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(mach_frame, orient=tk.VERTICAL, command=self._machine_list.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._machine_list.configure(yscrollcommand=scrollbar.set)

        self._machine_keys = []
        self._populate_machines()

        self._machine_list.bind("<<ListboxSelect>>", self._on_machine_select)

        tk.Label(
            tab, text="Credential:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=2, column=0, sticky="nw", padx=15, pady=(10, 0))

        cred_frame = tk.Frame(tab, bg="#000000")
        cred_frame.grid(row=2, column=1, sticky="nsew", padx=15, pady=(10, 0))
        cred_frame.columnconfigure(0, weight=1)
        cred_frame.rowconfigure(0, weight=1)

        self._cred_list = tk.Listbox(
            cred_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._cred_list.grid(row=0, column=0, sticky="nsew")

        cred_scroll = tk.Scrollbar(cred_frame, orient=tk.VERTICAL, command=self._cred_list.yview)
        cred_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        cred_scroll.grid(row=0, column=1, sticky="ns")
        self._cred_list.configure(yscrollcommand=cred_scroll.set)

        self._cred_keys = []
        self._populate_creds()
        self._cred_list.bind("<<ListboxSelect>>", self._on_cred_select)

        fields = [
            ("Host:", "host", "hostname_or_ip"),
            ("Port:", "port", "22" if self._ftp_proto.get() == "sftp" else "21"),
            ("Username:", "user", "anonymous"),
            ("Password:", "pass", ""),
        ]
        row = 3
        self._ftp_vars = {}
        for label, key, default in fields:
            tk.Label(
                tab, text=label, font=fonts.view_font_bold(11),
                fg=MUTED, bg=BG,
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(8, 0))
            var = tk.StringVar(value=default)
            tk.Entry(
                tab, textvariable=var,
                bg="#000000", fg=FG, insertbackground=FG,
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 0))
            self._ftp_vars[key] = var
            row += 1

        self._ftp_feedback = tk.Label(
            tab, text="", font=fonts.view_font(11),
            fg=SUCCESS, bg=BG,
        )
        self._ftp_feedback.grid(row=row, column=0, columnspan=2, pady=(10, 0))

        def on_proto_change(*_):
            port_var = self._ftp_vars["port"]
            if self._ftp_proto.get() == "sftp" and port_var.get() in ("21", ""):
                port_var.set("22")
            elif self._ftp_proto.get() == "ftp" and port_var.get() in ("22", ""):
                port_var.set("21")
        self._ftp_proto.trace_add("write", on_proto_change)

    def _populate_machines(self):
        self._machine_list.delete(0, tk.END)
        self._machine_keys = []
        from src.machines import store
        for m in store.get_all_sorted():
            if m.ip in ("127.0.0.1", "::1") or m.ip.startswith("127."):
                continue
            hostname = m.hostname or ""
            label = f"{m.ip:<18}{hostname}"
            self._machine_list.insert(tk.END, f"  {label}")
            self._machine_keys.append(m.ip)

    def _on_machine_select(self, event):
        sel = self._machine_list.curselection()
        if sel and sel[0] < len(self._machine_keys):
            ip = self._machine_keys[sel[0]]
            self._ftp_vars["host"].set(ip)

    def _populate_creds(self):
        self._cred_list.delete(0, tk.END)
        self._cred_keys = []
        from src.machines import credential_db
        for c in credential_db.load_credentials():
            user = (c.get("username") or "").strip()
            pwd = (c.get("password") or "").strip()
            if not user or not pwd:
                continue
            domain = c.get("domain") or ""
            label = f"{user:<20}{'@' + domain if domain else ''}"
            self._cred_list.insert(tk.END, f"  {label}")
            self._cred_keys.append((user, pwd))

    def _on_cred_select(self, event):
        sel = self._cred_list.curselection()
        if sel and sel[0] < len(self._cred_keys):
            user, pwd = self._cred_keys[sel[0]]
            self._ftp_vars["user"].set(user)
            self._ftp_vars["pass"].set(pwd)

    def _populate_ssh_machines(self):
        self._ssh_machine_list.delete(0, tk.END)
        self._ssh_machine_keys = []
        from src.machines import store
        for m in store.get_all_sorted():
            if m.ip in ("127.0.0.1", "::1") or m.ip.startswith("127."):
                continue
            hostname = m.hostname or ""
            label = f"{m.ip:<18}{hostname}"
            self._ssh_machine_list.insert(tk.END, f"  {label}")
            self._ssh_machine_keys.append(m.ip)

    def _on_ssh_machine_select(self, event):
        sel = self._ssh_machine_list.curselection()
        if sel and sel[0] < len(self._ssh_machine_keys):
            ip = self._ssh_machine_keys[sel[0]]
            self._ssh_vars["host"].set(ip)

    def _populate_ssh_creds(self):
        self._ssh_cred_list.delete(0, tk.END)
        self._ssh_cred_keys = []
        from src.machines import credential_db
        for c in credential_db.load_credentials():
            user = (c.get("username") or "").strip()
            pwd = (c.get("password") or "").strip()
            if not user or not pwd:
                continue
            domain = c.get("domain") or ""
            label = f"{user:<20}{'@' + domain if domain else ''}"
            self._ssh_cred_list.insert(tk.END, f"  {label}")
            self._ssh_cred_keys.append((user, pwd))

    def _on_ssh_cred_select(self, event):
        sel = self._ssh_cred_list.curselection()
        if sel and sel[0] < len(self._ssh_cred_keys):
            user, pwd = self._ssh_cred_keys[sel[0]]
            self._ssh_vars["user"].set(user)
            self._ssh_vars["pass"].set(pwd)

    def _populate_winrm_machines(self):
        self._winrm_machine_list.delete(0, tk.END)
        self._winrm_machine_keys = []
        from src.machines import store
        for m in store.get_all_sorted():
            if m.ip in ("127.0.0.1", "::1") or m.ip.startswith("127."):
                continue
            hostname = m.hostname or ""
            label = f"{m.ip:<18}{hostname}"
            self._winrm_machine_list.insert(tk.END, f"  {label}")
            self._winrm_machine_keys.append(m.ip)

    def _on_winrm_machine_select(self, event):
        sel = self._winrm_machine_list.curselection()
        if sel and sel[0] < len(self._winrm_machine_keys):
            ip = self._winrm_machine_keys[sel[0]]
            self._winrm_vars["host"].set(ip)

    def _populate_winrm_creds(self):
        self._winrm_cred_list.delete(0, tk.END)
        self._winrm_cred_keys = []
        from src.machines import credential_db
        for c in credential_db.load_credentials():
            user = (c.get("username") or "").strip()
            pwd = (c.get("password") or "").strip()
            if not user or not pwd:
                continue
            domain = c.get("domain") or ""
            label = f"{user:<20}{'@' + domain if domain else ''}"
            self._winrm_cred_list.insert(tk.END, f"  {label}")
            self._winrm_cred_keys.append((user, pwd))

    def _on_winrm_cred_select(self, event):
        sel = self._winrm_cred_list.curselection()
        if sel and sel[0] < len(self._winrm_cred_keys):
            user, pwd = self._winrm_cred_keys[sel[0]]
            self._winrm_vars["user"].set(user)
            self._winrm_vars["pass"].set(pwd)

    def _build_ssh_tab(self):
        tab = self._tab_ssh
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)

        tk.Label(
            tab, text="Machine:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=0, column=0, sticky="nw", padx=15, pady=(15, 0))

        mach_frame = tk.Frame(tab, bg="#000000")
        mach_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=(15, 0))
        mach_frame.columnconfigure(0, weight=1)
        mach_frame.rowconfigure(0, weight=1)

        self._ssh_machine_list = tk.Listbox(
            mach_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._ssh_machine_list.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(mach_frame, orient=tk.VERTICAL, command=self._ssh_machine_list.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._ssh_machine_list.configure(yscrollcommand=scrollbar.set)

        self._ssh_machine_keys = []
        self._populate_ssh_machines()
        self._ssh_machine_list.bind("<<ListboxSelect>>", self._on_ssh_machine_select)

        tk.Label(
            tab, text="Credential:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=1, column=0, sticky="nw", padx=15, pady=(10, 0))

        cred_frame = tk.Frame(tab, bg="#000000")
        cred_frame.grid(row=1, column=1, sticky="nsew", padx=15, pady=(10, 0))
        cred_frame.columnconfigure(0, weight=1)
        cred_frame.rowconfigure(0, weight=1)

        self._ssh_cred_list = tk.Listbox(
            cred_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._ssh_cred_list.grid(row=0, column=0, sticky="nsew")

        cred_scroll = tk.Scrollbar(cred_frame, orient=tk.VERTICAL, command=self._ssh_cred_list.yview)
        cred_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        cred_scroll.grid(row=0, column=1, sticky="ns")
        self._ssh_cred_list.configure(yscrollcommand=cred_scroll.set)

        self._ssh_cred_keys = []
        self._populate_ssh_creds()
        self._ssh_cred_list.bind("<<ListboxSelect>>", self._on_ssh_cred_select)

        ssh_fields = [
            ("Host:", "host", "hostname_or_ip"),
            ("Port:", "port", "22"),
            ("Username:", "user", "root"),
            ("Password:", "pass", ""),
        ]
        row = 2
        self._ssh_vars = {}
        for label, key, default in ssh_fields:
            tk.Label(
                tab, text=label, font=fonts.view_font_bold(11),
                fg=MUTED, bg=BG,
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(8, 0))
            var = tk.StringVar(value=default)
            tk.Entry(
                tab, textvariable=var,
                bg="#000000", fg=FG, insertbackground=FG,
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 0))
            self._ssh_vars[key] = var
            row += 1

        self._ssh_feedback = tk.Label(
            tab, text="", font=fonts.view_font(11),
            fg=SUCCESS, bg=BG,
        )
        self._ssh_feedback.grid(row=row, column=0, columnspan=2, pady=(10, 0))

    def _build_winrm_tab(self):
        tab = self._tab_winrm
        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)

        tk.Label(
            tab, text="Machine:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=0, column=0, sticky="nw", padx=15, pady=(15, 0))

        mach_frame = tk.Frame(tab, bg="#000000")
        mach_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=(15, 0))
        mach_frame.columnconfigure(0, weight=1)
        mach_frame.rowconfigure(0, weight=1)

        self._winrm_machine_list = tk.Listbox(
            mach_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._winrm_machine_list.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(mach_frame, orient=tk.VERTICAL, command=self._winrm_machine_list.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._winrm_machine_list.configure(yscrollcommand=scrollbar.set)

        self._winrm_machine_keys = []
        self._populate_winrm_machines()
        self._winrm_machine_list.bind("<<ListboxSelect>>", self._on_winrm_machine_select)

        tk.Label(
            tab, text="Credential:", font=fonts.view_font_bold(11),
            fg=MUTED, bg=BG,
        ).grid(row=1, column=0, sticky="nw", padx=15, pady=(10, 0))

        cred_frame = tk.Frame(tab, bg="#000000")
        cred_frame.grid(row=1, column=1, sticky="nsew", padx=15, pady=(10, 0))
        cred_frame.columnconfigure(0, weight=1)
        cred_frame.rowconfigure(0, weight=1)

        self._winrm_cred_list = tk.Listbox(
            cred_frame, bg="#000000", fg=FG,
            selectbackground="#333333", selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._winrm_cred_list.grid(row=0, column=0, sticky="nsew")

        cred_scroll = tk.Scrollbar(cred_frame, orient=tk.VERTICAL, command=self._winrm_cred_list.yview)
        cred_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        cred_scroll.grid(row=0, column=1, sticky="ns")
        self._winrm_cred_list.configure(yscrollcommand=cred_scroll.set)

        self._winrm_cred_keys = []
        self._populate_winrm_creds()
        self._winrm_cred_list.bind("<<ListboxSelect>>", self._on_winrm_cred_select)

        winrm_fields = [
            ("Host:", "host", "hostname_or_ip"),
            ("Port:", "port", "5985"),
            ("Domain:", "domain", ""),
            ("Username:", "user", "Administrator"),
            ("Password:", "pass", ""),
        ]
        self._winrm_vars = {}
        for i, (label, key, default) in enumerate(winrm_fields):
            row = i + 2
            tk.Label(
                tab, text=label, font=fonts.view_font_bold(11),
                fg=MUTED, bg=BG,
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(8, 0))
            var = tk.StringVar(value=default)
            tk.Entry(
                tab, textvariable=var,
                bg="#000000", fg=FG, insertbackground=FG,
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 0))
            self._winrm_vars[key] = var

        self._winrm_feedback = tk.Label(
            tab, text="", font=fonts.view_font(11),
            fg=SUCCESS, bg=BG,
        )
        self._winrm_feedback.grid(row=len(winrm_fields) + 2, column=0, columnspan=2, pady=(10, 0))

    def _build_buttons(self):
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(5, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        self._connect_btn = tk.Label(
            btn_frame, text="  Connect  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        self._connect_btn.pack(side=tk.RIGHT)
        self._connect_btn.bind("<Button-1>", lambda e: self._on_connect())
        self._connect_btn.bind("<Enter>", lambda e: self._connect_btn.config(bg="#333333"))
        self._connect_btn.bind("<Leave>", lambda e: self._connect_btn.config(bg="#222222"))

    def _on_connect(self):
        tab = self._notebook.index(self._notebook.select())
        if tab == 0:
            self._connect_ftp()
        elif tab == 1:
            self._connect_ssh()
        elif tab == 2:
            self._connect_winrm()
        else:
            self._feedback_tab("Not implemented yet", ERR_COLOR)

    def _feedback_tab(self, text, color=SUCCESS):
        tab_idx = self._notebook.index(self._notebook.select())
        if tab_idx == 0:
            self._ftp_feedback.config(text=text, fg=color)
        elif tab_idx == 1:
            self._ssh_feedback.config(text=text, fg=color)
        elif tab_idx == 2:
            self._winrm_feedback.config(text=text, fg=color)

    def _connect_ftp(self):
        host = self._ftp_vars["host"].get().strip()
        port_str = self._ftp_vars["port"].get().strip()
        user = self._ftp_vars["user"].get().strip()
        password = self._ftp_vars["pass"].get().strip()
        proto = self._ftp_proto.get()

        if not host:
            self._feedback_tab("Host is required", ERR_COLOR)
            return
        try:
            port = int(port_str) if port_str else 0
        except ValueError:
            self._feedback_tab("Invalid port", ERR_COLOR)
            return

        if proto == "sftp":
            _dbg(f"[remote-access] sftp connecting to {host}:{port}")

            def on_connected(sid):
                _dbg(f"[remote-access] sftp session #{sid} created")
                self.after(0, self._on_connected)

            def on_error(msg):
                self.after(0, lambda: self._feedback_tab(f"{msg}", ERR_COLOR))
                self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

            sftp_thread = SFTPConnectionThread(
                host, port, user, password,
                on_connected=on_connected,
                on_error=on_error,
            )
            sftp_thread.start()
            return

        self._connect_btn.config(text="Connecting...", fg=MUTED)
        self._feedback_tab(f"Connecting {proto.upper()} to {host}:{port}...", SUCCESS)
        threading.Thread(
            target=self._run_pty_connect,
            args=(proto, host, port, user, password),
            daemon=True,
        ).start()

    def _connect_ssh(self):
        host = self._ssh_vars["host"].get().strip()
        port_str = self._ssh_vars["port"].get().strip()
        user = self._ssh_vars["user"].get().strip()
        password = self._ssh_vars["pass"].get().strip()

        if not host:
            self._feedback_tab("Host is required", ERR_COLOR)
            return
        if not user:
            self._feedback_tab("Username is required", ERR_COLOR)
            return
        try:
            port = int(port_str) if port_str else 22
        except ValueError:
            self._feedback_tab("Invalid port", ERR_COLOR)
            return

        self._connect_btn.config(text="Connecting...", fg=MUTED)
        self._feedback_tab(f"Connecting SSH to {host}:{port}...", SUCCESS)
        threading.Thread(
            target=self._run_ssh_connect,
            args=(host, port, user, password),
            daemon=True,
        ).start()

    def _run_ssh_connect(self, host, port, user, password):
        try:
            def on_connected(sid):
                _dbg(f"[remote-access] ssh session #{sid} to {host}:{port}")
                self.after(0, self._on_connected)

            def on_error(msg):
                self.after(0, lambda: self._feedback_tab(f"{msg}", ERR_COLOR))
                self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

            ssh_thread = SSHConnectionThread(
                host, port, user, password,
                on_connected=on_connected,
                on_error=on_error,
            )
            ssh_thread.start()
        except Exception as e:
            _dbg(f"[remote-access] ssh start error: {e}")
            self.after(0, lambda: self._feedback_tab(f"Connection failed: {e}", ERR_COLOR))
            self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

    def _connect_winrm(self):
        host = self._winrm_vars["host"].get().strip()
        port_str = self._winrm_vars["port"].get().strip()
        domain = self._winrm_vars["domain"].get().strip()
        user = self._winrm_vars["user"].get().strip()
        password = self._winrm_vars["pass"].get().strip()

        if not host:
            self._feedback_tab("Host is required", ERR_COLOR)
            return
        if not user:
            self._feedback_tab("Username is required", ERR_COLOR)
            return
        try:
            port = int(port_str) if port_str else 5985
        except ValueError:
            self._feedback_tab("Invalid port", ERR_COLOR)
            return

        self._connect_btn.config(text="Connecting...", fg=MUTED)
        self._feedback_tab(f"Connecting WinRM to {host}:{port}...", SUCCESS)
        threading.Thread(
            target=self._run_winrm_connect,
            args=(host, port, user, password, domain),
            daemon=True,
        ).start()

    def _run_winrm_connect(self, host, port, user, password, domain):
        try:
            def on_connected(sid):
                _dbg(f"[remote-access] winrm session #{sid} to {host}:{port}")
                self.after(0, self._on_connected)

            def on_error(msg):
                self.after(0, lambda: self._feedback_tab(f"{msg}", ERR_COLOR))
                self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

            winrm_thread = WinRMConnectionThread(
                host, port, user, password, domain,
                on_connected=on_connected,
                on_error=on_error,
            )
            winrm_thread.start()
        except Exception as e:
            _dbg(f"[remote-access] winrm start error: {e}")
            self.after(0, lambda: self._feedback_tab(f"Connection failed: {e}", ERR_COLOR))
            self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

    def _run_pty_connect(self, proto, host, port, user, password):
        try:
            if proto == "ftp":
                _dbg(f"[remote-access] ftp connecting to {host}:{port}")

                def on_connected(sid):
                    _dbg(f"[remote-access] ftp session #{sid} created")
                    self.after(0, self._on_connected)

                def on_error(msg):
                    self.after(0, lambda: self._feedback_tab(f"{msg}", ERR_COLOR))
                    self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

                ftp_thread = FTPConnectionThread(
                    host, port, user, password,
                    on_connected=on_connected,
                    on_error=on_error,
                )
                ftp_thread.start()
                return

            target = f"{user}@{host}" if user else host
            cmd_parts = ["sftp", "-o", "StrictHostKeyChecking=no"]
            if port and port != 22:
                cmd_parts.append(f"-oPort={port}")
            cmd_parts.append(target)

            _dbg(f"[remote-access] pty spawning: {' '.join(cmd_parts)}")

            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                cmd_parts,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
            os.close(slave_fd)

            session = shell_db.add_session(host, port, 0)
            session["type"] = "SFTP"
            session["pty_fd"] = master_fd
            session["pid"] = proc.pid
            from src.gui.views.shell_list import enable_default_agent_access
            enable_default_agent_access(session["id"])
            _dbg(f"[remote-access] sftp session #{session['id']} pty_fd={master_fd}")

            t = threading.Thread(
                target=self._read_pty,
                args=(session["id"], master_fd, proc.pid),
                daemon=True,
            )
            t.start()

            self.after(0, self._on_connected)

        except Exception as e:
            _dbg(f"[remote-access] connect error: {e}")
            self.after(0, lambda: self._feedback_tab(f"Connection failed: {e}", ERR_COLOR))
            self.after(0, lambda: self._connect_btn.config(text="Connect", fg=FG))

    def _read_pty(self, sid, master_fd, pid):
        _dbg(f"[remote-access] pty reader #{sid} started")
        try:
            while True:
                r, _, _ = select.select([master_fd], [], [], 1.0)
                if r:
                    data = os.read(master_fd, 4096)
                    if not data:
                        _dbg(f"[remote-access] pty reader #{sid} EOF")
                        break
                    text = data.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n")
                    _dbg(f"[remote-access] pty reader #{sid} got {len(text)} chars")
                    shell_db.append_output(sid, text)
                wpid, status = os.waitpid(pid, os.WNOHANG)
                if wpid != 0:
                    _dbg(f"[remote-access] pty reader #{sid} process exited status={status}")
                    try:
                        while True:
                            r, _, _ = select.select([master_fd], [], [], 0.1)
                            if not r:
                                break
                            data = os.read(master_fd, 4096)
                            if not data:
                                break
                            text = data.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n")
                            _dbg(f"[remote-access] pty reader #{sid} drain {len(text)} chars")
                            shell_db.append_output(sid, text)
                    except Exception:
                        pass
                    break
        except Exception as e:
            _dbg(f"[remote-access] pty reader #{sid} error: {e}")
        finally:
            _dbg(f"[remote-access] pty reader #{sid} stopped")
            shell_db.set_status(sid, "disconnected")
            try:
                os.close(master_fd)
            except Exception:
                pass

    def _on_connected(self):
        self._feedback_tab("Connected", SUCCESS)
        self._connect_btn.config(text="Connect", fg=FG)
        self.after(1000, self.destroy)
