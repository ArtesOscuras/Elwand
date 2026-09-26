import tkinter as tk
from src.gui import fonts, windowing
from src.machines import credential_db
from .base import BaseView

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"


class _UserEditDialog(tk.Toplevel):
    def __init__(self, parent, u):
        super().__init__(parent)
        self._username = u["username"]
        self.title(f"Edit User \u2014 {self._username}")
        windowing.size_dialog(self, 450, 340)
        self.configure(bg="#111111")
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._utype_var = tk.StringVar(value=u.get("type", "local") or "local")
        self._origin_var = tk.StringVar(value=u.get("origin", ""))
        self._machine_var = tk.StringVar(value=u.get("machine", ""))
        self._domain_var = tk.StringVar(value=u.get("domain", ""))
        self._groups_var = tk.StringVar(value=u.get("groups", ""))

        row = 0

        tk.Label(
            self, text="Username:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 3))
        tk.Label(
            self, text=self._username, font=fonts.view_font_bold(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=1, sticky="w", padx=15, pady=(10, 3))
        row += 1

        tk.Label(
            self, text="Type:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))

        type_frame = tk.Frame(self, bg="#111111")
        type_frame.grid(row=row, column=1, sticky="w", padx=15, pady=(5, 3))

        local_rb = tk.Radiobutton(
            type_frame, text="  Local  ", variable=self._utype_var,
            value="local", bg="#222222", fg=MUTED, selectcolor="#111111",
            font=fonts.view_font(11), indicatoron=False, relief=tk.FLAT,
            padx=10, pady=4,
            activebackground="#333333", activeforeground=BRIGHT,
            command=self._on_type_changed,
        )
        local_rb.pack(side=tk.LEFT)
        local_rb.bind("<Enter>", lambda e, b=local_rb: b.config(
            bg="#444444" if self._utype_var.get() == "local" else "#333333"))
        local_rb.bind("<Leave>", lambda e, b=local_rb: b.config(
            bg="#333333" if self._utype_var.get() == "local" else "#222222"))

        domain_rb = tk.Radiobutton(
            type_frame, text="  Domain  ", variable=self._utype_var,
            value="domain", bg="#222222", fg=MUTED, selectcolor="#111111",
            font=fonts.view_font(11), indicatoron=False, relief=tk.FLAT,
            padx=10, pady=4,
            activebackground="#333333", activeforeground=BRIGHT,
            command=self._on_type_changed,
        )
        domain_rb.pack(side=tk.LEFT, padx=(8, 0))
        domain_rb.bind("<Enter>", lambda e, b=domain_rb: b.config(
            bg="#444444" if self._utype_var.get() == "domain" else "#333333"))
        domain_rb.bind("<Leave>", lambda e, b=domain_rb: b.config(
            bg="#333333" if self._utype_var.get() == "domain" else "#222222"))

        self._local_rb = local_rb
        self._domain_rb = domain_rb
        self._update_rb_styles()
        row += 1

        tk.Label(
            self, text="Machine:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
        self._machine_entry = tk.Entry(
            self, textvariable=self._machine_var, bg="#000000", fg=BRIGHT,
            insertbackground=BRIGHT, font=fonts.view_font(11),
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333",
        )
        self._machine_entry.grid(row=row, column=1, sticky="ew", padx=15,
                                 pady=(5, 3))
        row += 1

        tk.Label(
            self, text="Domain:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
        self._domain_entry = tk.Entry(
            self, textvariable=self._domain_var, bg="#000000", fg=BRIGHT,
            insertbackground=BRIGHT, font=fonts.view_font(11),
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333",
        )
        self._domain_entry.grid(row=row, column=1, sticky="ew", padx=15,
                                pady=(5, 3))
        row += 1

        tk.Label(
            self, text="Origin:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
        tk.Entry(
            self, textvariable=self._origin_var, bg="#000000", fg=BRIGHT,
            insertbackground=BRIGHT, font=fonts.view_font(11),
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333",
        ).grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))
        row += 1

        tk.Label(
            self, text="Groups:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 3))
        tk.Entry(
            self, textvariable=self._groups_var, bg="#000000", fg=BRIGHT,
            insertbackground=BRIGHT, font=fonts.view_font(11),
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333",
        ).grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 3))
        row += 1

        self._feedback = tk.Label(
            self, text="", font=fonts.view_font(10),
            fg=SUCCESS, bg="#111111",
        )
        self._feedback.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        row += 1

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(15, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        update_btn = tk.Label(
            btn_frame, text="  Update  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        update_btn.pack(side=tk.RIGHT)
        update_btn.bind("<Button-1>", lambda e: self._save())
        update_btn.bind("<Enter>", lambda e: update_btn.config(bg="#333333"))
        update_btn.bind("<Leave>", lambda e: update_btn.config(bg="#222222"))

        self._on_type_changed()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        from .users import _add_autocomplete

        def _machines():
            from src.machines import store
            machines = store.get_all()
            if not machines:
                store.load()
                machines = store.get_all()
            return [m.ip for m in machines if m.ip]

        def _domains():
            from src.machines import domain_db
            return domain_db.list_all()

        _add_autocomplete(self._machine_entry, self._machine_var, _machines)
        _add_autocomplete(self._domain_entry, self._domain_var, _domains)

    def _on_type_changed(self):
        utype = self._utype_var.get()
        if utype == "domain":
            self._machine_entry.config(state=tk.DISABLED)
            self._domain_entry.config(state=tk.NORMAL)
        else:
            self._machine_entry.config(state=tk.NORMAL)
            self._domain_entry.config(state=tk.DISABLED)
        self._update_rb_styles()

    def _update_rb_styles(self):
        utype = self._utype_var.get()
        self._local_rb.config(
            fg=BRIGHT if utype == "local" else MUTED,
            bg="#333333" if utype == "local" else "#222222")
        self._domain_rb.config(
            fg=BRIGHT if utype == "domain" else MUTED,
            bg="#333333" if utype == "domain" else "#222222")

    def _save(self):
        utype = self._utype_var.get()
        credential_db.update_user(
            username=self._username,
            origin=self._origin_var.get().strip(),
            utype=utype,
            machine=self._machine_var.get().strip() if utype == "local" else "",
            domain=self._domain_var.get().strip() if utype == "domain" else "",
            groups=self._groups_var.get().strip(),
        )
        self._feedback.config(text="Updated.")
        self.after(800, self.destroy)


class UserDetailView(BaseView):
    name = "user_detail"
    description = "User detail view"

    def __init__(self, parent, username, **kwargs):
        self._username = username
        super().__init__(parent, **kwargs)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 10))

        self._title_label = tk.Label(
            header, text="",
            font=fonts.view_font_bold(22),
            fg="#ffffff", bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind(
            "<Enter>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold(22)))
        self._on_back_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew",
                        padx=(220, 20), pady=(0, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT, cursor="",
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))

        inner = tk.Frame(btn_frame, bg="#000000")
        inner.pack(anchor="center")

        edit_btn = tk.Label(
            inner, text="  Edit  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        edit_btn.pack(side=tk.LEFT, padx=(0, 10))
        edit_btn.bind("<Button-1>", lambda e: self._open_edit())
        edit_btn.bind("<Enter>", lambda e: edit_btn.config(bg="#333333"))
        edit_btn.bind("<Leave>", lambda e: edit_btn.config(bg="#222222"))

        back_btn = tk.Label(
            inner, text="  \u2190 Back  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.LEFT)
        back_btn.bind("<Button-1>",
                      lambda e: self._on_back_click
                      and self._on_back_click())
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

    def on_activate(self):
        self._refresh()

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _open_edit(self):
        items = credential_db.load_users()
        u = None
        for item in items:
            if item["username"] == self._username:
                u = item
                break
        if not u:
            return
        _UserEditDialog(self, u)
        self._refresh()

    def _refresh(self):
        items = credential_db.load_users()
        u = None
        for item in items:
            if item["username"] == self._username:
                u = item
                break

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not u:
            self._title_label.config(text="User — not found")
            self.text.insert(tk.END, "User not found.\n", "muted")
            self.text.configure(state=tk.DISABLED)
            return

        self._title_label.config(text=u["username"])

        utype = u.get("type", "") or "-"
        machine = u.get("machine", "") or "-"
        domain = u.get("domain", "") or "-"
        origin = u.get("origin", "") or "-"
        groups = u.get("groups", "") or "-"

        rows = [
            ("Username", u.get("username", "") or "-"),
            ("Type", utype),
            ("Machine", machine),
            ("Domain", domain),
            ("Origin", origin),
            ("Groups", groups),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END,
                             f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value}\n", "bright")

        self.text.configure(state=tk.DISABLED)
