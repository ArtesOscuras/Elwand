import json
import os
import threading
from src.elwand_paths import settings_file as _settings_path

_lock = threading.Lock()
_data = {}


def load():
    global _data
    path = _settings_path()
    if not path.exists():
        _data = {}
        return
    try:
        with _lock, open(str(path)) as f:
            _data = json.load(f)
    except (json.JSONDecodeError, OSError):
        _data = {}


def save():
    path = _settings_path()
    try:
        os.makedirs(str(path.parent), exist_ok=True)
        with _lock, open(str(path), "w") as f:
            json.dump(_data, f, indent=2)
    except (PermissionError, OSError):
        pass


def get(key, default=None):
    with _lock:
        return _data.get(key, default)


def set(key, value):
    with _lock:
        _data[key] = value
