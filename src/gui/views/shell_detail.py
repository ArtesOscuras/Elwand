import re
from src.gui import fonts, windowing, theme
import json
import os
import time
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
_PROMPT_SPACE_RE = re.compile(r"[\$#%>:\]] $")
_PROMPT_END_RE = re.compile(r"[\$#%>:\]]\s*$")

_MAX_DRAIN_CHARS = 150_000
_MAX_TERM_LINES = 5_000
_MAX_TERM_CHARS = 400_000
_FLOOD_CHARS = 400_000

_RAW_KEYS = {
    "Up": "\x1b[A", "Down": "\x1b[B", "Right": "\x1b[C", "Left": "\x1b[D",
    "Home": "\x1b[H", "End": "\x1b[F", "Prior": "\x1b[5~", "Next": "\x1b[6~",
    "Insert": "\x1b[2~", "Delete": "\x1b[3~",
    "F1": "\x1bOP", "F2": "\x1bOQ", "F3": "\x1bOR", "F4": "\x1bOS",
    "F5": "\x1b[15~", "F6": "\x1b[17~", "F7": "\x1b[18~", "F8": "\x1b[19~",
    "F9": "\x1b[20~", "F10": "\x1b[21~", "F11": "\x1b[23~", "F12": "\x1b[24~",
    "BackSpace": "\x7f", "Return": "\r", "KP_Enter": "\r",
    "Tab": "\t", "ISO_Left_Tab": "\x1b[Z", "Escape": "\x1b",
}
_RAW_MODIFIERS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "Caps_Lock", "Num_Lock",
}
_ALT_ENTER_SEQS = ("\x1b[?1049h", "\x1b[?47h", "\x1b[?1047h")
_ALT_EXIT_SEQS = ("\x1b[?1049l", "\x1b[?47l", "\x1b[?1047l")
_RAW_COLORS = {
    "black": "#000000", "red": "#cc0000", "green": "#4e9a06",
    "brown": "#c4a000", "blue": "#3465a4", "magenta": "#75507b",
    "cyan": "#06989a", "white": "#d3d7cf",
    "brightblack": "#555753", "brightred": "#ef2929",
    "brightgreen": "#8ae234", "brightbrown": "#fce94f",
    "brightblue": "#729fcf", "brightmagenta": "#ad7fa8",
    "brightcyan": "#34e2e2", "brightwhite": "#eeeeec",
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
        theme.entry(self, textvariable=self._name_var).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 10))

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 15))

        theme.button(btn_frame, "  Cancel  ", command=self.destroy).pack(
            side=tk.RIGHT, padx=(5, 0))
        theme.button(btn_frame, "  Start Recording  ",
                     command=self._select).pack(side=tk.RIGHT)

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
        self._strip_buffer = ""
        self._strip_started = None
        self._auto_until_prompt = False
        self._auto_seen = False
        self._flood = False
        self._last_tty_size = None
        self._raw_capable = (
            stype == "SSH"
            or ("revers" in stype.lower() and "windows" not in stype.lower())
        )
        self._raw_mode = False
        self._screen = None
        self._stream = None
        self._raw_tags = {}
        self._raw_sig = None
        self._raw_alt = False
        self._raw_force = False
        self._raw_auto = False
        self._raw_tail = ""
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
            cursor="xterm", wrap=tk.CHAR,
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
        self.terminal.tag_configure("info", foreground=INFO)
        self.terminal.tag_configure("error", foreground="#f44747")
        self.terminal.tag_configure("prompt", foreground=SUCCESS)
        self.terminal.tag_configure("auto", foreground=MUTED)
        self.terminal.tag_raise("auto")

        self.terminal.bind("<Return>", self._on_enter)
        self.terminal.bind("<Control-c>", self._on_ctrl_c)
        self.terminal.bind("<Control-Shift-C>", self._copy_selection)
        self.terminal.bind("<Command-c>", self._copy_selection)
        self.terminal.bind("<Control-Insert>", self._copy_selection)
        self.terminal.bind("<Control-v>", self._on_paste)
        self.terminal.bind("<Control-Shift-V>", self._on_paste)
        self.terminal.bind("<Command-v>", self._on_paste)
        self.terminal.bind("<Shift-Insert>", self._on_paste)
        self.terminal.bind("<Control-a>", self._jump_to_prompt)
        self.terminal.bind("<Command-a>", self._select_all)
        self.terminal.bind("<BackSpace>", self._on_backspace)
        self.terminal.bind("<Delete>", self._on_backspace)
        self.terminal.bind("<Key>", self._on_key)
        self.terminal.bind("<Button-1>", self._on_click)
        self.terminal.bind("<Up>", self._on_history_up)
        self.terminal.bind("<Down>", self._on_history_down)
        self.terminal.bind("<Home>", self._jump_to_prompt)
        self.terminal.bind("<Configure>", self._on_terminal_resize)

        bar = tk.Frame(self, bg="#000000")
        bar.grid(row=2, column=0, sticky="ew", padx=(200, 200), pady=(0, 10))

        self._record_btn = tk.Label(
            bar, text="  Record evidence  ",
            bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
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
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=12, pady=6, cursor="",
        )
        self._agent_toggle.pack(side=tk.RIGHT, padx=(0, 10))
        self._agent_toggle.bind("<Button-1>", lambda e: self._on_agent_toggle())
        self._agent_toggle.bind("<Enter>", lambda e: self._agent_toggle.config(bg="#333333"))
        self._agent_toggle.bind("<Leave>", lambda e: self._agent_toggle.config(bg="#222222"))

        self._raw_toggle = tk.Label(
            bar, text="Raw: OFF",
            bg="#222222", fg="#f44747",
            font=fonts.view_font(10), relief=tk.FLAT, bd=0,
            padx=12, pady=6, cursor="",
        )
        if self._raw_capable:
            self._raw_toggle.pack(side=tk.RIGHT, padx=(0, 10))
            self._raw_toggle.bind("<Button-1>", lambda e: self._on_raw_toggle())
            self._raw_toggle.bind("<Enter>", lambda e: self._raw_toggle.config(bg="#333333"))
            self._raw_toggle.bind("<Leave>", lambda e: self._raw_toggle.config(bg="#222222"))

        self._last_output = ""
        self._poll_id = None
        self._resize_id = None

    def _insert_prompt(self):
        self.terminal.mark_set("insert", tk.END)
        self.terminal.insert(tk.END, "\n", "bright")
        prompt_start = self.terminal.index("end-1c")
        self.terminal.insert(tk.END, self._prompt, "prompt")
        self.terminal.mark_set("freeze", prompt_start)
        self._freeze_mark = "freeze"
        self.terminal.mark_set("prompt", "insert")
        self.terminal.mark_gravity("prompt", tk.LEFT)
        self._see_end()

    def _jump_to_prompt(self, event=None):
        if self._raw_mode:
            return self._send_raw_key(event)
        self.terminal.mark_set("insert", self.terminal.index("prompt"))
        return "break"

    def _has_selection(self):
        try:
            return bool(self.terminal.tag_ranges("sel"))
        except tk.TclError:
            return False

    def _copy_selection(self, event=None):
        try:
            text = self.terminal.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
        return "break"

    def _select_all(self, event=None):
        self.terminal.tag_add("sel", "1.0", "end-1c")
        self.terminal.mark_set("insert", "1.0")
        return "break"

    def _on_paste(self, event=None):
        if self._raw_mode:
            try:
                text = self.clipboard_get()
            except tk.TclError:
                return "break"
            if text:
                try:
                    send_raw(
                        self._sid,
                        text.replace("\r\n", "\n").replace("\n", "\r"))
                except Exception:
                    pass
            return "break"
        self._end_auto()
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return "break"
        if not text:
            return "break"
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.terminal.tag_remove("sel", "1.0", tk.END)
        self.terminal.mark_set("insert", tk.END)
        self.terminal.insert(tk.END, text)
        self.terminal.see(tk.END)
        return "break"

    def _see_end(self):
        if not self._has_selection():
            self.terminal.see(tk.END)

    def _on_click(self, event):
        self.terminal.focus_set()

    def _on_key(self, event):
        if self._raw_mode:
            return self._send_raw_key(event)
        if event.keysym in (
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Meta_L", "Meta_R", "Super_L", "Super_R", "Caps_Lock", "Num_Lock",
        ):
            return
        if self._auto_seen:
            self._end_auto()
        printable = bool(event.char) and ord(event.char[0]) >= 32
        if self._has_selection():
            self.terminal.tag_remove("sel", "1.0", tk.END)
            if printable:
                self.terminal.mark_set("insert", tk.END)
        if self.terminal.compare("insert", "<", "prompt"):
            self.terminal.mark_set("insert", tk.END)
        if printable:
            self.terminal.see(tk.END)
        c = event.keysym
        if c in ("Left", "Right"):
            prompt_idx = self.terminal.index("prompt")
            insert_idx = self.terminal.index("insert")
            if c == "Left" and self.terminal.compare(insert_idx, "==", prompt_idx):
                return "break"

    def _on_backspace(self, event):
        if self._raw_mode:
            return self._send_raw_key(event)
        if self._auto_seen:
            self._end_auto()
        if self._has_selection():
            try:
                if self.terminal.compare("sel.first", ">=", "prompt"):
                    return
            except tk.TclError:
                pass
            self.terminal.tag_remove("sel", "1.0", tk.END)
            self.terminal.mark_set("insert", tk.END)
            return "break"
        if self.terminal.compare("insert", "<=", "prompt"):
            return "break"

    def _get_current_cmd(self):
        return self.terminal.get("prompt", "end-1c")

    def _start_strip(self, cmd):
        self._strip_echo_cmd = cmd
        self._strip_buffer = ""
        self._strip_started = None

    def _clear_strip(self):
        self._strip_echo_cmd = None
        self._strip_buffer = ""
        self._strip_started = None

    def _resolve_echo(self, data):
        """Strip the remote echo of the just-sent command, even if split."""
        if self._strip_echo_cmd is None:
            return data
        if self._strip_started is None:
            self._strip_started = time.time()
        self._strip_buffer += data
        buf = self._strip_buffer
        cmd = self._strip_echo_cmd
        if cmd == "":
            if buf.startswith("\n"):
                self._clear_strip()
                return buf[1:]
            if buf:
                self._clear_strip()
                return buf
            return ""
        if buf.startswith("\n"):
            b2 = buf[1:]
            if b2.startswith(cmd) or cmd.startswith(b2):
                buf = b2
        if buf.startswith(cmd):
            rest = buf[len(cmd):]
            if rest.startswith("\n"):
                rest = rest[1:]
            if rest or time.time() - self._strip_started > 1.0:
                self._clear_strip()
                return rest
            return ""
        if cmd.startswith(buf):
            if time.time() - self._strip_started > 1.0:
                self._clear_strip()
                return buf
            return ""
        self._clear_strip()
        return buf

    def _send_auto(self, cmd):
        """Send an Elwand-driven command (resize/stabilize) shown in grey."""
        if not self._freeze_mark:
            return
        try:
            line_start = self.terminal.index(f"{self._freeze_mark} linestart")
        except tk.TclError:
            line_start = self._freeze_mark
        try:
            prev = self.terminal.get(f"{self._freeze_mark}-1c", self._freeze_mark)
        except tk.TclError:
            prev = ""
        prefix = " " if prev and not prev.isspace() else ""
        try:
            self.terminal.tag_add("auto", line_start, self._freeze_mark)
            self.terminal.insert(self._freeze_mark, prefix + cmd + "\n", "auto")
            self.terminal.tag_raise("auto")
        except tk.TclError as e:
            shell_db._dbg(f"[shell] auto send error: {e}")
            return
        if self._recording:
            self._record_buffer.append(cmd + "\n")
        self._start_strip(cmd)
        self._auto_until_prompt = True
        send_command(self._sid, cmd, auto=True)

    def _lock_and_send(self, cmd):
        shell_db.stop_discard(self._sid)
        self._end_auto()
        s = shell_db.get_session(self._sid)
        if s:
            s["_truncated"] = False
        self.terminal.delete("prompt", tk.END)
        if cmd.strip():
            self.terminal.insert(tk.END, cmd + "\n", "bright")
        self.terminal.mark_set("freeze", tk.END)
        self._freeze_mark = "freeze"

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
        if self._raw_mode:
            return self._send_raw_key(event)
        cmd = self._get_current_cmd()
        self.terminal.delete("prompt", tk.END)
        if cmd.strip().lower() == "exit":
            if self._on_back_click:
                self._on_back_click()
            return "break"
        if cmd.strip().lower() == "clear":
            shell_db.stop_discard(self._sid)
            s = shell_db.get_session(self._sid)
            if s:
                s["_truncated"] = False
            self.terminal.delete("1.0", tk.END)
            self.terminal.mark_set("freeze", "1.0")
            self._freeze_mark = "freeze"
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
        if self._raw_mode:
            return self._send_raw_key(event)
        shell_db.start_discard(self._sid)
        if self._auto_seen:
            self._end_auto()
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
        self.terminal.mark_set("freeze", tk.END)
        self._freeze_mark = "freeze"
        self._insert_prompt()
        return "break"

    def _on_history_up(self, event):
        if self._raw_mode:
            return self._send_raw_key(event)
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
        if self._raw_mode:
            return self._send_raw_key(event)
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

    def _update_raw_btn(self):
        if not hasattr(self, "_raw_toggle"):
            return
        try:
            if self._raw_mode:
                self._raw_toggle.config(text="Raw: ON", fg=SUCCESS)
            else:
                self._raw_toggle.config(text="Raw: OFF", fg="#f44747")
        except tk.TclError:
            pass

    def _on_raw_toggle(self):
        if not self._raw_capable:
            return
        if self._raw_mode:
            self._exit_raw()
        else:
            self._enter_raw()

    def _raw_dimensions(self):
        try:
            import tkinter.font as tkfont
            w = self.terminal.winfo_width()
            h = self.terminal.winfo_height()
            f = tkfont.Font(font=self.terminal.cget("font"))
            char_w = max(1, f.measure(" "))
            char_h = max(1, f.metrics("linespace"))
            pad_x = int(self.terminal.cget("padx") or 0) * 2
            pad_y = int(self.terminal.cget("pady") or 0) * 2
            cols = max(20, (w - pad_x) // char_w)
            rows = max(5, (h - pad_y) // char_h)
            return rows, cols
        except Exception:
            return 24, 80

    def _enter_raw(self, auto=False, initial_data=""):
        try:
            import pyte
        except Exception:
            self._append_output(
                "pyte is required for the raw terminal. Reinstall Elwand.\n",
                "error")
            return
        if not auto:
            try:
                self._resize_terminal()
            except Exception:
                pass
        if self._last_tty_size:
            rows, cols = self._last_tty_size
        else:
            rows, cols = self._raw_dimensions()
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)
        self._raw_tags = {}
        self._raw_sig = None
        self._raw_alt = False
        self._raw_force = False
        self._raw_auto = bool(auto)
        self._raw_tail = ""
        self._raw_mode = True
        self._clear_strip()
        self._auto_seen = False
        self._auto_until_prompt = False
        shell_db.set_auto_output(self._sid, 0)
        self.terminal.configure(wrap="none")
        self.terminal.tag_remove("sel", "1.0", tk.END)
        self.terminal.delete("1.0", tk.END)
        self._update_raw_btn()
        self.terminal.focus_force()
        self.after(100, lambda: self.terminal.focus_force())
        if initial_data:
            if any(seq in initial_data for seq in _ALT_ENTER_SEQS):
                self._raw_alt = True
            if any(seq in initial_data for seq in _ALT_EXIT_SEQS):
                self._raw_alt = False
            try:
                self._stream.feed(initial_data)
            except Exception as e:
                shell_db._dbg(f"[shell raw] initial feed error: {e}")
            try:
                self._render_raw(force=True)
            except Exception as e:
                shell_db._dbg(f"[shell raw] initial render error: {e}")
        if not auto:
            try:
                send_raw(self._sid, "\r")
            except Exception as e:
                shell_db._dbg(f"[shell raw] enter newline error: {e}")
        if self._poll_id:
            self.after_cancel(self._poll_id)
        self._poll_id = self.after(50, self._poll)

    def _reset_raw_force(self):
        self._raw_force = False
        self._update_raw_btn()

    def _exit_raw(self):
        if not self._raw_mode:
            return
        if self._raw_alt and not self._raw_force:
            self._raw_force = True
            try:
                self._raw_toggle.config(text="Raw: click again", fg="#f44747")
                self.after(2000, self._reset_raw_force)
            except tk.TclError:
                pass
            return
        self._raw_force = False
        self._raw_auto = False
        self._raw_tail = ""
        self._raw_mode = False
        self._screen = None
        self._stream = None
        self._raw_tags = {}
        self.terminal.configure(wrap="char", insertwidth=2)
        self.terminal.delete("1.0", tk.END)
        self.terminal.mark_set("freeze", "1.0")
        self._freeze_mark = "freeze"
        self._start_strip("")
        try:
            send_raw(self._sid, "\r")
        except Exception as e:
            shell_db._dbg(f"[shell raw] exit newline error: {e}")
        self._insert_prompt()
        self._last_tty_size = None
        self._update_raw_btn()
        self.terminal.focus_force()
        self.after(150, self._resize_terminal)
        if self._poll_id:
            self.after_cancel(self._poll_id)
        self._poll_id = self.after(200, self._poll)

    def _raw_color(self, value, default):
        if value in (None, "default", ""):
            return default
        if isinstance(value, int):
            if value < 16:
                name = ["black", "red", "green", "brown", "blue", "magenta",
                        "cyan", "white", "brightblack", "brightred",
                        "brightgreen", "brightbrown", "brightblue",
                        "brightmagenta", "brightcyan", "brightwhite"][value]
                return _RAW_COLORS.get(name, default)
            if value < 232:
                n = value - 16
                r, g, b = n // 36, (n % 36) // 6, n % 6
                conv = lambda v: 0 if v == 0 else 55 + v * 40
                return f"#{conv(r):02x}{conv(g):02x}{conv(b):02x}"
            v = min(255, 8 + (value - 232) * 10)
            return f"#{v:02x}{v:02x}{v:02x}"
        s = str(value)
        if s.startswith("#") and len(s) == 7:
            return s
        if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
            return "#" + s
        return _RAW_COLORS.get(s, default)

    def _raw_tag(self, cell):
        fg = self._raw_color(cell.fg, BRIGHT)
        bg = self._raw_color(cell.bg, "#000000")
        if cell.reverse:
            fg, bg = bg, fg
        key = (fg, bg, bool(cell.bold), bool(cell.underscore),
               bool(cell.strikethrough))
        tag = self._raw_tags.get(key)
        if tag:
            return tag
        tag = f"raw_{len(self._raw_tags)}"
        conf = {"foreground": fg, "background": bg}
        if cell.bold:
            conf["font"] = fonts.view_font_bold(13)
        if cell.underscore:
            conf["underline"] = True
        if cell.strikethrough:
            conf["overstrike"] = True
        self.terminal.tag_configure(tag, **conf)
        try:
            self.terminal.tag_raise("sel")
        except tk.TclError:
            pass
        self._raw_tags[key] = tag
        return tag

    def _render_raw(self, force=False):
        if self._screen is None or self._has_selection():
            return
        display = list(self._screen.display)
        cur = self._screen.cursor
        sig = (tuple(display), cur.x, cur.y)
        if not force and sig == self._raw_sig:
            return
        self._raw_sig = sig
        self.terminal.delete("1.0", tk.END)
        for y, row in enumerate(display):
            line = self._screen.buffer[y]
            x = 0
            n = len(row)
            while x < n:
                tag = self._raw_tag(line[x])
                j = x + 1
                while j < n and self._raw_tag(line[j]) == tag:
                    j += 1
                self.terminal.insert(tk.END, row[x:j], tag)
                x = j
            if y < len(display) - 1:
                self.terminal.insert(tk.END, "\n")
        cy = min(max(cur.y, 0), max(0, len(display) - 1))
        cx = min(max(cur.x, 0), max(0, len(display[0]) - 1)) if display else 0
        self.terminal.mark_set("insert", f"{cy + 1}.{cx}")
        self.terminal.see("insert")
        try:
            hidden = bool(getattr(cur, "hidden", False))
            self.terminal.configure(insertwidth=0 if hidden else 2)
        except tk.TclError:
            pass

    def _send_raw_key(self, event):
        if event.keysym in _RAW_MODIFIERS:
            return "break"
        seq = _RAW_KEYS.get(event.keysym)
        if seq is None:
            seq = event.char
            if seq and (event.state & 0x0008):
                seq = "\x1b" + seq
        if seq:
            try:
                ok = send_raw(self._sid, seq)
                if not ok:
                    shell_db._dbg(f"[shell raw] send failed: {seq!r}")
            except Exception as e:
                shell_db._dbg(f"[shell raw] send error: {e}")
        return "break"

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
            extra = " [output truncated]" if s.get("_truncated") else ""
            self._title_label.config(
                text=f"Shell #{s['id']} — {s['ip']} ({s['status']}){extra}"
            )
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        if self._raw_mode:
            self.after(100, lambda: self.terminal.focus_force())
            self.after(200, self._poll)
            return
        if self.terminal.get("1.0", tk.END).strip() == "":
            self.terminal.mark_set("freeze", "1.0")
            self._freeze_mark = "freeze"
            self._append_output("[connected]\n", "info")
            self._insert_prompt()
        self.after(100, lambda: self.terminal.focus_force())
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
        if self._raw_mode:
            auto_exit = False
            try:
                entered = self._raw_alt
                fed = False
                pending = shell_db.buffer_chars(self._sid)
                budget = 50_000 if pending > 400_000 else _MAX_DRAIN_CHARS
                for data, _auto in shell_db.drain_output(
                        self._sid, max_chars=budget):
                    if not data:
                        continue
                    if any(seq in data for seq in _ALT_ENTER_SEQS):
                        self._raw_alt = True
                        entered = True
                    if any(seq in data for seq in _ALT_EXIT_SEQS):
                        self._raw_alt = False
                    try:
                        if self._stream is not None:
                            self._stream.feed(data)
                            fed = True
                    except Exception as e:
                        shell_db._dbg(f"[shell raw] feed error: {e}")
                self._render_raw(force=fed)
                if self._raw_auto and entered and not self._raw_alt:
                    auto_exit = True
            except Exception as e:
                shell_db._dbg(f"[shell raw] poll error: {e}")
            if auto_exit:
                self._exit_raw()
                return
            pending = shell_db.buffer_chars(self._sid)
            delay = 100 if pending > 400_000 else (50 if pending else 300)
            self._poll_id = self.after(delay, self._poll)
            return
        s = shell_db.get_session(self._sid)
        if s and s.get("_discard"):
            if time.time() - s.get("_discard_last", 0) > 0.4:
                shell_db.stop_discard(self._sid)
        pending = shell_db.buffer_chars(self._sid)
        if (pending > _FLOOD_CHARS and s
                and (datetime.now() - s["last_active"]).total_seconds() < 0.5):
            self._flood = True
            try:
                self._title_label.config(
                    text=(f"Shell #{s['id']} — {s['ip']} "
                          f"({s['status']}) [flooding…]"))
            except tk.TclError:
                pass
            self._poll_id = self.after(200, self._poll)
            return
        self._flood = False
        moved = False
        agent_cmd = None
        touch = shell_db.pop_agent_touch(self._sid)
        if touch:
            self.terminal.mark_set("freeze", tk.END)
            self._freeze_mark = "freeze"
            if isinstance(touch, str):
                agent_cmd = touch
            moved = True

        if agent_cmd:
            self.terminal.delete("prompt", tk.END)
            self.terminal.insert(tk.END, agent_cmd + "\n", "info")
            self.terminal.mark_set("insert", tk.END)
            self.terminal.mark_set("freeze", tk.END)
            self._freeze_mark = "freeze"
            self._start_strip(agent_cmd)
            self._insert_prompt()
            moved = False

        budget = 50_000 if pending > 400_000 else _MAX_DRAIN_CHARS
        segments = shell_db.drain_output(self._sid, max_chars=budget)
        joined = "".join(d for d, _ in segments)
        scan = self._raw_tail + joined
        self._raw_tail = scan[-32:]
        if self._raw_capable and any(seq in scan for seq in _ALT_ENTER_SEQS):
            self._enter_raw(auto=True, initial_data=joined)
            if not self._raw_mode:
                self._poll_id = self.after(500, self._poll)
            return
        appended = False
        for data, auto in segments:
            if not data:
                continue
            data = data.replace("\r\n", "\n").replace("\r", "\n")
            data = self._resolve_echo(data)
            if data:
                self._append_output(
                    data, "auto" if auto else None, scroll=False)
                appended = True
        if appended:
            self._trim_terminal()
            self._see_end()

        if moved:
            self._insert_prompt()

        if self._auto_seen and not shell_db.is_auto_output(self._sid):
            self._auto_seen = False
            self._whiten_last_prompt()

        s = shell_db.get_session(self._sid)
        if s:
            extra = " [output truncated]" if s.get("_truncated") else ""
            self._title_label.config(
                text=f"Shell #{s['id']} — {s['ip']} ({s['status']}){extra}"
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
        pending = shell_db.buffer_chars(self._sid)
        delay = 100 if pending > 400_000 else (50 if pending else 500)
        self._poll_id = self.after(delay, self._poll)

    def _trim_terminal(self):
        if self._has_selection():
            return
        try:
            end = str(self.terminal.index("end-1c"))
            lines = int(end.split(".")[0])
            if lines > _MAX_TERM_LINES + 500:
                self.terminal.delete("1.0", f"{lines - _MAX_TERM_LINES}.0")
            cnt = self.terminal.count("1.0", "end-1c", "chars")
            total = int(cnt[0] if isinstance(cnt, tuple) else cnt)
            if total > _MAX_TERM_CHARS + 50_000:
                idx = self.terminal.index(
                    f"1.0 + {total - _MAX_TERM_CHARS} chars")
                self.terminal.delete("1.0", idx)
        except Exception:
            pass

    def _drop_remote_prompt_space(self, start, text):
        """Avoid a double gap when the remote prompt already ends with a space."""
        if self._prompt != " " or not text.endswith(" "):
            return
        tail = text.rsplit("\n", 1)[-1]
        try:
            prev = self.terminal.get(f"{start}-1c", start)
        except tk.TclError:
            prev = ""
        if not _PROMPT_SPACE_RE.search(prev + tail):
            return
        try:
            end = f"{start}+{len(text)}c"
            self.terminal.delete(f"{end}-1c", end)
        except tk.TclError:
            pass

    @staticmethod
    def _strip_ansi_codes(text):
        text = re.sub(r"\x1b\].*?(\x07|\x1b\\)", "", text, flags=re.S)
        text = text.replace("\x07", "")
        text = re.sub(r"\x1b\[[?0-9;]*[a-zA-Z]", "", text)
        text = re.sub(r"\x1b[^\[\]]", "", text)
        text = re.sub(r"\x1b$", "", text)
        return text

    def _whiten_final_prompt(self, start, text):
        """Keep the final prompt of an automated block white, not grey."""
        last = text.rsplit("\n", 1)[-1]
        if not _PROMPT_END_RE.search(last):
            return
        try:
            end = self.terminal.index(f"{start}+{len(text)}c")
            nl = text.rfind("\n")
            pstart = self.terminal.index(
                f"{start}+{nl + 1}c") if nl >= 0 else start
            self.terminal.tag_remove("auto", pstart, end)
        except tk.TclError:
            return
        if self._auto_until_prompt:
            self._auto_until_prompt = False
            self._auto_seen = False
            shell_db.set_auto_output(self._sid, 0)

    def _whiten_last_prompt(self):
        """Make the current (last) prompt white after an automated block."""
        try:
            last = self.terminal.index("end-1c")
            start = self.terminal.index(f"{last} linestart")
            line = self.terminal.get(start, last)
        except tk.TclError:
            return
        if not _PROMPT_END_RE.search(line):
            return
        self.terminal.tag_remove("auto", start, last)

    def _end_auto(self):
        if self._auto_seen or self._auto_until_prompt:
            self._whiten_last_prompt()
        self._auto_seen = False
        self._auto_until_prompt = False
        shell_db.set_auto_output(self._sid, 0)

    def _append_output(self, text, tag=None, scroll=True):
        if tag == "auto" and "\x1b" in text:
            text = self._strip_ansi_codes(text)
        if self._use_ansi and "\x1b" in text and tag != "auto":
            self._append_ansi_text(text)
        else:
            start = self.terminal.index(self._freeze_mark)
            if tag:
                self.terminal.insert(self._freeze_mark, text, tag)
            else:
                self.terminal.insert(self._freeze_mark, text)
            if tag == "auto":
                self._auto_seen = True
                if self._auto_until_prompt:
                    self._whiten_final_prompt(start, text)
            self._drop_remote_prompt_space(start, text)
        if scroll:
            self._see_end()
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
        start = self.terminal.index(self._freeze_mark)
        self.terminal.insert(self._freeze_mark, plain)
        idx = start
        for text_part, fg, bg, bold in segments:
            if not text_part:
                continue
            end = f"{idx}+{len(text_part)}c"
            tag = self._ansi_tag(fg, bg, bold)
            self.terminal.tag_add(tag, idx, end)
            idx = end
        self._drop_remote_prompt_space(start, plain)
