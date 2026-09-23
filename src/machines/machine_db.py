import json
import os
import sqlite3
from datetime import datetime


from src.elwand_paths import databases_dir as _databases_dir

_DB_DIR = None


def _init_db_dir():
    global _DB_DIR
    if _DB_DIR is None:
        _DB_DIR = str(_databases_dir())


def _get_path(machine_id):
    _init_db_dir()
    return os.path.join(_DB_DIR, f"machine_{machine_id}.dbs")


def save_machine_info(machine):
    _init_db_dir()
    path = _get_path(machine.id)
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS machine_info (
                    ip TEXT,
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
            cur = conn.execute("PRAGMA table_info(machine_info)")
            cols = [r[1] for r in cur.fetchall()]
            if "ipv6" not in cols:
                conn.execute("ALTER TABLE machine_info ADD COLUMN ipv6 TEXT")
            conn.execute("DELETE FROM machine_info")
            conn.execute(
                "INSERT INTO machine_info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    machine.ip,
                    machine.ipv6,
                    machine.hostname,
                    machine.mac,
                    machine.device_type,
                    machine.model,
                    machine.os,
                    machine.domain,
                    json.dumps(sorted(machine.methods)),
                    machine.first_seen.isoformat(),
                    machine.last_seen.isoformat(),
                ),
            )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def save_tcp_ports(machine_id, ports):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tcp_ports (
                    port INTEGER,
                    service TEXT,
                    discovered_at TEXT
                )
            """)
            conn.execute("DELETE FROM tcp_ports")
            for p in ports:
                conn.execute(
                    "INSERT INTO tcp_ports VALUES (?, ?, ?)",
                    (p, "", now),
                )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def save_tcp_port(machine_id, port):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tcp_ports (
                    port INTEGER,
                    service TEXT,
                    discovered_at TEXT
                )
            """)
            existing = conn.execute(
                "SELECT 1 FROM tcp_ports WHERE port = ?", (port,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO tcp_ports VALUES (?, ?, ?)",
                    (port, "", now),
                )
                return True
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass
    return False


def save_directory(machine_id, path):
    _init_db_dir()
    path_file = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS directories (
                    path TEXT,
                    discovered_at TEXT
                )
            """)
            existing = conn.execute(
                "SELECT 1 FROM directories WHERE path = ?", (path,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO directories VALUES (?, ?)",
                    (path, now),
                )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_directories(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS directories (
                    path TEXT,
                    discovered_at TEXT
                )
            """)
            rows = conn.execute(
                "SELECT path, discovered_at FROM directories ORDER BY discovered_at"
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def load_tcp_ports(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tcp_ports (
                    port INTEGER,
                    service TEXT,
                    discovered_at TEXT
                )
            """)
            rows = conn.execute("SELECT port FROM tcp_ports ORDER BY port").fetchall()
            return [r[0] for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def load_udp_ports(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS udp_ports (
                    port INTEGER,
                    service TEXT,
                    discovered_at TEXT
                )
            """)
            rows = conn.execute("SELECT port FROM udp_ports ORDER BY port").fetchall()
            return [r[0] for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def save_udp_ports(machine_id, ports):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS udp_ports (
                    port INTEGER,
                    service TEXT,
                    discovered_at TEXT
                )
            """)
            conn.execute("DELETE FROM udp_ports")
            for p in ports:
                conn.execute(
                    "INSERT INTO udp_ports VALUES (?, ?, ?)",
                    (p, "", now),
                )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def save_udp_port(machine_id, port):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS udp_ports (
                    port INTEGER,
                    service TEXT,
                    discovered_at TEXT
                )
            """)
            existing = conn.execute(
                "SELECT 1 FROM udp_ports WHERE port = ?", (port,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO udp_ports VALUES (?, ?, ?)",
                    (port, "", now),
                )
                return True
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass
    return False


def save_web_service(machine_id, port, output):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS web_services (
                    port INTEGER,
                    output TEXT,
                    scanned_at TEXT
                )
            """)
            conn.execute("DELETE FROM web_services WHERE port = ?", (port,))
            conn.execute("INSERT INTO web_services VALUES (?, ?, ?)", (port, output, now))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_web_services(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS web_services (
                    port INTEGER,
                    output TEXT,
                    scanned_at TEXT
                )
            """)
            rows = conn.execute(
                "SELECT port, output FROM web_services ORDER BY port"
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def save_domain(machine_id, domain, source=""):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domains (
                    domain TEXT,
                    source TEXT,
                    discovered_at TEXT
                )
            """)
            conn.execute(
                "INSERT OR IGNORE INTO domains VALUES (?, ?, ?)",
                (domain, source, now),
            )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_domains(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domains (
                    domain TEXT,
                    source TEXT,
                    discovered_at TEXT
                )
            """)
            rows = conn.execute(
                "SELECT domain, source FROM domains ORDER BY discovered_at"
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def delete_machine_db(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except (PermissionError, OSError):
        pass


def save_banner(machine_id, port, output, probe=""):
    _init_db_dir()
    path = _get_path(machine_id)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS banners (
                    port INTEGER,
                    output TEXT,
                    probe TEXT,
                    scanned_at TEXT
                )
            """)
            conn.execute(
                "INSERT INTO banners VALUES (?, ?, ?, ?)",
                (port, output, probe, now),
            )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_banners(machine_id):
    _init_db_dir()
    path = _get_path(machine_id)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS banners (
                    port INTEGER,
                    output TEXT,
                    probe TEXT,
                    scanned_at TEXT
                )
            """)
            rows = conn.execute(
                "SELECT port, output, probe FROM banners ORDER BY scanned_at"
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def delete_all():
    _init_db_dir()
    for filename in os.listdir(_DB_DIR):
        if filename.startswith("machine_") and filename.endswith(".dbs"):
            try:
                os.remove(os.path.join(_DB_DIR, filename))
            except (PermissionError, OSError):
                pass
