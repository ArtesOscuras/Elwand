import tkinter as tk
import tkinter.font as tkfont
from src.gui import fonts, windowing
from src.gui import icons
from src.machines import people_db
from .base import BaseView
from .nav import build as build_nav

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"

COL_GAP = "   "
ICON_SIZE = 50


class PeopleView(BaseView):
    name = "people"
    description = "Manage people"

    MIN_NAME = 10
    MIN_INFO = 10

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "people", self.master)

        self._title_label = tk.Label(
            header, text="People",
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
            btn_frame, text="  Add person  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.LEFT)
        add_btn.bind("<Button-1>", lambda e: self._open_add_person())
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

        self._on_person_click = None

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
        items = people_db.load_people()
        current_hash = hash(tuple(
            (i["id"], i.get("first_name", ""), i.get("last_name", ""),
             i.get("company", ""), i.get("role", ""))
            for i in items))
        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_name = self.MIN_NAME
        w_info = self.MIN_INFO
        for item in items:
            full = f"{item.get('first_name','')} {item.get('last_name','')}".strip()
            w_name = max(w_name, len(full))
            co = item.get("company", "") or "-"
            w_info = max(w_info, len(co))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        row_px = ICON_SIZE + gap_px + col_w(w_name) + gap_px + col_w(w_info) + char_w + 20

        w = self.text.winfo_width()
        if w > row_px:
            pad_chars = int((w - row_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + ICON_SIZE + gap_px
        tabs.append(t)
        t += col_w(w_name) + gap_px
        tabs.append(t)
        t += col_w(w_info) + gap_px
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not items:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No people stored yet.\n", "muted")
        else:
            for item in items:
                self._insert_line(item, w_name, w_info, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)
        self._poll_id = self.after(2000, self._poll)

    def _insert_line(self, item, w_name, w_info, center_pad):
        full_name = f"{item.get('first_name','')} {item.get('last_name','')}".strip()
        if not full_name:
            full_name = f"#{item['id']}"
        company = item.get("company", "") or item.get("domain", "") or "-"

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon("people.png", size=ICON_SIZE)
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        tag = f"person_{item['id']}"
        self.text.tag_configure(tag, underline=False)
        self.text.insert(tk.END, full_name, ("bright", tag))
        self.text.tag_bind(tag, "<Button-1>",
                           lambda e, pid=item["id"]: (
                               self._on_person_click
                               and self._on_person_click(pid)))
        self.text.tag_bind(tag, "<Enter>",
                           lambda e, t=tag: self.text.tag_configure(
                               t, underline=True))
        self.text.tag_bind(tag, "<Leave>",
                           lambda e, t=tag: self.text.tag_configure(
                               t, underline=False))
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, company, "muted")
        self.text.insert(tk.END, "\t", "bright")

        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"delp_{item['id']}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>",
                               lambda e, pid=item["id"]: (
                                   people_db.delete_person(pid),
                                   "break")[-1])

        self.text.insert(tk.END, "\n", "bright")

    def _open_add_person(self):
        _AddPersonDialog(self)


class _AddPersonDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Person")
        windowing.size_dialog(self, 500, 500)
        self.configure(bg="#111111")
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._first_var = tk.StringVar()
        self._last_var = tk.StringVar()
        self._company_var = tk.StringVar()
        self._domain_var = tk.StringVar()
        self._username_var = tk.StringVar()
        self._role_var = tk.StringVar()
        self._linkedin_var = tk.StringVar()
        self._source_var = tk.StringVar(value="Added manually by user")
        self._interests_var = tk.StringVar()

        row = 0

        fields = [
            ("First Name:", self._first_var),
            ("Last Name:", self._last_var),
            ("Company:", self._company_var),
            ("Domain:", self._domain_var),
            ("Username:", self._username_var),
            ("Role:", self._role_var),
            ("LinkedIn URL:", self._linkedin_var),
            ("Source:", self._source_var),
            ("Interests:", self._interests_var),
        ]

        for label_text, var in fields:
            tk.Label(
                self, text=label_text, font=fonts.view_font(11),
                fg=BRIGHT, bg="#111111",
            ).grid(row=row, column=0, sticky="w", padx=15,
                    pady=(10 if row == 0 else 3, 0))
            tk.Entry(
                self, textvariable=var, bg="#000000", fg=BRIGHT,
                insertbackground=BRIGHT, font=fonts.view_font(11),
                borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333",
                highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15,
                    pady=(10 if row == 0 else 3, 0))
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

        save_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        save_btn.pack(side=tk.RIGHT)
        save_btn.bind("<Button-1>", lambda e: self._save())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#333333"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _save(self):
        fn = self._first_var.get().strip()
        ln = self._last_var.get().strip()
        if not fn and not ln:
            return
        people_db.save_person(
            first_name=fn,
            last_name=ln,
            company=self._company_var.get().strip(),
            domain=self._domain_var.get().strip(),
            username=self._username_var.get().strip(),
            role=self._role_var.get().strip(),
            linkedin_url=self._linkedin_var.get().strip(),
            source=self._source_var.get().strip(),
            interests=self._interests_var.get().strip(),
        )
        self._feedback.config(text="Done.")
        self.after(800, self.destroy)
