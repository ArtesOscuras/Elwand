from src.gui import fonts, windowing
import struct
import tkinter as tk
from .base import BaseView
from .nav import build as build_nav
from src.machines import credential_db

BRIGHT = "#ffffff"
INFO = "#5ba3ec"
MUTED = "#888888"


def _ntlm_hash(password):
    if not password:
        return ""
    data = password.encode("utf-16-le")

    def _left_rotate(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    def _md4(msg):
        A = 0x67452301
        B = 0xEFCDAB89
        C = 0x98BADCFE
        D = 0x10325476

        padded = msg + b"\x80"
        while (len(padded) % 64) != 56:
            padded += b"\x00"
        padded += struct.pack("<Q", len(msg) * 8)

        for i in range(0, len(padded), 64):
            X = list(struct.unpack("<16I", padded[i:i+64]))
            AA, BB, CC, DD = A, B, C, D

            for rnd, (order, shifts, constant, func) in enumerate([
                ([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
                 [3,7,11,19,3,7,11,19,3,7,11,19,3,7,11,19],
                 0, lambda b,c,d: (b & c) | ((~b) & d)),
                ([0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15],
                 [3,5,9,13,3,5,9,13,3,5,9,13,3,5,9,13],
                 0x5A827999, lambda b,c,d: (b & c) | (b & d) | (c & d)),
                ([0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15],
                 [3,9,11,15,3,9,11,15,3,9,11,15,3,9,11,15],
                 0x6ED9EBA1, lambda b,c,d: b ^ c ^ d),
            ]):
                for j in range(16):
                    k = order[j]
                    s = shifts[j]
                    F = func(B, C, D)
                    a_new = _left_rotate((A + F + X[k] + constant) & 0xFFFFFFFF, s)
                    A, B, C, D = D, a_new, B, C

            A = (A + AA) & 0xFFFFFFFF
            B = (B + BB) & 0xFFFFFFFF
            C = (C + CC) & 0xFFFFFFFF
            D = (D + DD) & 0xFFFFFFFF

        return struct.pack("<4I", A, B, C, D).hex()

    return _md4(data)


class UserPassView(BaseView):
    name = "user-pass"
    description = "Users and passwords"

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "credentials", self.master)

        self._title_label = tk.Label(
            header, text="Users & Passwords",
            font=fonts.view_font_bold(22), fg="#ffffff", bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", lambda e: self.master.activate_view("credentials"))
        self._title_label.bind("<Enter>", lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind("<Leave>", lambda e: self._title_label.config(font=fonts.view_font_bold(22)))

        content = tk.Frame(self, bg="#000000")
        content.grid(row=1, column=0, sticky="nsew", padx=(300, 300))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=0)
        content.rowconfigure(1, weight=0)
        content.rowconfigure(2, weight=1)

        tk.Label(
            content, text="Users",
            font=fonts.view_font_bold(14), fg=BRIGHT, bg="#000000",
        ).grid(row=0, column=0, pady=(10, 5))

        tk.Label(
            content, text="Passwords",
            font=fonts.view_font_bold(14), fg=BRIGHT, bg="#000000",
        ).grid(row=0, column=1, pady=(10, 5))

        self._users_text = self._build_editor(content, 1, 0)
        self._pwds_text = self._build_editor(content, 1, 1)

        self._last_users = None
        self._last_pwds = None
        self._loaded = False
        self._poll_id = None

        btn_frame2 = tk.Frame(self, bg="#000000")
        btn_frame2.grid(row=2, column=0, pady=(10, 15))

        gen_btn = tk.Label(
            btn_frame2,
            text="  Generate credentials  ",
            bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10),
            relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        gen_btn.pack(side=tk.LEFT, padx=(0, 10))

        back_btn = tk.Label(
            btn_frame2, text="  \u2190 Back  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.LEFT)

        gen_btn.bind("<Button-1>", lambda e: self._open_generator())
        gen_btn.bind("<Enter>", lambda e: gen_btn.config(bg="#333333"))
        gen_btn.bind("<Leave>", lambda e: gen_btn.config(bg="#222222"))
        back_btn.bind("<Button-1>", lambda e: self.master.activate_view("credentials"))
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

    def _build_editor(self, parent, row, col):
        text_frame = tk.Frame(parent, bg="#000000")
        text_frame.grid(row=row, column=col, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        text = tk.Text(
            text_frame, bg="#111111", fg=BRIGHT,
            font=fonts.view_font(13), borderwidth=1,
            relief=tk.FLAT, pady=5, cursor="xterm",
            wrap=tk.NONE, height=12,
            highlightthickness=1,
            highlightcolor="#333333", highlightbackground="#333333",
            insertbackground=BRIGHT,
        )
        text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)

        return text

    def on_activate(self):
        self._loaded = False
        self.after(100, self._poll)

    def on_deactivate(self):
        self._sync_all()
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self):
        if not self._loaded:
            self._load_from_db()
            self._loaded = True
        else:
            self._sync_all()
        self._poll_id = self.after(2000, self._poll)

    def _load_from_db(self):
        users = credential_db.load_users()
        pwds = credential_db.load_passwords()

        self._users_text.delete("1.0", tk.END)
        for u in users:
            self._users_text.insert(tk.END, f"{u}\n")

        self._pwds_text.delete("1.0", tk.END)
        for p in pwds:
            self._pwds_text.insert(tk.END, f"{p}\n")

        self._last_users = users
        self._last_pwds = pwds

    def _sync_all(self):
        self._sync_text(self._users_text, self._last_users,
                        credential_db.delete_user, credential_db.save_user)
        self._sync_text(self._pwds_text, self._last_pwds,
                        credential_db.delete_password, credential_db.save_password)

    def _sync_text(self, text_widget, last_items, delete_fn, save_fn):
        content = text_widget.get("1.0", "end-1c")
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if lines == (last_items or []):
            return

        for old in (last_items or []):
            delete_fn(old)
        for item in lines:
            save_fn(item)

        if text_widget is self._users_text:
            self._last_users = lines
        else:
            self._last_pwds = lines

    def _open_generator(self):
        _CredentialGenerator(self, on_created=self._on_cred_created)


class _CredentialGenerator(tk.Toplevel):
    def __init__(self, parent, on_created=None):
        super().__init__(parent)
        self.result = None
        self._on_created = on_created

        self.title("Generate Credentials")
        windowing.size_dialog(self, 600, 500)
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)
        self.rowconfigure(4, weight=0)
        self.rowconfigure(5, weight=0)

        tk.Label(
            self,             text="Users", font=fonts.view_font_bold(14),
            fg=INFO, bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        tk.Label(
            self,             text="Passwords", font=fonts.view_font_bold(14),
            fg=INFO, bg="#111111",
        ).grid(row=0, column=1, sticky="w", padx=15, pady=(15, 5))

        self._user_listbox = self._build_listbox(self, 1, 0)
        self._pwd_listbox = self._build_listbox(self, 1, 1)

        users = credential_db.load_users()
        pwds = credential_db.load_passwords()
        self._users_data = {}
        for u in users:
            name = u["username"]
            self._user_listbox.insert(tk.END, f"  {name}")
            self._users_data[name] = u
        for p in pwds:
            self._pwd_listbox.insert(tk.END, f"  {p}")
        if users:
            self._user_listbox.selection_set(0)

        self._sel_user = users[0]["username"] if users else None
        self._sel_pwd = None

        self._user_listbox.bind("<<ListboxSelect>>", self._on_user_select)
        self._pwd_listbox.bind("<<ListboxSelect>>", self._on_pwd_select)

        self.bind("<Button-1>", self._on_dialog_click)

        domain_frame = tk.Frame(self, bg="#111111")
        domain_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(15, 0))
        tk.Label(
            domain_frame, text="Domain", font=fonts.view_font_bold(11),
            fg=INFO, bg="#111111",
        ).pack(anchor="w")
        self._domain_var = tk.StringVar()
        tk.Entry(
            domain_frame, textvariable=self._domain_var,
            bg="#000000", fg="#ffffff", insertbackground="#ffffff",
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).pack(fill=tk.X)

        hash_frame = tk.Frame(self, bg="#111111")
        hash_frame.grid(row=2, column=1, sticky="ew", padx=15, pady=(15, 0))
        tk.Label(
            hash_frame, text="Hash NT", font=fonts.view_font_bold(11),
            fg=INFO, bg="#111111",
        ).pack(anchor="w")
        self._hash_var = tk.StringVar()
        tk.Entry(
            hash_frame, textvariable=self._hash_var,
            bg="#000000", fg="#ffffff", insertbackground="#ffffff",
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).pack(fill=tk.X)
        self._auto_hash_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            hash_frame, text="  Auto NTLM",
            variable=self._auto_hash_var,
            bg="#111111", fg=MUTED, selectcolor="#111111",
            font=fonts.view_font(10),
            activebackground="#111111", activeforeground=MUTED,
        ).pack(anchor="w", pady=(5, 0))

        self._feedback_label = tk.Label(
            self,             text="", font=fonts.view_font(11),
            fg="#00cc66", bg="#111111",
        )
        self._feedback_label.grid(row=3, column=0, columnspan=2, pady=(10, 0))

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(15, 15))

        cancel_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.bind("<Button-1>", lambda e: self.destroy())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#333333"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg="#222222"))

        add_btn = tk.Label(
            btn_frame, text="  Add  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.RIGHT)
        add_btn.bind("<Button-1>", lambda e: self._select())
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

        self._user_listbox.bind("<Return>", lambda e: self._select())
        self._pwd_listbox.bind("<Return>", lambda e: self._select())

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _build_listbox(self, parent, row, col):
        frame = tk.Frame(parent, bg="#000000")
        frame.grid(row=row, column=col, sticky="nsew", padx=15, pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        lb = tk.Listbox(
            frame, bg="#000000", fg="#ffffff",
            selectbackground="#333333", selectforeground="#ffffff",
            font=fonts.view_font(12), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False,
        )
        lb.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=lb.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        lb.configure(yscrollcommand=scrollbar.set)

        return lb

    def _on_user_select(self, event):
        idx = self._user_listbox.curselection()
        if idx:
            self._sel_user = self._user_listbox.get(idx[0]).strip()
            u = self._users_data.get(self._sel_user)
            if u:
                self._domain_var.set(u.get("domain", ""))

    def _on_pwd_select(self, event):
        idx = self._pwd_listbox.curselection()
        if idx:
            pwd = self._pwd_listbox.get(idx[0]).strip()
            self._sel_pwd = pwd
            if self._auto_hash_var.get():
                self._hash_var.set(_ntlm_hash(pwd))

    def _on_dialog_click(self, event):
        w = event.widget
        if w != self._pwd_listbox:
            self._pwd_listbox.selection_clear(0, tk.END)
            self._sel_pwd = None

    def _select(self):
        if not self._sel_user:
            return

        pwd = self._sel_pwd or ""
        hnt = self._hash_var.get().strip()
        credential_db.save_credential(
            self._sel_user,
            pwd,
            self._domain_var.get().strip(),
            hnt,
            "Generated by user" if pwd else "",
            "Generated by user" if hnt else "",
        )

        self.result = {
            "user": self._sel_user,
            "password": pwd,
        }

        if self._on_created:
            self._on_created(self._sel_user, pwd)

        self._feedback_label.config(text="Done.")
        self.after(1500, lambda: self._feedback_label.config(text=""))
