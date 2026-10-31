"""Shared machine/domain target selector for dialogs (fuzz, bruteforce, ...).

Displays a Machine/Domain toggle and a listbox of inventory entries, and can
notify the owning dialog when the selection changes. Pure Tk widgets; must be
built on the main thread.
"""

import tkinter as tk

from src.gui import fonts, theme
from src.machines import store, domain_db


class TargetSection:
    def __init__(self, parent, row, mode="both", on_select=None,
                 label="Target"):
        self._target_keys = []
        self._on_select = on_select
        self._mode = mode

        tk.Label(
            parent, text=label, font=fonts.view_font_bold(11),
            fg=theme.FG, bg=theme.BG,
        ).grid(row=row, column=0, sticky="nw", padx=15, pady=(10, 5))

        mode_frame = tk.Frame(parent, bg=theme.BG)
        mode_frame.grid(row=row, column=1, sticky="w", padx=15, pady=(10, 5))

        self._target_mode = tk.StringVar(
            value="machine" if mode == "both" else "domain")

        if mode == "both":
            theme.Segmented(
                mode_frame,
                [("machine", "  Machine  "), ("domain", "  Domain  ")],
                self._target_mode, command=self._populate).pack(side=tk.LEFT)

        frame = tk.Frame(parent, bg=theme.PANEL)
        frame.grid(row=row + 1, column=0, columnspan=2, sticky="nsew",
                   padx=15, pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._listbox = theme.listbox(frame, height=3)
        self._listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = theme.scrollbar(frame, self._listbox)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._populate()
        self._listbox.bind(
            "<Return>", lambda e: self._start if hasattr(self, "_start") else None)

    def _on_list_select(self, event):
        if self._on_select:
            target = self.selected()
            if target:
                self._on_select(target[1])

    def _populate(self):
        self._listbox.delete(0, tk.END)
        self._target_keys = []

        if self._target_mode.get() == "machine":
            machines = store.get_all_sorted()
            for m in machines:
                if m.ip in ("127.0.0.1", "::1") or m.ip.startswith("127."):
                    continue
                label = f"{m.ip:<18}{m.hostname or ''}".rstrip()
                self._listbox.insert(tk.END, f"  {label}")
                self._target_keys.append(("machine", m.ip, m.hostname, m.ip))
        else:
            domains = domain_db.list_all()
            domains.sort()
            for d in domains:
                self._listbox.insert(tk.END, f"  {d}")
                self._target_keys.append(("domain", d, d, None))

        if self._target_keys:
            self._listbox.selection_set(0)
            self._on_list_select(None)

    def selected(self):
        sel = self._listbox.curselection()
        if not sel:
            return None
        return self._target_keys[sel[0]]
