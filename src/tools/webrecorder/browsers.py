import tkinter as tk
from src.gui import fonts, windowing, theme
from .browser_finder import find_browsers


class BrowserSelector(tk.Toplevel):
    def __init__(self, parent, browsers):
        super().__init__(parent)
        self.result = None

        self.title("Select Browser")
        windowing.size_dialog(self, 450, 280)
        self.configure(bg=theme.BG)
        self.transient(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        tk.Label(
            self, text="Multiple browsers detected. Select one:",
            font=fonts.view_font(11), fg=theme.FG, bg=theme.BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        frame = tk.Frame(self, bg=theme.BG)
        frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._listbox = theme.listbox(frame)
        self._listbox.grid(row=0, column=0, sticky="nsew")
        theme.scrollbar(frame, self._listbox).grid(row=0, column=1, sticky="ns")

        self._paths = []
        for path, label in sorted(browsers.items()):
            self._listbox.insert(tk.END, f"  {label}  ({path})")
            self._paths.append(path)

        if self._paths:
            self._listbox.selection_set(0)

        self._listbox.bind("<Return>", lambda e: self._select())
        self._listbox.bind("<Double-Button-1>", lambda e: self._select())

        btn_frame = tk.Frame(self, bg=theme.BG)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 15))

        theme.button(btn_frame, "  Cancel  ", command=self.destroy).pack(
            side=tk.RIGHT, padx=(5, 0))
        theme.button(btn_frame, "  Select  ", command=self._select).pack(
            side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.update_idletasks()
        self.wait_visibility()
        self.grab_set()
        self._listbox.focus_set()
        self.wait_window(self)

    def _select(self):
        sel = self._listbox.curselection()
        if sel:
            self.result = self._paths[sel[0]]
        self.destroy()
