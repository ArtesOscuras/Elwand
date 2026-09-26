import os
import threading
import tkinter as tk
import tkinter.font as tkfont
from src.gui import fonts
from src.gui import icons
from src.gui import windowing
from .base import BaseView
from .nav import build as build_nav
from src.elwand_paths import handshakes_dir

MUTED = "#888888"
BRIGHT = "#ffffff"

COL_GAP = "   "
ICON_BASE = 50
MIN_NAME = 12


class HandshakesView(BaseView):
    name = "handshakes"
    description = "Captured WPA handshakes"

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 5))
        nav_frame = tk.Frame(header, bg="#000000")
        nav_frame.pack(pady=(0, 10))

        build_nav(header, "handshakes", self.master)

        self._title_label = tk.Label(
            header, text="Handshakes",
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
            text_frame, bg="#000000", fg=BRIGHT,
            font=fonts.view_font(16), borderwidth=0, highlightthickness=0,
            pady=10, state=tk.DISABLED, cursor="",
            wrap=tk.NONE, spacing1=8, spacing3=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)

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

        extract_btn = tk.Label(
            btn_frame, text="  Extract hash  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        extract_btn.pack(side=tk.LEFT, padx=(0, 10))
        extract_btn.bind("<Button-1>", lambda e: self._open_extract())
        extract_btn.bind("<Enter>", lambda e: extract_btn.config(bg="#333333"))
        extract_btn.bind("<Leave>", lambda e: extract_btn.config(bg="#222222"))

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

        self._last_hash = None
        self._poll_id = None
        self._resize_id = None

    def _open_extract(self, pcap_path=None):
        ExtractHashDialog(self.winfo_toplevel(), preselect=pcap_path)

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

    def _list_files(self):
        try:
            d = str(handshakes_dir())
            files = sorted(f for f in os.listdir(d)
                           if os.path.isfile(os.path.join(d, f))
                           and f.lower().endswith(".pcap"))
            return d, files
        except OSError:
            return str(handshakes_dir()), []

    def _poll(self):
        d, files = self._list_files()
        current_hash = hash(tuple(files))
        if current_hash == self._last_hash:
            self._poll_id = self.after(2000, self._poll)
            return
        self._last_hash = current_hash

        w_name = MIN_NAME
        for f in files:
            w_name = max(w_name, len(f))

        font = tkfont.Font(font=self.text.cget("font"))
        gap_px = font.measure(COL_GAP)
        char_w = font.measure(" ")

        def col_w(n):
            return font.measure(" " * n)

        w_size = 8
        row_px = icons.scaled(ICON_BASE) + gap_px + col_w(w_name) + gap_px + col_w(w_size) + gap_px + 20

        w = self.text.winfo_width()
        if w > row_px:
            pad_chars = int((w - row_px) // 2 // char_w)
            center_pad = " " * max(0, pad_chars)
        else:
            center_pad = "  "

        center_px = font.measure(center_pad)
        tabs = [center_px + icons.scaled(ICON_BASE) + gap_px]
        tabs.append(tabs[0] + col_w(w_name) + gap_px)
        tabs.append(tabs[1] + col_w(w_size) + gap_px)

        scroll_pos = self.text.yview()[0]

        self.text.configure(state=tk.NORMAL, tabs=tabs)
        self.text.delete("1.0", tk.END)

        if not files:
            self.text.insert(tk.END, "\n", "bright")
            self.text.insert(tk.END, center_pad, "bright")
            self.text.insert(tk.END, "No handshakes captured yet.\n", "muted")
        else:
            for f in files:
                path = os.path.join(d, f)
                size_bytes = os.path.getsize(path) if os.path.isfile(path) else 0
                if size_bytes >= 1024 * 1024:
                    size_str = f"{size_bytes / (1024 * 1024):.1f}M"
                elif size_bytes >= 1024:
                    size_str = f"{size_bytes / 1024:.0f}K"
                else:
                    size_str = f"{size_bytes}B"

                self.text.insert(tk.END, center_pad, "bright")

                hs_icon = icons.icon("handshake.png", size=icons.scaled(ICON_BASE))
                if hs_icon:
                    self.text.image_create(tk.END, image=hs_icon)
                else:
                    self.text.insert(tk.END, "?")

                self.text.insert(tk.END, "\t", "bright")
                name_tag = f"hsname_{f}"
                self.text.tag_configure(name_tag, underline=False)
                self.text.insert(tk.END, f, ("bright", name_tag))
                self.text.tag_bind(
                    name_tag, "<Button-1>",
                    lambda e, p=path: self._open_extract(p))
                self.text.tag_bind(
                    name_tag, "<Enter>",
                    lambda e, t=name_tag: self.text.tag_configure(
                        t, underline=True))
                self.text.tag_bind(
                    name_tag, "<Leave>",
                    lambda e, t=name_tag: self.text.tag_configure(
                        t, underline=False))
                self.text.insert(tk.END, "\t", "bright")
                self.text.insert(tk.END, size_str, "muted")

                del_img = icons.delete_icon()
                if del_img:
                    self.text.insert(tk.END, "\t", "bright")
                    self.text.image_create(tk.END, image=del_img)
                    del_tag = f"delhs_{f}"
                    self.text.tag_add(del_tag, "end-2c", "end-1c")
                    self.text.tag_bind(del_tag, "<Button-1>",
                                       lambda e, p=path: (
                                           os.remove(p),
                                           "break")[-1])

                self.text.insert(tk.END, "\n", "bright")

        self.text.yview_moveto(scroll_pos)
        self.text.configure(state=tk.DISABLED)
        self._poll_id = self.after(2000, self._poll)


class ExtractHashDialog(tk.Toplevel):
    def __init__(self, parent, preselect=None):
        super().__init__(parent)
        self.title("Extract hash")
        windowing.size_dialog(self, 860, 560, min_w=720, min_h=460)
        self.configure(bg="#111111")
        self.transient(parent)

        self._preselect = preselect
        self._pcaps = []
        self._handshakes = []
        self._parse_token = 0
        self._extract_enabled = False

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        tk.Label(self, text="PCAP files", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(11), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=(15, 8), pady=(12, 2))
        tk.Label(self, text="Handshakes found", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(11), anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(8, 15), pady=(12, 2))

        left = tk.Frame(self, bg="#000000")
        left.grid(row=1, column=0, sticky="nsew", padx=(15, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self._pcap_list = tk.Listbox(
            left, bg="#000000", fg=BRIGHT, font=fonts.view_font(11),
            selectbackground="#333333", selectforeground=BRIGHT,
            activestyle="none", borderwidth=0, highlightthickness=0,
            cursor="", exportselection=False,
        )
        self._pcap_list.grid(row=0, column=0, sticky="nsew")
        self._make_scrollbar(left, self._pcap_list).grid(
            row=0, column=1, sticky="ns")
        self._pcap_list.bind("<<ListboxSelect>>", self._on_pcap_select)

        right = tk.Frame(self, bg="#000000")
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 15))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self._hs_list = tk.Listbox(
            right, bg="#000000", fg=BRIGHT, font=fonts.view_font(11),
            selectbackground="#333333", selectforeground=BRIGHT,
            activestyle="none", borderwidth=0, highlightthickness=0,
            cursor="", exportselection=False,
        )
        self._hs_list.grid(row=0, column=0, sticky="nsew")
        self._make_scrollbar(right, self._hs_list).grid(
            row=0, column=1, sticky="ns")
        self._hs_list.bind("<<ListboxSelect>>", self._on_hs_select)

        self._status = tk.Label(
            self, text="", fg=MUTED, bg="#111111",
            font=fonts.view_font(10), anchor="w", justify=tk.LEFT,
        )
        self._status.grid(row=2, column=0, columnspan=2, sticky="ew",
                          padx=15, pady=(8, 0))

        btns = tk.Frame(self, bg="#111111")
        btns.grid(row=3, column=0, columnspan=2, sticky="ew",
                  padx=15, pady=(8, 14))

        self._extract_btn = tk.Label(
            btns, text="  Extract hash  ", bg="#222222", fg=MUTED,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        self._extract_btn.pack(side=tk.LEFT)
        self._extract_btn.bind("<Button-1>", lambda e: self._extract())
        self._extract_btn.bind(
            "<Enter>", lambda e: self._extract_hover(True))
        self._extract_btn.bind(
            "<Leave>", lambda e: self._extract_hover(False))

        close_btn = tk.Label(
            btns, text="  Close  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._load_pcaps()

        self.update_idletasks()
        self.wait_visibility()
        self.grab_set()

    @staticmethod
    def _make_scrollbar(parent, widget):
        sb = tk.Scrollbar(parent, orient=tk.VERTICAL, command=widget.yview)
        sb.configure(bg="#333333", troughcolor="#1a1a1a",
                     activebackground="#555555", width=10,
                     borderwidth=0, highlightthickness=0,
                     elementborderwidth=0)
        widget.configure(yscrollcommand=sb.set)
        return sb

    def _set_extract_state(self, enabled):
        self._extract_enabled = enabled
        self._extract_btn.config(fg=BRIGHT if enabled else MUTED)

    def _extract_hover(self, entering):
        if not self._extract_enabled:
            return
        self._extract_btn.config(bg="#333333" if entering else "#222222")

    def _post(self, fn, *args):
        safe = getattr(self.winfo_toplevel(), "_safe_after", None)
        if callable(safe):
            safe(fn, *args)
            return
        try:
            if args:
                self.after(0, fn, *args)
            else:
                self.after(0, fn)
        except (tk.TclError, RuntimeError):
            pass

    def _load_pcaps(self):
        base = str(handshakes_dir())
        try:
            files = sorted(f for f in os.listdir(base)
                           if f.lower().endswith(".pcap")
                           and os.path.isfile(os.path.join(base, f)))
        except OSError:
            files = []
        self._pcaps = [os.path.join(base, f) for f in files]
        self._pcap_list.delete(0, tk.END)
        for f in files:
            self._pcap_list.insert(tk.END, f)
        if self._pcaps:
            idx = 0
            if self._preselect:
                target = os.path.basename(self._preselect)
                for i, f in enumerate(files):
                    if f == target:
                        idx = i
                        break
            self._pcap_list.selection_set(idx)
            self._pcap_list.see(idx)
            self._on_pcap_select()
        else:
            self._status.config(text="No .pcap files in the handshakes folder.")

    def _on_pcap_select(self, event=None):
        sel = self._pcap_list.curselection()
        self._handshakes = []
        self._hs_list.delete(0, tk.END)
        self._set_extract_state(False)
        if not sel or sel[0] >= len(self._pcaps):
            return
        path = self._pcaps[sel[0]]
        self._status.config(text="Parsing handshakes...")
        self._parse_token += 1
        threading.Thread(target=self._parse_worker,
                         args=(path, self._parse_token), daemon=True).start()

    def _parse_worker(self, path, token):
        from src.tools.scanner import wifi_monitor as wm
        try:
            results, err = wm.extract_handshakes_from_pcap(path), None
        except Exception as e:
            results, err = [], str(e)
        self._post(self._show_results, token, results, err)

    def _show_results(self, token, results, err):
        if token != self._parse_token or not self.winfo_exists():
            return
        self._handshakes = results
        self._hs_list.delete(0, tk.END)
        if err:
            self._status.config(text=f"Error parsing pcap: {err}")
            return
        if not results:
            self._status.config(
                text="No complete handshake found in this pcap.")
            return
        for hs in results:
            ssid = hs["ssid"] or "(hidden)"
            msgs = "".join(str(m) for m in hs["messages"]) or "?"
            self._hs_list.insert(
                tk.END,
                f"{ssid}   {hs['bssid']}   client {hs['client']}   "
                f"MSGs {msgs}   mp {hs['message_pair']}")
        self._status.config(
            text=f"{len(results)} handshake(s) found. Select one and press "
                 f"Extract hash.")

    def _on_hs_select(self, event=None):
        sel = self._hs_list.curselection()
        self._set_extract_state(bool(sel))

    def _extract(self):
        sel = self._hs_list.curselection()
        if not sel or sel[0] >= len(self._handshakes):
            return
        line = self._handshakes[sel[0]]["line"]
        try:
            from src.machines import credential_db
            existing = {h.get("hash", "") for h in credential_db.load_hashes()}
            if line in existing:
                self._status.config(
                    text="This hash is already in the inventory.")
                return
            hid = credential_db.save_hash_entry(
                "WPA handshake", line, hascat_mode="22000",
                origin="manual extract")
        except Exception as e:
            self._status.config(text=f"Could not save hash: {e}")
            return
        self._status.config(
            text=f"Hash created (#{hid}). Crack it from the Hashes view "
                 f"with hashcat.")
