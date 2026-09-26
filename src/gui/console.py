from src.gui import fonts
from src.gui.markdown import MarkdownRenderer
import tkinter as tk
import tkinter.font as tkfont
from tkinter import scrolledtext


FG = "#ffffff"
FG_DIM = "#888888"
FG_CONSULTOR = "#e6b422"
FG_AGENT = "#5ba3ec"
BG = "#000000"
BG_INPUT = "#111111"
SUCCESS = "#00cc66"
TITLE_COLOR = "#ffffff"
INFO_COLOR = "#888888"
WARN_COLOR = "#ce9178"
ERR_COLOR = "#f44747"
AGENT_COLOR = "#5ba3ec"


class Console(tk.Frame):
    @staticmethod
    def _matches_word(prefix, word):
        if word.startswith(prefix):
            return True
        if word.startswith("#") and word[1:].startswith(prefix):
            return True
        return False

    @staticmethod
    def _common_prefix(strings):
        if not strings:
            return ""
        result = strings[0]
        for s in strings[1:]:
            while not s.startswith(result):
                result = result[:-1]
                if not result:
                    return ""
        return result

    def __init__(self, parent, initial_font_size=11, **kwargs):
        super().__init__(parent, **kwargs)
        self.commands = {}
        self.help_sections = []
        self._history = []
        self._history_index = -1
        self._saved_input = ""
        self._font_size = initial_font_size
        self._system_handler = None
        self._system_stop_handler = None
        self._mode_handler = None
        self._mode_label = ""
        self._mode_fg = FG
        self._mode_commands = None
        self._mode_cycle_cb = None
        self._prompt_hovered = False
        self._focus_callback = None
        self._is_system = False
        self._thinking = False
        self._spinner_timer = None
        self._spinner_idx = 0
        self._skip_release = False
        self._autocomplete_popup = None
        self._autocomplete_listbox = None
        self._autocomplete_matches = []
        self._autocomplete_index = -1
        self._autocomplete_names = []
        self._track_id = None
        self._filter_id = None
        self._last_popup_y = None
        self._subcommands = {}
        self._arg_popup = None
        self._arg_listbox = None
        self._arg_matches = []
        self._arg_index = -1

        self._arg2_providers = {}
        self._arg2_popup = None
        self._arg2_listbox = None
        self._arg2_matches = []
        self._arg2_index = -1

        self._arg3_providers = {}
        self._arg3_popup = None
        self._arg3_listbox = None
        self._arg3_matches = []
        self._arg3_index = -1

        self._arg2_contains = set()
        self._arg3_contains = set()

        self._arg4_providers = {}
        self._arg4_popup = None
        self._arg4_listbox = None
        self._arg4_matches = []
        self._arg4_index = -1

        self._arg4_contains = set()

        self._arg5_providers = {}
        self._arg5_popup = None
        self._arg5_listbox = None
        self._arg5_matches = []
        self._arg5_index = -1

        self._arg5_contains = set()

        self._segments = []
        self._live_active = False

        self.grid_propagate(False)
        self.config(bg=BG)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        self.output_area = scrolledtext.ScrolledText(
            self,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=BG,
            fg=FG_DIM,
            insertbackground=FG,
            font=(fonts.family(), self._font_size),
            borderwidth=0,
            highlightthickness=0,
        )
        self.output_area.grid(row=0, column=0, sticky="nsew")
        self.output_area.vbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                                         width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        self._md_renderer = MarkdownRenderer(self.output_area, self._font_size)

        input_frame = tk.Frame(self, bg=BG_INPUT)
        input_frame.columnconfigure(0, weight=0)
        input_frame.columnconfigure(1, weight=0)
        input_frame.columnconfigure(2, weight=1)
        input_frame.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.prompt_label = tk.Label(
            input_frame,
            text="Elwand> ",
            bg=BG_INPUT,
            fg=FG,
            font=(fonts.family(), self._font_size),
        )
        self.prompt_label.grid(row=0, column=0, sticky="w")

        self._spinner_label = tk.Label(
            input_frame, text="\u2800", bg=BG_INPUT, fg="#5ba3ec",
            font=(fonts.family(), self._font_size),
        )
        self._spinner_label.grid(row=0, column=1, sticky="w")

        self.prompt_label.bind("<Button-1>", self._on_prompt_click)
        self.prompt_label.bind("<Enter>", self._on_prompt_enter)
        self.prompt_label.bind("<Leave>", self._on_prompt_leave)
        self._spinner_label.bind("<Button-1>", self._on_prompt_click)

        self.input_var = tk.StringVar()
        self.input_text = tk.Text(
            input_frame,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            font=(fonts.family(), self._font_size),
            borderwidth=1,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightcolor="#222222",
            highlightbackground="#222222",
            height=1,
            wrap=tk.WORD,
            undo=False,
        )
        self.input_text.grid(row=0, column=2, sticky="ew")
        self.input_text.bind("<Return>", self._on_enter)
        self.input_text.bind("<Up>", self._on_up)
        self.input_text.bind("<Down>", self._on_down)
        self.input_text.bind("<KeyPress>", self._on_key_press)
        self.input_text.bind("<KeyRelease>", self._on_key_release)
        self.input_text.bind("<Tab>", self._on_tab)
        self.input_text.bind("<Escape>", self._on_escape)
        self.input_text.bind("<FocusIn>", self._on_focus_in)
        self.input_text.bind("<FocusOut>", self._on_focus_out)
        self.input_text.focus()

        self.input_text.bind("<Control-plus>", lambda e: self._adjust_font(+1), add="+")
        self.input_text.bind("<Control-minus>", lambda e: self._adjust_font(-1), add="+")
        self.input_text.bind("<Command-plus>", lambda e: self._adjust_font(+1), add="+")
        self.input_text.bind("<Command-minus>", lambda e: self._adjust_font(-1), add="+")
        self.input_text.bind("<Control-equal>", lambda e: self._adjust_font(+1), add="+")
        self.input_text.bind("<Command-equal>", lambda e: self._adjust_font(+1), add="+")
        self.input_text.bind("<Control-f>", lambda e: self._focus_callback and self._focus_callback(), add="+")
        self.input_text.bind("<Command-f>", lambda e: self._focus_callback and self._focus_callback(), add="+")

        self.winfo_toplevel().bind("<Button-1>", self._on_root_click, add="+")
        self.winfo_toplevel().bind("<Escape>", self._on_escape, add="+")

        self.bind_all("<Control-plus>", lambda e: self._adjust_font(+1))
        self.bind_all("<Control-minus>", lambda e: self._adjust_font(-1))
        self.bind_all("<Command-plus>", lambda e: self._adjust_font(+1))
        self.bind_all("<Command-minus>", lambda e: self._adjust_font(-1))
        self.bind_all("<Control-equal>", lambda e: self._adjust_font(+1))
        self.bind_all("<Command-equal>", lambda e: self._adjust_font(+1))

        self.register_command("help", self._cmd_help, "Show this help message")
        self.register_command("clear", self._cmd_clear, "Clear the console")

    def _input_get(self):
        return self.input_text.get("1.0", "end-1c")

    def _input_set(self, text):
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)
        self.input_text.mark_set("insert", "end-1c")
        self.after(1, self._sync_input_height)

    def _input_focus(self):
        self.input_text.focus()

    def register_command(self, name, handler, help_text=""):
        self.commands[name] = {"handler": handler, "help": help_text}

    def set_subcommands(self, name, items):
        self._subcommands[name] = items

    def set_arg2_provider(self, cmd, subcmd, provider):
        self._arg2_providers[(cmd, subcmd)] = provider

    def set_arg3_provider(self, cmd, subcmd, provider):
        self._arg3_providers[(cmd, subcmd)] = provider

    def set_arg2_filter_contains(self, cmd, subcmd):
        self._arg2_contains.add((cmd, subcmd))

    def set_arg3_filter_contains(self, cmd, subcmd):
        self._arg3_contains.add((cmd, subcmd))

    def set_arg4_provider(self, cmd, subcmd, provider):
        self._arg4_providers[(cmd, subcmd)] = provider

    def set_arg4_filter_contains(self, cmd, subcmd):
        self._arg4_contains.add((cmd, subcmd))

    def set_arg5_provider(self, cmd, subcmd, provider):
        self._arg5_providers[(cmd, subcmd)] = provider

    def set_arg5_filter_contains(self, cmd, subcmd):
        self._arg5_contains.add((cmd, subcmd))

    def set_system_handler(self, handler):
        self._system_handler = handler

    def set_system_stop_handler(self, handler):
        self._system_stop_handler = handler

    def set_mode_handler(self, handler, label="", fg=FG, commands=None):
        self._mode_handler = handler
        self._mode_label = label
        self._mode_fg = fg
        self._mode_commands = commands
        if handler:
            self.prompt_label.config(text=f"{self._mode_label}> ", fg=self._mode_fg)
        self._filter_autocomplete()

    def set_mode_cycle_callback(self, callback):
        self._mode_cycle_cb = callback

    _SPINNER_CHARS = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]

    def start_thinking(self):
        self.after(0, self._start_thinking_ui)

    def _start_thinking_ui(self):
        self._spinner_idx = 0
        self._thinking = True
        self._tick_spinner()

    def _tick_spinner(self):
        if not self._thinking:
            return
        ch = self._SPINNER_CHARS[self._spinner_idx % len(self._SPINNER_CHARS)]
        self._spinner_label.config(text=ch)
        self._spinner_idx += 1
        try:
            self._spinner_timer = self.after(150, self._tick_spinner)
        except RuntimeError:
            pass

    def stop_thinking(self):
        self._thinking = False
        try:
            self.after(0, self._stop_thinking_ui)
        except RuntimeError:
            pass

    def _stop_thinking_ui(self):
        if getattr(self, '_spinner_timer', None):
            self.after_cancel(self._spinner_timer)
            self._spinner_timer = None
        self._spinner_label.config(text="\u2800", fg="#5ba3ec")

    def _set_spinner_color(self, color):
        self._spinner_label.config(fg=color)

    def block_input(self):
        self.input_text.configure(state="disabled")

    def unblock_input(self):
        self.input_text.configure(state="normal")
        self.input_text.focus()

    def add_help_section(self, title, items):
        self.help_sections.append((title, items))

    def write(self, text, color=None):
        if not self.winfo_exists():
            return
        if self._live_active:
            self.clear_live_status()
        self.output_area.config(state=tk.NORMAL)
        is_at_bottom = self.output_area.yview()[1] >= 1.0
        tag = None
        if color:
            tag = f"color_{id(color)}"
            self.output_area.tag_configure(tag, foreground=color)
            self.output_area.insert(tk.END, text, tag)
        else:
            self.output_area.insert(tk.END, text)
        self._segments.append((text, color))
        if is_at_bottom:
            self.output_area.see(tk.END)
        self.output_area.config(state=tk.DISABLED)

    def live_status(self, text, color=None):
        """Write/replace a single transient status line at the end.

        The line is not added to the persisted segments, so it does not
        survive a session restart (it only exists while an operation runs).
        Any normal write() drops it first, and the next live_status()
        re-creates it.
        """
        if not self.winfo_exists():
            return
        self.output_area.config(state=tk.NORMAL)
        is_at_bottom = self.output_area.yview()[1] >= 1.0
        ranges = self.output_area.tag_ranges("live_status_tag")
        if ranges:
            try:
                self.output_area.delete(ranges[0], ranges[1])
            except tk.TclError:
                pass
        tags = ["live_status_tag"]
        if color:
            tag = f"color_{id(color)}"
            self.output_area.tag_configure(tag, foreground=color)
            tags.append(tag)
        self.output_area.insert("end", text + "\n", tuple(tags))
        self._live_active = True
        if is_at_bottom:
            self.output_area.see("end")
        self.output_area.config(state=tk.DISABLED)

    def clear_live_status(self):
        if not self._live_active:
            return
        self._live_active = False
        try:
            ranges = self.output_area.tag_ranges("live_status_tag")
            if ranges:
                self.output_area.config(state=tk.NORMAL)
                self.output_area.delete(ranges[0], ranges[1])
                self.output_area.config(state=tk.DISABLED)
        except tk.TclError:
            pass

    def writeln(self, text="", color=None):
        self.write(text + "\n", color)

    def _blank_line_if_needed(self):
        try:
            content = self.output_area.get("1.0", "end-1c")
        except tk.TclError:
            return
        if content and not content.endswith("\n\n"):
            self.writeln("")

    def title(self, text):
        self.writeln(f"\u2500\u2500\u2500 {text} \u2500\u2500\u2500", TITLE_COLOR)

    def info(self, text):
        self.writeln(f"[*] {text}", INFO_COLOR)

    def success(self, text):
        self.writeln(f"[+] {text}", SUCCESS)

    def body(self, text):
        self.writeln(text, FG_DIM)

    def agent(self, text):
        self._write_segments([(text, "__md__")])

    def consultor(self, text):
        self._write_segments([(text, "__md__")])

    def _insert_markdown(self, text):
        self._md_renderer.insert_line(text)

    def reset_markdown_state(self):
        self._md_renderer.reset()

    def flush_markdown(self):
        self._md_renderer.flush()

    def _markdown_enabled(self):
        from src import settings as _app_settings
        return bool(_app_settings.get("console_markdown", True))

    def _configure_md_tags(self):
        self._md_renderer.configure_tags(self._font_size)

    def _write_segments(self, segments):
        if not self.winfo_exists():
            return
        self.output_area.config(state=tk.NORMAL)
        is_at_bottom = self.output_area.yview()[1] >= 1.0
        for text, color in segments:
            if color == "__md__":
                if self._markdown_enabled():
                    self._insert_markdown(text)
                else:
                    self.output_area.insert(tk.END, text, "md_plain")
            elif color:
                tag = f"color_{id(color)}"
                self.output_area.tag_configure(tag, foreground=color)
                self.output_area.insert(tk.END, text, tag)
            else:
                self.output_area.insert(tk.END, text)
        self.output_area.insert(tk.END, "\n")
        self._segments.extend(segments)
        self._segments.append(("\n", None))
        if is_at_bottom:
            self.output_area.see(tk.END)
        self.output_area.config(state=tk.DISABLED)

    def get_segments(self):
        return list(self._segments)

    def restore_segments(self, segments):
        self.output_area.config(state=tk.NORMAL)
        self.output_area.delete("1.0", tk.END)
        self._live_active = False
        self.reset_markdown_state()
        for text, color in segments:
            if color == "__md__":
                if self._markdown_enabled():
                    self._insert_markdown(text)
                else:
                    self.output_area.insert(tk.END, text, "md_plain")
            elif color:
                tag = f"color_{id(color)}"
                self.output_area.tag_configure(tag, foreground=color)
                self.output_area.insert(tk.END, text, tag)
            else:
                self.output_area.insert(tk.END, text)
        self.flush_markdown()
        self._segments = list(segments)
        self.output_area.see(tk.END)
        self.output_area.config(state=tk.DISABLED)

    def role_mark(self, text, color):
        self._write_segments([("\u25a3 ", color), (text, "__md__")])

    def warning(self, text):
        self.writeln(f"[!] {text}", WARN_COLOR)

    def error(self, text):
        self.writeln(f"[!] {text}", ERR_COLOR)

    def _on_enter(self, event):
        if event.state & 0x0001:
            self.input_text.insert("insert", "\n")
            try:
                result = self.input_text.count("1.0", "end", "displaylines")
                lines = result[0] if isinstance(result, tuple) else result
            except Exception:
                lines = 1
            self.input_text.configure(height=lines)
            return "break"
        self._close_autocomplete()
        raw = self._input_get().strip()
        self._input_set("")
        self.after(1, self._sync_input_height)
        if self._is_system:
            if raw == "stop":
                self._is_system = False
                self.prompt_label.config(
                    text=f"{self._mode_label}> "
                    if self._mode_handler else "Elwand> ",
                    fg=self._mode_fg if self._mode_handler else FG)
                self.writeln(f"! stop", color=FG)
                if self._system_stop_handler:
                    self._system_stop_handler()
                return
            if not raw:
                return
            if not self._history or self._history[-1] != raw:
                self._history.append(raw)
            self._history_index = len(self._history)
            self._saved_input = ""
            self.writeln(f"! {raw}", color=FG)
            if self._system_handler:
                self._system_handler(raw)
            return

        if not raw:
            return
        if not self._history or self._history[-1] != raw:
            self._history.append(raw)
        self._history_index = len(self._history)
        self._saved_input = ""
        self._execute(raw)
        return "break"

    def _on_up(self, event):
        if not self._history:
            return "break"
        if self._history_index == len(self._history):
            self._saved_input = self._input_get()
        if self._history_index > 0:
            self._history_index -= 1
            self._input_set(self._history[self._history_index])
            
        return "break"

    def _on_down(self, event):
        if self._history_index == len(self._history):
            return "break"
        self._history_index += 1
        if self._history_index == len(self._history):
            self._input_set(self._saved_input)
        else:
            self._input_set(self._history[self._history_index])
            
        return "break"

    def _adjust_font(self, delta):
        self._font_size = max(8, min(24, self._font_size + delta))
        new_font = (fonts.family(), self._font_size)
        self.output_area.configure(font=new_font)
        self._configure_md_tags()
        self.input_text.configure(font=new_font)
        self.prompt_label.configure(font=new_font)
        self._spinner_label.configure(font=new_font)
        if self._prompt_hovered:
            self.prompt_label.config(font=(fonts.family(), self._font_size, "underline"))
        if self._autocomplete_popup:
            self._close_arg_popup()
            self._close_arg2_popup()
            self._close_arg5_popup()
            self._autocomplete_listbox.configure(font=new_font)
            items = list(self._autocomplete_listbox.get(0, tk.END))
            longest = max((len(it.strip()) for it in items), default=10)
            self._autocomplete_listbox.configure(width=longest + 3)
            self._autocomplete_listbox.delete(0, tk.END)
            for item in items:
                self._autocomplete_listbox.insert(tk.END, item)
            self._autocomplete_listbox.selection_set(self._autocomplete_index)
            fs = self._font_size
            f = tkfont.Font(font=(fonts.family(), fs))
            longest = max((len(it.strip()) for it in items), default=10)
            w = f.measure(" " * (longest + 3)) + 4
            h = self._popup_height(self._autocomplete_listbox, len(items))
            con_top = self.winfo_rooty() - self.master.winfo_rooty()
            y = con_top - h
            self._autocomplete_popup.place_configure(x=0, y=y, width=w, height=h)
        from src.settings import set as _set_setting, save as _save_settings
        _set_setting("console_font_size", self._font_size)
        _save_settings()
        return "break"

    def _execute(self, raw):
        if raw.startswith("!"):
            cmd = raw[1:].strip()
            self.writeln(f"! {cmd}", color=FG)
            if self._system_handler and cmd:
                self._system_handler(cmd)
            return

        if self._mode_handler:
            self._blank_line_if_needed()
            self.write("User prompt > ", color=self._mode_fg)
            self.writeln(raw, color=FG)
            self.writeln("")
            self._mode_handler(raw)
            return

        self.writeln(f"Elwand> {raw}", color=FG)

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in self.commands:
            try:
                self.commands[cmd]["handler"](args)
            except Exception as e:
                self.error(str(e))
        else:
            self.body(f"Unknown command: {cmd}. Type 'help' for available commands.")

    def _cmd_help(self, args):
        self.title("Available commands")
        for name, info in sorted(self.commands.items()):
            self.body(f"  {name:<12} {info['help']}")
        for section_title, items in self.help_sections:
            self.writeln("")
            self.title(section_title)
            for item, desc in items:
                self.body(f"  {item:<12} {desc}")

    def _cmd_clear(self, args):
        self.output_area.config(state=tk.NORMAL)
        self.output_area.delete("1.0", tk.END)
        self._segments = []
        self._live_active = False
        self.reset_markdown_state()
        self.output_area.config(state=tk.DISABLED)

    def _on_key_press(self, event):
        if event.char == "!" and not self._is_system:
            self._is_system = True
            self.prompt_label.config(text="Local> ", fg=FG_DIM)
            self._skip_release = True
            self._close_autocomplete()
            return "break"
        if event.keysym not in ("Tab", "Return", "Escape", "Up", "Down", "Shift_L", "Shift_R",
                                "Control_L", "Control_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R",
                                "Command", "Caps_Lock", "BackSpace", "Delete"):
            if self._filter_id:
                self.after_cancel(self._filter_id)
            self._filter_id = self.after(80, self._filter_autocomplete)
        if event.keysym not in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                                "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Command",
                                "Caps_Lock"):
            self.after(1, self._sync_input_height)

    def _sync_input_height(self):
        try:
            result = self.input_text.count("1.0", "end", "displaylines")
            lines = result[0] if isinstance(result, tuple) else result
        except Exception:
            lines = 1
        self.input_text.configure(height=max(1, lines))

    def _on_key_release(self, event):
        if self._skip_release:
            self._skip_release = False
            return
        if self._is_system and not self._input_get() and event.keysym in ("BackSpace", "Delete"):
            self._is_system = False
            self.prompt_label.config(
                text=f"{self._mode_label}> "
                if self._mode_handler else "Elwand> ",
                fg=self._mode_fg if self._mode_handler else FG)
            return
        if event.keysym in ("BackSpace", "Delete"):
            if self._filter_id:
                self.after_cancel(self._filter_id)
            self._filter_id = self.after(80, self._filter_autocomplete)

    def _on_prompt_click(self, event=None):
        if self._mode_cycle_cb:
            self._mode_cycle_cb()

    def _on_prompt_enter(self, event=None):
        self._prompt_hovered = True
        self.prompt_label.config(font=(fonts.family(), self._font_size, "underline"))

    def _on_prompt_leave(self, event=None):
        self._prompt_hovered = False
        self.prompt_label.config(font=(fonts.family(), self._font_size))

    def _on_tab(self, event):
        if self._is_system:
            return "break"
        raw = self._input_get()
        prefix = raw.strip()
        if not prefix:
            if self._mode_cycle_cb:
                self._mode_cycle_cb()
            return "break"

        parts = prefix.split(None, 1)
        cmd_prefix = parts[0]
        arg_prefix = parts[1] if len(parts) > 1 else ""
        in_arg_mode = " " in raw.lstrip()

        if self._mode_handler and self._mode_commands:
            match_src = self._mode_commands
        else:
            match_src = self.commands
        if arg_prefix and not any(n.startswith(cmd_prefix) for n in match_src):
            if self._mode_cycle_cb:
                self._mode_cycle_cb()
            return "break"

        if in_arg_mode and cmd_prefix in self._subcommands:
            arg1 = arg_prefix.split(None, 1)[0] if arg_prefix else ""
            sc_matches = [s for s in self._subcommands[cmd_prefix] if s.startswith(arg1)]
            if sc_matches:
                if self._arg5_popup:
                    if len(self._arg5_matches) == 1:
                        _, insert = self._arg5_matches[0]
                        if insert:
                            p5 = prefix.split(None, 5)
                            c = p5[0] if len(p5) > 0 else ""
                            a1 = p5[1] if len(p5) > 1 else ""
                            a2 = p5[2] if len(p5) > 2 else ""
                            a3 = p5[3] if len(p5) > 3 else ""
                            a4 = p5[4] if len(p5) > 4 else ""
                            self._input_set(f"{c} {a1} {a2} {a3} {a4} {insert} ")
                            
                            self._filter_autocomplete()
                        return "break"
                    inserts = [i for _, i in self._arg5_matches if i]
                    if inserts:
                        cp = self._common_prefix(inserts)
                        p5 = prefix.split(None, 5)
                        a5_text = p5[5] if len(p5) > 5 else ""
                        if len(cp) > len(a5_text):
                            c = p5[0] if len(p5) > 0 else ""
                            a1 = p5[1] if len(p5) > 1 else ""
                            a2 = p5[2] if len(p5) > 2 else ""
                            a3 = p5[3] if len(p5) > 3 else ""
                            a4 = p5[4] if len(p5) > 4 else ""
                            self._input_set(f"{c} {a1} {a2} {a3} {a4} {cp}")
                            
                            self._filter_autocomplete()
                            return "break"
                    self._arg5_index = (self._arg5_index + 1) % len(self._arg5_matches)
                    self._arg5_listbox.selection_clear(0, tk.END)
                    self._arg5_listbox.selection_set(self._arg5_index)
                    self._arg5_listbox.activate(self._arg5_index)
                    return "break"
                if self._arg4_popup:
                    if len(self._arg4_matches) == 1:
                        _, insert = self._arg4_matches[0]
                        if insert:
                            p4 = prefix.split(None, 4)
                            c = p4[0] if len(p4) > 0 else ""
                            a1 = p4[1] if len(p4) > 1 else ""
                            a2 = p4[2] if len(p4) > 2 else ""
                            a3 = p4[3] if len(p4) > 3 else ""
                            self._input_set(f"{c} {a1} {a2} {a3} {insert} ")
                            
                            self._filter_autocomplete()
                        return "break"
                    inserts = [i for _, i in self._arg4_matches if i]
                    if inserts:
                        cp = self._common_prefix(inserts)
                        p4 = prefix.split(None, 4)
                        a4_text = p4[4] if len(p4) > 4 else ""
                        if len(cp) > len(a4_text):
                            c = p4[0] if len(p4) > 0 else ""
                            a1 = p4[1] if len(p4) > 1 else ""
                            a2 = p4[2] if len(p4) > 2 else ""
                            a3 = p4[3] if len(p4) > 3 else ""
                            self._input_set(f"{c} {a1} {a2} {a3} {cp}")
                            
                            self._filter_autocomplete()
                            return "break"
                    self._arg4_index = (self._arg4_index + 1) % len(self._arg4_matches)
                    self._arg4_listbox.selection_clear(0, tk.END)
                    self._arg4_listbox.selection_set(self._arg4_index)
                    self._arg4_listbox.activate(self._arg4_index)
                    return "break"
                if self._arg3_popup:
                    if len(self._arg3_matches) == 1:
                        _, insert = self._arg3_matches[0]
                        if insert:
                            p3 = prefix.split(None, 3)
                            c = p3[0] if len(p3) > 0 else ""
                            a1 = p3[1] if len(p3) > 1 else ""
                            a2 = p3[2] if len(p3) > 2 else ""
                            self._input_set(f"{c} {a1} {a2} {insert} ")
                            
                            self._filter_autocomplete()
                        return "break"
                    inserts = [i for _, i in self._arg3_matches if i]
                    if inserts:
                        cp = self._common_prefix(inserts)
                        p3 = prefix.split(None, 3)
                        a3_text = p3[3] if len(p3) > 3 else ""
                        if len(cp) > len(a3_text):
                            c = p3[0] if len(p3) > 0 else ""
                            a1 = p3[1] if len(p3) > 1 else ""
                            a2 = p3[2] if len(p3) > 2 else ""
                            self._input_set(f"{c} {a1} {a2} {cp}")
                            
                            self._filter_autocomplete()
                            return "break"
                    self._arg3_index = (self._arg3_index + 1) % len(self._arg3_matches)
                    self._arg3_listbox.selection_clear(0, tk.END)
                    self._arg3_listbox.selection_set(self._arg3_index)
                    self._arg3_listbox.activate(self._arg3_index)
                    return "break"
                if self._arg2_popup:
                    if len(self._arg2_matches) == 1:
                        _, insert = self._arg2_matches[0]
                        if insert:
                            self._input_set(f"{cmd_prefix} {arg1} {insert} ")
                            
                            self._filter_autocomplete()
                        return "break"
                    inserts = [i for _, i in self._arg2_matches if i]
                    if inserts:
                        cp = self._common_prefix(inserts)
                        p2 = prefix.split(None, 2)
                        a2_text = p2[2] if len(p2) > 2 else ""
                        if len(cp) > len(a2_text):
                            self._input_set(f"{cmd_prefix} {arg1} {cp}")
                            
                            self._filter_autocomplete()
                            return "break"
                    self._arg2_index = (self._arg2_index + 1) % len(self._arg2_matches)
                    self._arg2_listbox.selection_clear(0, tk.END)
                    self._arg2_listbox.selection_set(self._arg2_index)
                    self._arg2_listbox.activate(self._arg2_index)
                    return "break"
                if len(sc_matches) == 1 and arg_prefix and arg_prefix != sc_matches[0]:
                    self._input_set(f"{cmd_prefix} {sc_matches[0]} ")
                    
                    self._filter_autocomplete()
                    return "break"
                if len(sc_matches) > 1 and self._arg_popup:
                    cp = self._common_prefix(sc_matches)
                    if len(cp) > len(arg1):
                        self._input_set(f"{cmd_prefix} {cp}")
                        
                        self._filter_autocomplete()
                        return "break"
                if self._arg_popup:
                    self._arg_index = (self._arg_index + 1) % len(self._arg_matches)
                    self._arg_listbox.selection_clear(0, tk.END)
                    self._arg_listbox.selection_set(self._arg_index)
                    self._arg_listbox.activate(self._arg_index)
                return "break"

        if self._mode_handler and self._mode_commands:
            match_src = self._mode_commands
        else:
            match_src = self.commands
        matches = [(n, match_src[n] if isinstance(match_src, dict) else match_src[n]["help"])
                   for n in match_src
                   if n.startswith(prefix)]
        matches.sort(key=lambda x: x[0])
        if not matches:
            return "break"
        if len(matches) == 1 and prefix:
            self._input_set(matches[0][0] + " ")
            
            self._filter_autocomplete()
            return "break"
        if len(matches) > 1:
            cp = self._common_prefix([m[0] for m in matches])
            if len(cp) > len(prefix):
                self._input_set(cp)
                
                self._filter_autocomplete()
                return "break"

        if self._autocomplete_popup:
            self._autocomplete_index = (self._autocomplete_index + 1) % len(self._autocomplete_matches)
            self._autocomplete_listbox.selection_clear(0, tk.END)
            self._autocomplete_listbox.selection_set(self._autocomplete_index)
            self._autocomplete_listbox.activate(self._autocomplete_index)
            return "break"

        self._show_or_update(matches)
        return "break"

    def _on_escape(self, event):
        if self._autocomplete_popup:
            self._close_autocomplete()
            return "break"

    def _popup_height(self, lb, n):
        lb.configure(height=max(1, n))
        return lb.winfo_reqheight() + 2

    def _show_autocomplete(self, matches):
        self._close_autocomplete()
        fs = self._font_size
        f = tkfont.Font(font=(fonts.family(), fs))
        longest = max((len(name) for name, _ in matches), default=10)
        frame = tk.Frame(self.master, bg="#111111", highlightbackground="#333333", highlightthickness=1)

        lb = tk.Listbox(frame, bg="#111111", fg="#FFFFFF", selectbackground="#333333",
                        selectforeground="#FFFFFF", font=(fonts.family(), fs),
                        width=longest + 3, borderwidth=0,
                        highlightthickness=0, activestyle="none", exportselection=False)
        lb.pack(fill=tk.BOTH, expand=True)
        for name, help_text in matches:
            lb.insert(tk.END, f"  {name}")
        lb.selection_set(0)
        lb.activate(0)
        lb.bind("<ButtonRelease-1>", self._on_popup_click)
        lb.bind("<Escape>", lambda e: (self._close_autocomplete(), self._input_focus()))

        popup_w = f.measure(" " * (longest + 3)) + 4
        h = self._popup_height(lb, len(matches))
        con_top = self.winfo_rooty() - self.master.winfo_rooty()
        y = con_top - h

        frame.place(x=0, y=y, width=popup_w, height=h)
        frame.lift()

        self._autocomplete_popup = frame
        self._autocomplete_listbox = lb
        self._start_tracking()

    def _show_or_update(self, matches):
        names = [m[0] for m in matches]
        self._autocomplete_names = names
        if self._autocomplete_popup:
            lb = self._autocomplete_listbox
            lb.delete(0, tk.END)
            for name, help_text in matches:
                lb.insert(tk.END, f"  {name}")
            lb.selection_set(0)
            lb.activate(0)
            self._autocomplete_matches = matches
            self._autocomplete_index = 0
            fs = self._font_size
            f = tkfont.Font(font=(fonts.family(), fs))
            longest = max((len(name) for name, _ in matches), default=10)
            lb.configure(width=longest + 3)
            popup_w = f.measure(" " * (longest + 3)) + 4
            h = self._popup_height(lb, len(matches))
            con_top = self.winfo_rooty() - self.master.winfo_rooty()
            y = con_top - h
            self._autocomplete_popup.place_configure(x=0, y=y, width=popup_w, height=h)
            self._autocomplete_popup.lift()
        else:
            self._show_autocomplete(matches)

    def _filter_autocomplete(self):
        if self._is_system:
            return
        raw = self._input_get()
        prefix = raw.strip()
        if not prefix:
            if self._mode_handler and self._mode_commands:
                all_cmds = [(n, h) for n, h in self._mode_commands.items()]
            else:
                all_cmds = [(n, info["help"]) for n, info in self.commands.items()]
            all_cmds.sort(key=lambda x: x[0])
            self._close_arg_popup()
            self._close_arg2_popup()
            self._close_arg3_popup()
            self._close_arg4_popup()
            self._close_arg5_popup()
            self._show_or_update(all_cmds)
            return

        parts = prefix.split(None, 2)
        cmd_prefix = parts[0]
        arg_prefix = parts[1] if len(parts) > 1 else ""
        in_arg_mode = " " in raw.lstrip()

        if self._mode_handler and self._mode_commands:
            match_src = self._mode_commands
        else:
            match_src = self.commands
        cmd_matches = [(n, match_src[n] if isinstance(match_src, dict) else match_src[n]["help"])
                       for n in match_src
                       if n.startswith(cmd_prefix)]
        cmd_matches.sort(key=lambda x: x[0])

        if not cmd_matches:
            self._close_autocomplete()
            return

        if in_arg_mode and cmd_prefix in self._subcommands:
            sc_items = self._subcommands[cmd_prefix]
            arg1_text = arg_prefix.split(None, 1)[0] if arg_prefix else ""
            sc_matches = [s for s in sc_items if s.startswith(arg1_text)]
            self._show_or_update(cmd_matches)
            self._show_arg_popup(sc_matches)

            if len(parts) >= 2 and parts[1] in sc_items:
                parts3 = prefix.split(None, 3)
                parts4 = prefix.split(None, 5)

                provider = self._arg2_providers.get((cmd_prefix, parts[1]))
                if provider:
                    arg2_text = parts3[2] if len(parts3) > 2 else ""
                    raw_items = provider(arg2_text)
                    normalized = []
                    for it in raw_items:
                        if isinstance(it, tuple):
                            d, i = it
                        else:
                            d, i = it, it
                        if (cmd_prefix, parts[1]) in self._arg2_contains:
                            if not arg2_text or arg2_text in d:
                                normalized.append((d, i))
                        elif i.startswith(arg2_text) or any(self._matches_word(arg2_text, w) for w in d.split()):
                            normalized.append((d, i))
                    if normalized:
                        self._show_arg2_popup(normalized)
                    else:
                        self._close_arg2_popup()
                else:
                    self._close_arg2_popup()

                has_arg3 = len(parts3) >= 4 or (len(parts3) >= 3 and raw.rstrip() != raw)
                if has_arg3:
                    provider3 = self._arg3_providers.get((cmd_prefix, parts[1]))
                    if provider3:
                        arg3_text = parts4[3] if len(parts4) > 3 else ""
                        arg2_value = parts3[2] if len(parts3) > 2 else ""
                        raw3 = provider3(arg3_text, arg2_value)
                        normalized3 = []
                        hint3 = None
                        for it in raw3:
                            if isinstance(it, tuple):
                                d, i = it
                            else:
                                d, i = it, it
                            if (cmd_prefix, parts[1]) in self._arg3_contains:
                                if not arg3_text or arg3_text in d or not i:
                                    if not i:
                                        hint3 = (d, i)
                                    else:
                                        normalized3.append((d, i))
                            elif i.startswith(arg3_text) or any(self._matches_word(arg3_text, w) for w in d.split()):
                                normalized3.append((d, i))
                        if not normalized3 and hint3:
                            normalized3 = [hint3]
                        if normalized3:
                            self._show_arg3_popup(normalized3)
                        else:
                            self._close_arg3_popup()
                    else:
                        self._close_arg3_popup()
                else:
                    self._close_arg3_popup()

                has_arg4 = len(parts4) >= 5 or (len(parts4) >= 4 and raw.rstrip() != raw)
                if has_arg4:
                    provider4 = self._arg4_providers.get((cmd_prefix, parts[1]))
                    if provider4:
                        arg4_text = parts4[4] if len(parts4) > 4 else ""
                        arg2_val = parts3[2] if len(parts3) > 2 else ""
                        try:
                            raw4 = provider4(arg4_text, arg2_val) if arg2_val else provider4(arg4_text)
                        except TypeError:
                            raw4 = provider4(arg4_text)
                        normalized4 = []
                        hint4 = None
                        for it in raw4:
                            if isinstance(it, tuple):
                                d, i = it
                            else:
                                d, i = it, it
                            if (cmd_prefix, parts[1]) in self._arg4_contains:
                                if not arg4_text or arg4_text in d or not i:
                                    if not i:
                                        hint4 = (d, i)
                                    else:
                                        normalized4.append((d, i))
                            elif i.startswith(arg4_text) or any(self._matches_word(arg4_text, w) for w in d.split()):
                                normalized4.append((d, i))
                        if not normalized4 and hint4:
                            normalized4 = [hint4]
                        if normalized4:
                            self._show_arg4_popup(normalized4)
                        else:
                            self._close_arg4_popup()
                    else:
                        self._close_arg4_popup()
                else:
                    self._close_arg4_popup()

                has_arg5 = len(parts4) >= 6 or (len(parts4) >= 5 and raw.rstrip() != raw)
                if has_arg5:
                    provider5 = self._arg5_providers.get((cmd_prefix, parts[1]))
                    if provider5:
                        arg5_text = parts4[5] if len(parts4) > 5 else ""
                        arg2_val = parts3[2] if len(parts3) > 2 else ""
                        try:
                            raw5 = provider5(arg5_text, arg2_val) if arg2_val else provider5(arg5_text)
                        except TypeError:
                            raw5 = provider5(arg5_text)
                        normalized5 = []
                        hint5 = None
                        for it in raw5:
                            if isinstance(it, tuple):
                                d, i = it
                            else:
                                d, i = it, it
                            if (cmd_prefix, parts[1]) in self._arg5_contains:
                                if not arg5_text or arg5_text in d or not i:
                                    if not i:
                                        hint5 = (d, i)
                                    else:
                                        normalized5.append((d, i))
                            elif i.startswith(arg5_text) or any(self._matches_word(arg5_text, w) for w in d.split()):
                                normalized5.append((d, i))
                        if not normalized5 and hint5:
                            normalized5 = [hint5]
                        if normalized5:
                            self._show_arg5_popup(normalized5)
                        else:
                            self._close_arg5_popup()
                    else:
                        self._close_arg5_popup()
                else:
                    self._close_arg5_popup()
            else:
                self._close_arg2_popup()
                self._close_arg3_popup()
                self._close_arg4_popup()
                self._close_arg5_popup()
        else:
            self._close_arg_popup()
            self._close_arg2_popup()
            self._close_arg3_popup()
            self._close_arg4_popup()
            self._close_arg5_popup()
            self._show_or_update(cmd_matches)

    def _show_arg_popup(self, items):
        if not self._autocomplete_popup:
            return
        fs = self._font_size
        f = tkfont.Font(font=(fonts.family(), fs))
        longest = max((len(s) for s in items), default=10)
        popup_w = f.measure(" " * (longest + 3)) + 4

        cmd_x = self._autocomplete_popup.winfo_x()
        cmd_w = self._autocomplete_popup.winfo_width()
        cmd_y = self._autocomplete_popup.winfo_y()
        cmd_h = self._autocomplete_popup.winfo_height()
        bottom = cmd_y + cmd_h

        if self._arg_popup:
            lb = self._arg_listbox
            lb.delete(0, tk.END)
            for s in items:
                lb.insert(tk.END, f"  {s}")
            lb.selection_set(0)
            lb.activate(0)
            lb.configure(width=longest + 3)
            self._arg_matches = items
            self._arg_index = 0
            h = self._popup_height(lb, len(items))
            self._arg_popup.place_configure(
                x=cmd_x + cmd_w, y=bottom - h, width=popup_w, height=h)
            self._arg_popup.lift()
        else:
            frame = tk.Frame(self.master, bg="#111111", highlightbackground="#333333", highlightthickness=1)
            lb = tk.Listbox(frame, bg="#111111", fg="#FFFFFF", selectbackground="#333333",
                            selectforeground="#FFFFFF", font=(fonts.family(), fs),
                            width=longest + 3, borderwidth=0,
                            highlightthickness=0, activestyle="none", exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            for s in items:
                lb.insert(tk.END, f"  {s}")
            lb.selection_set(0)
            lb.activate(0)
            lb.bind("<ButtonRelease-1>", lambda e: self._on_arg_click())
            lb.bind("<Escape>", lambda e: (self._close_autocomplete(), self._input_focus()))

            h = self._popup_height(lb, len(items))
            frame.place(x=cmd_x + cmd_w, y=bottom - h, width=popup_w, height=h)
            frame.lift()

            self._arg_popup = frame
            self._arg_listbox = lb
            self._arg_matches = items
            self._arg_index = 0

    def _close_arg_popup(self):
        if self._arg_popup:
            self._arg_popup.destroy()
            self._arg_popup = None
            self._arg_listbox = None
            self._arg_matches = []
            self._arg_index = -1

    def _show_arg2_popup(self, items):
        if not self._arg_popup:
            return
        normalized = []
        for it in items:
            if isinstance(it, tuple):
                display, insert = it
            else:
                display, insert = it, it
            normalized.append((display, insert))

        displays = [d for d, _ in normalized]

        fs = self._font_size
        f = tkfont.Font(font=(fonts.family(), fs))
        longest = max((len(s) for s in displays), default=10)
        popup_w = f.measure(" " * (longest + 3)) + 4

        arg1_x = self._arg_popup.winfo_x()
        arg1_w = self._arg_popup.winfo_width()
        arg1_y = self._arg_popup.winfo_y()
        arg1_h = self._arg_popup.winfo_height()
        bottom = arg1_y + arg1_h

        if self._arg2_popup:
            lb = self._arg2_listbox
            lb.delete(0, tk.END)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.configure(width=longest + 3)
            self._arg2_matches = normalized
            self._arg2_index = 0
            h = self._popup_height(lb, len(displays))
            self._arg2_popup.place_configure(
                x=arg1_x + arg1_w, y=bottom - h, width=popup_w, height=h)
            self._arg2_popup.lift()
        else:
            frame = tk.Frame(self.master, bg="#111111", highlightbackground="#333333", highlightthickness=1)
            lb = tk.Listbox(frame, bg="#111111", fg="#FFFFFF", selectbackground="#333333",
                            selectforeground="#FFFFFF", font=(fonts.family(), fs),
                            width=longest + 3, borderwidth=0,
                            highlightthickness=0, activestyle="none", exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.bind("<ButtonRelease-1>", lambda e: self._on_arg2_click())
            lb.bind("<Escape>", lambda e: (self._close_autocomplete(), self._input_focus()))

            h = self._popup_height(lb, len(displays))
            frame.place(x=arg1_x + arg1_w, y=bottom - h, width=popup_w, height=h)
            frame.lift()

            self._arg2_popup = frame
            self._arg2_listbox = lb
            self._arg2_matches = normalized
            self._arg2_index = 0

    def _close_arg2_popup(self):
        if self._arg2_popup:
            self._arg2_popup.destroy()
            self._arg2_popup = None
            self._arg2_listbox = None
            self._arg2_matches = []
            self._arg2_index = -1

    def _on_arg2_click(self):
        if self._arg2_index >= 0 and self._arg2_matches:
            current = self._input_get().strip()
            parts = current.split(None, 2)
            cmd = parts[0] if len(parts) > 0 else ""
            arg1_val = parts[1] if len(parts) > 1 else ""
            _, insert = self._arg2_matches[self._arg2_index]
            if insert:
                self._input_set(f"{cmd} {arg1_val} {insert} ")
                
        self._close_autocomplete()
        self._input_focus()

    def _show_arg3_popup(self, items):
        if not self._arg2_popup:
            return
        normalized = []
        for it in items:
            if isinstance(it, tuple):
                display, insert = it
            else:
                display, insert = it, it
            normalized.append((display, insert))

        displays = [d for d, _ in normalized]

        fs = self._font_size
        f = tkfont.Font(font=(fonts.family(), fs))
        longest = max((len(s) for s in displays), default=10)
        popup_w = f.measure(" " * (longest + 3)) + 4

        arg2_x = self._arg2_popup.winfo_x()
        arg2_w = self._arg2_popup.winfo_width()
        arg2_y = self._arg2_popup.winfo_y()
        arg2_h = self._arg2_popup.winfo_height()
        bottom = arg2_y + arg2_h

        if self._arg3_popup:
            lb = self._arg3_listbox
            lb.delete(0, tk.END)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.configure(width=longest + 3)
            self._arg3_matches = normalized
            self._arg3_index = 0
            h = self._popup_height(lb, len(displays))
            self._arg3_popup.place_configure(
                x=arg2_x + arg2_w, y=bottom - h, width=popup_w, height=h)
            self._arg3_popup.lift()
        else:
            frame = tk.Frame(self.master, bg="#111111", highlightbackground="#333333", highlightthickness=1)
            lb = tk.Listbox(frame, bg="#111111", fg="#FFFFFF", selectbackground="#333333",
                            selectforeground="#FFFFFF", font=(fonts.family(), fs),
                            width=longest + 3, borderwidth=0,
                            highlightthickness=0, activestyle="none", exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.bind("<ButtonRelease-1>", lambda e: self._on_arg3_click())
            lb.bind("<Escape>", lambda e: (self._close_autocomplete(), self._input_focus()))

            h = self._popup_height(lb, len(displays))
            frame.place(x=arg2_x + arg2_w, y=bottom - h, width=popup_w, height=h)
            frame.lift()

            self._arg3_popup = frame
            self._arg3_listbox = lb
            self._arg3_matches = normalized
            self._arg3_index = 0

    def _close_arg3_popup(self):
        if self._arg3_popup:
            self._arg3_popup.destroy()
            self._arg3_popup = None
            self._arg3_listbox = None
            self._arg3_matches = []
            self._arg3_index = -1

    def _on_arg3_click(self):
        if self._arg3_index >= 0 and self._arg3_matches:
            current = self._input_get().strip()
            parts = current.split(None, 3)
            cmd = parts[0] if len(parts) > 0 else ""
            arg1_val = parts[1] if len(parts) > 1 else ""
            arg2_val = parts[2] if len(parts) > 2 else ""
            _, insert = self._arg3_matches[self._arg3_index]
            if insert:
                self._input_set(f"{cmd} {arg1_val} {arg2_val} {insert} ")
                
        self._close_autocomplete()
        self._input_focus()

    def _show_arg4_popup(self, items):
        if not self._arg3_popup:
            return
        normalized = []
        for it in items:
            if isinstance(it, tuple):
                display, insert = it
            else:
                display, insert = it, it
            normalized.append((display, insert))

        displays = [d for d, _ in normalized]

        fs = self._font_size
        f = tkfont.Font(font=(fonts.family(), fs))
        longest = max((len(s) for s in displays), default=10)
        popup_w = f.measure(" " * (longest + 3)) + 4

        arg3_x = self._arg3_popup.winfo_x()
        arg3_w = self._arg3_popup.winfo_width()
        arg3_y = self._arg3_popup.winfo_y()
        arg3_h = self._arg3_popup.winfo_height()
        bottom = arg3_y + arg3_h

        if self._arg4_popup:
            lb = self._arg4_listbox
            lb.delete(0, tk.END)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.configure(width=longest + 3)
            self._arg4_matches = normalized
            self._arg4_index = 0
            h = self._popup_height(lb, len(displays))
            self._arg4_popup.place_configure(
                x=arg3_x + arg3_w, y=bottom - h, width=popup_w, height=h)
            self._arg4_popup.lift()
        else:
            frame = tk.Frame(self.master, bg="#111111", highlightbackground="#333333", highlightthickness=1)
            lb = tk.Listbox(frame, bg="#111111", fg="#FFFFFF", selectbackground="#333333",
                            selectforeground="#FFFFFF", font=(fonts.family(), fs),
                            width=longest + 3, borderwidth=0,
                            highlightthickness=0, activestyle="none", exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.bind("<ButtonRelease-1>", lambda e: self._on_arg4_click())
            lb.bind("<Escape>", lambda e: (self._close_autocomplete(), self._input_focus()))

            h = self._popup_height(lb, len(displays))
            frame.place(x=arg3_x + arg3_w, y=bottom - h, width=popup_w, height=h)
            frame.lift()

            self._arg4_popup = frame
            self._arg4_listbox = lb
            self._arg4_matches = normalized
            self._arg4_index = 0

    def _close_arg4_popup(self):
        if self._arg4_popup:
            self._arg4_popup.destroy()
            self._arg4_popup = None
            self._arg4_listbox = None
            self._arg4_matches = []
            self._arg4_index = -1

    def _on_arg4_click(self):
        if self._arg4_index >= 0 and self._arg4_matches:
            current = self._input_get().strip()
            parts = current.split(None, 4)
            cmd = parts[0] if len(parts) > 0 else ""
            arg1_val = parts[1] if len(parts) > 1 else ""
            arg2_val = parts[2] if len(parts) > 2 else ""
            arg3_val = parts[3] if len(parts) > 3 else ""
            _, insert = self._arg4_matches[self._arg4_index]
            if insert:
                self._input_set(f"{cmd} {arg1_val} {arg2_val} {arg3_val} {insert} ")
                
        self._close_autocomplete()
        self._input_focus()

    def _show_arg5_popup(self, items):
        if not self._arg4_popup:
            return
        normalized = []
        for it in items:
            if isinstance(it, tuple):
                display, insert = it
            else:
                display, insert = it, it
            normalized.append((display, insert))

        displays = [d for d, _ in normalized]
        fs = self._font_size
        f = tkfont.Font(font=(fonts.family(), fs))
        longest = max((len(s) for s in displays), default=10)
        popup_w = f.measure(" " * (longest + 3)) + 4

        arg4_x = self._arg4_popup.winfo_x()
        arg4_w = self._arg4_popup.winfo_width()
        arg4_y = self._arg4_popup.winfo_y()
        arg4_h = self._arg4_popup.winfo_height()
        bottom = arg4_y + arg4_h

        if self._arg5_popup:
            lb = self._arg5_listbox
            lb.delete(0, tk.END)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.configure(width=longest + 3)
            self._arg5_matches = normalized
            self._arg5_index = 0
            h = self._popup_height(lb, len(displays))
            self._arg5_popup.place_configure(
                x=arg4_x + arg4_w, y=bottom - h, width=popup_w, height=h)
            self._arg5_popup.lift()
        else:
            frame = tk.Frame(self.master, bg="#111111", highlightbackground="#333333", highlightthickness=1)
            lb = tk.Listbox(frame, bg="#111111", fg="#FFFFFF", selectbackground="#333333",
                            selectforeground="#FFFFFF", font=(fonts.family(), fs),
                            width=longest + 3, borderwidth=0,
                            highlightthickness=0, activestyle="none", exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            for d in displays:
                lb.insert(tk.END, f"  {d}")
            lb.selection_set(0)
            lb.activate(0)
            lb.bind("<ButtonRelease-1>", lambda e: self._on_arg5_click())
            lb.bind("<Escape>", lambda e: (self._close_autocomplete(), self._input_focus()))
            h = self._popup_height(lb, len(displays))
            frame.place(x=arg4_x + arg4_w, y=bottom - h, width=popup_w, height=h)
            frame.lift()
            self._arg5_popup = frame
            self._arg5_listbox = lb
            self._arg5_matches = normalized
            self._arg5_index = 0

    def _close_arg5_popup(self):
        if self._arg5_popup:
            self._arg5_popup.destroy()
            self._arg5_popup = None
            self._arg5_listbox = None
            self._arg5_matches = []
            self._arg5_index = -1

    def _on_arg5_click(self):
        if self._arg5_index >= 0 and self._arg5_matches:
            current = self._input_get().strip()
            parts = current.split(None, 5)
            cmd = parts[0] if len(parts) > 0 else ""
            a1 = parts[1] if len(parts) > 1 else ""
            a2 = parts[2] if len(parts) > 2 else ""
            a3 = parts[3] if len(parts) > 3 else ""
            a4 = parts[4] if len(parts) > 4 else ""
            _, insert = self._arg5_matches[self._arg5_index]
            if insert:
                self._input_set(f"{cmd} {a1} {a2} {a3} {a4} {insert} ")
                
        self._close_autocomplete()
        self._input_focus()

    def _on_arg_click(self):
        if self._arg_index >= 0 and self._arg_matches:
            current = self._input_get().strip()
            parts = current.split(None, 1)
            cmd = parts[0]
            arg = self._arg_matches[self._arg_index]
            self._input_set(f"{cmd} {arg} ")
            
        self._close_autocomplete()
        self._input_focus()

    def _on_focus_in(self, event):
        if not self._is_system:
            self.after(50, self._filter_autocomplete)

    def _on_focus_out(self, event):
        pass

    def _on_root_click(self, event):
        if not self._autocomplete_popup:
            return
        if event.widget == self.input_text:
            return
        popup = self._autocomplete_popup
        if popup.winfo_containing(event.x_root, event.y_root) == popup:
            return
        if self._arg_popup and self._arg_popup.winfo_containing(event.x_root, event.y_root) == self._arg_popup:
            return
        if self._arg2_popup and self._arg2_popup.winfo_containing(event.x_root, event.y_root) == self._arg2_popup:
            return
        if self._arg3_popup and self._arg3_popup.winfo_containing(event.x_root, event.y_root) == self._arg3_popup:
            return
        if self._arg4_popup and self._arg4_popup.winfo_containing(event.x_root, event.y_root) == self._arg4_popup:
            return
        if self._arg5_popup and self._arg5_popup.winfo_containing(event.x_root, event.y_root) == self._arg5_popup:
            return
        self._close_autocomplete()

    def _close_autocomplete(self):
        self._close_arg_popup()
        self._close_arg2_popup()
        self._close_arg3_popup()
        self._close_arg4_popup()
        self._close_arg5_popup()
        if self._filter_id:
            self.after_cancel(self._filter_id)
            self._filter_id = None
        if self._track_id:
            self.after_cancel(self._track_id)
            self._track_id = None
        if self._autocomplete_popup:
            self._autocomplete_popup.destroy()
            self._autocomplete_popup = None
            self._autocomplete_listbox = None
            self._autocomplete_matches = []
            self._autocomplete_index = -1

    def _autocomplete_navigate(self, delta):
        idx = self._autocomplete_index + delta
        if 0 <= idx < len(self._autocomplete_matches):
            self._autocomplete_index = idx
            self._autocomplete_listbox.selection_clear(0, tk.END)
            self._autocomplete_listbox.selection_set(idx)
            self._autocomplete_listbox.activate(idx)

    def _autocomplete_select(self):
        if self._autocomplete_index >= 0 and self._autocomplete_matches:
            self._input_set(self._autocomplete_matches[self._autocomplete_index][0] + " ")
            
        self._close_autocomplete()
        self._input_focus()

    def _on_popup_click(self, event):
        idx = self._autocomplete_listbox.nearest(event.y)
        if 0 <= idx < len(self._autocomplete_matches):
            self._autocomplete_index = idx
            self._autocomplete_select()

    def _start_tracking(self):
        self._stop_tracking()
        self._track_id = self.after(100, self._track_popup)

    def _stop_tracking(self):
        if self._track_id:
            self.after_cancel(self._track_id)
            self._track_id = None

    def _track_popup(self):
        if not self._autocomplete_popup:
            return
        h = self._autocomplete_popup.winfo_height()
        con_top = self.winfo_rooty() - self.master.winfo_rooty()
        y = con_top - h
        if y != self._last_popup_y:
            self._last_popup_y = y
            self._autocomplete_popup.place_configure(y=y)
        self._track_id = self.after(100, self._track_popup)
