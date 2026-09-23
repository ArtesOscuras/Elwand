import json
import os
import sqlite3
import threading
import time as _time
from datetime import datetime


# --- debug logging -----------------------------------------------------------
from src.elwand_paths import logs_dir as _logs_dir
_DBG_FILE = os.path.join(_logs_dir(), "debugging_logs")
_DBG_LOCK = threading.Lock()


def _dbg(msg):
    line = f"{_time.strftime('%H:%M:%S')}  {msg}\n"
    try:
        with _DBG_LOCK:
            os.makedirs(os.path.dirname(_DBG_FILE), exist_ok=True)
            with open(_DBG_FILE, "a") as f:
                f.write(line)
    except (PermissionError, OSError):
        pass
# ---------------------------------------------------------------------------

from src.elwand_paths import databases_dir as _databases_dir

_DB_FILE = None
_AUTOSAVE_INTERVAL = 10
_autosave_running = False
_autosave_thread = None
_save_lock = threading.Lock()


def _init_db_path():
    global _DB_FILE
    if _DB_FILE is None:
        db_dir = _databases_dir()
        _DB_FILE = os.path.join(db_dir, "machines.dbs")


class Machine:
    def __init__(self, ip, hostname="", mac="", method=""):
        self.id = 0
        self.ip = ip
        self.ipv6 = ""
        self.hostname = hostname
        self.mac = mac
        self.device_type = ""
        self.model = ""
        self.os = ""
        self.domain = ""
        self.methods = {method} if method else set()
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()

    def update(self, hostname="", mac="", method=""):
        if hostname and not self.hostname:
            self.hostname = hostname
        if mac and not self.mac:
            self.mac = mac
        if method:
            self.methods.add(method)
        self.last_seen = datetime.now()

    def to_dict(self):
        return {
            "id": self.id,
            "ip": self.ip,
            "ipv6": self.ipv6,
            "hostname": self.hostname,
            "mac": self.mac,
            "device_type": self.device_type,
            "model": self.model,
            "os": self.os,
            "domain": self.domain,
            "methods": sorted(self.methods),
            "first_seen": self.first_seen.strftime("%H:%M:%S"),
            "last_seen": self.last_seen.strftime("%H:%M:%S"),
        }


class MachineStore:
    def __init__(self):
        self._machines = {}
        self._next_id = 1

    def add_or_update(self, ip, hostname="", mac="", method=""):
        if ip in self._machines:
            self._machines[ip].update(hostname=hostname, mac=mac, method=method)
        else:
            m = Machine(ip, hostname=hostname, mac=mac, method=method)
            m.id = self._next_id
            self._next_id += 1
            self._machines[ip] = m
        return self._machines[ip]

    def get(self, ip):
        return self._machines.get(ip)

    def get_by_hostname(self, hostname):
        if not hostname:
            return None
        for m in self._machines.values():
            if m.hostname.lower() == hostname.lower():
                return m
        return None

    def get_by_id(self, mid):
        for m in self._machines.values():
            if m.id == mid:
                return m
        return None

    def get_all(self):
        return list(self._machines.values())

    def get_all_sorted(self):
        return sorted(self._machines.values(), key=lambda m: m.id)

    def count(self):
        return len(self._machines)

    def clear(self):
        self._machines.clear()
        self._next_id = 1

    def remove(self, ip):
        if ip in self._machines:
            del self._machines[ip]

    def save(self):
        _dbg(f"[store.save] saving {len(self._machines)} machines")
        _init_db_path()
        try:
            with _save_lock, sqlite3.connect(_DB_FILE) as conn:
                cur = conn.execute("PRAGMA table_info(machines)")
                columns = [r[1] for r in cur.fetchall()]
                if columns and "id" not in columns:
                    conn.execute("DROP TABLE machines")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS machines (
                        id INTEGER PRIMARY KEY,
                        ip TEXT UNIQUE,
                        ipv6 TEXT,
                        hostname TEXT,
                        mac TEXT,
                        device_type TEXT,
                        model TEXT,
                        os TEXT,
                        domain TEXT,
                        methods TEXT,
                        first_seen TEXT,
                        last_seen TEXT
                    )
                """)
                cur = conn.execute("PRAGMA table_info(machines)")
                cols = [r[1] for r in cur.fetchall()]
                if "ipv6" not in cols:
                    conn.execute("ALTER TABLE machines ADD COLUMN ipv6 TEXT")
                conn.execute("DELETE FROM machines")
                for m in self._machines.values():
                    conn.execute(
                        """INSERT OR REPLACE INTO machines
                           (id, ip, ipv6, hostname, mac, device_type, model, os, domain, methods, first_seen, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            m.id,
                            m.ip,
                            m.ipv6,
                            m.hostname,
                            m.mac,
                            m.device_type,
                            m.model,
                            m.os,
                            m.domain,
                            json.dumps(sorted(m.methods)),
                            m.first_seen.isoformat(),
                            m.last_seen.isoformat(),
                        ),
                    )
                _dbg(f"[store.save] done")
        except (PermissionError, OSError, sqlite3.OperationalError):
            _dbg(f"[store.save] error")

    def load(self):
        _init_db_path()
        if not os.path.isfile(_DB_FILE):
            _dbg("[store.load] no file, starting fresh")
            return
        try:
            with sqlite3.connect(_DB_FILE) as conn:
                cur = conn.execute("PRAGMA table_info(machines)")
                columns = [r[1] for r in cur.fetchall()]
                if "id" not in columns:
                    _dbg("[store.load] no id column, skipping")
                    self._next_id = 1
                    return
                rows = conn.execute(
                    "SELECT id, ip, ipv6, hostname, mac, device_type, model, os, domain, methods, first_seen, last_seen FROM machines"
                ).fetchall()
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            _dbg("[store.load] db error")
            return

        max_id = 0
        for row in rows:
            mid, ip, ipv6, hostname, mac, device_type, model, os_val, domain_val, methods_json, first_seen, last_seen = row
            m = Machine(ip, hostname=hostname, mac=mac)
            try:
                m.id = int(mid)
            except (ValueError, TypeError):
                pass
            if m.id > max_id:
                max_id = m.id
            m.ipv6 = ipv6 or ""
            m.device_type = device_type
            m.model = model or ""
            m.os = os_val or ""
            m.domain = domain_val or ""
            try:
                m.methods = set(json.loads(methods_json))
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                m.first_seen = datetime.fromisoformat(first_seen)
            except (ValueError, TypeError):
                pass
            try:
                m.last_seen = datetime.fromisoformat(last_seen)
            except (ValueError, TypeError):
                pass
            self._machines[ip] = m
        self._next_id = max_id + 1
        _dbg(f"[store.load] loaded {len(self._machines)} machines")


def start_autosave(store_instance):
    global _autosave_running, _autosave_thread, _store_ref
    _store_ref = store_instance
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
        _time.sleep(_AUTOSAVE_INTERVAL)
        if _autosave_running:
            _store_ref.save()
