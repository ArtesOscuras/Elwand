import os
from PIL import Image, ImageTk
from src.elwand_paths import icons_dir as _icons_dir

_ICONS_DIR = str(_icons_dir())
_cache = {}


def _path(name):
    return os.path.join(_ICONS_DIR, name)


def icon(name, size=50):
    key = (name, size)
    if key in _cache:
        return _cache[key]
    path = _path(name)
    if not os.path.isfile(path):
        _cache[key] = None
        return None
    try:
        img = Image.open(path).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        _cache[key] = ImageTk.PhotoImage(img)
    except Exception:
        _cache[key] = None
    return _cache[key]


def all_icons(size=50):
    if not os.path.isdir(_ICONS_DIR):
        return {}
    result = {}
    for fname in os.listdir(_ICONS_DIR):
        if not fname.lower().endswith(".png"):
            continue
        name = os.path.splitext(fname)[0].lower()
        img = icon(fname, size)
        if img:
            result[name] = img
    return result


def delete_icon():
    return icon("delete.png", size=20)
