import os
import re
import subprocess
import threading
import tkinter as tk
from src.gui import fonts, windowing

MUTED = "#888888"
BRIGHT = "#ffffff"
BG = "#111111"
FG = "#ffffff"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"
LINE_NUM_FG = "#555555"
BASE_BG = "#000000"


class FileDetailView:
    pass


class PocDialog(tk.Toplevel):
    MAX_MATCHES = 200

    def __init__(self, parent, file_path, title="POC"):
        super().__init__(parent)
        self._file_path = file_path
        self._proc = None
        self._dirty = False
        self._lines = []
        self._total = 0
        self._matches = []
        self._match_index = -1
        self._last_query = ""
        self._last_regex = False

        self.title(title)
        windowing.size_dialog(self, 1100, 800, min_w=800, min_h=600)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=0)

        self._build_search_bar()
        self._build_editor_with_output()
        self._build_footer()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._load_file)

        self.bind("<Control-f>", lambda e: self._focus_search())
        self.bind("<Control-s>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self._focus_editor())
        self.bind("<F5>", lambda e: self._exec_poc())

    def _build_search_bar(self):
        top = tk.Frame(self, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 0))

        search_frame = tk.Frame(top, bg=BG)
        search_frame.pack(fill=tk.X, pady=(0, 4))
        search_frame.columnconfigure(0, weight=1)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._on_query_changed())
        self._search_entry = tk.Entry(
            search_frame, textvariable=self._search_var,
            bg="#000000", fg=FG, insertbackground=FG,
            font=fonts.view_font(13), relief=tk.FLAT, borderwidth=0,
            highlightbackground="#333333", highlightthickness=1,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self._search_entry.bind("<Return>", lambda e: self._find_next())

        self._regex_var = tk.BooleanVar(value=False)
        self._regex_var.trace_add("write", lambda *a: self._on_query_changed())
        regex_cb = tk.Checkbutton(
            search_frame, text="Regex", variable=self._regex_var,
            bg=BG, fg=MUTED, selectcolor="#333333",
            font=fonts.view_font(11), activebackground=BG,
            activeforeground=FG,
        )
        regex_cb.grid(row=0, column=1, padx=(10, 4))

        clear_q = tk.Label(search_frame, text="\u00d7", fg=MUTED, bg=BG,
                           font=fonts.view_font_bold(16), cursor="")
        clear_q.grid(row=0, column=2)
        clear_q.bind("<Button-1>", lambda e: self._search_var.set(""))
        clear_q.bind("<Enter>", lambda e: clear_q.config(fg=FG))
        clear_q.bind("<Leave>", lambda e: clear_q.config(fg=MUTED))

        nav_frame = tk.Frame(top, bg=BG)
        nav_frame.pack(fill=tk.X)

        prev_btn = self._make_btn(nav_frame, "\u25B2  Prev")
        prev_btn.pack(side=tk.LEFT)
        prev_btn.bind("<Button-1>", lambda e: self._find_prev())

        next_btn = self._make_btn(nav_frame, "Next  \u25BC")
        next_btn.pack(side=tk.LEFT, padx=(6, 0))
        next_btn.bind("<Button-1>", lambda e: self._find_next())

        self._match_label = tk.Label(
            nav_frame, text="", fg=MUTED, bg=BG, font=fonts.view_font(11))
        self._match_label.pack(side=tk.LEFT, padx=(12, 0))

        line_frame = tk.Frame(nav_frame, bg=BG)
        line_frame.pack(side=tk.RIGHT)
        tk.Label(line_frame, text="Line:", fg=MUTED, bg=BG,
                 font=fonts.view_font(11)).pack(side=tk.LEFT)
        self._line_var = tk.StringVar()
        self._line_entry = tk.Entry(
            line_frame, textvariable=self._line_var,
            bg="#000000", fg=FG, insertbackground=FG,
            font=fonts.view_font(11), relief=tk.FLAT, borderwidth=0,
            highlightbackground="#333333", highlightthickness=1, width=6)
        self._line_entry.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
        self._line_entry.bind("<Return>", lambda e: self._go_line())
        go_btn = self._make_btn(line_frame, "Go")
        go_btn.pack(side=tk.LEFT, padx=(4, 0))
        go_btn.bind("<Button-1>", lambda e: self._go_line())

    def _build_editor_with_output(self):
        info_frame = tk.Frame(self, bg=BG)
        info_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(6, 0))

        self._info_label = tk.Label(
            info_frame, text="", fg=MUTED, bg=BG,
            font=fonts.view_font(10))
        self._info_label.pack(side=tk.LEFT)

        tk.Label(info_frame, text="Ctrl+F Search  |  Ctrl+S Save  |  F5 Execute",
                 fg=MUTED, bg=BG, font=fonts.view_font(10)).pack(side=tk.RIGHT)

        self._pane = tk.PanedWindow(
            self, orient=tk.VERTICAL,
            bg=BG, sashwidth=6, sashrelief=tk.RAISED,
            sashpad=0, borderwidth=0)
        self._pane.grid(row=2, column=0, sticky="nsew", padx=15, pady=4)

        editor_frame = tk.Frame(self._pane, bg=BASE_BG)
        editor_frame.columnconfigure(1, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        self._line_nums = tk.Text(
            editor_frame, bg=BASE_BG, fg=LINE_NUM_FG,
            font=fonts.view_font(13), borderwidth=0,
            highlightthickness=0, state=tk.DISABLED,
            cursor="", wrap=tk.NONE, width=5,
            padx=8, pady=2, takefocus=False,
        )
        self._line_nums.grid(row=0, column=0, sticky="ns")

        self._editor = tk.Text(
            editor_frame, bg=BASE_BG, fg=BRIGHT,
            font=fonts.view_font(13), borderwidth=0,
            highlightthickness=0,
            insertbackground=BRIGHT,
            wrap=tk.NONE, undo=True, maxundo=100,
            padx=8, pady=2,
        )
        self._editor.tag_configure("highlight", background="#444400",
                                   foreground=BRIGHT)
        self._editor.grid(row=0, column=1, sticky="nsew")

        self._scrollbar = tk.Scrollbar(
            editor_frame, orient=tk.VERTICAL,
            command=self._on_scrollbar_move)
        self._scrollbar.configure(
            bg="#333333", troughcolor="#1a1a1a",
            activebackground="#555555", width=10,
            borderwidth=0, highlightthickness=0,
            elementborderwidth=0)
        self._scrollbar.grid(row=0, column=2, sticky="ns")

        self._editor.configure(yscrollcommand=self._on_editor_scroll)

        self._editor.bind("<Key>", lambda e: self.after(10, self._update_line_nums))
        self._editor.bind("<<Modified>>", lambda e: self._on_modified())

        self._pane.add(editor_frame)
        self._pane.paneconfigure(editor_frame, stretch="always")

        out_frame = tk.Frame(self._pane, bg=BG)
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(0, weight=0)
        out_frame.rowconfigure(1, weight=1)

        self._out_label = tk.Label(
            out_frame, text="Output", fg=MUTED, bg=BG,
            font=fonts.view_font_bold(11), anchor="w")
        self._out_label.grid(row=0, column=0, sticky="w")

        self._out_text = tk.Text(
            out_frame, bg=BASE_BG, fg=BRIGHT,
            font=fonts.view_font(12), borderwidth=0,
            highlightthickness=0, state=tk.DISABLED,
            cursor="", wrap=tk.WORD,
            padx=8, pady=4,
        )
        self._out_text.tag_configure("muted", foreground=MUTED)
        self._out_text.tag_configure("error", foreground=ERR_COLOR)
        self._out_text.tag_configure("success", foreground=SUCCESS)
        self._out_text.grid(row=1, column=0, sticky="nsew")

        self._pane.add(out_frame)
        self._pane.paneconfigure(out_frame, stretch="always", height=120)

        self._append_output("Press F5 or click Execute to run this POC.\n", "muted")

    def _build_footer(self):
        footer = tk.Frame(self, bg=BG)
        footer.grid(row=5, column=0, sticky="ew", padx=15, pady=(8, 15))

        self._exec_btn = self._make_btn(footer, "  Execute  ")
        self._exec_btn.configure(fg=SUCCESS)
        self._exec_btn.pack(side=tk.LEFT)
        self._exec_btn.bind("<Button-1>", lambda e: self._exec_poc())

        self._stop_btn = self._make_btn(footer, "  Stop  ")
        self._stop_btn.configure(fg=ERR_COLOR)
        self._stop_btn.bind("<Button-1>", lambda e: self._stop_poc())

        self._save_btn = self._make_btn(footer, "  Save  ")
        self._save_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._save_btn.bind("<Button-1>", lambda e: self._save())

        close_btn = self._make_btn(footer, "  Close  ")
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self._on_close())

    def _make_btn(self, parent, text):
        btn = tk.Label(parent, text=text, bg="#222222", fg=FG,
                       relief=tk.RAISED, bd=1, padx=14, pady=6,
                       font=fonts.view_font(10), cursor="")
        btn.bind("<Enter>", lambda e: btn.config(bg="#333333"))
        btn.bind("<Leave>", lambda e: btn.config(bg="#222222"))
        return btn

    # ─── File I/O ──────────────────────────────────────────

    def _load_file(self):
        def _run():
            try:
                with open(self._file_path, "r", encoding="utf-8",
                          errors="replace") as f:
                    self._lines = f.read().splitlines()
            except Exception:
                self._lines = ["# Could not read file."]
            self.after(0, self._on_loaded)
        threading.Thread(target=_run, daemon=True).start()

    def _on_loaded(self):
        self._total = len(self._lines)
        self._editor.delete("1.0", tk.END)
        for line in self._lines:
            self._editor.insert(tk.END, line + "\n")
        self._editor.edit_reset()
        self._editor.edit_modified(False)
        self._dirty = False
        self._update_line_nums()
        self._update_info()
        self._editor.focus_set()

    def _save(self):
        content = self._editor.get("1.0", "end-1c")
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except (PermissionError, OSError) as e:
            self._append_output(f"Error saving: {e}\n", "error")
            return
        self._lines = content.splitlines()
        self._total = len(self._lines)
        self._editor.edit_modified(False)
        self._dirty = False
        self._update_info()
        self._on_query_changed()

    def _on_modified(self):
        if self._editor.edit_modified():
            self._dirty = True
            self._update_info()
            self._editor.edit_modified(False)

    def _on_close(self):
        if self._dirty:
            self._save()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self.destroy()

    def _update_info(self):
        size = os.path.getsize(self._file_path) if os.path.isfile(self._file_path) else 0
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.0f} KB"
        else:
            size_str = f"{size} B"
        dirty = " \u2022" if self._dirty else ""
        self._info_label.config(
            text=f"{os.path.basename(self._file_path)}{dirty}  |  "
                 f"{self._total} lines  |  {size_str}")

    # ─── Line numbers ──────────────────────────────────────

    def _update_line_nums(self):
        content = self._editor.get("1.0", "end-1c")
        self._lines = content.splitlines()
        self._total = len(self._lines)
        num_pad = max(1, len(str(self._total)))
        ln_fmt = f"{{:>{num_pad}}} "
        editor_top = self._editor.yview()[0]
        self._line_nums.configure(state=tk.NORMAL)
        self._line_nums.delete("1.0", tk.END)
        for i in range(self._total):
            self._line_nums.insert(tk.END, ln_fmt.format(i + 1) + "\n")
        self._line_nums.configure(state=tk.DISABLED)
        self._line_nums.yview_moveto(editor_top)

    def _on_editor_scroll(self, *args):
        self._line_nums.yview_moveto(float(args[0]) if args else 0.0)
        self._scrollbar.set(*args)

    def _on_scrollbar_move(self, *args):
        self._editor.yview(*args)
        self._line_nums.yview(*args)

    # ─── Search ────────────────────────────────────────────

    def _focus_search(self):
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)

    def _focus_editor(self):
        self._editor.focus_set()

    def _on_query_changed(self):
        self._matches = []
        self._match_index = -1
        self._last_query = ""
        self._last_regex = False
        self._match_label.config(text="")

    def _ensure_fresh(self):
        query = self._search_var.get().strip()
        use_regex = self._regex_var.get()
        if not query:
            return False
        if (query != self._last_query or use_regex != self._last_regex
                or not self._matches):
            count = self._find_all_matches(query)
            if count == 0:
                self._match_label.config(text="No matches", fg=ERR_COLOR)
                return False
            self._match_index = 0
        return True

    def _find_all_matches(self, query):
        self._matches = []
        use_regex = self._regex_var.get()
        self._last_query = query
        self._last_regex = use_regex
        content = self._editor.get("1.0", "end-1c")
        search_lines = content.split("\n")
        if use_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                self._match_label.config(text="Invalid regex", fg=ERR_COLOR)
                return 0
            for line_num in range(len(search_lines)):
                if len(self._matches) >= self.MAX_MATCHES:
                    break
                for m in pattern.finditer(search_lines[line_num]):
                    if len(self._matches) >= self.MAX_MATCHES:
                        break
                    self._matches.append((line_num, m.start(), m.end()))
        else:
            qlower = query.lower()
            for line_num in range(len(search_lines)):
                if len(self._matches) >= self.MAX_MATCHES:
                    break
                line = search_lines[line_num].lower()
                col = 0
                while True:
                    col = line.find(qlower, col)
                    if col < 0:
                        break
                    if len(self._matches) >= self.MAX_MATCHES:
                        break
                    self._matches.append((line_num, col, col + len(query)))
                    col += 1
        return len(self._matches)

    def _find_next(self):
        if not self._ensure_fresh():
            return
        self._match_index = (self._match_index + 1) % len(self._matches)
        self._goto_match(self._match_index)

    def _find_prev(self):
        if not self._ensure_fresh():
            return
        self._match_index = (self._match_index - 1) % len(self._matches)
        self._goto_match(self._match_index)

    def _goto_match(self, index):
        line_num, col_start, col_end = self._matches[index]
        pos = f"{line_num + 1}.{col_start}"
        end_pos = f"{line_num + 1}.{col_end}"
        self._editor.tag_remove("highlight", "1.0", tk.END)
        self._editor.tag_add("highlight", pos, end_pos)
        self._editor.see(pos)
        self._update_line_nums()
        count = len(self._matches)
        self._match_label.config(
            text=f"{index + 1} of {count}",
            fg=SUCCESS)

    def _go_line(self):
        try:
            n = int(self._line_var.get())
        except ValueError:
            return
        if n < 1 or n > self._total:
            return
        self._editor.tag_remove("highlight", "1.0", tk.END)
        self._editor.see(f"{n}.0")
        self._editor.mark_set("insert", f"{n}.0")
        self._update_line_nums()
        self._match_label.config(text=f"Line {n}", fg=SUCCESS)

    # ─── Execution ─────────────────────────────────────────

    def _exec_poc(self):
        if self._proc and self._proc.poll() is None:
            return
        if self._dirty:
            self._save()
        self._append_output("", tag=None)
        self._append_output("Running...\n", "muted")
        self._exec_btn.pack_forget()
        self._stop_btn.pack(side=tk.LEFT, padx=(6, 0))
        threading.Thread(target=self._run_poc, daemon=True).start()

    def _run_poc(self):
        try:
            self._proc = subprocess.Popen(
                ["python3", self._file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(self._file_path),
            )
        except Exception as e:
            self.after(0, lambda: self._append_output(f"Error: {e}\n", "error"))
            self.after(0, self._on_done)
            return

        def read_stream(stream, tag):
            for line in iter(stream.readline, ""):
                self.after(0, lambda l=line, t=tag: self._append_output(l, t))
            stream.close()

        t1 = threading.Thread(target=read_stream,
                              args=(self._proc.stdout, None), daemon=True)
        t2 = threading.Thread(target=read_stream,
                              args=(self._proc.stderr, "error"), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self._proc.wait()
        self.after(0, self._on_done)

    def _on_done(self):
        rc = self._proc.returncode if self._proc else -1
        tag = "success" if rc == 0 else "error"
        self._append_output(f"\nExit code: {rc}\n", tag)
        self._stop_btn.pack_forget()
        self._exec_btn.pack(side=tk.LEFT)
        self._proc = None

    def _stop_poc(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._append_output("\nStopped by user.\n", "error")

    def _append_output(self, text, tag=None):
        self._out_text.configure(state=tk.NORMAL)
        if tag:
            self._out_text.insert(tk.END, text, tag)
        else:
            self._out_text.insert(tk.END, text)
        self._out_text.see(tk.END)
        self._out_text.configure(state=tk.DISABLED)


class _SearchDialog(tk.Toplevel):
    MAX_MATCHES = 200
    CONTEXT = 50

    def __init__(self, parent, file_path=None, title=None):
        super().__init__(parent)
        self._parent = parent
        self._file_path = file_path
        self._lines = []
        self._shown_start = 0
        self._shown_end = 0
        self.title(title or "Search")
        windowing.size_dialog(self, 950, 700, min_w=700, min_h=500)
        self.configure(bg=BG)

        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        top = tk.Frame(self, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 0))

        tk.Label(top, text="Search", font=fonts.view_font_bold(12),
                 fg=FG, bg=BG,
                 ).grid(row=0, column=0, sticky="w", columnspan=3)

        search_frame = tk.Frame(top, bg=BG)
        search_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        search_frame.columnconfigure(0, weight=1)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._on_query_changed())
        self._search_entry = tk.Entry(
            search_frame, textvariable=self._search_var,
            bg="#000000", fg=FG, insertbackground=FG,
            font=fonts.view_font(12), relief=tk.FLAT, borderwidth=0,
            highlightbackground="#333333", highlightthickness=1,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", ipady=4)
        self._search_entry.bind("<Return>", lambda e: self._find_next())

        self._regex_var = tk.BooleanVar(value=False)
        self._regex_var.trace_add("write", lambda *a: self._on_query_changed())
        regex_cb = tk.Checkbutton(
            search_frame, text="Regex", variable=self._regex_var,
            bg=BG, fg=MUTED, selectcolor="#333333",
            font=fonts.view_font(11), activebackground=BG,
            activeforeground=FG,
        )
        regex_cb.grid(row=0, column=1, padx=(10, 4))

        clear_q = tk.Label(search_frame, text="\u00d7", fg=MUTED, bg=BG,
                           font=fonts.view_font_bold(16), cursor="")
        clear_q.grid(row=0, column=2)
        clear_q.bind("<Button-1>", lambda e: self._search_var.set(""))
        clear_q.bind("<Enter>", lambda e: clear_q.config(fg=FG))
        clear_q.bind("<Leave>", lambda e: clear_q.config(fg=MUTED))

        nav_frame = tk.Frame(top, bg=BG)
        nav_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        search_btn = self._make_button(nav_frame, "Search")
        search_btn.pack(side=tk.LEFT)
        search_btn.bind("<Button-1>", lambda e: self._find_next())

        prev_btn = self._make_button(nav_frame, "\u25B2  Prev")
        prev_btn.pack(side=tk.LEFT, padx=(8, 0))
        prev_btn.bind("<Button-1>", lambda e: self._find_prev())

        next_btn = self._make_button(nav_frame, "Next  \u25BC")
        next_btn.pack(side=tk.LEFT, padx=(8, 0))
        next_btn.bind("<Button-1>", lambda e: self._find_next())

        self._match_label = tk.Label(
            nav_frame, text="", fg=MUTED, bg=BG, font=fonts.view_font(11))
        self._match_label.pack(side=tk.LEFT, padx=(16, 0))

        clear_hl = self._make_button(nav_frame, "Clear highlights")
        clear_hl.pack(side=tk.RIGHT)
        clear_hl.bind("<Button-1>", lambda e: self._clear_highlights())

        line_frame = tk.Frame(top, bg=BG)
        line_frame.grid(row=3, column=0, sticky="w", pady=(8, 0))
        tk.Label(line_frame, text="Go to line:", fg=MUTED, bg=BG,
                 font=fonts.view_font(11)).pack(side=tk.LEFT)
        self._line_var = tk.StringVar()
        self._line_entry = tk.Entry(
            line_frame, textvariable=self._line_var,
            bg="#000000", fg=FG, insertbackground=FG,
            font=fonts.view_font(11), relief=tk.FLAT, borderwidth=0,
            highlightbackground="#333333", highlightthickness=1, width=8)
        self._line_entry.pack(side=tk.LEFT, padx=(6, 0), ipady=2)
        self._line_entry.bind("<Return>", lambda e: self._go_line())
        go_btn = self._make_button(line_frame, "Go")
        go_btn.pack(side=tk.LEFT, padx=(6, 0))
        go_btn.bind("<Button-1>", lambda e: self._go_line())

        content_frame = tk.Frame(self, bg=BG)
        content_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(10, 0))
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self._text = tk.Text(
            content_frame, bg="#000000", fg=BRIGHT,
            font=fonts.view_font(12), borderwidth=0,
            highlightthickness=0, state=tk.DISABLED,
            cursor="", wrap=tk.NONE)
        self._text.tag_configure("muted", foreground=MUTED)
        self._text.tag_configure("highlight", background="#444400",
                                 foreground=BRIGHT)
        self._text.grid(row=0, column=0, sticky="nsew")

        t_scroll = tk.Scrollbar(content_frame, orient=tk.VERTICAL,
                                command=self._text.yview)
        t_scroll.configure(bg="#333333", troughcolor="#1a1a1a",
                           activebackground="#555555", width=10,
                           borderwidth=0, highlightthickness=0,
                           elementborderwidth=0)
        t_scroll.grid(row=0, column=1, sticky="ns")
        self._text.configure(yscrollcommand=t_scroll.set)

        self._loading = tk.Label(
            content_frame, text="Opening file...", fg=MUTED, bg="#000000",
            font=fonts.view_font(14))
        self._loading.place(relx=0.5, rely=0.5, anchor="center")

        bottom = tk.Frame(self, bg=BG)
        bottom.grid(row=2, column=0, sticky="ew", padx=15, pady=(10, 15))

        close_btn = self._make_button(bottom, "Close")
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self._on_close())

        self._matches = []
        self._match_index = -1
        self._last_query = ""
        self._last_regex = False
        self._loaded = False
        self._total = 0
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._load_file)

    def _make_button(self, parent, text):
        btn = tk.Label(parent, text=text, bg="#222222", fg=FG,
                       relief=tk.RAISED, bd=1, padx=14, pady=6,
                       font=fonts.view_font(10), cursor="")
        btn.bind("<Enter>", lambda e: btn.config(bg="#333333"))
        btn.bind("<Leave>", lambda e: btn.config(bg="#222222"))
        return btn

    def _load_file(self):
        def _run():
            try:
                with open(self._file_path, "r", encoding="utf-8",
                          errors="replace") as f:
                    self._lines = f.read().splitlines()
            except Exception:
                self._lines = ["Could not read file."]
            self.after(0, self._on_loaded)
        threading.Thread(target=_run, daemon=True).start()

    def _on_loaded(self):
        self._loading.destroy()
        self._loading = None
        self._total = len(self._lines)
        self._load_window(0)
        self._loaded = True
        self._search_entry.focus()

    def _load_window(self, center_line):
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        start = max(0, center_line - self.CONTEXT)
        end = min(self._total, center_line + self.CONTEXT + 1)
        if start != 0:
            self._text.insert(tk.END, "...\n", "muted")
        for i in range(start, end):
            self._text.insert(tk.END, self._lines[i] + "\n")
        if end < self._total:
            self._text.insert(tk.END, "\n...", "muted")
        self._text.insert(tk.END,
                          f"\n\n(Lines {start+1:,}\u2013{min(end, self._total):,} "
                          f"of {self._total:,})", "muted")
        size = os.path.getsize(self._file_path)
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.0f} KB"
        else:
            size_str = f"{size} B"
        self._text.insert(tk.END, f"\n({size_str})", "muted")
        self._text.configure(state=tk.DISABLED)
        self._shown_start = start
        self._shown_end = end

    def _on_query_changed(self):
        self._matches = []
        self._match_index = -1
        self._last_query = ""
        self._last_regex = False
        self._match_label.config(text="")

    def _on_close(self):
        self._clear_highlights()
        self.destroy()

    def _clear_highlights(self):
        if not self._loaded:
            return
        self._text.configure(state=tk.NORMAL)
        self._text.tag_remove("highlight", "1.0", tk.END)
        self._text.configure(state=tk.DISABLED)
        self._matches = []
        self._match_index = -1
        self._match_label.config(text="")

    def _find_all_matches(self, query):
        self._matches = []
        use_regex = self._regex_var.get()
        self._last_query = query
        self._last_regex = use_regex
        if use_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                self._match_label.config(text="Invalid regex", fg=ERR_COLOR)
                return 0
            for line_num in range(self._total):
                if len(self._matches) >= self.MAX_MATCHES:
                    break
                line = self._lines[line_num]
                for m in pattern.finditer(line):
                    if len(self._matches) >= self.MAX_MATCHES:
                        break
                    self._matches.append((line_num, m.start(), m.end()))
        else:
            qlower = query.lower()
            for line_num in range(self._total):
                if len(self._matches) >= self.MAX_MATCHES:
                    break
                line = self._lines[line_num]
                search_in = line.lower()
                col = 0
                while True:
                    col = search_in.find(qlower, col)
                    if col < 0:
                        break
                    if len(self._matches) >= self.MAX_MATCHES:
                        break
                    self._matches.append((line_num, col, col + len(query)))
                    col += 1
        return len(self._matches)

    def _highlight_position(self, index):
        if not self._loaded:
            return
        if 0 <= index < len(self._matches):
            line_num, col_start, col_end = self._matches[index][:3]
            if (line_num < self._shown_start
                    or line_num >= self._shown_end):
                self._load_window(line_num)
            offset = 2 if self._shown_start != 0 else 1
            tag_start = "%d.%d" % (line_num - self._shown_start + offset, col_start)
            tag_end = "%s + %dc" % (tag_start, col_end - col_start)
            self._text.configure(state=tk.NORMAL)
            self._text.tag_remove("highlight", "1.0", tk.END)
            self._text.tag_add("highlight", tag_start, tag_end)
            self._text.see(tag_start)
            self._text.configure(state=tk.DISABLED)

    def _show_status(self):
        count = len(self._matches)
        if count == 0:
            self._match_label.config(text="No matches", fg=ERR_COLOR)
        else:
            self._match_label.config(text="%d of %d" % (self._match_index + 1, count),
                                     fg=SUCCESS)

    def _ensure_fresh(self):
        if not self._loaded:
            return False
        query = self._search_var.get().strip()
        use_regex = self._regex_var.get()
        if not query:
            return False
        if (query != self._last_query or use_regex != self._last_regex
                or not self._matches):
            count = self._find_all_matches(query)
            if count == 0:
                self._match_label.config(text="No matches", fg=ERR_COLOR)
                return False
            self._match_index = 0
        return True

    def _find_next(self):
        if not self._ensure_fresh():
            return
        self._match_index = (self._match_index + 1) % len(self._matches)
        self._highlight_position(self._match_index)
        self._show_status()

    def _find_prev(self):
        if not self._ensure_fresh():
            return
        self._match_index = (self._match_index - 1) % len(self._matches)
        self._highlight_position(self._match_index)
        self._show_status()

    def _go_line(self):
        if not self._loaded:
            return
        try:
            n = int(self._line_var.get())
        except ValueError:
            return
        if n < 1 or n > self._total:
            return
        line_idx = n - 1
        if line_idx < self._shown_start or line_idx >= self._shown_end:
            self._load_window(line_idx)
        self._text.configure(state=tk.NORMAL)
        self._text.tag_remove("highlight", "1.0", tk.END)
        self._text.configure(state=tk.DISABLED)
        offset = 2 if self._shown_start != 0 else 1
        self._text.see("%d.0" % (line_idx - self._shown_start + offset))
        self._match_label.config(text="Line %d" % n, fg=SUCCESS)


def open_file_search(parent, file_path, title="Search", file_type=None):
    if file_type == "poc":
        return PocDialog(parent, file_path=file_path, title=title)
    return _SearchDialog(parent, file_path=file_path, title=title)

