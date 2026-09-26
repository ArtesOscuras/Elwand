from src.gui import fonts
import tkinter as tk
import tkinter.font as tkfont
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav
from src.machines import credential_db

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"

COL_GAP = "   "
ICON_BASE = 50


class HashListView(BaseView):
    name = "hashes"
    description = "Stored hashes"

    MIN_TYPE = 8
    MIN_HASH = 16
    MIN_ID = 4

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "hashes", self.master)

        self._title_label = tk.Label(
            header, text="Hashes",
            font=fonts.view_font_bold(22), fg=BRIGHT, bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", lambda e: self.master.activate_view("inventory"))
        self._title_label.bind("<Enter>", lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind("<Leave>", lambda e: self._title_label.config(font=fonts.view_font_bold(22)))

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

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
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
        back_btn.bind("<Button-1>", lambda e: self.master.activate_view("inventory"))
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

        add_btn = tk.Label(
            btn_frame, text="  Add hash  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        add_btn.pack(side=tk.LEFT)
        add_btn.bind("<Button-1>", lambda e: self._open_add_hash())
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#333333"))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#222222"))

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
        self._items = []

    def _insert_line(self, item, w_type, w_hash, center_pad):
        hid = item["id"]
        htype = item.get("type", "") or ""
        hval = item.get("hash", "") or ""

        self.text.insert(tk.END, center_pad, "bright")
        self.text.insert(tk.END, f"#{hid}", "muted")
        self.text.insert(tk.END, "\t", "bright")

        icon = icons.icon("hashes2.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        tag = f"htype_{item['id']}"
        self.text.tag_configure(tag, underline=False)
        self.text.insert(tk.END, htype, ("bright", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda e, hid=item["id"]: (
            self._on_hash_click and self._on_hash_click(hid)))
        self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, hval[:16] + "\u2026" if len(hval) > 16 else hval, "muted")
        self.text.insert(tk.END, "\t", "bright")

        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"delh_{item['id']}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>", lambda e, hid=item["id"]: (
                credential_db.delete_hash_entry(hid), "break")[-1])

        self.text.insert(tk.END, "\n", "bright")

    def _poll(self):
        items = credential_db.load_hashes()
        self._items = items

        current_hash = hash(tuple((i["id"], i.get("type", ""), i.get("hash", "")) for i in items))

        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_id = self.MIN_ID
        w_type = self.MIN_TYPE
        w_hash = self.MIN_HASH
        for item in items:
            w_id = max(w_id, len(str(item["id"])))
            w_type = max(w_type, len(item.get("type", "") or ""))
            hval = item.get("hash", "") or ""
            w_hash = max(w_hash, min(len(hval), 17))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        row_content_px = col_w(w_id) + gap_px + icons.scaled(ICON_BASE) + gap_px + col_w(w_type) + gap_px + col_w(w_hash) + char_w + 20

        w = self.text.winfo_width()
        if w > row_content_px:
            pad_chars = int((w - row_content_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + col_w(w_id) + gap_px
        tabs.append(t)
        t += icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += col_w(w_type) + gap_px
        tabs.append(t)
        t += col_w(w_hash) + char_w
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not items:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No hashes stored yet.\n", "muted")
        else:
            for item in items:
                self._insert_line(item, w_type, w_hash, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)

        self._poll_id = self.after(2000, self._poll)

    def _open_add_hash(self):
        from src.gui.dialogs.hashcat import HashcatDialog
        HashcatDialog(self, active_tab=2)

