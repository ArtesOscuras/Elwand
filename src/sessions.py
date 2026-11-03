"""Workspace sessions: one isolated data root per engagement.

A session is a directory under ``<global home>/sessions/<id>/`` holding all the
operational data (databases, credentials, evidence, handshakes, cache, POCs,
reports, logs and the LLM conversation). Global settings/assets (settings.json,
llm.json, models catalog, bundled dictionaries/rules, browser profiles, the
RT2800 driver) stay shared across sessions.

The active session is persisted in ``<global home>/active_session`` and applied
to :mod:`src.elwand_paths` so every path helper resolves inside it.
"""

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime

import src.elwand_paths as paths

_LOCK = threading.Lock()

_LEGACY_DIRS = ("databases", "credentials", "evidence", "handshakes",
                "cache", "pocs", "reports", "logs")
_SESSION_SUBDIRS = _LEGACY_DIRS + ("lst", "rules")


def _root():
    return paths.global_home()


def sessions_root():
    p = _root() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _active_file():
    return _root() / "active_session"


def session_dir(session_id):
    return sessions_root() / session_id


def _meta_path(session_id):
    return session_dir(session_id) / "meta.json"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _slug(text):
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", (text or "").strip()).strip("-")[:40]


def _next_auto_name():
    """Next free `newN` name for sessions created without a custom name."""
    used = set()
    try:
        for d in sessions_root().iterdir():
            if d.is_dir():
                meta = _read_json(d / "meta.json") or {}
                name = (meta.get("name") or "").strip().lower()
                if name:
                    used.add(name)
    except OSError:
        pass
    i = 1
    while f"new{i}" in used:
        i += 1
    return f"new{i}"


def _gen_id(name=""):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    slug = _slug(name)
    return f"{stamp}-{slug}-{suffix}" if slug else f"{stamp}-{suffix}"


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, str(path))


def _read_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def read_meta(session_id):
    meta = _read_json(_meta_path(session_id)) or {}
    meta.setdefault("id", session_id)
    meta.setdefault("name", session_id)
    return meta


def _write_meta(session_id, meta):
    meta["id"] = session_id
    meta["updated"] = _now()
    _write_json(_meta_path(session_id), meta)


def _touch(session_id):
    meta = read_meta(session_id)
    meta["updated"] = _now()
    _write_json(_meta_path(session_id), meta)


def get_active_id():
    try:
        sid = _active_file().read_text().strip()
    except OSError:
        return None
    return sid or None


def set_active(session_id):
    d = session_dir(session_id)
    if not d.is_dir():
        raise ValueError(f"Session not found: {session_id}")
    paths.set_session_dir(d)
    _active_file().write_text(session_id)
    _touch(session_id)
    return session_id


def create(name=None, activate=True):
    with _LOCK:
        name = (name or "").strip() or _next_auto_name()
        sid = _gen_id(name)
        d = session_dir(sid)
        d.mkdir(parents=True, exist_ok=False)
        for sub in _SESSION_SUBDIRS:
            (d / sub).mkdir(exist_ok=True)
        _write_meta(sid, {
            "name": name,
            "created": _now(),
            "target": "",
            "notes": "",
        })
    if activate:
        set_active(sid)
    return sid


def list_sessions():
    result = []
    active = get_active_id()
    try:
        entries = list(sessions_root().iterdir())
    except OSError:
        return result
    for d in entries:
        if not d.is_dir():
            continue
        meta = _read_json(d / "meta.json")
        if meta is None:
            # tolerate a directory without meta (partial copy/import)
            meta = {"id": d.name, "name": d.name,
                    "created": "", "updated": ""}
        meta.setdefault("id", d.name)
        meta["active"] = d.name == active
        result.append(meta)
    result.sort(key=lambda m: (m.get("updated") or "", m.get("id") or ""),
                reverse=True)
    return result


def rename(session_id, name):
    meta = read_meta(session_id)
    meta["name"] = (name or "").strip() or meta.get("name") or session_id
    _write_meta(session_id, meta)
    return meta["name"]


def delete(session_id):
    if session_id == get_active_id():
        raise ValueError("Cannot delete the active session; switch first.")
    d = session_dir(session_id)
    if not d.is_dir():
        raise ValueError(f"Session not found: {session_id}")
    shutil.rmtree(d)


def _migrate_legacy():
    """Best-effort move of the old flat layout into a 'default' session."""
    home = paths.global_home()
    has_legacy = any((home / n).is_dir() for n in _LEGACY_DIRS) \
        or (home / "session.json").is_file()
    if not has_legacy:
        return None

    sid = "default"
    d = session_dir(sid)
    d.mkdir(parents=True, exist_ok=True)
    for sub in _SESSION_SUBDIRS:
        (d / sub).mkdir(exist_ok=True)

    # The model catalog cache is global, not per-session.
    catalog = home / "databases" / "models_catalog.json"
    if catalog.is_file():
        try:
            shutil.move(str(catalog), str(home / "models_catalog.json"))
        except (OSError, shutil.Error):
            pass

    moved = False
    for name in _LEGACY_DIRS:
        src = home / name
        if not src.is_dir():
            continue
        dst = d / name
        for item in list(src.iterdir()):
            try:
                shutil.move(str(item), str(dst / item.name))
                moved = True
            except (OSError, shutil.Error):
                pass

    sf = home / "session.json"
    if sf.is_file():
        try:
            shutil.move(str(sf), str(d / "session.json"))
            moved = True
        except (OSError, shutil.Error):
            pass

    # Keep user-created dictionaries/rules; the seeded stock copies are
    # redundant now that the package is the stock source.
    for sub, stock in (("lst", paths.stock_lst_dir()),
                       ("rules", paths.stock_rules_dir())):
        src = home / sub
        if not src.is_dir():
            continue
        stock_names = set()
        try:
            stock_names = {f.name for f in stock.iterdir() if f.is_file()}
        except OSError:
            pass
        for f in list(src.iterdir()):
            if not f.is_file() or f.name in stock_names:
                continue
            try:
                shutil.move(str(f), str(d / sub / f.name))
                moved = True
            except (OSError, shutil.Error):
                pass

    if not moved:
        try:
            shutil.rmtree(d)
        except OSError:
            pass
        return None

    _write_meta(sid, {"name": "default", "created": _now(),
                      "target": "", "notes": ""})
    return sid


def bootstrap():
    """Ensure sessions exist, apply the active one, and return its id."""
    existing = list_sessions()
    if not existing:
        migrated = _migrate_legacy()
        if migrated:
            set_active(migrated)
            return migrated
        sid = create(name=None, activate=False)
        set_active(sid)
        return sid

    active = get_active_id()
    if active and session_dir(active).is_dir():
        paths.set_session_dir(session_dir(active))
        return active

    sid = existing[0]["id"]
    set_active(sid)
    return sid
