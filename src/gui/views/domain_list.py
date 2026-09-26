from src.gui import fonts
import tkinter as tk
import tkinter.font as tkfont
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav
from src.machines import domain_db

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"

COL_GAP = "   "
ICON_BASE = 50


class DomainListView(BaseView):
    name = "domains"
    description = "Discovered domains"

    MIN_DOMAIN = 10

    def _build_ui(self):


        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "domains", self.master)

        tk.Label(
            header,
            text="Domains",
            font=fonts.view_font_bold(22),
            fg="#ffffff",
            bg="#000000",
        ).pack(anchor="center")

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000",
            fg=BRIGHT,
            font=fonts.view_font(16),
            borderwidth=0,
            highlightthickness=0,
            pady=10,
            state=tk.DISABLED,
            cursor="",
            wrap=tk.NONE,
            spacing1=8,
            spacing3=8,
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
        self._domains = []

    def _insert_line(self, domain, info, center_pad):
        first = info.get("first_seen", "") if info else ""
        if first and "T" in first:
            first = first[:19].replace("T", " ")

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon("domain.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")
        self.text.insert(tk.END, "\t", "bright")

        tag = f"d_{domain}"
        self.text.tag_configure(tag, underline=False)
        self.text.insert(tk.END, domain[:50] + "\u2026" if len(domain) > 50 else domain, ("bright", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda e, d=domain: (
            self._on_domain_click and self._on_domain_click(d)))
        self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
        self.text.insert(tk.END, "\t", "bright")

        self.text.insert(tk.END, f"{first}", "muted")
        self.text.insert(tk.END, "\t", "bright")

        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"del_{domain}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>", lambda e, d=domain: (
                self._delete_domain(d), "break")[-1])

        self.text.insert(tk.END, "\n", "muted")

    def _delete_domain(self, domain):
        domain_db.delete_domain(domain)

    def _poll(self):
        domains = domain_db.list_all()
        domains.sort()

        current_hash = hash(tuple(domains))
        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        self._domains = domains

        w_domain = self.MIN_DOMAIN
        for d in domains:
            w_domain = max(w_domain, len(d))

        w_date = 19

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        row_content_px = icons.scaled(ICON_BASE) + gap_px + col_w(w_domain) + gap_px + col_w(w_date) + gap_px + col_w(3)

        w = self.text.winfo_width()
        if w > row_content_px:
            pad_chars = int((w - row_content_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = []
        t = center_px + icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += col_w(w_domain) + gap_px
        tabs.append(t)
        t += col_w(w_date) + gap_px
        tabs.append(t)

        self.text.configure(tabs=tabs)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not domains:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No domains discovered yet.\n", "muted")
        else:
            for d in domains:
                info = domain_db.load_domain_info(d)
                self._insert_line(d, info, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)

        self._poll_id = self.after(2000, self._poll)
