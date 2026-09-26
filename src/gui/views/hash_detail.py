from src.gui import fonts, windowing
import os
import sqlite3
import tkinter as tk
from .base import BaseView
from src.machines import credential_db

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"


class _HashEditDialog(tk.Toplevel):
    def __init__(self, parent, h):
        super().__init__(parent)
        self._h = h
        self.result = None

        self.title(f"Edit Hash #{h['id']}")
        windowing.size_dialog(self, 780, 560)
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        tk.Label(
            self, text="Type",             font=fonts.view_font_bold(11),
            fg=MUTED, bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        type_frame = tk.Frame(self, bg="#000000")
        type_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 5))
        type_frame.columnconfigure(0, weight=1)
        type_frame.rowconfigure(0, weight=1)

        self._type_list = tk.Listbox(
            type_frame, bg="#000000", fg="#ffffff",
            selectbackground="#333333", selectforeground="#ffffff",
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=6,
        )
        self._type_list.grid(row=0, column=0, sticky="nsew")
        self._type_list.bind("<<ListboxSelect>>", self._on_type_select)

        scrollbar = tk.Scrollbar(type_frame, orient=tk.VERTICAL, command=self._type_list.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._type_list.configure(yscrollcommand=scrollbar.set)

        self._type_names = []
        self._type_modes = {}
        self._type_examples = {}
        try:
            db_path = str(_hashcat_db())
            if os.path.isfile(db_path):
                conn = sqlite3.connect(db_path)
                rows = conn.execute('SELECT "Hash-Mode", "Hash-Name", "Example" FROM DefaultMode ORDER BY "Hash-Mode"').fetchall()
                for mode, name, example in rows:
                    self._type_list.insert(tk.END, f"  {name}")
                    self._type_names.append(name)
                    self._type_modes[name] = str(mode) if mode != -1 else ""
                    self._type_examples[name] = example
                conn.close()
        except Exception:
            pass

        self._sel_type = h.get("type", "") or ""
        if self._sel_type in self._type_names:
            idx = self._type_names.index(self._sel_type)
            self._type_list.selection_set(idx)
            self._type_list.see(idx)

        self._example_label = tk.Label(
            self,             text="", font=fonts.view_font(9),
            fg=MUTED, bg="#111111", wraplength=600,
        )
        self._example_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=15, pady=(2, 5))

        fields = [
            ("Hash", "hash", h.get("hash", "")),
            ("Salt", "salt", h.get("salt", "")),
            ("Peper", "peper", h.get("peper", "")),
            ("Hashcat mode", "hascat_mode", h.get("hascat_mode", "")),
            ("Origin", "origin_obteined", h.get("origin_obteined", "")),
        ]

        row = 3
        for label, key, default in fields:
            tk.Label(
                self, text=f"{label}:", font=fonts.view_font(11),
                fg=MUTED, bg="#111111",
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 0))
            var = tk.StringVar(value=default)
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

        update_btn = tk.Label(
            btn_frame, text="  Update  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        update_btn.pack(side=tk.RIGHT)
        update_btn.bind("<Button-1>", lambda e: self._save())
        update_btn.bind("<Enter>", lambda e: update_btn.config(bg="#333333"))
        update_btn.bind("<Leave>", lambda e: update_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _on_type_select(self, event):
        idx = self._type_list.curselection()
        if idx and idx[0] < len(self._type_names):
            name = self._type_names[idx[0]]
            self._sel_type = name
            self._hascat_mode_var.set(self._type_modes.get(name, ""))

    def _save(self):
        if not self._sel_type:
            return
        credential_db.delete_hash_entry(self._h["id"])
        credential_db.save_hash_entry(
            self._sel_type,
            self._hash_var.get().strip(),
            self._salt_var.get().strip(),
            self._peper_var.get().strip(),
            self._hascat_mode_var.get().strip(),
            self._origin_obteined_var.get().strip(),
        )
        self._feedback.config(text="Updated.")
        self.result = True
        self.after(800, self.destroy)


class HashDetailView(BaseView):
    name = "hash_detail"
    description = "Hash detail view"

    def __init__(self, parent, hash_id, **kwargs):
        self._hash_id = hash_id
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
        back_btn.bind("<Button-1>", lambda e: self._on_back_click and self._on_back_click())
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

    def on_activate(self):
        self._refresh()

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _open_edit(self):
        items = credential_db.load_hashes()
        h = None
        for item in items:
            if item["id"] == self._hash_id:
                h = item
                break
        if not h:
            return
        dialog = _HashEditDialog(self, h)
        if dialog.result:
            self._refresh()

    def _refresh(self):
        items = credential_db.load_hashes()
        h = None
        for item in items:
            if item["id"] == self._hash_id:
                h = item
                break

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not h:
            self._title_label.config(text="Hash — not found")
            self.text.insert(tk.END, "Hash not found.\n", "muted")
            self.text.configure(state=tk.DISABLED)
            return

        self._title_label.config(text=f"Hash #{h['id']}")

        obtained = h.get("obtained_date_time", "") or ""
        if "T" in obtained:
            obtained = obtained[:19].replace("T", " ")

        rows = [
            ("ID", str(h.get("id", ""))),
            ("Type", h.get("type", "") or "-"),
            ("Hash", h.get("hash", "") or "-"),
            ("Salt", h.get("salt", "") or "-"),
            ("Peper", h.get("peper", "") or "-"),
            ("Hashcat mode", h.get("hascat_mode", "") or "-"),
            ("Origin", h.get("origin_obteined", "") or "-"),
            ("Obtained", obtained or "-"),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value}\n", "bright")

        self.text.configure(state=tk.DISABLED)
