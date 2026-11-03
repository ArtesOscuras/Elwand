import tkinter as tk
import tkinter.font as tkfont
from .shell_detail import ShellDetailView
from src.shells import shell_db, send_command


class ReverseShellDetailView(ShellDetailView):
    name = "reverse_shell_detail"
    description = "Reverse shell interaction view"

    def __init__(self, parent, sid, **kwargs):
        super().__init__(parent, sid, **kwargs)
        self._prompt = " "
        self._use_ansi = True

    def _build_ui(self):
        super()._build_ui()
        self.terminal.tag_configure("prompt", foreground="#000000")

    def on_activate(self):
        super().on_activate()
        self.after(1500, self._resize_terminal)

    def _resize_terminal(self):
        if self._raw_mode:
            return
        try:
            w = self.terminal.winfo_width()
            h = self.terminal.winfo_height()
            f = tkfont.Font(font=self.terminal.cget("font"))
            char_w = f.measure(" ")
            char_h = f.metrics("linespace")
            pad_x = int(self.terminal.cget("padx") or 0) * 2
            pad_y = int(self.terminal.cget("pady") or 0) * 2
            useful_w = max(1, w - pad_x)
            useful_h = max(1, h - pad_y)
            cols = max(20, useful_w // char_w)
            rows = max(5, useful_h // char_h)
            s = shell_db.get_session(self._sid)
            if s and s["status"] == "connected":
                size = (rows, cols)
                if size == self._last_tty_size:
                    return
                self._last_tty_size = size
                self._send_auto(f"stty rows {rows} cols {cols}")
        except Exception:
            pass

    def _do_resize(self):
        self._resize_id = None
        self._resize_terminal()

    def _insert_prompt(self):
        self.terminal.mark_set("insert", tk.END)
        prompt_start = self.terminal.index("end-1c")
        self.terminal.insert(tk.END, self._prompt, "prompt")
        self.terminal.mark_set("freeze", prompt_start)
        self._freeze_mark = "freeze"
        self.terminal.mark_set("prompt", "insert")
        self.terminal.mark_gravity("prompt", tk.LEFT)
        self._see_end()

    def _lock_and_send(self, cmd):
        self._end_auto()
        self.terminal.delete("prompt", tk.END)
        if cmd.strip():
            self.terminal.insert(tk.END, cmd, "bright")
            self._strip_echo_cmd = cmd
        else:
            self._strip_echo_cmd = ""
        self.terminal.insert(tk.END, "\n", "bright")
        self.terminal.mark_set("freeze", tk.END)
        self._freeze_mark = "freeze"
        self._protect("1.0", self._freeze_mark)
        if cmd.strip():
            self._history.append(cmd.strip())
            self._history_idx = len(self._history)
        send_command(self._sid, cmd if cmd.strip() else "")
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
            self._end_auto()
            self.terminal.delete("1.0", tk.END)
            self.terminal.mark_set("freeze", "1.0")
            self._freeze_mark = "freeze"
            self._protect("1.0", self._freeze_mark)
            self._insert_prompt()
            self._strip_echo_cmd = "clear"
            send_command(self._sid, "clear")
            return "break"
        self._lock_and_send(cmd)
        return "break"
