import tkinter as tk
from src.gui import fonts
from src.machines import credential_db
from .base import BaseView
from .nav import build as build_nav

MUTED = "#888888"
BRIGHT = "#ffffff"


class PasswordsView(BaseView):
    name = "passwords"
    description = "Manage passwords"

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "passwords", self.master)

        self._title_label = tk.Label(
            header, text="Passwords",
            font=fonts.view_font_bold(22), fg=BRIGHT, bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind(
            "<Button-1>",
            lambda e: self.master.activate_view("inventory"))
        self._title_label.bind(
            "<Enter>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold(22)))

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew",
                        padx=(300, 300), pady=(0, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame, bg="#111111", fg=BRIGHT,
            font=fonts.view_font(13), borderwidth=1,
            relief=tk.FLAT, pady=10, padx=15,
            cursor="xterm", wrap=tk.NONE,
            highlightthickness=1,
            highlightcolor="#333333", highlightbackground="#333333",
            insertbackground=BRIGHT,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.bind("<Return>", self._on_return)

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, pady=(10, 15))

        back_btn = tk.Label(
            btn_frame, text="  \u2190 Back  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.LEFT)
        back_btn.bind("<Button-1>",
                      lambda e: self.master.activate_view("inventory"))
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

        self._last_items = set()
        self._poll_id = None

    def on_activate(self):
        self._load_from_db()
        self._poll_id = self.after(2000, self._poll)

    def on_deactivate(self):
        self._sync()
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self):
        self._sync()
        self._poll_id = self.after(2000, self._poll)

    def _load_from_db(self):
        items = credential_db.load_passwords()
        self.text.delete("1.0", tk.END)
        for p in items:
            self.text.insert(tk.END, f"{p}\n")
        self._last_items = set(items)

    def _on_return(self, event):
        cursor = self.text.index(tk.INSERT)
        line_num = int(cursor.split('.')[0])
        line = self.text.get(f"{line_num}.0", f"{line_num}.end").rstrip("\n\r")
        if line:
            credential_db.save_password(line)
        self.text.insert(tk.INSERT, "\n")
        return "break"

    def _sync(self):
        content = self.text.get("1.0", "end-1c")
        text_lines = set(l.rstrip("\n\r") for l in content.split("\n") if l.strip())
        db_items = set(credential_db.load_passwords())

        # A) User added → save to DB
        for item in text_lines - db_items:
            credential_db.save_password(item)

        # B) User deleted → remove from DB
        for old in self._last_items - text_lines:
            credential_db.delete_password(old)

        # C) Agent added → insert at end of Text
        for item in db_items - text_lines - self._last_items:
            self.text.insert(tk.END, f"{item}\n")

        # D) Agent deleted → remove line from Text
        if self._last_items - db_items:
            cur = self.text.get("1.0", "end-1c").split("\n")
            for old in self._last_items - db_items:
                for i, line in enumerate(cur):
                    if line.rstrip("\n\r") == old:
                        self.text.delete(f"{i+1}.0", f"{i+2}.0")
                        break

        self._last_items = set(credential_db.load_passwords())
