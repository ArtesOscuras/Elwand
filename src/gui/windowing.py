import os
import subprocess
import sys
import tkinter as tk

_BASE_DPI = 96.0
_UI_SCALE = 1.0


def _env_float(name):
    val = os.environ.get(name)
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _settings_scale():
    try:
        from src import settings as _settings
        val = _settings.get("ui_scale")
    except Exception:
        return None
    if val is None:
        return None
    try:
        val = float(val)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def _xrdb_dpi():
    try:
        out = subprocess.run(["xrdb", "-query"], capture_output=True,
                             text=True, timeout=3)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        if line.lower().startswith("xft.dpi"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                try:
                    return float(parts[1].strip())
                except ValueError:
                    return None
    return None


def _detect_linux_dpi(root):
    dpi = _env_float("ELWAND_DPI")
    if dpi and dpi > 0:
        return dpi

    gdk = _env_float("GDK_SCALE")
    gdk_dpi = _env_float("GDK_DPI_SCALE")
    if gdk or gdk_dpi:
        return _BASE_DPI * (gdk or 1.0) * (gdk_dpi or 1.0)

    qt = _env_float("QT_SCALE_FACTOR")
    if qt and qt > 0:
        return _BASE_DPI * qt

    xft = _xrdb_dpi()
    if xft and xft > 0:
        return xft

    try:
        fp = float(root.winfo_fpixels("1i"))
        if fp > 0:
            return fp
    except Exception:
        pass
    return _BASE_DPI


def _apply_scaling(root, dpi):
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:
        pass


def init(root):
    """Configure global DPI scaling. Call once after tk.Tk() is created.

    macOS Aqua already applies a correct backing scale, so it is left
    untouched. On Linux, `tk scaling` is derived from the display DPI so
    both fonts and widget metrics grow on HiDPI screens. An explicit
    override can be provided via the ELWAND_UI_SCALE/ELWAND_DPI env vars
    or the `ui_scale` key in settings.json.
    """
    global _UI_SCALE
    override = _env_float("ELWAND_UI_SCALE")
    if override is None or override <= 0:
        override = _settings_scale()

    if override is not None and override > 0:
        _UI_SCALE = override
        _apply_scaling(root, _BASE_DPI * override)
        return

    if sys.platform.startswith("linux"):
        dpi = _detect_linux_dpi(root)
        _UI_SCALE = max(1.0, dpi / _BASE_DPI)
        _apply_scaling(root, dpi)
    else:
        _UI_SCALE = 1.0


def ui_scale():
    return _UI_SCALE


def px(n):
    return int(round(n * _UI_SCALE))


def size_dialog(win, w, h, min_w=0, min_h=0, center=True):
    """Apply a DPI-scaled, screen-clamped geometry to a dialog.

    `w`/`h` are the reference sizes at 96 DPI. `min_w`/`min_h`, when given,
    are also scaled and applied as the window's minimum size.
    """
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()

    W = max(px(w), px(min_w)) if min_w else px(w)
    H = max(px(h), px(min_h)) if min_h else px(h)
    W = min(W, int(sw * 0.95))
    H = min(H, int(sh * 0.95))
    W = max(W, 1)
    H = max(H, 1)

    if center:
        x = max(0, (sw - W) // 2)
        y = max(0, (sh - H) // 2 - px(20))
        win.geometry(f"{W}x{H}+{x}+{y}")
    else:
        win.geometry(f"{W}x{H}")

    if min_w or min_h:
        min_size(win, min_w, min_h)
    return W, H


def min_size(win, w=0, h=0):
    """Apply a DPI-scaled, screen-clamped minimum size to a window."""
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    W = min(px(w), int(sw * 0.95)) if w else 1
    H = min(max(1, px(h)), int(sh * 0.95)) if h and h > 1 else 1
    win.minsize(max(1, W), max(1, H))
