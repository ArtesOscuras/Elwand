import re
from src.gui import fonts, windowing
import json
import os
import tkinter as tk
from datetime import datetime
from .base import BaseView
from src.shells import shell_db, send_command, send_raw
from src.elwand_paths import evidence_dir as _evidence_dir

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"

_ANSI_FG = {
    30: "#555555", 31: "#f44747", 32: "#00cc66", 33: "#ce9178",
    34: "#5ba3ec", 35: "#c586c0", 36: "#4ec9b0", 37: "#ffffff",
    90: "#888888", 91: "#ff6b6b", 92: "#4cdf8b", 93: "#e5c07b",
    94: "#7fc6f0", 95: "#d4a0d4", 96: "#70d4c8", 97: "#ffffff",
}
_ANSI_BG = {
    40: "#1a1a1a", 41: "#5c1a1a", 42: "#1a3c1a", 43: "#4c3c1a",
    44: "#1a2a4c", 45: "#3c1a4c", 46: "#1a3c3c", 47: "#555555",
    100: "#333333", 101: "#7c2a2a", 102: "#2a5c2a", 103: "#6c5c2a",
    104: "#2a4a7c", 105: "#5c2a7c", 106: "#2a5c5c", 107: "#888888",
}


class _RecordDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None

        self.title("Record Shell Evidence")
        windowing.size_dialog(self, 420, 160)
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=1)

        tk.Label(
            self,             text="Evidence name:", font=fonts.view_font(11),
            fg=BRIGHT, bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 0))
        tk.Label(
            self,             text="(name for the evidence folder)", font=fonts.view_font(9),
            fg=MUTED, bg="#111111",
        ).grid(row=1, column=0, sticky="w", padx=15, pady=(0, 5))

        self._name_var = tk.StringVar()
        tk.Entry(
            self, textvariable=self._name_var,
            bg="#000000", fg=BRIGHT, insertbackground=BRIGHT,
            font=fonts.view_font(12), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 10))

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 15))

        cancel_btn = tk.Label(
            btn_frame, text="  Cancel  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.bind("<Button-1>", lambda e: self.destroy())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#333333"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg="#222222"))

        start_btn = tk.Label(
            btn_frame, text="  Start Recording  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        start_btn.pack(side=tk.RIGHT)
        start_btn.bind("<Button-1>", lambda e: self._select())
        start_btn.bind("<Enter>", lambda e: start_btn.config(bg="#333333"))
        start_btn.bind("<Leave>", lambda e: start_btn.config(bg="#222222"))

        self.bind("<Return>", lambda e: self._select())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _select(self):
        name = self._name_var.get().strip()
        if name:
            self.result = name
            self.destroy()


def _evidence_dir_local():
    return str(_evidence_dir())


def _sanitize(name):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


class ShellDetailView(BaseView):
    name = "shell_detail"
    description = "Shell interaction view"

    def __init__(self, parent, sid, **kwargs):
        self._sid = sid
        self._recording = False
        self._record_name = ""
        self._record_tdir = ""
        self._record_buffer = []
        session = shell_db.get_session(sid)
        stype = (session or {}).get("type", "")
        if stype == "FTP":
            self._prompt = "ftp> "
        elif stype == "SFTP":
            self._prompt = "sftp> "
        elif stype == "WINRM":
            self._prompt = "PS> "
        else:
            self._prompt = "$ "
        self._freeze_mark = None
        self._history = []
        self._history_idx = -1
        self._partial_input = ""
        self._use_ansi = False
        self._ansi_tags = {}
        self._strip_echo_cmd = None
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

        terminal_frame = tk.Frame(self, bg="#000000")
        terminal_frame.grid(row=1, column=0, sticky="nsew", padx=(200, 200), pady=(0, 5))
        terminal_frame.columnconfigure(0, weight=1)
        terminal_frame.rowconfigure(0, weight=1)

        self.terminal = tk.Text(
            terminal_frame,
            bg="#000000", fg=BRIGHT,
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            cursor="xterm", wrap=tk.WORD,
            insertbackground=BRIGHT,
            pady=10, padx=10,
        )
        self.terminal.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(terminal_frame, orient=tk.VERTICAL, command=self.terminal.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.terminal.configure(yscrollcommand=scrollbar.set)

        self.terminal.tag_configure("muted", foreground=MUTED)
        self.terminal.tag_configure("bright", foreground=BRIGHT)
        self.terminal.tag_configure("protected", foreground=BRIGHT)
        self.terminal.tag_configure("info", foreground=INFO)
        self.terminal.tag_configure("error", foreground="#f44747")
        self.terminal.tag_configure("prompt", foreground=SUCCESS)

        self.terminal.bind("<Return>", self._on_enter)
        self.terminal.bind("<Control-c>", self._on_ctrl_c)
        self.terminal.bind("<BackSpace>", self._on_backspace)
        self.terminal.bind("<Delete>", self._on_backspace)
        self.terminal.bind("<Key>", self._on_key)
        self.terminal.bind("<KeyRelease>", self._on_key_release)
        self.terminal.bind("<Button-1>", self._on_click)
        self.terminal.bind("<Up>", self._on_history_up)
        self.terminal.bind("<Down>", self._on_history_down)
        self.terminal.bind("<Home>", self._jump_to_prompt)
        self.terminal.bind("<Control-a>", self._jump_to_prompt)
        self.terminal.bind("<Configure>", self._on_terminal_resize)

        bar = tk.Frame(self, bg="#000000")
        bar.grid(row=2, column=0, sticky="ew", padx=(200, 200), pady=(0, 10))

        self._record_btn = tk.Label(
            bar, text="  Record evidence  ",
            bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        self._record_btn.pack(side=tk.RIGHT)
        self._record_btn.bind("<Button-1>", lambda e: self._on_record())
        self._record_btn.bind("<Enter>", lambda e: self._record_btn.config(bg="#333333") if not self._recording else None)
        self._record_btn.bind("<Leave>", lambda e: self._record_btn.config(bg="#222222") if not self._recording else None)

        from .shell_list import is_agent_allowed, toggle_agent_shell
        agent_on = is_agent_allowed(self._sid)
        self._agent_toggle = tk.Label(
            bar, text="Agent: ON" if agent_on else "Agent: OFF",
            bg="#222222",
            fg=SUCCESS if agent_on else "#f44747",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=12, pady=6, cursor="",
        )
        self._agent_toggle.pack(side=tk.RIGHT, padx=(0, 10))
        self._agent_toggle.bind("<Button-1>", lambda e: self._on_agent_toggle())
        self._agent_toggle.bind("<Enter>", lambda e: self._agent_toggle.config(bg="#333333"))
        self._agent_toggle.bind("<Leave>", lambda e: self._agent_toggle.config(bg="#222222"))

        self._last_output = ""
        self._poll_id = None
        self._resize_id = None

    def _insert_prompt(self):
        self.terminal.insert(tk.END, "\n", "bright")
        self._freeze_mark = self.terminal.index("insert")
        self.terminal.insert(tk.END, self._prompt, "prompt")
        self.terminal.mark_set("prompt", "insert")
        self.terminal.mark_gravity("prompt", tk.LEFT)
        self.terminal.see(tk.END)

    def _protect(self, start=None, end=None):
        self.terminal.tag_add("protected", start or "1.0", end or self._freeze_mark)

    def _jump_to_prompt(self, event=None):
        self.terminal.mark_set("insert", self.terminal.index("prompt"))
        return "break"

    def _on_click(self, event):
        self.terminal.focus_set()
        self.terminal.mark_set("insert", tk.END)
        self.terminal.see(tk.END)
        return "break"

    def _on_key(self, event):
        if self.terminal.compare("insert", "<", "prompt"):
            self.terminal.mark_set("insert", tk.END)
        c = event.keysym
        if c in ("Left", "Right"):
            prompt_idx = self.terminal.index("prompt")
            insert_idx = self.terminal.index("insert")
            if c == "Left" and self.terminal.compare(insert_idx, "==", prompt_idx):
                return "break"

    def _on_key_release(self, event):
        self._protect("1.0", self._freeze_mark)

    def _on_backspace(self, event):
        if self.terminal.compare("insert", "<=", "prompt"):
            return "break"

    def _get_current_cmd(self):
        return self.terminal.get("prompt", "end-1c")

    def _lock_and_send(self, cmd):
        self.terminal.delete("prompt", tk.END)
        self.terminal.insert(tk.END, cmd + "\n", "bright")
        self._freeze_mark = self.terminal.index("insert")
        self._protect("1.0", self._freeze_mark)

        if cmd.strip():
            self._history.append(cmd.strip())
            self._history_idx = len(self._history)
            send_command(self._sid, cmd)

        s = shell_db.get_session(self._sid)
        if s:
            cwd = s.get("winrm_cwd")
            if cwd:
                self._prompt = f"PS {cwd}> "
        self._insert_prompt()

    def _on_enter(self, event):
        cmd = self._get_current_cmd()
        self.terminal.delete("prompt", tk.END)
        if cmd.strip().lower() == "exit":
            if self._on_back_click:
                self._on_back_click()
            return "break"
        if cmd.strip().lower() == "clear":
            self.terminal.delete("1.0", tk.END)
            self._freeze_mark = "1.0"
            self._protect("1.0", self._freeze_mark)
            s = shell_db.get_session(self._sid)
            if s:
                cwd = s.get("winrm_cwd")
                if cwd:
                    self._prompt = f"PS {cwd}> "
            self._insert_prompt()
            return "break"
        self._lock_and_send(cmd)
        return "break"

    def _on_ctrl_c(self, event):
        s = shell_db.get_session(self._sid)
        if s and s["status"] == "connected":
            rs = s.get("winrm_runspace")
            if rs:
                try:
                    rs.interrupt()
                except Exception:
                    pass
            else:
                send_raw(self._sid, "\x03")
        self.terminal.insert(tk.END, "^C\n", "muted")
        self._freeze_mark = self.terminal.index("insert")
        self._protect("1.0", self._freeze_mark)
        self._insert_prompt()
        return "break"

    def _on_history_up(self, event):
        if not self._history:
            return "break"
        if self._history_idx == len(self._history):
            self._partial_input = self._get_current_cmd()
        if self._history_idx > 0:
            self._history_idx -= 1
            self.terminal.delete("prompt", tk.END)
            self.terminal.insert("prompt", self._history[self._history_idx])
        return "break"

    def _on_history_down(self, event):
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.terminal.delete("prompt", tk.END)
            self.terminal.insert("prompt", self._history[self._history_idx])
        elif self._history_idx == len(self._history) - 1:
            self._history_idx = len(self._history)
            self.terminal.delete("prompt", tk.END)
            self.terminal.insert("prompt", self._partial_input)
        return "break"

    def _on_record(self):
        if self._recording:
            self._stop_recording()
        else:
            dialog = _RecordDialog(self)
            if dialog.result:
                self._start_recording(dialog.result)

    def _on_agent_toggle(self):
        from .shell_list import toggle_agent_shell, is_agent_allowed
        on = toggle_agent_shell(self._sid)
        self._agent_toggle.config(
            text="Agent: ON" if on else "Agent: OFF",
            fg=SUCCESS if on else "#f44747",
        )

    def _start_recording(self, name):
        self._record_name = _sanitize(name)
        base = _evidence_dir_local()
        self._record_tdir = os.path.join(base, self._record_name)
        os.makedirs(self._record_tdir, exist_ok=True)
        self._recording = True
        self._record_buffer = []

        s = shell_db.get_session(self._sid)
        meta = {
            "type": "shell_evidence",
            "name": name,
            "shell_id": self._sid,
            "shell_ip": s["ip"] if s else "",
            "started_at": datetime.now().isoformat(),
        }
        with open(os.path.join(self._record_tdir, "session.json"), "w") as f:
            json.dump(meta, f, indent=2)

        self._update_record_btn()
        self._append_output("[recording started]\n", "info")

    def _stop_recording(self):
        self._recording = False

        output_path = os.path.join(self._record_tdir, "shell_output.txt")
        buffer_text = "".join(self._record_buffer)
        with open(output_path, "w") as f:
            f.write(buffer_text)

        with open(os.path.join(self._record_tdir, "session.json")) as f:
            meta = json.load(f)
        meta["ended_at"] = datetime.now().isoformat()
        meta["output_lines"] = len(self._record_buffer)
        with open(os.path.join(self._record_tdir, "session.json"), "w") as f:
            json.dump(meta, f, indent=2)

        self._update_record_btn()
        self._append_output("[recording stopped]\n", "info")

    def _update_record_btn(self):
        if self._recording:
            self._record_btn.config(
                text="  Stop recording  ",
                fg=INFO, bg="#331111",
            )
        else:
            self._record_btn.config(
                text="  Record evidence  ",
                fg=BRIGHT, bg="#222222",
            )

    def _on_terminal_resize(self, event=None):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._resize_id = self.after(500, self._do_resize)

    def _do_resize(self):
        self._resize_id = None

    def _resize_terminal(self):
        pass

    def on_activate(self):
        s = shell_db.get_session(self._sid)
        if s:
            self._title_label.config(
                text=f"Shell #{s['id']} — {s['ip']} ({s['status']})"
            )
        if self.terminal.get("1.0", tk.END).strip() == "":
            self._freeze_mark = "1.0"
            self._protect("1.0", self._freeze_mark)
            self._append_output("[connected]\n", "info")
            self._insert_prompt()
        self.after(100, lambda: self.terminal.focus_set())
        self.after(500, self._poll)

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        if self._recording:
            self._stop_recording()

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _poll(self):
        moved = False
        agent_cmd = None
        touch = shell_db.pop_agent_touch(self._sid)
        if touch:
            self._freeze_mark = self.terminal.index(tk.END)
            self._protect("1.0", self._freeze_mark)
            if isinstance(touch, str):
                agent_cmd = touch
            moved = True

        if agent_cmd:
            self.terminal.delete("prompt", tk.END)
            self.terminal.insert(tk.END, agent_cmd + "\n", "info")
            self._freeze_mark = self.terminal.index("insert")
            self._protect("1.0", self._freeze_mark)
            self._strip_echo_cmd = agent_cmd
            self._insert_prompt()
            moved = False

        new_data = shell_db.drain_output(self._sid)
        if new_data:
            data = new_data.replace("\r\n", "\n").replace("\r", "\n")
            if self._strip_echo_cmd:
                cmd = self._strip_echo_cmd
                self._strip_echo_cmd = None
                prefix = cmd + "\n"
                if data.startswith(prefix):
                    data = data[len(prefix):]
            if data:
                self._append_output(data, "bright")

        if moved:
            self._insert_prompt()

        s = shell_db.get_session(self._sid)
        if s:
            self._title_label.config(
                text=f"Shell #{s['id']} — {s['ip']} ({s['status']})"
            )
            cwd = s.get("winrm_cwd")
            if cwd:
                old_prompt = self._prompt
                new_prompt = f"PS {cwd}> "
                if new_prompt != old_prompt:
                    self._prompt = new_prompt
                    try:
                        last = self.terminal.index("end - 1 chars")
                        lstart = self.terminal.index(f"{last} linestart")
                        line = self.terminal.get(lstart, "end - 1 chars")
                        if line.strip().startswith("PS "):
                            self.terminal.delete(lstart, "end - 1 chars")
                            self.terminal.insert("end - 1 chars", new_prompt, "prompt")
                            self.terminal.mark_set("prompt", "insert")
                            self.terminal.mark_gravity("prompt", tk.LEFT)
                    except Exception:
                        pass
        self._poll_id = self.after(500, self._poll)

    def _append_output(self, text, tag=None):
        if self._use_ansi and "\x1b" in text:
            self._append_ansi_text(text)
        else:
            self.terminal.insert(self._freeze_mark, text, tag or "bright")
        self.terminal.see(tk.END)
        if self._recording:
            self._record_buffer.append(text)

    def _ansi_tag(self, fg, bg, bold):
        key = (fg, bg, bold)
        if key in self._ansi_tags:
            return self._ansi_tags[key]
        name = f"ansi_{len(self._ansi_tags)}"
        conf = {}
        if fg is not None:
            conf["foreground"] = fg
        if bg is not None:
            conf["background"] = bg
        if bold:
            name += "_b"
        if not conf:
            conf["foreground"] = "#ffffff"
        self.terminal.tag_configure(name, **conf)
        self._ansi_tags[key] = name
        return name

    def _append_ansi_text(self, text):
        text = re.sub(r"\x1b\].*?(\x07|$)", "", text)
        text = text.replace("\x07", "")
        text = re.sub(r"\x1b[^\[\]]", "", text)
        text = re.sub(r"\x1b$", "", text)
        parts = re.split(r"(\x1b\[[?0-9;]*[a-zA-Z])", text)
        segments = []
        fg = None; bg = None; bold = False
        for part in parts:
            if not part:
                continue
            if part.startswith("\x1b["):
                m = re.match(r"\x1b\[([?0-9;]*)m", part)
                if not m:
                    continue
                params = m.group(1)
                if not params:
                    fg = None; bg = None; bold = False
                    continue
                for p in params.split(";"):
                    if not p: continue
                    code = int(p)
                    if code == 0: fg = None; bg = None; bold = False
                    elif code == 1: bold = True
                    elif 30 <= code <= 37: fg = _ANSI_FG.get(code)
                    elif 40 <= code <= 47: bg = _ANSI_BG.get(code)
                    elif 90 <= code <= 97: fg = _ANSI_FG.get(code)
                    elif 100 <= code <= 107: bg = _ANSI_BG.get(code)
                continue
            segments.append((part, fg, bg, bold))
        if not segments:
            return
        plain = "".join(s[0] for s in segments)
        idx = self.terminal.index(self._freeze_mark)
        self.terminal.insert(self._freeze_mark, plain)
        for text_part, fg, bg, bold in segments:
            if not text_part:
                continue
            end = f"{idx}+{len(text_part)}c"
            tag = self._ansi_tag(fg, bg, bold)
            self.terminal.tag_add(tag, idx, end)
            idx = end
