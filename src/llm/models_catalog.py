import json
import os
import threading
import time
import urllib.request

from src.elwand_paths import models_catalog_file

URL = "https://models.dev/api.json"
TTL_SECONDS = 24 * 60 * 60

_lock = threading.Lock()
_catalog = None


def _read_disk():
    path = models_catalog_file()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    fetched_at = data.get("fetched_at", 0)
    if time.time() - fetched_at > TTL_SECONDS:
        return None
    return data.get("catalog")


def _write_disk(catalog):
    path = models_catalog_file()
    payload = {"fetched_at": time.time(), "catalog": catalog}
    try:
        tmp = f"{path}.{os.getpid()}.{time.time()}.tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except (OSError, TypeError):
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _download():
    req = urllib.request.Request(URL, headers={"User-Agent": "elwand"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load():
    global _catalog
    with _lock:
        if _catalog is not None:
            return _catalog
        _catalog = _read_disk()
        return _catalog


def fetch():
    global _catalog
    try:
        catalog = _download()
    except Exception:
        return load()
    with _lock:
        _catalog = catalog
    _write_disk(catalog)
    return catalog


def refresh_async():
    def _run():
        try:
            fetch()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def lookup_context_limit(model_name):
    if not model_name:
        return None
    catalog = load()
    if not catalog:
        return None
    target = model_name.lower()
    for provider in catalog.values():
        models = provider.get("models", {}) if isinstance(provider, dict) else {}
        for mid, m in models.items():
            if not isinstance(m, dict):
                continue
            if mid.lower() == target:
                limit = m.get("limit") or {}
                value = limit.get("context")
                if isinstance(value, int) and value > 0:
                    return value
                return None
    return None
