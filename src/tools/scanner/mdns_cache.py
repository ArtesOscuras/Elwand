import json
import os
import time
import threading


from src.elwand_paths import databases_dir as _databases_dir

_cache = {}
_save_lock = threading.Lock()

_DB_DIR = str(_databases_dir())
_CACHE_FILE = os.path.join(_DB_DIR, "mdns_cache.json")
_MAX_AGE = 24 * 3600
_AUTOSAVE_INTERVAL = 10
_autosave_running = False
_autosave_thread = None


def decode_properties(raw_properties):
    out = {}
    if not raw_properties:
        return out
    for key, value in raw_properties.items():
        try:
            k = key.decode() if isinstance(key, bytes) else str(key)
        except (UnicodeDecodeError, AttributeError):
            k = str(key)
        try:
            v = value.decode() if isinstance(value, bytes) else str(value)
        except (UnicodeDecodeError, AttributeError):
            v = str(value)
        out[k] = v
    return out


def add_service(ip, service_name, hostname="", txt=None):
    if ip not in _cache:
        _cache[ip] = {}
    _cache[ip][service_name] = {
        "hostname": hostname,
        "txt": txt or {},
        "timestamp": time.time(),
        "found": True,
    }


def mark_absent(ip, service_name):
    if ip not in _cache:
        _cache[ip] = {}
    _cache[ip][service_name] = {
        "hostname": "",
        "txt": {},
        "timestamp": time.time(),
        "found": False,
    }


def has_service(ip, service_name):
    entry = _cache.get(ip, {}).get(service_name)
    if entry is None:
        return None
    return entry["found"]


def get_services(ip):
    return {
        name: info
        for name, info in _cache.get(ip, {}).items()
        if info["found"]
    }


def get_txt(ip, service_name):
    entry = _cache.get(ip, {}).get(service_name)
    if entry:
        return entry["txt"]
    return {}


def get_hostname(ip, service_name):
    entry = _cache.get(ip, {}).get(service_name)
    if entry:
        return entry["hostname"]
    return ""


def all_known_ips():
    return list(_cache.keys())


def clear():
    _cache.clear()


def wipe():
    _cache.clear()
    for filename in os.listdir(_DB_DIR):
        filepath = os.path.join(_DB_DIR, filename)
        if os.path.isfile(filepath):
            os.remove(filepath)


def save():
    os.makedirs(_DB_DIR, exist_ok=True)
    with _save_lock:
        data = {}
        for ip, services in _cache.items():
            data[ip] = {}
            for svc, info in services.items():
                data[ip][svc] = dict(info)
        try:
            with open(_CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except (PermissionError, OSError):
            pass


def load():
    if not os.path.isfile(_CACHE_FILE):
        return
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    now = time.time()
    cutoff = now - _MAX_AGE

    for ip, services in data.items():
        for svc, info in services.items():
            if info.get("timestamp", 0) >= cutoff:
                if ip not in _cache:
                    _cache[ip] = {}
                _cache[ip][svc] = info


def start_autosave():
    global _autosave_running, _autosave_thread
    if _autosave_running:
        return
    _autosave_running = True
    _autosave_thread = threading.Thread(target=_autosave_loop, daemon=True)
    _autosave_thread.start()


def stop_autosave():
    global _autosave_running
    _autosave_running = False


def _autosave_loop():
    while _autosave_running:
        time.sleep(_AUTOSAVE_INTERVAL)
        if _autosave_running:
            save()
