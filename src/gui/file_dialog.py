"""Minimalist, theme-styled file chooser for Linux.

On macOS/Windows `tkinter.filedialog` opens the native chooser, which matches
the OS. On Linux Tk falls back to its own classic dialog (light background,
inconsistent with Elwand). This module provides a small dark chooser built with
the shared theme (`src/gui/theme.py`) and is used only on Linux.

Use `windowing.ask_open_file` / `windowing.ask_save_file`, not this module
directly.
"""

import fnmatch
import os
import tkinter as tk

from src.gui import fonts, theme, windowing


def _norm_ext(ext):
    if not ext:
        return ""
    return ext if ext.startswith(".") else "." + ext


def _pattern_matches(name, pattern):
    if not pattern or pattern in ("*", "*.*"):
        return True
    for part in str(pattern).split():
        if fnmatch.fnmatch(name, part):
            return True
    return False


def choose(parent, mode="open", title=None, initialdir=None, initialfile="",
           defaultextension="", filetypes=None):
    """Show the themed chooser and return the chosen path ("" if cancelled)."""
    dlg = FileChooser(parent, mode=mode, title=title, initialdir=initialdir,
                      initialfile=initialfile,
                      defaultextension=defaultextension, filetypes=filetypes)
    master = dlg.master
    try:
        (master or dlg).wait_window(dlg)
    except Exception:
        pass
    return dlg.result or ""


