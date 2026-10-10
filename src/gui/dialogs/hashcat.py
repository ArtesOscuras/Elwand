import json
import os
import queue
import re
import shlex
import sqlite3
import threading
import time
import tkinter as tk
from collections import defaultdict
from tkinter import ttk
from src.gui import fonts, windowing, theme
from src.machines import credential_db
from src.tools.hashcat import HashcatEngine
from src.tools.hashcat.engine import build_command, format_command, count_lines
from src.elwand_paths import hashcat_db as _hashcat_db

BG = theme.BG
BG_WIDGET = theme.PANEL
FG = theme.FG
FG_DIM = theme.MUTED
SEL_BG = theme.SEL_BG
SUCCESS = theme.SUCCESS
ERR_COLOR = theme.ERROR
INFO_COLOR = theme.INFO

# -S (slow-candidates) heuristic: hashcat under-uses the device when the
# wordlist ("base loop") is small; -S moves candidate generation to the host.
# Recommended when the ruleset is large and the wordlist is small relative to
# the GPU's compute units.
_S_MCU_FACTOR = 1024
_S_RULES_MIN = 1000
_S_WORK_MIN = 1_000_000


def _fmt_int(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _fmt_hms(sec):
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_speed(hps):
    hps = max(0.0, float(hps))
    if hps >= 1e9:
        return f"{hps / 1e9:.2f} GH/s"
    if hps >= 1e6:
        return f"{hps / 1e6:.2f} MH/s"
    if hps >= 1e3:
        return f"{hps / 1e3:.2f} kH/s"
    return f"{int(hps)} H/s"


class _StatusPanel:
    """Elwand-styled hashcat status panel with a single output pane.

    Progress bar plus live status/timing/device lines, and one output area
    showing hashcat's real output (Elwand messages are interleaved in it).
    """

    def __init__(self, parent, row):
        self.parent = parent
        self._started_at = None
        self._est_end = None
        self._state = "idle"
        self._last_end = 0
        self._indeterminate = False
        self._device_part = ""
        self._timing_part = ""

        # Header (also shows the live state) — replaces a separate "Status"
        # heading, so it costs no extra line.
        self.info = tk.Label(parent, text="Status: Ready",
                             font=fonts.view_font(10), fg=FG, bg=BG,
                             anchor="w", justify=tk.LEFT)
        self.info.grid(row=row, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(6, 2))
        row += 1

        self.progress_var = tk.IntVar(value=0)
        self.bar = ttk.Progressbar(parent, variable=self.progress_var,
                                   maximum=100)
        self.bar.grid(row=row, column=0, columnspan=2, sticky="ew",
                      padx=15, pady=(0, 2))
        row += 1

        # Device + Elapsed/ETA share a single line.
        self.device = tk.Label(parent, text="", font=fonts.view_font(9),
                               fg=FG_DIM, bg=BG, anchor="w")
        self.device.grid(row=row, column=0, columnspan=2, sticky="ew",
                         padx=15, pady=(0, 2))
        row += 1

        out_frame = tk.Frame(parent, bg=BG_WIDGET)
        out_frame.grid(row=row, column=0, columnspan=2, sticky="nsew",
                       padx=15, pady=(2, 2))
        parent.rowconfigure(row, weight=1)
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(0, weight=1)
        self.output = tk.Text(
            out_frame, bg=BG_WIDGET, fg=FG, font=fonts.view_font(9), height=16,
            state=tk.DISABLED, wrap=tk.WORD, cursor="", borderwidth=0,
            highlightthickness=0)
        self.output.grid(row=0, column=0, sticky="nsew")
        out_sb = tk.Scrollbar(out_frame, orient=tk.VERTICAL,
                              command=self.output.yview)
        out_sb.configure(bg="#333333", troughcolor="#1a1a1a",
                         activebackground="#555555", width=10, borderwidth=0,
                         highlightthickness=0, elementborderwidth=0)
        out_sb.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=out_sb.set)
        for tag, col in (("success", SUCCESS), ("error", ERR_COLOR),
                         ("info", INFO_COLOR), ("muted", FG_DIM),
                         ("warn", theme.WARN)):
            self.output.tag_configure(tag, foreground=col)
        row += 1

        self.end_row = row

    def reset(self):
        self._set_indeterminate(False)
        self.progress_var.set(0)
        self.info.config(text="Status: Ready")
        self._device_part = ""
        self._timing_part = ""
        self.device.config(text="")
        self._started_at = None
        self._est_end = None
        self._state = "idle"
        self._last_end = 0
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.configure(state=tk.DISABLED)

    def _set_indeterminate(self, on):
        if on == self._indeterminate:
            return
        self._indeterminate = on
        try:
            if on:
                self.bar.configure(mode="indeterminate")
                self.bar.start(15)
            else:
                self.bar.stop()
                self.bar.configure(mode="determinate")
        except tk.TclError:
            pass

    def start(self, desc):
        self._started_at = time.time()
        self._est_end = None
        self._state = "starting"
        self._set_indeterminate(True)
        self.info.config(text="Status: Starting\u2026")
        self.log(f"[>] {desc}", "info")
        self.tick()

    def phase(self, label):
        if not self._started_at:
            self._started_at = time.time()
        self._state = "preparing"
        self._set_indeterminate(True)
        self.info.config(text=f"Status: {label}")
        self.log(f"[*] {label}", "muted")
        self.tick()

    def log(self, text, tag=None):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text + "\n", tag or ())
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def log_raw(self, text):
        self.output.configure(state=tk.NORMAL)
        at_bottom = self.output.yview()[1] >= 1.0
        self.output.insert(tk.END, text,
                           "error" if "error" in text.lower() else ())
        if at_bottom:
            self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def set_status(self, st):
        self._state = st["state"]
        if self._state in ("running", "cracked", "exhausted"):
            self._set_indeterminate(False)
        cur, end = st["progress"]
        rejected = st.get("rejected", 0) or 0
        rec = st["recovered"]
        self._last_end = end
        parts = [f"Status: {st['state'].capitalize()}"]
        # hashcat counts REJECTED candidates (e.g. too short/long for the hash)
        # as "progress". With a tiny wordlist + huge ruleset that makes the bar
        # jump at startup (the rejects are booked almost instantly). Base the
        # percentage on the actually-hashed candidates instead.
        hashed = max(0, cur - rejected)
        usable = end - rejected
        if usable > 0:
            pct = int(hashed * 100 / usable)
            self.progress_var.set(max(0, min(100, pct)))
            parts.append(f"{_fmt_int(hashed)} / {_fmt_int(usable)} ({pct}%)")
        elif end > 0:
            self.progress_var.set(100)
            parts.append("100%")
        if rejected:
            parts.append(f"rejected {_fmt_int(rejected)}")
        if st["speed"]:
            parts.append(_fmt_speed(st["speed"]))
        if rec[1]:
            parts.append(f"Recovered: {rec[0]}/{rec[1]}")
        self.info.config(text="    ".join(parts))

        if st["devices"]:
            d = st["devices"][0]
            dev = [d["name"] or d["type"] or "Device"]
            if d.get("util"):
                dev.append(f"Util {d['util']}%")
            if d.get("temp", -1) > 0:
                dev.append(f"Temp {d['temp']}C")
            self._device_part = "    ".join(dev)
        else:
            self._device_part = ""

        if st["elapsed"]:
            self._started_at = time.time() - st["elapsed"]
        self._est_end = (time.time() + st["eta"]) if st["eta"] else None
        self.tick()

    def set_progress(self, done, total, recovered):
        if not self._started_at:
            self._started_at = time.time()
        self._set_indeterminate(False)
        if total > 0:
            pct = int(done * 100 / total)
            self.progress_var.set(max(0, min(100, pct)))
            parts = [f"Status: Running",
                     f"{_fmt_int(done)} / {_fmt_int(total)} ({pct}%)"]
            if recovered:
                parts.append(f"Recovered: {recovered}")
            self.info.config(text="    ".join(parts))
        self.tick()

    def tick(self):
        if (self._state in ("starting", "preparing", "running", "paused")
                and self._started_at):
            now = time.time()
            parts = [f"Elapsed {_fmt_hms(now - self._started_at)}"]
            if self._est_end and self._est_end > now:
                parts.append(f"ETA ~{_fmt_hms(self._est_end - now)}")
            elif self._state == "running":
                parts.append("ETA computing\u2026")
            self._timing_part = "    ".join(parts)
        else:
            self._timing_part = ""
        self._update_device_line()

    def _update_device_line(self):
        parts = [p for p in (self._device_part, self._timing_part) if p]
        self.device.config(text="    ".join(parts))

    def cracked(self, plain):
        self.log(f"[+] Cracked: {plain}  (saved to inventory)", "success")

    def finish(self, cracked_list, failed=False):
        self._est_end = None
        self._set_indeterminate(False)
        self._timing_part = ""
        self._update_device_line()
        if failed:
            self.info.config(text="Status: Failed")
            self.log("[!] Hashcat failed \u2014 see the output above.",
                     "error")
            self._state = "idle"
            return
        if cracked_list:
            if self._state != "cracked":
                self.info.config(text="Status: Cracked")
            self.log(f"[*] Finished: {len(cracked_list)} password(s) found",
                     "info")
        else:
            if self._state not in ("exhausted", "cracked"):
                self.info.config(text="Status: Exhausted")
            self.progress_var.set(100)
            self.log("[*] Finished: no password found", "muted")
        self._state = "idle"


