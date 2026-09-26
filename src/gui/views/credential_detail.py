from src.gui import fonts, windowing
import tkinter as tk
from .base import BaseView
from src.machines import credential_db

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"


class _EditDialog(tk.Toplevel):
    def __init__(self, parent, cred):
        super().__init__(parent)
        self.result = None
        self._cred = cred

        self.title(f"Edit Credential #{cred['id']}")
        windowing.size_dialog(self, 500, 440)
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        for i in range(8):
            self.rowconfigure(i, weight=0)

        fields = [
            ("Username", "username"), ("Password", "password"),
            ("Pwd origin", "password_origin"),
            ("Domain", "domain"),
            ("Hash NT", "hash_nt"), ("Hash origin", "hash_nt_origin"),
        ]
        row = 0
        for label, key in fields:
            tk.Label(
                self, text=f"{label}:", font=fonts.view_font(11),
                fg=MUTED, bg="#111111",
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 0))
            var = tk.StringVar(value=cred.get(key, "") or "")
            if key == "password":
                var.trace_add("write", self._on_password_change)
            elif key == "hash_nt":
                var.trace_add("write", self._on_hash_change)
            tk.Entry(
                self, textvariable=var,
                bg="#000000", fg="#ffffff", insertbackground="#ffffff",
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 0))
            setattr(self, f"_{key}_var", var)
            row += 1

        self._feedback = tk.Label(
            self,             text="", font=fonts.view_font(11),
            fg=SUCCESS, bg="#111111",
        )
        self._feedback.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        row += 1

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(15, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        save_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        save_btn.pack(side=tk.RIGHT)
        save_btn.bind("<Button-1>", lambda e: self._save(cred["id"]))
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#333333"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _on_password_change(self, *args):
        if self._password_var.get() != self._cred.get("password", ""):
            self._password_origin_var.set("Edited by user")

    def _on_hash_change(self, *args):
        if self._hash_nt_var.get() != self._cred.get("hash_nt", ""):
            self._hash_nt_origin_var.set("Edited by user")

    def _save(self, cred_id):
        credential_db.update_credential(
            cred_id,
            self._username_var.get().strip(),
            self._password_var.get().strip(),
            self._domain_var.get().strip(),
            self._hash_nt_var.get().strip(),
            self._password_origin_var.get().strip(),
            self._hash_nt_origin_var.get().strip(),
        )
        self.result = True
        self._feedback.config(text="Saved.")
        self.after(800, self.destroy)


class CredentialDetailView(BaseView):
    name = "credential_detail"
    description = "Credential detail view"

    def __init__(self, parent, cred_id, **kwargs):
        self._cred_id = cred_id
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
        self._title_label.bind("<Enter>", lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind("<Leave>", lambda e: self._title_label.config(font=fonts.view_font_bold(22)))
        self._on_back_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=(220, 20), pady=(0, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT, cursor="",
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, pady=(0, 15))

        edit_btn = tk.Label(
            btn_frame, text="  Edit  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        edit_btn.pack(side=tk.LEFT, padx=(0, 10))
        edit_btn.bind("<Button-1>", lambda e: self._open_edit())
        edit_btn.bind("<Enter>", lambda e: edit_btn.config(bg="#333333"))
        edit_btn.bind("<Leave>", lambda e: edit_btn.config(bg="#222222"))

        back_btn = tk.Label(
            btn_frame, text="  \u2190 Back  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.LEFT)
        back_btn.bind("<Button-1>", lambda e: self._on_back_click and self._on_back_click())
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

    def on_activate(self):
        self._refresh()

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _open_edit(self):
        c = credential_db.load_credential(self._cred_id)
        if not c:
            return
        dialog = _EditDialog(self, c)
        if dialog.result:
            self._refresh()

    def _refresh(self):
        c = credential_db.load_credential(self._cred_id)
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not c:
            self._title_label.config(text="Credential — not found")
            self.text.insert(tk.END, "Credential not found.\n", "muted")
            self.text.configure(state=tk.DISABLED)
            return

        self._title_label.config(text=f"Credential #{c['id']}")

        rows = [
            ("ID", str(c.get("id", ""))),
            ("Username", c.get("username", "") or "-"),
            ("Password", c.get("password", "") or "-"),
            ("Pwd origin", c.get("password_origin", "") or "-"),
            ("Domain", c.get("domain", "") or "-"),
            ("Hash NT", c.get("hash_nt", "") or "-"),
            ("Hash origin", c.get("hash_nt_origin", "") or "-"),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value}\n", "bright")

        self.text.configure(state=tk.DISABLED)
