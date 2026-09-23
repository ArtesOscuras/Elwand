import os
import tkinter as tk
from src.gui import fonts
from src.elwand_paths import reports_dir

BG = "#111111"
BG_WIDGET = "#000000"
FG = "#ffffff"
FG_DIM = "#888888"


class ReportDialog(tk.Toplevel):
    def __init__(self, parent, fname=None, on_save=None):
        super().__init__(parent)
        self._fname = fname
        self._on_save = on_save
        is_new = fname is None
        self.title("New Report" if is_new else "Edit Report")
        self.configure(bg=BG)
        self.transient(parent)

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        tk.Label(
            self, text="Filename:", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(12, 3))
        self._name_var = tk.StringVar(value=fname or "")
        self._name_entry = tk.Entry(
            self, textvariable=self._name_var, bg=BG_WIDGET, fg=FG,
            insertbackground=FG, font=fonts.view_font(11),
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333",
        )
        self._name_entry.grid(row=0, column=1, sticky="ew", padx=15, pady=(12, 3))

        tk.Label(
            self, text="Content:", font=fonts.view_font(11),
            fg=FG_DIM, bg=BG,
        ).grid(row=1, column=0, sticky="nw", padx=15, pady=(5, 3))

        content_frame = tk.Frame(self, bg=BG)
        content_frame.grid(row=1, column=1, sticky="nsew", padx=15, pady=(5, 3))
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self._text = tk.Text(
            content_frame, bg=BG_WIDGET, fg=FG, insertbackground=FG,
            font=fonts.view_font(12), wrap=tk.WORD,
            borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333", height=22, undo=True,
        )
        self._text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(content_frame, orient=tk.VERTICAL,
                                 command=self._text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._text.configure(yscrollcommand=scrollbar.set)

        if not is_new:
            path = self._path_for(fname)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._text.insert("1.0", f.read())
                except (PermissionError, OSError):
                    pass

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(10, 12))

        cancel_btn = tk.Label(
            btn_frame, text="  Cancel  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.bind("<Button-1>", lambda e: self.destroy())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#333333"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg="#222222"))

        save_btn = tk.Label(
            btn_frame, text="  Save  ", bg="#222222", fg=FG,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        save_btn.pack(side=tk.RIGHT)
        save_btn.bind("<Button-1>", lambda e: self._save())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#333333"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#222222"))

        self.minsize(620, 1)
        self.update_idletasks()
        self.wait_visibility()
        self.grab_set()

    def _path_for(self, fname):
        return os.path.join(str(reports_dir()), fname)

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            return
        if not name.endswith(".md"):
            name += ".md"
        content = self._text.get("1.0", "end-1c")
        try:
            with open(self._path_for(name), "w", encoding="utf-8") as f:
                f.write(content)
        except (PermissionError, OSError):
            return
        if self._on_save:
            try:
                self._on_save(name)
            except Exception:
                pass
        self.destroy()
