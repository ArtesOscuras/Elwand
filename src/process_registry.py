"""Central registry of Elwand background processes.

Tools and inline tasks that run in separate threads register here while they
are alive, so the Process view can list everything running in the background.
Pure Python (no tkinter), safe to import from `src/tools/**`.
"""
import threading
import time

_lock = threading.Lock()
_procs = {}
_counter = 0


def register(name, detail="", icon="service.png"):
    """Register a running process and return its id. Call `finish` when done."""
    global _counter
    with _lock:
        _counter += 1
        pid = _counter
        _procs[pid] = {
            "id": pid,
            "name": name,
            "detail": detail,
            "icon": icon,
            "started": time.time(),
        }
        return pid


def finish(pid):
    """Remove a process from the registry. Idempotent."""
    if pid is None:
        return
    with _lock:
        _procs.pop(pid, None)


def list_active():
    """Return the active processes, oldest first, with elapsed seconds."""
    now = time.time()
    with _lock:
        items = list(_procs.values())
    items.sort(key=lambda p: p["started"])
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "detail": p["detail"],
            "icon": p["icon"],
            "elapsed": max(0, int(now - p["started"])),
        }
        for p in items
    ]


def clear():
    with _lock:
        _procs.clear()
