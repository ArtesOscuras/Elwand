import tkinter as tk
from src.gui import fonts, icons

_ORDER = [
    ("Wifi", "wifi"),
    ("Tools", "tools"),
    ("Machines", "machines"),
    ("Domains", "domains"),
    ("Inventory", "inventory"),
    ("Shells", "shells"),
    ("Process", "process"),
    ("Services", "services"),
]

_frame = None
_btns = []
_zoom_labels = []
_icon_buttons = []
_settings_callback = None
_zoom_callback = None


def build(parent, active_view, navigator):
    global _frame
    _frame = tk.Frame(parent, bg="#000000")
    _frame.pack(pady=(0, 10), fill=tk.X)

    zoom_frame = tk.Frame(_frame, bg="#000000")
    zoom_frame.pack(side=tk.RIGHT, padx=(0, 5))

    minus_btn = tk.Label(
        zoom_frame, text="\u2212", bg="#222222", fg="#ffffff",
        font=fonts.view_font(11),
        padx=6, pady=2,
    )
    minus_btn.pack(side=tk.LEFT)
    minus_btn.bind("<Button-1>", lambda e: _zoom(-0.1))
    minus_btn.bind("<Enter>", lambda e: minus_btn.config(bg="#333333"))
    minus_btn.bind("<Leave>", lambda e: minus_btn.config(bg="#222222"))

    zoom_label = tk.Label(
        zoom_frame, text=f"{int(fonts.view_scale() * 100)}%", bg="#000000",
        fg="#888888",
        font=fonts.view_font(10),
        padx=6,
    )
    zoom_label.pack(side=tk.LEFT)
    _zoom_labels.append(zoom_label)

    plus_btn = tk.Label(
        zoom_frame, text="+", bg="#222222", fg="#ffffff",
        font=fonts.view_font(11),
        padx=6, pady=2,
    )
    plus_btn.pack(side=tk.LEFT)
    plus_btn.bind("<Button-1>", lambda e: _zoom(+0.1))
    plus_btn.bind("<Enter>", lambda e: plus_btn.config(bg="#333333"))
    plus_btn.bind("<Leave>", lambda e: plus_btn.config(bg="#222222"))

    settings_frame = tk.Frame(_frame, bg="#000000")
    settings_frame.pack(side=tk.LEFT, padx=(15, 0))
    settings_img = icons.icon("settings.png", size=icons.scaled(34))
    settings_btn = tk.Label(
        settings_frame, image=settings_img, bg="#000000",
        cursor="",
    )
    settings_btn.image = settings_img
    settings_btn.pack()
    settings_btn.bind("<Button-1>", lambda e: _settings_callback and _settings_callback())
    settings_btn.bind("<Enter>", lambda e: settings_btn.config(bg="#222222"))
    settings_btn.bind("<Leave>", lambda e: settings_btn.config(bg="#000000"))
    _icon_buttons.append((settings_btn, "settings.png", 34))

    tk.Frame(_frame, bg="#000000", width=40).pack(side=tk.LEFT)
    tk.Frame(_frame, bg="#000000").pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    inner = tk.Frame(_frame, bg="#000000")
    inner.pack(side=tk.LEFT)

    for text, view_name in _ORDER:
        is_active = view_name == active_view
        normal = fonts.view_font_bold(11) if is_active else fonts.view_font(11)
        hover = fonts.view_font_bold_under(11) if is_active else fonts.view_font_under(11)
        btn = tk.Label(
            inner, text=f"  {text}  ",
            font=normal,
            fg="#ffffff" if is_active else "#888888",
            bg="#000000",
        )
        btn.pack(side=tk.LEFT, padx=5)
        btn.bind("<Button-1>", lambda e, vn=view_name: navigator.activate_view(vn))
        btn.bind("<Enter>", lambda e, b=btn, h=hover: b.config(font=h))
        btn.bind("<Leave>", lambda e, b=btn, n=normal: b.config(font=n))
        _btns.append(btn)

    tk.Frame(_frame, bg="#000000").pack(side=tk.LEFT, fill=tk.BOTH, expand=True)


def _zoom(delta):
    from src.settings import set as _set_setting, save as _save_settings
    fonts.set_view_scale(fonts.view_scale() + delta)
    _update_label()
    _refresh_icons()
    _notify_zoom()
    _set_setting("view_scale", fonts.view_scale())
    _save_settings()


def set_settings_callback(fn):
    global _settings_callback
    _settings_callback = fn


def set_zoom_callback(fn):
    global _zoom_callback
    _zoom_callback = fn


def set_initial_zoom(scale):
    fonts.set_view_scale(scale)
    _update_label()
    _refresh_icons()


def _notify_zoom():
    if _zoom_callback:
        try:
            _zoom_callback()
        except Exception:
            pass


def _refresh_icons():
    for btn, name, base in _icon_buttons:
        try:
            img = icons.icon(name, size=icons.scaled(base))
            if img is not None:
                btn.config(image=img)
                btn.image = img
        except tk.TclError:
            pass


def _update_label():
    text = f"{int(fonts.view_scale() * 100)}%"
    for label in _zoom_labels:
        try:
            label.config(text=text)
        except tk.TclError:
            pass


def refresh():
    if not _btns:
        return
    for btn in _btns:
        btn.pack_forget()
    for btn in _btns:
        btn.pack(side=tk.LEFT, padx=5)
