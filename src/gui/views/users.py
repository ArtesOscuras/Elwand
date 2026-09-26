import tkinter as tk
import tkinter.font as tkfont
from src.gui import fonts
from src.gui import icons
from src.gui import windowing
from src.machines import credential_db
from .base import BaseView
from .nav import build as build_nav

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"

COL_GAP = "   "
ICON_BASE = 50


def _add_autocomplete(entry, var, items_fn):
    """Show a popup listbox below entry when focused (using place)."""
    popup = {"lb": None}
    key_id = [None]

    def _show():
        _hide()
        try:
            items = items_fn()
        except Exception:
            return
        if not items:
            return
        lb = tk.Listbox(
            entry.master, bg="#000000", fg=BRIGHT,
            selectbackground="#333333", selectforeground=BRIGHT,
            font=fonts.view_font(11), borderwidth=1, highlightthickness=0,
            activestyle="none", exportselection=False, height=5,
        )
        for item in items:
            lb.insert(tk.END, f"  {item}")

        def _select(e):
            sel = lb.curselection()
            if sel:
                var.set(lb.get(sel[0]).strip())
            _hide()
            entry.focus()

        def _on_key(e):
            lb = popup["lb"]
            if not lb:
                return
            txt = var.get().lower()
            lb.delete(0, tk.END)
            for item in items_fn():
                if txt in str(item).lower():
                    lb.insert(tk.END, f"  {item}")

        lb.bind("<ButtonRelease-1>", _select)
        lb.bind("<Escape>", lambda e: _hide())
        if key_id[0]:
            entry.unbind("<KeyRelease>", key_id[0])
        key_id[0] = entry.bind("<KeyRelease>", _on_key)
        popup["lb"] = lb

        x = entry.winfo_x()
        y = entry.winfo_y() + entry.winfo_height()
        lb.place(x=x, y=y, width=max(entry.winfo_width(), 200))

    def _hide(e=None):
        if popup["lb"]:
            popup["lb"].place_forget()
            popup["lb"].destroy()
            popup["lb"] = None

    entry.bind("<FocusIn>", lambda e: entry.after(50, _show))


class UsersView(BaseView):
    name = "users"
    description = "Manage users"

    MIN_NAME = 8
    MIN_INFO = 8

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "users", self.master)

        self._title_label = tk.Label(
            header, text="Users",
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
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT,
            font=fonts.view_font(16), borderwidth=0, highlightthickness=0,
            pady=10, state=tk.DISABLED, cursor="",
            wrap=tk.NONE, spacing1=8, spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, pady=(15, 15))

        back_btn = tk.Label(
            btn_frame, text="  \u2190 Back  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.RIGHT, padx=(10, 0))
        back_btn.bind("<Button-1>",
                      lambda e: self.master.activate_view("inventory"))
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

        add_btn = tk.Label(
            btn_frame, text="  Add user  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.LEFT)
        add_btn.bind("<Button-1>", lambda e: self._open_add_user())
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

        self._on_user_click = None

        self._last_hash = None
        self._poll_id = None
        self._resize_id = None

    def _on_resize(self, event):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._last_hash = None
        self._resize_id = self.after(200, self._poll)

    def on_activate(self):
        self.after(100, self._poll)

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self):
        items = credential_db.load_users()
        current_hash = hash(tuple(
            (i["id"], i.get("username", ""), i.get("type", ""),
             i.get("machine", ""), i.get("domain", ""), i.get("groups", ""))
            for i in items))
        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_name = self.MIN_NAME
        w_info = self.MIN_INFO
        for item in items:
            w_name = max(w_name, len(item.get("username", "") or ""))
            utype = item.get("type", "") or ""
            domain = item.get("domain", "") or ""
            machine = item.get("machine", "") or ""
            info = domain if utype == "domain" else machine
            w_info = max(w_info, len(info))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        row_px = icons.scaled(ICON_BASE) + gap_px + col_w(w_name) + gap_px + col_w(w_info) + char_w + 20

        w = self.text.winfo_width()
        if w > row_px:
            pad_chars = int((w - row_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += col_w(w_name) + gap_px
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not items:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No users stored yet.\n", "muted")
        else:
            for item in items:
                self._insert_line(item, w_name, w_info, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)
        self._poll_id = self.after(2000, self._poll)

    def _insert_line(self, item, w_name, w_info, center_pad):
        user = item.get("username", "") or ""
        utype = item.get("type", "") or ""
        domain = item.get("domain", "") or ""
        machine = item.get("machine", "") or ""
        info = domain if utype == "domain" else machine

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon("user.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        tag = f"user_{item['id']}"
        self.text.tag_configure(tag, underline=False)
        self.text.insert(tk.END, user, ("bright", tag))
        self.text.tag_bind(tag, "<Button-1>",
                           lambda e, u=item["username"]: (
                               self._on_user_click
                               and self._on_user_click(u)))
        self.text.tag_bind(tag, "<Enter>",
                           lambda e, t=tag: self.text.tag_configure(
                               t, underline=True))
        self.text.tag_bind(tag, "<Leave>",
                           lambda e, t=tag: self.text.tag_configure(
                               t, underline=False))
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, info or "\u2014", "muted")
        self.text.insert(tk.END, "\t", "bright")

        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"delu_{item['id']}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>",
                               lambda e, u=item["username"]: (
                                   credential_db.delete_user(u),
                                   "break")[-1])

        self.text.insert(tk.END, "\n", "bright")

    def _open_add_user(self):
        _AddUserDialog(self)


class _AddUserDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add User")
        windowing.size_dialog(self, 450, 340)
        self.configure(bg="#111111")
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._utype_var = tk.StringVar(value="local")
        self._name_var = tk.StringVar()
        self._domain_var = tk.StringVar()
        self._machine_var = tk.StringVar()
        self._origin_var = tk.StringVar(value="Added manually by user")
        self._groups_var = tk.StringVar()

        row = 0

        tk.Label(
            self, text="Username:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 3))
        tk.Entry(
            self, textvariable=self._name_var, bg="#000000", fg=BRIGHT,
            insertbackground=BRIGHT, font=fonts.view_font(11),
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333",
        ).grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 3))
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
            fg="#00cc66", bg="#111111",
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

        add_btn = tk.Label(
            btn_frame, text="  Add  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.RIGHT)
        add_btn.bind("<Button-1>", lambda e: self._save())
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

        self._on_type_changed()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

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
        name = self._name_var.get().strip()
        if not name:
            return
        utype = self._utype_var.get()
        credential_db.save_user(
            username=name,
            origin=self._origin_var.get().strip(),
            utype=utype,
            machine=self._machine_var.get().strip() if utype == "local" else "",
            domain=self._domain_var.get().strip() if utype == "domain" else "",
            groups=self._groups_var.get().strip(),
        )
        self._feedback.config(text="Done.")
        self.after(800, self.destroy)
