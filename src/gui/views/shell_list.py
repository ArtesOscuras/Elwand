from src.gui import fonts
import tkinter as tk
import tkinter.font as tkfont
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav
from src.shells import shell_db
from src.gui.dialogs.remote_access import RemoteAccessDialog

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"

_agent_allowed = set()

COL_GAP = "   "
ICON_BASE = 50


class ShellListView(BaseView):
    name = "shells"
    description = "Reverse shell sessions"

    MIN_NAME = 10

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "shells", self.master)

        tk.Label(
            header,
            text="Shells",
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

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(5, 10))

        remote_btn = tk.Label(
            btn_frame, text="  New remote connection  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        remote_btn.pack()
        remote_btn.bind("<Button-1>", lambda e: self._open_remote_access())
        remote_btn.bind("<Enter>", lambda e: remote_btn.config(bg="#333333"))
        remote_btn.bind("<Leave>", lambda e: remote_btn.config(bg="#222222"))

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

    def _insert_line(self, item, center_pad):
        sid = item["id"]
        ip = item["ip"]
        stype = item.get("type", "Revershell")
        status = item["status"]
        status_color = "info" if status == "connected" else "muted"

        self.text.insert(tk.END, center_pad, "bright")

        id_tag = f"s_{sid}"
        self.text.tag_configure(id_tag, underline=False)
        self.text.insert(tk.END, f"#{sid}", ("bright", id_tag))
        self.text.tag_bind(id_tag, "<Button-1>", lambda e, s=sid: (
            self._on_shell_click and self._on_shell_click(s)))
        self.text.tag_bind(id_tag, "<Enter>", lambda e, t=id_tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(id_tag, "<Leave>", lambda e, t=id_tag: self.text.tag_configure(t, underline=False))

        self.text.insert(tk.END, "\t", "bright")

        icon = icons.icon("shells.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "#")

        self.text.insert(tk.END, "\t", "bright")

        ip_tag = f"ip_{sid}"
        self.text.tag_configure(ip_tag, underline=False)
        self.text.insert(tk.END, f"{ip}", ("bright", ip_tag))
        self.text.tag_bind(ip_tag, "<Button-1>", lambda e, s=sid: (
            self._on_shell_click and self._on_shell_click(s)))
        self.text.tag_bind(ip_tag, "<Enter>", lambda e, t=ip_tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(ip_tag, "<Leave>", lambda e, t=ip_tag: self.text.tag_configure(t, underline=False))

        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, f"{stype}", "muted")
        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, f"{status}", status_color)
        self.text.insert(tk.END, "\t", "bright")

        del_img = icons.delete_icon()
        if del_img:
            self.text.image_create(tk.END, image=del_img)
            del_tag = f"del_{sid}"
            self.text.tag_add(del_tag, "end-2c", "end-1c")
            self.text.tag_bind(del_tag, "<Button-1>", lambda e, s=sid: (
                self._delete_shell(s), "break")[-1])

        self.text.insert(tk.END, "\n", "bright")

    def _delete_shell(self, sid):
        shell_db.close_session(sid)
        _agent_allowed.discard(sid)

    def _open_remote_access(self):
        RemoteAccessDialog(self)

    def _poll(self):
        items = shell_db.get_all()
        self._items = items

        current_hash = hash(tuple((i["id"], i["status"], i.get("type", ""), i.get("os", "")) for i in items))

        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_id = 4
        w_ip = 12
        w_type = 10
        w_status = 12
        for item in items:
            w_ip = max(w_ip, len(item["ip"]))
            w_type = max(w_type, len(item.get("type", "Revershell")))
            w_status = max(w_status, len(item["status"]))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        row_content_px = col_w(w_id) + gap_px + icons.scaled(ICON_BASE) + gap_px + col_w(w_ip) + gap_px + col_w(w_type) + gap_px + col_w(w_status)

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
        t += col_w(w_ip) + gap_px
        tabs.append(t)
        t += col_w(w_type) + gap_px
        tabs.append(t)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not items:
            msg1 = "No shells connected yet."
            msg2 = "Use 'start-listener' to start the listener."
            msg_w = max(font.measure(msg1), font.measure(msg2))
            w = self.text.winfo_width()
            if w > msg_w:
                pad_chars = int((w - msg_w) // 2 // char_w)
                center_pad_msg = " " * max(0, pad_chars)
            else:
                center_pad_msg = "  "
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad_msg, "bright")
            self.text.insert(tk.END, msg1 + "\n", "muted")
            self.text.insert(tk.END, center_pad_msg, "bright")
            self.text.insert(tk.END, msg2 + "\n", "muted")
        else:
            for item in items:
                self._insert_line(item, center_pad)

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)

        self._poll_id = self.after(2000, self._poll)


def is_agent_allowed(sid):
    return sid in _agent_allowed


def toggle_agent_shell(sid):
    if sid in _agent_allowed:
        _agent_allowed.discard(sid)
        return False
    else:
        _agent_allowed.add(sid)
        return True


def enable_default_agent_access(sid):
    from src import settings
    if settings.get("agent_default_shell_access", False):
        _agent_allowed.add(sid)
