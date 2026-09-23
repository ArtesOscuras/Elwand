import os
import time
import tkinter as tk
from datetime import datetime
from src.gui import fonts
from src.elwand_paths import logs_dir
from .views import BaseView

_DBG_FILE = os.path.join(logs_dir(), "debugging_logs")


def _dbg(msg):
    try:
        os.makedirs(os.path.dirname(_DBG_FILE), exist_ok=True)
        with open(_DBG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except (PermissionError, OSError):
        pass


class Visualizer(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#000000", **kwargs)
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.views = {}
        self._active_view_name = None
        self._active_view = None

        self._placeholder = tk.Label(
            self,
            text="Visualization Area",
            font=(fonts.family(), 18),
            fg="#888888",
            bg="#000000",
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def register_view(self, name, view):
        self.views[name] = view

    def get_view_names(self):
        return list(self.views.keys())

    def get_view(self, name):
        return self.views.get(name)

    def get_active_view(self):
        return self._active_view

    def get_active_view_name(self):
        return self._active_view_name

    def activate_view(self, name):
        t0 = time.perf_counter()
        if name not in self.views:
            raise ValueError(f"Unknown view: {name}")

        _dbg(f"[view] activate_view START: {name}")

        if self._active_view:
            _dbg(f"[view]   on_deactivate: {self._active_view_name}")
            t1 = time.perf_counter()
            self._active_view.on_deactivate()
            _dbg(f"[view]   on_deactivate DONE ({time.perf_counter() - t1:.3f}s)")
            t1 = time.perf_counter()
            self._active_view.grid_forget()
            _dbg(f"[view]   grid_forget DONE ({time.perf_counter() - t1:.3f}s)")

        self._placeholder.place_forget()

        self._active_view_name = name
        self._active_view = self.views[name]
        t1 = time.perf_counter()
        self._active_view.grid(row=0, column=0, sticky="nsew")
        _dbg(f"[view]   grid DONE ({time.perf_counter() - t1:.3f}s)")
        t1 = time.perf_counter()
        self._active_view.on_activate()
        _dbg(f"[view]   on_activate DONE ({time.perf_counter() - t1:.3f}s)")
        self.winfo_toplevel().update_idletasks()
        self._active_view.update_idletasks()
        self._refresh_labels(self._active_view)
        self.winfo_toplevel().update_idletasks()
        _dbg(f"[view] activate_view DONE ({time.perf_counter() - t0:.3f}s)")

    @staticmethod
    def _refresh_labels(widget):
        if isinstance(widget, tk.Label):
            try:
                f = widget.cget("font")
                if f:
                    widget.config(font=f)
            except Exception:
                pass
        for child in widget.winfo_children():
            Visualizer._refresh_labels(child)
