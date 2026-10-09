"""Shared visual theme for Elwand dialogs.

Single source of truth for the palette and the ttk look (tabs use the Fuzzer
style) plus small factories for the recurring widgets (flat buttons, label
toggles instead of bright checkboxes, list boxes, scroll bars, output panes).

All fonts come from `src.gui.fonts` named fonts (`view_font`/`view_font_bold`)
so everything follows the bundled JetBrains Mono NL font and live zoom.
"""

import tkinter as tk
from tkinter import ttk

from src.gui import fonts

# ── Palette ────────────────────────────────────────────────────────────────
BG = "#111111"
PANEL = "#000000"
FG = "#ffffff"
MUTED = "#888888"
SUCCESS = "#00cc66"
ERROR = "#f44747"
INFO = "#5ba3ec"
WARN = "#ce9178"
SEL_BG = "#2d6cdf"
BTN_BG = "#222222"
BTN_HOVER = "#333333"
SCROLL_BG = "#333333"
SCROLL_ACTIVE = "#555555"
TROUGH = "#1a1a1a"
BORDER = "#333333"

_installed = False


def install():
    """Configure the global ttk look once. Tabs follow the Fuzzer dialog."""
    global _installed
    if _installed:
        return
    style = ttk.Style()
    try:
        style.theme_use("default")
    except tk.TclError:
        pass
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=BTN_BG, foreground=FG,
                    padding=[20, 6], font=fonts.view_font(10), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", BTN_HOVER)])
    style.configure("TCombobox", fieldbackground=PANEL, background=BTN_BG,
                    foreground=FG, insertcolor=FG, arrowcolor=FG,
                    selectbackground=SEL_BG, selectforeground=FG, arrowsize=12)
    style.map("TCombobox",
              fieldbackground=[("readonly", PANEL)],
              foreground=[("readonly", FG)])
    # Style the ttk.Combobox popdown list (otherwise it can render light).
    root = tk._default_root
    if root is not None:
        for pattern, value in (
            ("*TCombobox*Listbox.background", PANEL),
            ("*TCombobox*Listbox.foreground", FG),
            ("*TCombobox*Listbox.selectBackground", SEL_BG),
            ("*TCombobox*Listbox.selectForeground", FG),
        ):
            try:
                root.option_add(pattern, value)
            except tk.TclError:
                pass
    _installed = True


# ── Widget factories ───────────────────────────────────────────────────────

def button(parent, text, command=None, padx=15, pady=6, size=10, **kw):
    """Flat clickable Label button with hover (no relief, no cursor change).

    The returned widget has `.enable()` / `.disable()` (a disabled button is
    dimmed and ignores clicks)."""
    btn = tk.Label(parent, text=text, bg=BTN_BG, fg=FG, padx=padx, pady=pady,
                   font=fonts.view_font(size), cursor="", **kw)
    btn._disabled = False

    def _on_enter(event=None):
        if not btn._disabled:
            btn.config(bg=BTN_HOVER)

    def _on_leave(event=None):
        btn.config(bg=BG if btn._disabled else BTN_BG)

    def _on_click(event=None):
        if btn._disabled:
            return
        command()

    btn.enable = lambda: (setattr(btn, "_disabled", False),
                          btn.config(bg=BTN_BG, fg=FG))
    btn.disable = lambda: (setattr(btn, "_disabled", True),
                           btn.config(bg=BG, fg=MUTED))
    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    if command is not None:
        btn.bind("<Button-1>", _on_click)
    return btn


def listbox(parent, **kw):
    return tk.Listbox(
        parent, bg=PANEL, fg=FG, font=fonts.view_font(10),
        selectbackground=SEL_BG, selectforeground=FG,
        activestyle="none", borderwidth=0, highlightthickness=0,
        cursor="", exportselection=False, **kw)


def scrollbar(parent, widget=None, horizontal=False):
    sb = tk.Scrollbar(parent, orient=tk.HORIZONTAL if horizontal else tk.VERTICAL)
    sb.configure(bg=SCROLL_BG, troughcolor=TROUGH, activebackground=SCROLL_ACTIVE,
                 width=10, borderwidth=0, highlightthickness=0,
                 elementborderwidth=0)
    if widget is not None:
        if horizontal:
            sb.configure(command=widget.xview)
            widget.configure(xscrollcommand=sb.set)
        else:
            sb.configure(command=widget.yview)
            widget.configure(yscrollcommand=sb.set)
    return sb


