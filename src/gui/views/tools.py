from src.gui import fonts
import tkinter as tk
import tkinter.font as tkfont
from src.gui import icons
from .base import BaseView
from .nav import build as build_nav

MUTED = "#888888"
BRIGHT = "#ffffff"

COL_GAP = "   "
ICON_BASE = 50


class ToolsView(BaseView):
    name = "tools"
    description = "Available tools"

    MIN_NAME = 14

    def _build_ui(self):


        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))

        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "tools", self.master)

        tk.Label(
            header,
            text="Tools",
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
            state=tk.NORMAL,
            cursor="",
            wrap=tk.NONE,
            spacing1=8,
            spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("tool_name", foreground=BRIGHT, font=fonts.view_font(18))
        self.text.tag_configure("tool_desc", foreground=MUTED, font=fonts.view_font(12))

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.bind("<Configure>", self._on_resize)
        self._tools = [
            {"name": "Scanner", "action": "scanner", "desc": "Scan interface or ip."},
            {"name": "Fuzzer", "action": "fuzzer", "desc": "Fuzz directory or subdommains."},
            {"name": "Webrecorder", "action": "webrecorder", "desc": "Record web evidences for analisis."},
            {"name": "Bruteforce", "action": "bruteforce", "desc": "Brute force FTP, SSH, SMB credentials."},
            {"name": "Hashcat", "action": "hashcat", "desc": "Crack hashes with hashcat."},
            {"name": "Dicma", "action": "dicma", "desc": "Generate custom wordlists."},
            {"name": "Wifi operator", "action": "wifioperator", "desc": "Deauth clients from nearby WiFi networks."},
        ]
        self._rendered = False
        self._poll_id = None
        self._resize_id = None

    def _on_resize(self, event):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._rendered = False
        self._resize_id = self.after(200, self._poll)


    def on_activate(self):
        self.after(100, self._poll)

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self):
        if not self._rendered:
            self._rendered = True
            self._render()
        self._poll_id = self.after(2000, self._poll)

    def _render(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        w_name = self.MIN_NAME
        w_desc = 20
        for t in self._tools:
            w_name = max(w_name, len(t["name"]))
            w_desc = max(w_desc, len(t["desc"]))

        font = tkfont.Font(font=(fonts.family(), 18))
        font_desc = tkfont.Font(font=(fonts.family(), 12))
        tw = tkfont.Font(font=self.text.cget("font"))
        gap_px = tw.measure(COL_GAP)
        char_w = tw.measure(" ")
        name_px = font.measure(" " * w_name)
        desc_px = font_desc.measure(" " * w_desc)

        row_content_px = icons.scaled(ICON_BASE) + gap_px + name_px + gap_px + desc_px

        w = self.text.winfo_width()
        if w > row_content_px:
            pad_chars = int((w - row_content_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = tw.measure(center_pad)
        tabs = []
        t = center_px + icons.scaled(ICON_BASE) + gap_px
        tabs.append(t)
        t += name_px + gap_px
        tabs.append(t)

        self.text.configure(tabs=tabs)

        for tool in self._tools:
            self._insert_tool(tool, center_pad)

        self.text.configure(state=tk.DISABLED)

    def _insert_tool(self, tool, center_pad):
        name = tool["name"]
        action = tool["action"]

        self.text.insert(tk.END, center_pad, "bright")

        icon = icons.icon(f"{action}.png", size=icons.scaled(ICON_BASE))
        if icon:
            self.text.image_create(tk.END, image=icon)
        else:
            self.text.insert(tk.END, "?")

        tag = f"tool_{name}"
        self.text.tag_configure(tag, underline=False)

        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, name, ("tool_name", tag))
        self.text.tag_bind(tag, "<Button-1>", lambda e, t=tool: (
            self._on_tool_click and self._on_tool_click(t["action"])))
        self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
        self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))

        self.text.insert(tk.END, "\t", "bright")
        self.text.insert(tk.END, tool["desc"], "tool_desc")

        self.text.insert(tk.END, "\n", "bright")