class HashcatDialog(tk.Toplevel):
    def __init__(self, parent, active_tab=0, on_hash_added=None):
        super().__init__(parent)
        self._engine = None
        self._cracked = []
        self._hash_items = []
        self._modes_by_type = {}
        self._hw = None
        self._mcu = 0
        self._slow_recommended = False
        self._detect_db = None
        self.result = None
        self._on_hash_added = on_hash_added
        self._ui_q = queue.Queue()
        self._drain_id = None
        self._tick_id = None
        self._closing = False

        self.title("Hashcat")
        windowing.size_dialog(self, 1100, 880, min_w=960, min_h=700)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._nb = ttk.Notebook(self)
        self._nb.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self._tab_crack = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_crack, text="  Hashcat Wrdlst  ")
        self._build_crack_tab(self._tab_crack)

        self._tab_mask = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_mask, text="  Hashcat Mask  ")
        self._build_mask_tab(self._tab_mask)

        self._tab_add = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_add, text="  Add Hash  ")
        self._build_add_tab(self._tab_add)

        self._tab_detect = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_detect, text="  Detect  ")
        self._build_detect_tab(self._tab_detect)

        self._nb.select(active_tab)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._detect_hardware()

    # ─── Crack Tab ──────────────────────────────────────────────

    def _build_crack_tab(self, parent):
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)

        row = 0

        tk.Label(
            parent, text="Hash", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 2))

        hash_frame = tk.Frame(parent, bg=BG_WIDGET)
        hash_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 2))
        hash_frame.columnconfigure(0, weight=1)
        hash_frame.rowconfigure(0, weight=1)

        self._hash_listbox = tk.Listbox(
            hash_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._hash_listbox.grid(row=0, column=0, sticky="nsew")

        hash_scroll = tk.Scrollbar(hash_frame, orient=tk.VERTICAL, command=self._hash_listbox.yview)
        hash_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        hash_scroll.grid(row=0, column=1, sticky="ns")
        self._hash_listbox.configure(yscrollcommand=hash_scroll.set)

        self._mode_var = tk.StringVar()
        self._hash_val_var = tk.StringVar()
        self._type_label_var = tk.StringVar()

        self._populate_hashes()
        self._hash_listbox.bind("<<ListboxSelect>>", self._on_hash_select)

        row += 1

        tk.Label(
            parent, text="Hash value", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 0))
        self._hash_val_entry = tk.Entry(
            parent, textvariable=self._hash_val_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._hash_val_entry.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 0))
        row += 1

        tk.Label(
            parent, text="Hash type", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 0))
        self._type_label = tk.Label(
            parent, textvariable=self._type_label_var,
            fg=SUCCESS, bg=BG, font=fonts.view_font(11), anchor="w",
        )
        self._type_label.grid(row=row, column=1, sticky="w", padx=15, pady=(5, 0))
        row += 1

        tk.Label(
            parent, text="Mode", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 10))
        self._mode_entry = tk.Entry(
            parent, textvariable=self._mode_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG, width=8,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mode_entry.grid(row=row, column=1, sticky="w", padx=15, pady=(5, 10))
        row += 1

        tk.Label(
            parent, text="Device", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(5, 5))

        self._hw_frame = tk.Frame(parent, bg=BG)
        self._hw_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))

        self._hw_label = tk.Label(
            self._hw_frame, text="Detecting hardware...", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        )
        self._hw_label.pack(side=tk.LEFT)

        self._hw_var = tk.StringVar(value="auto")
        self._hw_cpu_rb = None
        self._hw_gpu_rb = None
        row += 1

        tk.Label(
            parent, text="Wordlist", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 5))

        wl_frame = tk.Frame(parent, bg=BG)
        wl_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        wl_frame.columnconfigure(0, weight=1)

        self._wl_var = tk.StringVar()
        self._wl_path_label = tk.Label(wl_frame, textvariable=self._wl_var, fg=FG, bg=BG,
                                       font=fonts.view_font(9), anchor="w")
        self._wl_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_btn = tk.Label(wl_frame, text="  Browse...  ", bg="#222222", fg=FG,
                              font=fonts.view_font(10), relief=tk.FLAT, bd=0, padx=10, pady=4)
        browse_btn.pack(side=tk.LEFT)
        browse_btn.bind("<Button-1>", lambda e: self._browse_wordlist())
        browse_btn.bind("<Enter>", lambda e: browse_btn.config(bg="#333333"))
        browse_btn.bind("<Leave>", lambda e: browse_btn.config(bg="#222222"))
        row += 1

        tk.Label(
            parent, text="Rules file", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(5, 5))

        rules_frame = tk.Frame(parent, bg=BG)
        rules_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(5, 5))
        rules_frame.columnconfigure(0, weight=1)

        self._rules_var = tk.StringVar()
        self._rules_path_label = tk.Label(rules_frame, textvariable=self._rules_var, fg=FG, bg=BG,
                                          font=fonts.view_font(9), anchor="w")
        self._rules_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self._slow_var = tk.BooleanVar(value=False)
        self._slow_toggle = theme.Toggle(
            rules_frame, "-S", variable=self._slow_var,
            command=self._on_slow_toggle, padx=10, pady=4)
        self._slow_toggle.pack(side=tk.LEFT, padx=(0, 6))

        rules_browse_btn = tk.Label(rules_frame, text="  Browse...  ", bg="#222222", fg=FG,
                                    font=fonts.view_font(10), relief=tk.FLAT, bd=0, padx=10, pady=4)
        rules_browse_btn.pack(side=tk.LEFT)
        rules_browse_btn.bind("<Button-1>", lambda e: self._browse_rules())
        rules_browse_btn.bind("<Enter>", lambda e: rules_browse_btn.config(bg="#333333"))
        rules_browse_btn.bind("<Leave>", lambda e: rules_browse_btn.config(bg="#222222"))
        row += 1

        tk.Label(
            parent, text="Command", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(8, 2))

        cmd_frame = tk.Frame(parent, bg=BG)
        cmd_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 2))
        cmd_frame.columnconfigure(0, weight=1)

        self._cmd_text = tk.Text(
            cmd_frame, height=6, wrap=tk.WORD, bg=BG_WIDGET, fg=FG,
            insertbackground=FG, font=fonts.view_font(9),
            borderwidth=0, highlightthickness=1,
            highlightbackground="#333333", highlightcolor="#333333",
        )
        self._cmd_text.grid(row=0, column=0, sticky="ew")
        cmd_scroll = tk.Scrollbar(cmd_frame, orient=tk.VERTICAL,
                                  command=self._cmd_text.yview)
        cmd_scroll.configure(bg="#333333", troughcolor="#1a1a1a",
                             activebackground="#555555", width=10, borderwidth=0,
                             highlightthickness=0, elementborderwidth=0)
        cmd_scroll.grid(row=0, column=1, sticky="ns")
        self._cmd_text.configure(yscrollcommand=cmd_scroll.set)
        self._cmd_text.bind("<Control-a>",
                            lambda e: (self._cmd_text.tag_add("sel", "1.0", "end-1c"),
                                       "break")[1])
        row += 1

        hint_row = tk.Frame(parent, bg=BG)
        hint_row.grid(row=row, column=1, sticky="ew", padx=15, pady=(2, 0))
        hint_row.columnconfigure(0, weight=1)
        tk.Label(
            hint_row,
            text="Editable. The GUI rewrites it on changes; Elwand supplies "
                 "--outfile for <TMP> to read results.",
            font=fonts.view_font(8), fg=FG_DIM, bg=BG, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        reset_btn = tk.Label(hint_row, text="  Reset  ", bg="#222222", fg=FG,
                             font=fonts.view_font(9), relief=tk.FLAT, bd=0,
                             padx=8, pady=2, cursor="")
        reset_btn.grid(row=0, column=1, sticky="e")
        reset_btn.bind("<Button-1>", lambda e: self._update_cmd_preview())
        reset_btn.bind("<Enter>", lambda e: reset_btn.config(bg="#333333"))
        reset_btn.bind("<Leave>", lambda e: reset_btn.config(bg="#222222"))
        row += 1

        for var in (self._mode_var, self._hash_val_var, self._wl_var,
                    self._rules_var, self._hw_var):
            var.trace_add("write", lambda *a: self._update_cmd_preview())
        self._update_cmd_preview()

        self._panel = _StatusPanel(parent, row)
        row = self._panel.end_row

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(8, 10))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6, cursor="",
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        stop_btn = tk.Label(
            btn_frame, text="  Stop  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6, cursor="",
        )
        stop_btn.pack(side=tk.RIGHT, padx=(5, 0))
        stop_btn.bind("<Button-1>", lambda e: self._stop())
        stop_btn.bind("<Enter>", lambda e: stop_btn.config(bg="#333333"))
        stop_btn.bind("<Leave>", lambda e: stop_btn.config(bg="#222222"))

        start_btn = tk.Label(
            btn_frame, text="  Start  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6, cursor="",
        )
        start_btn.pack(side=tk.RIGHT, padx=(5, 0))
        start_btn.bind("<Button-1>", lambda e: self._start())
        start_btn.bind("<Enter>", lambda e: start_btn.config(bg="#333333"))
        start_btn.bind("<Leave>", lambda e: start_btn.config(bg="#222222"))

    # ─── Mask Tab ──────────────────────────────────────────────

    def _build_mask_tab(self, parent):
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)

        row = 0

        tk.Label(
            parent, text="Hash", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 2))

        hash_frame = tk.Frame(parent, bg=BG_WIDGET)
        hash_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 2))
        hash_frame.columnconfigure(0, weight=1)
        hash_frame.rowconfigure(0, weight=1)

        self._mask_hash_listbox = tk.Listbox(
            hash_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False, height=3,
        )
        self._mask_hash_listbox.grid(row=0, column=0, sticky="nsew")

        hash_scroll = tk.Scrollbar(hash_frame, orient=tk.VERTICAL,
                                   command=self._mask_hash_listbox.yview)
        hash_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        hash_scroll.grid(row=0, column=1, sticky="ns")
        self._mask_hash_listbox.configure(yscrollcommand=hash_scroll.set)
        self._mask_hash_listbox.bind("<<ListboxSelect>>", self._on_mask_hash_select)
        row += 1

        tk.Label(
            parent, text="Hash value", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(3, 0))
        self._mask_hash_val_entry = tk.Entry(
            parent, textvariable=self._hash_val_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mask_hash_val_entry.grid(row=row, column=1, sticky="ew", padx=15, pady=(3, 0))
        row += 1

        tk.Label(
            parent, text="Hash type", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(3, 0))
        self._mask_type_label = tk.Label(
            parent, textvariable=self._type_label_var,
            fg=SUCCESS, bg=BG, font=fonts.view_font(11), anchor="w",
        )
        self._mask_type_label.grid(row=row, column=1, sticky="w", padx=15, pady=(3, 0))
        row += 1

        tk.Label(
            parent, text="Mode", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(3, 5))
        self._mask_mode_entry = tk.Entry(
            parent, textvariable=self._mode_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG, width=8,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mask_mode_entry.grid(row=row, column=1, sticky="w", padx=15, pady=(3, 5))
        row += 1

        tk.Label(
            parent, text="Device", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(3, 3))
        self._mask_hw_frame = tk.Frame(parent, bg=BG)
        self._mask_hw_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(3, 3))
        self._mask_hw_placeholder = tk.Label(
            self._mask_hw_frame, text="Detecting hardware...",
            font=fonts.view_font(11), fg=FG_DIM, bg=BG,
        )
        self._mask_hw_placeholder.pack(side=tk.LEFT)
        row += 1

        tk.Label(
            parent, text="Mask", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(10, 5))

        mask_entry_frame = tk.Frame(parent, bg=BG)
        mask_entry_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(10, 5))
        mask_entry_frame.columnconfigure(0, weight=1)

        self._mask_var = tk.StringVar()
        self._mask_entry = tk.Entry(
            mask_entry_frame, textvariable=self._mask_var,
            bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._mask_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        help_label = tk.Label(
            mask_entry_frame, text=" ?l=a-z ?u=A-Z ?d=0-9 ?s=spc ?a=all",
            font=fonts.view_font(9), fg=FG_DIM, bg=BG,
        )
        help_label.pack(side=tk.RIGHT)
        self._mask_var.trace_add("write", self._on_mask_changed)
        row += 1

        tk.Label(
            parent, text="Quick masks", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(2, 3))

        quick_frame = tk.Frame(parent, bg=BG)
        quick_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(2, 3))

        quick_masks = [
            ("?l?l?l?l?l?l", "6 lower"),
            ("?l?l?l?l?l?l?l?l", "8 lower"),
            ("?l?l?l?l?d?d?d?d", "4 lower + 4 digits"),
            ("?u?l?l?l?l?l?l?l", "1 upper + 7 lower"),
            ("?u?l?l?l?l?l?d?d", "common password"),
            ("?d?d?d?d?d?d?d?d", "8 digits"),
            ("?a?a?a?a?a?a", "6 all-printable"),
        ]
        for mask, desc in quick_masks:
            qb = tk.Label(
                quick_frame, text=f" {desc} ", bg="#333333", fg=FG_DIM,
                font=fonts.view_font(8), relief=tk.FLAT, padx=6, pady=2,
            )
            qb.pack(side=tk.LEFT, padx=(0, 4), pady=2)
            qb.bind("<Button-1>", lambda e, m=mask: self._mask_var.set(m))
            qb.bind("<Enter>", lambda e, b=qb: b.config(fg=FG, bg="#444444"))
            qb.bind("<Leave>", lambda e, b=qb: b.config(fg=FG_DIM, bg="#333333"))
        row += 1

        tk.Label(
            parent, text="Custom charsets", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(8, 3))

        cs_frame = tk.Frame(parent, bg=BG)
        cs_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 3))
        cs_frame.columnconfigure(1, weight=1)

        self._mask_cs_vars = {}
        cs_hint = {"1": "e.g. ?l?d", "2": "e.g. ?u?d",
                   "3": "e.g. ?s", "4": "e.g. ?l?u?d"}
        for i, key in enumerate(["1", "2", "3", "4"]):
            tk.Label(
                cs_frame, text=f"-{key}", font=fonts.view_font(11),
                fg=FG_DIM, bg=BG,
            ).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=(1, 0))
            var = tk.StringVar()
            self._mask_cs_vars[key] = var
            tk.Entry(
                cs_frame, textvariable=var,
                bg=BG_WIDGET, fg=FG, insertbackground=FG,
                font=fonts.view_font(11), borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333",
                highlightbackground="#333333", width=20,
            ).grid(row=i, column=1, sticky="w", pady=(1, 0))
            tk.Label(
                cs_frame, text=cs_hint[key],
                font=fonts.view_font(8), fg=FG_DIM, bg=BG,
            ).grid(row=i, column=2, sticky="w", padx=(5, 0), pady=(1, 0))
        row += 1

        tk.Label(
            parent, text="Command", font=fonts.view_font_bold(11),
            fg=FG, bg=BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(8, 2))

        mcmd_frame = tk.Frame(parent, bg=BG)
        mcmd_frame.grid(row=row, column=1, sticky="ew", padx=15, pady=(8, 2))
        mcmd_frame.columnconfigure(0, weight=1)

        self._mask_cmd_text = tk.Text(
            mcmd_frame, height=6, wrap=tk.WORD, bg=BG_WIDGET, fg=FG,
            insertbackground=FG, font=fonts.view_font(9),
            borderwidth=0, highlightthickness=1,
            highlightbackground="#333333", highlightcolor="#333333",
        )
        self._mask_cmd_text.grid(row=0, column=0, sticky="ew")
        mcmd_scroll = tk.Scrollbar(mcmd_frame, orient=tk.VERTICAL,
                                   command=self._mask_cmd_text.yview)
        mcmd_scroll.configure(bg="#333333", troughcolor="#1a1a1a",
                              activebackground="#555555", width=10,
                              borderwidth=0, highlightthickness=0,
                              elementborderwidth=0)
        mcmd_scroll.grid(row=0, column=1, sticky="ns")
        self._mask_cmd_text.configure(yscrollcommand=mcmd_scroll.set)
        row += 1

        mhint_row = tk.Frame(parent, bg=BG)
        mhint_row.grid(row=row, column=1, sticky="ew", padx=15, pady=(2, 0))
        mhint_row.columnconfigure(0, weight=1)
        tk.Label(
            mhint_row,
            text="Editable. The GUI rewrites it on changes; Elwand supplies "
                 "--outfile for <TMP> to read results.",
            font=fonts.view_font(8), fg=FG_DIM, bg=BG, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        mreset_btn = tk.Label(mhint_row, text="  Reset  ", bg="#222222", fg=FG,
                              font=fonts.view_font(9), relief=tk.FLAT, bd=0,
                              padx=8, pady=2, cursor="")
        mreset_btn.grid(row=0, column=1, sticky="e")
        mreset_btn.bind("<Button-1>",
                        lambda e: self._update_mask_cmd_preview())
        mreset_btn.bind("<Enter>", lambda e: mreset_btn.config(bg="#333333"))
        mreset_btn.bind("<Leave>", lambda e: mreset_btn.config(bg="#222222"))
        row += 1

        for var in (self._mode_var, self._hash_val_var, self._hw_var,
                    self._mask_var):
            var.trace_add("write", lambda *a: self._update_mask_cmd_preview())
        for var in self._mask_cs_vars.values():
            var.trace_add("write", lambda *a: self._update_mask_cmd_preview())
        self._update_mask_cmd_preview()

        self._mask_panel = _StatusPanel(parent, row)
        row = self._mask_panel.end_row

        mask_btn_frame = tk.Frame(parent, bg=BG)
        mask_btn_frame.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(8, 10),
        )

        close_btn = tk.Label(
            mask_btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6, cursor="",
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        stop_btn = tk.Label(
            mask_btn_frame, text="  Stop  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6, cursor="",
        )
        stop_btn.pack(side=tk.RIGHT, padx=(5, 0))
        stop_btn.bind("<Button-1>", lambda e: self._stop())
        stop_btn.bind("<Enter>", lambda e: stop_btn.config(bg="#333333"))
        stop_btn.bind("<Leave>", lambda e: stop_btn.config(bg="#222222"))

        start_btn = tk.Label(
            mask_btn_frame, text="  Start  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6, cursor="",
        )
        start_btn.pack(side=tk.RIGHT, padx=(5, 0))
        start_btn.bind("<Button-1>", lambda e: self._start_mask())
        start_btn.bind("<Enter>", lambda e: start_btn.config(bg="#333333"))
        start_btn.bind("<Leave>", lambda e: start_btn.config(bg="#222222"))

        self._populate_mask_hashes()

    def _populate_mask_hashes(self):
        items = credential_db.load_hashes()
        if not items:
            return
        self._mask_hash_listbox.delete(0, tk.END)
        for item in items:
            htype = item.get("type", "")
            mode = self._hash_mode(item)
            mode_str = f"  [{mode}] " if mode else "  "
            label = f"{mode_str}{htype:<30} {item.get('hash', '')[:30]}"
            self._mask_hash_listbox.insert(tk.END, label)
        self._mask_hash_listbox.selection_set(0)
        self._on_mask_hash_select()

    def _on_mask_hash_select(self, event=None):
        items = credential_db.load_hashes()
        sel = self._mask_hash_listbox.curselection()
        if not sel or sel[0] >= len(items):
            return
        item = items[sel[0]]
        htype = item.get("type", "")
        mode = self._hash_mode(item)
        self._mode_var.set(mode or "")
        self._hash_val_var.set(item.get("hash", ""))
        self._type_label_var.set(htype)

    def _on_mask_changed(self, *_):
        mask = self._mask_var.get()
        if mask:
            self._mask_panel.info.config(
                text=f"Mask: {mask} ({mask.count('?')} chars)")
        else:
            self._mask_panel.info.config(text="Ready")

    def _build_mask_hw_buttons(self, hw):
        self._mask_hw_placeholder.destroy()

        options = [("auto", "  Auto  ")]
        if hw.get("cpu", True):
            options.append(("1", "  CPU  "))
        if hw.get("gpu", True):
            options.append(("2", "  GPU  "))
        self._hw_var.set("auto")
        self._mask_hw_seg = theme.Segmented(
            self._mask_hw_frame, options, self._hw_var,
            command=self._sync_hw_segments)
        self._mask_hw_seg.pack(side=tk.LEFT)

    def _sync_hw_segments(self):
        for attr in ("_hw_seg", "_mask_hw_seg"):
            seg = getattr(self, attr, None)
            if seg is not None:
                try:
                    seg.refresh()
                except Exception:
                    pass

    def _start_mask(self):
        text = (self._mask_cmd_text.get("1.0", tk.END).strip()
                if getattr(self, "_mask_cmd_text", None) else "")
        if not text:
            self._mask_panel.log("[!] Command is empty.", "error")
            return
        try:
            argv = shlex.split(text)
        except ValueError as e:
            self._mask_panel.log(f"[!] Invalid command: {e}", "error")
            return
        if any(a in ("<mode>", "<hash>", "<mask>") for a in argv):
            self._mask_panel.log(
                "[!] Select a hash, mode and mask (or edit the command).",
                "error")
            return

        charsets = {k: v.get().strip()
                    for k, v in self._mask_cs_vars.items() if v.get().strip()}

        self._begin_run("mask")
        self._mask_panel.start(
            "  ".join(argv[:7]) + (" \u2026" if len(argv) > 7 else ""))

        engine = HashcatEngine(
            mode=self._mode_var.get().strip() or None,
            hash_value=self._hash_val_var.get().strip() or None,
            mask=self._mask_var.get().strip() or None,
            custom_charsets=charsets,
            command=argv,
            on_output=lambda t, c=None: self._ui_q.put(("raw", "mask", t)),
            on_status=lambda st: self._ui_q.put(("status", "mask", st)),
            on_phase=lambda label: self._ui_q.put(("phase", "mask", label)),
            on_cracked=lambda hv, p: self._ui_q.put(("cracked", "mask", p)),
            on_done=lambda c, f=False: self._ui_q.put(("done", "mask", c, f)),
            on_progress=lambda d, t, r: self._ui_q.put(
                ("progress", "mask", d, t, r)),
        )
        self._engine = engine
        engine.start()

    # ─── Add Hash Tab ───────────────────────────────────────────

    def _build_add_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)

        self._add_sel_type = None

        tk.Label(
            parent, text="Type", font=fonts.view_font_bold(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        type_frame = tk.Frame(parent, bg=BG_WIDGET)
        type_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=15, pady=(0, 5))
        type_frame.columnconfigure(0, weight=1)
        type_frame.rowconfigure(0, weight=1)

        self._add_type_list = theme.listbox(type_frame, height=4)
        self._add_type_list.grid(row=0, column=0, sticky="nsew")
        self._add_type_list.bind("<<ListboxSelect>>", self._add_on_type_select)

        scrollbar = theme.scrollbar(type_frame, self._add_type_list)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._add_type_names = []
        self._add_type_modes = {}
        self._add_type_examples = {}
        try:
            import sqlite3
            db_path = str(_hashcat_db())
            if os.path.isfile(db_path):
                conn = sqlite3.connect(db_path)
                rows = conn.execute(
                    'SELECT "Hash-Mode", "Hash-Name", "Example" '
                    'FROM DefaultMode ORDER BY "Hash-Mode"'
                ).fetchall()
                for mode, name, example in rows:
                    self._add_type_list.insert(tk.END, f"  {name}")
                    self._add_type_names.append(name)
                    self._add_type_modes[name] = str(mode) if mode != -1 else ""
                    self._add_type_examples[name] = example
                conn.close()
                if self._add_type_names:
                    self._add_type_list.selection_set(0)
        except Exception:
            pass

        self._add_example_label = tk.Label(
            parent, text="", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, wraplength=600,
        )
        self._add_example_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=15, pady=(2, 5))

        fields = [
            ("Hash", "hash", ""),
            ("Salt", "salt", ""),
            ("Peper", "peper", ""),
            ("Hashcat mode", "hascat_mode", ""),
            ("Origin", "origin_obteined", "Added manually by user"),
        ]

        row = 3
        for label, key, default in fields:
            tk.Label(
                parent, text=f"{label}:", font=fonts.view_font(11),
                fg=FG_DIM, bg=BG,
            ).grid(row=row, column=0, sticky="w", padx=15, pady=(6, 0))
            var = tk.StringVar(value=default)
            theme.entry(parent, textvariable=var).grid(
                row=row, column=1, sticky="ew", padx=15, pady=(6, 0))
            setattr(self, f"_add_{key}_var", var)
            row += 1

        if self._add_type_names:
            self._add_on_type_select(None)

        self._add_feedback = tk.Label(
            parent, text="", font=fonts.view_font(11),
            fg=SUCCESS, bg=BG,
        )
        self._add_feedback.grid(row=row, column=0, columnspan=2, pady=(6, 0))
        row += 1

        add_btn_frame = tk.Frame(parent, bg=BG)
        add_btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=(10, 10))

        theme.button(add_btn_frame, "  Close  ", command=self._on_close).pack(
            side=tk.RIGHT, padx=(5, 0))
        theme.button(add_btn_frame, "  Add  ", command=self._add_save).pack(
            side=tk.RIGHT)

    def _add_on_type_select(self, event):
        idx = self._add_type_list.curselection()
        if idx and idx[0] < len(self._add_type_names):
            name = self._add_type_names[idx[0]]
            self._add_sel_type = name
            self._add_hascat_mode_var.set(self._add_type_modes.get(name, ""))
            example = self._add_type_examples.get(name, "")
            if example:
                show = example if len(example) < 80 else example[:80] + "..."
                self._add_example_label.config(text=f"  Example: {show}")
            else:
                self._add_example_label.config(text="")

    def _add_save(self):
        if not self._add_sel_type:
            self._add_feedback.config(text="Select a hash type.", fg=ERR_COLOR)
            return
        hval = self._add_hash_var.get().strip()
        if not hval:
            self._add_feedback.config(text="Hash value is required.", fg=ERR_COLOR)
            return
        for item in credential_db.load_hashes():
            if (item.get("type", "") == self._add_sel_type
                    and (item.get("hash", "") or "").strip().lower() == hval.lower()):
                self._add_feedback.config(
                    text="Hash already in inventory.", fg=ERR_COLOR)
                return
        credential_db.save_hash_entry(
            self._add_sel_type,
            hval,
            self._add_salt_var.get().strip(),
            self._add_peper_var.get().strip(),
            self._add_hascat_mode_var.get().strip(),
            self._add_origin_obteined_var.get().strip(),
        )
        self.result = True
        self._add_feedback.config(text="Done.", fg=SUCCESS)
        self.after(1500, lambda: self._add_feedback.config(text=""))
        self._refresh_hash_list()
        if self._on_hash_added:
            try:
                self._on_hash_added()
            except Exception:
                pass

    # ─── Shared Methods ─────────────────────────────────────────

    def _refresh_hash_list(self):
        self._hash_items.clear()
        self._hash_listbox.delete(0, tk.END)
        self._modes_by_type.clear()
        self._populate_hashes()
        if hasattr(self, "_mask_hash_listbox"):
            self._populate_mask_hashes()

    def _populate_hashes(self):
        items = credential_db.load_hashes()
        if not items:
            return

        try:
            import sqlite3
            conn = sqlite3.connect(str(_hashcat_db()))
            rows = conn.execute(
                'SELECT "Hash-Name", "Hash-Mode" FROM DefaultMode'
            ).fetchall()
            for name, mode in rows:
                self._modes_by_type[name] = "" if mode == -1 else str(mode)
            conn.close()
        except Exception:
            pass

        for item in items:
            self._hash_items.append(item)
            htype = item.get("type", "")
            mode = self._hash_mode(item)
            mode_str = f"  [{mode}] " if mode else "  "
            label = f"{mode_str}{htype:<30} {item.get('hash', '')[:30]}"
            self._hash_listbox.insert(tk.END, label)
        if self._hash_items:
            self._hash_listbox.selection_set(0)
            self._on_hash_select()

    def _hash_mode(self, item):
        """The hashcat mode to use: the stored one wins, else the type's."""
        stored = (item.get("hascat_mode") or "").strip()
        if stored and stored != "-1":
            return stored
        db_mode = (self._modes_by_type.get(item.get("type", ""), "") or "").strip()
        return "" if db_mode == "-1" else db_mode

    def _on_hash_select(self, event=None):
        sel = self._hash_listbox.curselection()
        if not sel or sel[0] >= len(self._hash_items):
            return
        item = self._hash_items[sel[0]]
        htype = item.get("type", "")
        mode = self._hash_mode(item)
        self._mode_var.set(mode or "")
        self._hash_val_var.set(item.get("hash", ""))
        self._type_label_var.set(htype)

    def _browse_wordlist(self):
        from src.elwand_paths import lst_dir
        f = windowing.ask_open_file(
            self, title="Select wordlist",
            initialdir=str(lst_dir()),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            self._wl_var.set(f)
            self._evaluate_slow()

    def _browse_rules(self):
        from src.elwand_paths import rules_dir
        f = windowing.ask_open_file(
            self, title="Select rules file",
            initialdir=str(rules_dir()),
            filetypes=[("Rule files", "*.rule"), ("All files", "*.*")])
        if f:
            self._rules_var.set(f)
            self._evaluate_slow()

    def _evaluate_slow(self):
        """Decide -S from the wordlist/rules lengths (+ GPU compute units)."""
        recommended = False
        wl = self._wl_var.get().strip()
        rules = self._rules_var.get().strip()
        if wl and rules and os.path.isfile(wl) and os.path.isfile(rules):
            w = count_lines(wl)
            r = count_lines(rules)
            if (w > 0 and r >= _S_RULES_MIN
                    and w * r >= _S_WORK_MIN
                    and self._mcu > 0 and w < self._mcu * _S_MCU_FACTOR):
                recommended = True
        self._slow_recommended = recommended
        if recommended:
            self._slow_var.set(True)
            if getattr(self, "_slow_toggle", None):
                self._slow_toggle.refresh()
        self._update_cmd_preview()

    def _on_slow_toggle(self):
        self._update_cmd_preview()
        if not self._slow_var.get() and self._slow_recommended:
            self._panel.log(
                "[!] The -S option is recommended here (small wordlist, "
                "large ruleset). Enable it for a much faster attack.",
                "warn")

    def _detect_hardware(self):
        threading.Thread(target=self._run_hw_detect, daemon=True).start()

    def _run_hw_detect(self):
        hw = HashcatEngine.detect_hardware()
        try:
            self.after(0, lambda: self._on_hw_detected(hw))
        except tk.TclError:
            pass

    def _on_hw_detected(self, hw):
        if not self.winfo_exists():
            return
        self._hw = hw
        self._mcu = hw.get("mcu", 0)
        self._hw_label.destroy()

        has_cpu = hw.get("cpu", True)
        has_gpu = hw.get("gpu", True)

        options = [("auto", "  Auto  ")]
        if has_cpu:
            options.append(("1", "  CPU  "))
        if has_gpu:
            options.append(("2", "  GPU  "))
        self._hw_var.set("auto")
        self._hw_seg = theme.Segmented(
            self._hw_frame, options, self._hw_var,
            command=self._sync_hw_segments)
        self._hw_seg.pack(side=tk.LEFT)

        if hasattr(self, "_mask_hw_placeholder"):
            self._build_mask_hw_buttons(hw)

        # Now that the GPU compute units are known, re-check -S.
        self._evaluate_slow()

    def _update_cmd_preview(self):
        if not getattr(self, "_cmd_text", None):
            return
        mode = self._mode_var.get().strip() or "<mode>"
        hash_val = self._hash_val_var.get().strip() or "<hash>"
        wl = self._wl_var.get().strip() or "<wordlist>"
        rules = self._rules_var.get().strip() or None
        backend = self._hw_var.get()
        if backend == "auto":
            backend = None
        cmd = build_command(mode, hash_val, wordlist=wl, rules_file=rules,
                            backend=backend, binary="hashcat",
                            outfile="<TMP>", status_json=True,
                            slow_candidates=self._slow_var.get())
        try:
            self._cmd_text.delete("1.0", tk.END)
            self._cmd_text.insert("1.0", format_command(cmd))
        except tk.TclError:
            pass

    def _update_mask_cmd_preview(self):
        if not getattr(self, "_mask_cmd_text", None):
            return
        mode = self._mode_var.get().strip() or "<mode>"
        hash_val = self._hash_val_var.get().strip() or "<hash>"
        mask = self._mask_var.get().strip() or "<mask>"
        charsets = {k: v.get().strip()
                    for k, v in self._mask_cs_vars.items() if v.get().strip()}
        backend = self._hw_var.get()
        if backend == "auto":
            backend = None
        cmd = build_command(mode, hash_val, mask=mask,
                            custom_charsets=charsets, backend=backend,
                            binary="hashcat", outfile="<TMP>", status_json=True)
        try:
            self._mask_cmd_text.delete("1.0", tk.END)
            self._mask_cmd_text.insert("1.0", format_command(cmd))
        except tk.TclError:
            pass

    def _start(self):
        text = (self._cmd_text.get("1.0", tk.END).strip()
                if getattr(self, "_cmd_text", None) else "")
        if not text:
            self._panel.log("[!] Command is empty.", "error")
            return
        try:
            argv = shlex.split(text)
        except ValueError as e:
            self._panel.log(f"[!] Invalid command: {e}", "error")
            return
        if any(a in ("<mode>", "<hash>", "<wordlist>") for a in argv):
            self._panel.log(
                "[!] Select hash, mode and wordlist (or edit the command).",
                "error")
            return

        self._begin_run("crack")
        self._panel.start("  ".join(argv[:7]) + (" \u2026" if len(argv) > 7 else ""))

        engine = HashcatEngine(
            mode=self._mode_var.get().strip() or None,
            hash_value=self._hash_val_var.get().strip() or None,
            wordlist=self._wl_var.get().strip() or None,
            command=argv,
            on_output=lambda t, c=None: self._ui_q.put(("raw", "crack", t)),
            on_status=lambda st: self._ui_q.put(("status", "crack", st)),
            on_phase=lambda label: self._ui_q.put(("phase", "crack", label)),
            on_cracked=lambda hv, p: self._ui_q.put(("cracked", "crack", p)),
            on_done=lambda c, f=False: self._ui_q.put(("done", "crack", c, f)),
            on_progress=lambda d, t, r: self._ui_q.put(
                ("progress", "crack", d, t, r)),
        )
        self._engine = engine
        engine.start()

    def _begin_run(self, tab):
        self._cracked = []
        self._panel_for(tab).reset()
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
        self._engine = None
        self._start_drain()
        self._start_ticker()

    def _panel_for(self, tab):
        return self._mask_panel if tab == "mask" else self._panel

    def _start_drain(self):
        if self._drain_id is None and not self._closing:
            self._drain_id = self.after(50, self._drain)

    def _drain(self):
        self._drain_id = None
        try:
            while True:
                self._apply_ui(self._ui_q.get_nowait())
        except queue.Empty:
            pass
        if self._engine is not None and not self._closing:
            self._drain_id = self.after(50, self._drain)

    def _start_ticker(self):
        if self._tick_id is None and not self._closing:
            self._tick_id = self.after(1000, self._tick)

    def _tick(self):
        self._tick_id = None
        if self._closing or not self.winfo_exists():
            return
        for panel in (getattr(self, "_panel", None),
                      getattr(self, "_mask_panel", None)):
            if panel is not None:
                panel.tick()
        if self._engine is not None:
            self._tick_id = self.after(1000, self._tick)

    def _apply_ui(self, item):
        kind = item[0]
        if kind == "raw":
            self._panel_for(item[1]).log_raw(item[2])
        elif kind == "status":
            self._panel_for(item[1]).set_status(item[2])
        elif kind == "phase":
            self._panel_for(item[1]).phase(item[2])
        elif kind == "progress":
            self._panel_for(item[1]).set_progress(item[2], item[3], item[4])
        elif kind == "cracked":
            self._panel_for(item[1]).cracked(item[2])
            try:
                credential_db.save_password(item[2])
            except Exception:
                pass
        elif kind == "done":
            self._panel_for(item[1]).finish(item[2], item[3])
            self._engine = None

    def _stop(self):
        if self._engine:
            self._engine.stop()
        self._panel.log("[*] Stopped.", "muted")
        self._mask_panel.log("[*] Stopped.", "muted")

    # ─── Detect Tab ─────────────────────────────────────────────

    def _build_detect_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=0)
        parent.rowconfigure(3, weight=0)

        tk.Label(
            parent, text="Paste text or load a file to detect hash types",
            font=fonts.view_font_bold(11), fg=FG, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        text_frame = tk.Frame(parent, bg=BG_WIDGET)
        text_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self._detect_text = tk.Text(
            text_frame, bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            wrap=tk.WORD, height=6,
        )
        self._detect_text.grid(row=0, column=0, sticky="nsew")

        detect_scroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                     command=self._detect_text.yview)
        detect_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                                width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        detect_scroll.grid(row=0, column=1, sticky="ns")
        self._detect_text.configure(yscrollcommand=detect_scroll.set)

        detect_btn_frame = tk.Frame(parent, bg=BG)
        detect_btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))

        load_btn = tk.Label(
            detect_btn_frame, text="  Load file...  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6,
        )
        load_btn.pack(side=tk.LEFT)
        load_btn.bind("<Button-1>", lambda e: self._detect_load_file())
        load_btn.bind("<Enter>", lambda e: load_btn.config(bg="#333333"))
        load_btn.bind("<Leave>", lambda e: load_btn.config(bg="#222222"))

        detect_btn = tk.Label(
            detect_btn_frame, text="  Detect  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6,
        )
        detect_btn.pack(side=tk.LEFT, padx=(10, 0))
        detect_btn.bind("<Button-1>", lambda e: self._detect_hashes())
        detect_btn.bind("<Enter>", lambda e: detect_btn.config(bg="#333333"))
        detect_btn.bind("<Leave>", lambda e: detect_btn.config(bg="#222222"))

        self._detect_count_label = tk.Label(
            parent, text="", font=fonts.view_font(9),
            fg=FG_DIM, bg=BG, anchor="w",
        )
        self._detect_count_label.grid(row=3, column=0, sticky="w", padx=15, pady=(0, 5))

        results_frame = tk.Frame(parent, bg=BG_WIDGET)
        results_frame.grid(row=4, column=0, sticky="nsew", padx=15, pady=(0, 5))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        self._detect_listbox = tk.Listbox(
            results_frame, bg=BG_WIDGET, fg=FG,
            selectbackground=SEL_BG, selectforeground=FG,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False,
        )
        self._detect_listbox.grid(row=0, column=0, sticky="nsew")

        list_scroll = tk.Scrollbar(results_frame, orient=tk.VERTICAL,
                                   command=self._detect_listbox.yview)
        list_scroll.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                              width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self._detect_listbox.configure(yscrollcommand=list_scroll.set)

        self._detect_listbox.bind("<Double-Button-1>", lambda e: self._detect_save_selected())

        self._detect_results = []

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.grid(row=5, column=0, sticky="ew", padx=15, pady=(10, 10))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        save_sel_btn = tk.Label(
            btn_frame, text="  Save selected  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=15, pady=6,
        )
        save_sel_btn.pack(side=tk.RIGHT)
        save_sel_btn.bind("<Button-1>", lambda e: self._detect_save_selected())
        save_sel_btn.bind("<Enter>", lambda e: save_sel_btn.config(bg="#333333"))
        save_sel_btn.bind("<Leave>", lambda e: save_sel_btn.config(bg="#222222"))

    def _build_detect_db(self):
        if self._detect_db is not None:
            return
        self._detect_db = {"prefix": [], "length": defaultdict(list), "structured": []}
        try:
            db_path = str(_hashcat_db())
            if not os.path.isfile(db_path):
                return
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                'SELECT "Hash-Mode", "Hash-Name", "Example" FROM DefaultMode'
            ).fetchall()
            conn.close()
        except Exception:
            return

        for mode, name, example in rows:
            if not example or example.startswith("http"):
                continue
            mode = str(mode) if mode != -1 else ""
            hash_part = example.split(":")[0]

            prefix = _extract_prefix(hash_part)
            if prefix:
                if prefix == "$2a$" or prefix == "$2b$" or prefix == "$2y$":
                    prefix = r"\$2[aby]\$"
                else:
                    prefix = re.escape(prefix)
                pref_re = re.compile(r"(?:^|\s)(" + prefix + r"\S+)")
                self._detect_db["prefix"].append((pref_re, mode, name, hash_part))
                continue

            fields = example.split(":")
            if len(fields) >= 3:
                pattern = _build_structured_pattern(fields)
                if pattern:
                    try:
                        compiled = re.compile(pattern)
                        self._detect_db["structured"].append((compiled, mode, name))
                    except re.error:
                        pass
                continue

            cs = _charset_type(hash_part)
            if cs:
                key = (len(hash_part), cs)
                self._detect_db["length"][key].append((mode, name))

    def _detect_hashes(self):
        self._build_detect_db()
        if not self._detect_db:
            return

        text = self._detect_text.get("1.0", tk.END).strip()
        if not text:
            self._detect_count_label.config(text="")
            self._detect_listbox.delete(0, tk.END)
            self._detect_results.clear()
            return

        results = []
        seen = set()

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            matched = False
            if ":" in line:
                for regex, mode, name in self._detect_db["structured"]:
                    if regex.match(line):
                        key = f"{mode}:{line[:40]}"
                        if key not in seen:
                            seen.add(key)
                            results.append((line, [(mode, name)]))
                        matched = True
                        break

            tokens = _extract_tokens(line) if not matched else []
            for token in tokens:
                if token in seen:
                    continue
                matches = self._match_token(token)
                if matches:
                    seen.add(token)
                    results.append((token, matches))

        self._detect_results = results
        self._detect_listbox.delete(0, tk.END)

        if results:
            self._detect_count_label.config(
                text=f"  {len(results)} hash(es) found")
            for token, matches in results:
                for mode, name in matches:
                    display = token if len(token) <= 40 else token[:37] + "..."
                    mode_str = f"[{mode}]" if mode else "[?]"
                    self._detect_listbox.insert(
                        tk.END, f"  {mode_str:<8} {name:<28} {display}")
        else:
            self._detect_count_label.config(text="  No hashes detected")

    def _match_token(self, token):
        matches = []
        for pref_re, mode, name, _example in self._detect_db["prefix"]:
            if pref_re.match(token) or pref_re.search(token):
                matches.append((mode, name))
        if matches:
            return matches
        for charset in ("hex", "crypt", "b64"):
            cs = _charset_type_max(token, charset)
            if cs:
                key = (len(token), cs)
                matches.extend(self._detect_db["length"].get(key, []))
                if matches:
                    break
        return matches

    def _detect_load_file(self):
        f = windowing.ask_open_file(
            self, title="Load file for hash detection",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not f:
            return
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            return
        self._detect_text.delete("1.0", tk.END)
        self._detect_text.insert("1.0", content)

    def _detect_save_selected(self):
        sel = self._detect_listbox.curselection()
        if not sel or not self._detect_results:
            return
        line_idx = sel[0]
        current = 0
        for token, matches in self._detect_results:
            count = len(matches)
            if current + count > line_idx:
                match_idx = line_idx - current
                mode, name = matches[match_idx]
                credential_db.save_hash_entry(
                    hash_type=name,
                    hash_value=token,
                    hascat_mode=mode,
                    origin="detected",
                )
                self._detect_count_label.config(
                    text=f"  Saved: [{mode}] {name}")
                self._refresh_hash_list()
                self.after(1500, lambda: self._detect_count_label.config(
                    text=f"  {len(self._detect_results)} hash(es) found"))
                return
            current += count

    def _on_close(self):
        self._closing = True
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
        for attr in ("_drain_id", "_tick_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        self.destroy()


# ─── Hash Detection Helpers ─────────────────────────────────────

_HEX_RE = re.compile(r"^[a-fA-F0-9]+$")
_CRYPT_RE = re.compile(r"^[./0-9A-Za-z]+$")
_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")
_TOKEN_RE = re.compile(
    r"\b[a-fA-F0-9]{16,}\b"
    r"|\b[./0-9A-Za-z]{13,}\b"
    r"|\b[A-Za-z0-9+/=]{20,}\b"
)


def _extract_prefix(s):
    if s.startswith("$"):
        m = re.match(r"(\$[^$]+\$)", s)
        if m:
            return m.group(1)
    if s.startswith("{") and "}" in s:
        m = re.match(r"(\{[^}]+\})", s)
        if m:
            return m.group(1)
    return None


def _build_structured_pattern(fields):
    parts = []
    for i, f in enumerate(fields):
        f = f.strip()
        if not f:
            parts.append(r":?")
        elif _HEX_RE.match(f):
            n = len(f)
            if i == len(fields) - 1 and n >= 32:
                parts.append(r"[a-fA-F0-9]{32,}")
            else:
                parts.append(f"[a-fA-F0-9]{{{n}}}")
        elif _CRYPT_RE.match(f):
            parts.append(f"[./0-9A-Za-z]{{{len(f)}}}")
        else:
            parts.append(r"[^\s:]+")
    return r"^" + r":".join(parts) + r"$"


def _charset_type(s):
    if _HEX_RE.match(s):
        return "hex"
    if _CRYPT_RE.match(s):
        return "crypt"
    if _B64_RE.match(s):
        return "b64"
    return None


def _charset_type_max(s, default_cs):
    if default_cs == "hex" and _HEX_RE.match(s):
        return "hex"
    if default_cs == "crypt" and _CRYPT_RE.match(s):
        return "crypt"
    if default_cs == "b64" and _B64_RE.match(s):
        return "b64"
    return None


def _extract_tokens(line):
    if line.startswith("$") or line.startswith("{"):
        return [line]
    tokens = []
    for token in _TOKEN_RE.findall(line):
        if token and not _is_junk(token):
            tokens.append(token)
    return tokens


_JUNK_RE = re.compile(
    r"^(\d)\1{7,}$"             # all same digit  1111111111111111
    r"|^0+$"                     # all zeros      0000000000000000
    r"|^[a-fA-F](\d)\1{6,}$"    # hex with trailing repeated digit
)


def _is_junk(token):
    if not token:
        return True
    s = set(token.lower())
    if len(s) <= 2:
        return True
    if _JUNK_RE.match(token):
        return True
    return False