def output(parent, height=8, **kw):
    """Disabled Text pane with the standard success/error/info/muted tags."""
    txt = tk.Text(
        parent, bg=PANEL, fg=FG, font=fonts.view_font(10),
        state=tk.DISABLED, wrap=tk.WORD, cursor="",
        borderwidth=0, highlightthickness=0, height=height, **kw)
    txt.tag_configure("success", foreground=SUCCESS)
    txt.tag_configure("error", foreground=ERROR)
    txt.tag_configure("info", foreground=FG)
    txt.tag_configure("muted", foreground=MUTED)
    return txt


def entry(parent, textvariable=None, width=20, center=False, **kw):
    return tk.Entry(
        parent, textvariable=textvariable, width=width, bg=PANEL, fg=FG,
        insertbackground=FG, font=fonts.view_font(10), relief=tk.FLAT,
        borderwidth=0, highlightthickness=0,
        justify=tk.CENTER if center else tk.LEFT, **kw)


def combo(parent, textvariable=None, values=(), width=22, **kw):
    return ttk.Combobox(
        parent, textvariable=textvariable, values=list(values),
        state="readonly", font=fonts.view_font(10), width=width, **kw)


class Toggle:
    """Label-based on/off switch (no bright checkbox indicator).

    Wrap an optional `tk.BooleanVar`; state lives in the variable so existing
    `.get()` / `.set()` code keeps working. Highlighted with `SEL_BG` when on.
    """

    def __init__(self, parent, text, variable=None, command=None,
                 padx=12, pady=5, bold=True):
        self.var = variable if variable is not None else tk.BooleanVar(value=False)
        self.command = command
        f = fonts.view_font_bold(10) if bold else fonts.view_font(10)
        self.widget = tk.Label(parent, text=text, bg=BTN_BG, fg=MUTED,
                               font=f, cursor="", padx=padx, pady=pady)
        self.widget.bind("<Button-1>", self._click)
        self.widget.bind("<Enter>", lambda e: self._hover(True))
        self.widget.bind("<Leave>", lambda e: self._hover(False))
        self.refresh()

    def _click(self, event=None):
        self.var.set(not bool(self.var.get()))
        self.refresh()
        if self.command:
            self.command()

    def _hover(self, entering):
        if entering:
            self.widget.config(bg=BTN_HOVER)
        else:
            self.refresh()

    def refresh(self):
        on = bool(self.var.get())
        self.widget.config(bg=SEL_BG if on else BTN_BG, fg=FG if on else MUTED)

    def get(self):
        return self.var.get()

    def set(self, value):
        self.var.set(value)
        self.refresh()

    def pack(self, **kw):
        self.widget.pack(**kw)
        return self

    def grid(self, **kw):
        self.widget.grid(**kw)
        return self

    def config(self, **kw):
        self.widget.config(**kw)
        return self


class Segmented:
    """A row of mutually exclusive Label options (radio-like, no indicator)."""

    def __init__(self, parent, options, variable, command=None, bg=BG):
        self.var = variable
        self.command = command
        self._btns = {}
        self.widget = tk.Frame(parent, bg=bg)
        for value, text in options:
            b = tk.Label(self.widget, text=text, padx=12, pady=5,
                         font=fonts.view_font_bold(10), cursor="")
            b.pack(side=tk.LEFT, padx=(0, 6))
            b.bind("<Button-1>", lambda e, v=value: self._select(v))
            b.bind("<Enter>", lambda e, v=value: self._hover(v, True))
            b.bind("<Leave>", lambda e, v=value: self._hover(v, False))
            self._btns[value] = b
        self.refresh()

    def _select(self, value):
        self.var.set(value)
        self.refresh()
        if self.command:
            self.command()

    def _hover(self, value, entering):
        if value == self.var.get():
            return
        self._btns[value].config(bg=BTN_HOVER if entering else BTN_BG)

    def refresh(self):
        cur = self.var.get()
        for value, b in self._btns.items():
            active = value == cur
            b.config(bg=SEL_BG if active else BTN_BG, fg=FG if active else MUTED)

    def pack(self, **kw):
        self.widget.pack(**kw)
        return self

    def grid(self, **kw):
        self.widget.grid(**kw)
        return self