class FileChooser(tk.Toplevel):
    def __init__(self, parent, mode="open", title=None, initialdir=None,
                 initialfile="", defaultextension="", filetypes=None):
        super().__init__(parent)
        self.result = None
        self._mode = mode
        self._defaultextension = _norm_ext(defaultextension)
        self._filetypes = list(filetypes) if filetypes else [("All files", "*.*")]
        self._cwd = self._resolve_dir(initialdir)
        self._entries = []

        self.title(title or ("Save file" if mode == "save" else "Open file"))
        windowing.size_dialog(self, 660, 480, min_w=520, min_h=380)
        self.configure(bg=theme.BG)
        self.transient(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Directory / path row.
        path_row = tk.Frame(self, bg=theme.BG)
        path_row.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 6))
        path_row.columnconfigure(0, weight=1)
        self._path_var = tk.StringVar(value=self._cwd)
        path_entry = theme.entry(path_row, textvariable=self._path_var)
        path_entry.grid(row=0, column=0, sticky="ew")
        path_entry.bind("<Return>", lambda e: self._go(self._path_var.get()))
        up_btn = theme.button(path_row, "  Up  ", command=self._up,
                              padx=10, pady=4)
        up_btn.grid(row=0, column=1, padx=(6, 0))

        # File listing.
        list_frame = tk.Frame(self, bg=theme.BG)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=0)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self._list = theme.listbox(list_frame)
        self._list.grid(row=0, column=0, sticky="nsew")
        sb = theme.scrollbar(list_frame, self._list)
        sb.grid(row=0, column=1, sticky="ns")
        self._list.bind("<Double-Button-1>", self._on_activate)
        self._list.bind("<Return>", self._on_activate)
        self._list.bind("<<ListboxSelect>>", self._on_select)

        # File name.
        name_row = tk.Frame(self, bg=theme.BG)
        name_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(8, 0))
        tk.Label(name_row, text="File", fg=theme.MUTED, bg=theme.BG,
                 font=fonts.view_font_bold(10)).pack(side=tk.LEFT)
        self._name_var = tk.StringVar(value=initialfile or "")
        name_entry = theme.entry(name_row, textvariable=self._name_var)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        name_entry.bind("<Return>", lambda e: self._accept())

        # File type.
        type_row = tk.Frame(self, bg=theme.BG)
        type_row.grid(row=3, column=0, sticky="ew", padx=15, pady=(8, 0))
        tk.Label(type_row, text="Type", fg=theme.MUTED, bg=theme.BG,
                 font=fonts.view_font_bold(10)).pack(side=tk.LEFT)
        self._type_var = tk.StringVar()
        self._type_combo = theme.combo(
            type_row, textvariable=self._type_var,
            values=[label for label, _ in self._filetypes], width=26)
        self._type_combo.pack(side=tk.LEFT, padx=(8, 0))
        self._type_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())
        self._type_combo.current(0)

        # Buttons.
        btn_row = tk.Frame(self, bg=theme.BG)
        btn_row.grid(row=4, column=0, sticky="ew", padx=15, pady=(12, 15))
        theme.button(btn_row, "  Cancel  ", command=self._cancel).pack(side=tk.RIGHT)
        theme.button(btn_row, "  Save  " if mode == "save" else "  Open  ",
                     command=self._accept).pack(side=tk.RIGHT, padx=(0, 6))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._refresh()

        self.update_idletasks()
        self.wait_visibility()
        self.grab_set()
        self._list.focus_set()

    # ── helpers ────────────────────────────────────────────────────────────

    def _resolve_dir(self, initialdir):
        if initialdir and os.path.isdir(initialdir):
            return os.path.abspath(initialdir)
        return os.path.expanduser("~")

    def _current_pattern(self):
        idx = self._type_combo.current()
        if 0 <= idx < len(self._filetypes):
            return self._filetypes[idx][1]
        return "*.*"

    def _refresh(self):
        self._path_var.set(self._cwd)
        self._list.delete(0, tk.END)
        self._entries = []

        try:
            names = sorted(os.listdir(self._cwd), key=str.lower)
        except OSError:
            names = []

        dirs, files = [], []
        for name in names:
            if name.startswith("."):
                continue
            full = os.path.join(self._cwd, name)
            if os.path.isdir(full):
                dirs.append(name)
            elif _pattern_matches(name, self._current_pattern()):
                files.append(name)

        parent = os.path.dirname(self._cwd)
        if parent and parent != self._cwd:
            self._entries.append(("..", True))
            self._list.insert(tk.END, "  [..]")
        for name in dirs:
            self._entries.append((name, True))
            self._list.insert(tk.END, f"  [{name}]")
        for name in files:
            self._entries.append((name, False))
            self._list.insert(tk.END, f"  {name}")

        if self._list.size():
            self._list.selection_set(0)
            self._list.activate(0)

    def _selected_entry(self):
        sel = self._list.curselection()
        if not sel:
            return None
        idx = sel[0]
        if 0 <= idx < len(self._entries):
            return self._entries[idx]
        return None

    def _on_select(self, event=None):
        entry = self._selected_entry()
        if entry and not entry[1]:
            self._name_var.set(entry[0])

    def _on_activate(self, event=None):
        entry = self._selected_entry()
        if not entry:
            return
        name, is_dir = entry
        if is_dir:
            self._go(os.path.join(self._cwd, name))
        else:
            self._name_var.set(name)
            self._accept()

    def _go(self, path):
        path = os.path.expanduser(path.strip())
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        if os.path.isdir(path):
            self._cwd = os.path.abspath(path)
            self._refresh()
            if self._list.size():
                self._list.selection_clear(0, tk.END)
        elif os.path.isfile(path):
            self._cwd = os.path.dirname(os.path.abspath(path))
            self._name_var.set(os.path.basename(path))
            self._refresh()

    def _up(self):
        parent = os.path.dirname(self._cwd)
        if parent and parent != self._cwd:
            self._cwd = parent
            self._refresh()

    def _accept(self):
        name = self._name_var.get().strip()
        if not name:
            entry = self._selected_entry()
            if entry and not entry[1]:
                name = entry[0]
            else:
                return
        path = name if os.path.isabs(name) else os.path.join(self._cwd, name)

        if os.path.isdir(path):
            self._go(path)
            return
        if self._mode == "open":
            if not os.path.isfile(path):
                return
        else:
            if self._defaultextension and not os.path.splitext(path)[1]:
                path += self._defaultextension
        self.result = path
        self._close()

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
