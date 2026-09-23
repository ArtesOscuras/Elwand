import os
import re
import sqlite3
from datetime import datetime
from src.elwand_paths import databases_dir as _databases_dir


_DB_DIR = None


def _init_db_dir():
    global _DB_DIR
    if _DB_DIR is None:
        _DB_DIR = str(_databases_dir())


def _sanitize(domain):
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", domain)


def _get_path(domain):
    _init_db_dir()
    safe = _sanitize(domain)
    return os.path.join(_DB_DIR, f"dom_{safe}.dbs")


def init_or_update(domain, machine_id, machine_ip, source=""):
    _init_db_dir()
    path = _get_path(domain)
    now = datetime.now().isoformat()
    exists = os.path.isfile(path)
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domain_info (
                    domain TEXT,
                    first_seen TEXT,
                    last_seen TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domain_machines (
                    machine_id INTEGER,
                    machine_ip TEXT,
                    source TEXT,
                    discovered_at TEXT
                )
            """)
            if not exists:
                conn.execute(
                    "INSERT INTO domain_info VALUES (?, ?, ?)",
                    (domain, now, now),
                )
            else:
                conn.execute(
                    "UPDATE domain_info SET last_seen = ? WHERE domain = ?",
                    (now, domain),
                )
            existing_machine = conn.execute(
                "SELECT 1 FROM domain_machines WHERE machine_id = ?", (machine_id,)
            ).fetchone()
            if not existing_machine:
                conn.execute(
                    "INSERT INTO domain_machines VALUES (?, ?, ?, ?)",
                    (machine_id, machine_ip, source, now),
                )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_domain_info(domain):
    _init_db_dir()
    path = _get_path(domain)
    if not os.path.isfile(path):
        return None
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT domain, first_seen, last_seen FROM domain_info"
            ).fetchone()
            if row:
                return {"domain": row[0], "first_seen": row[1], "last_seen": row[2]}
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        pass
    return None


def load_domain_machines(domain):
    _init_db_dir()
    path = _get_path(domain)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT machine_id, machine_ip, source, discovered_at FROM domain_machines ORDER BY discovered_at"
            ).fetchall()
            return [{"machine_id": r[0], "machine_ip": r[1], "source": r[2], "discovered_at": r[3]} for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def save_subdomain(domain, subdomain, method=""):
    _init_db_dir()
    path = _get_path(domain)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subdomains (
                    subdomain TEXT,
                    discovered_at TEXT,
                    method TEXT
                )
            """)
            existing = conn.execute(
                "SELECT 1 FROM subdomains WHERE subdomain = ?", (subdomain,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO subdomains VALUES (?, ?, ?)",
                    (subdomain, now, method),
                )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def save_directory(domain, path):
    _init_db_dir()
    file_path = _get_path(domain)
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(file_path) as conn:
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


def load_directories(domain):
    _init_db_dir()
    path = _get_path(domain)
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


def save_web_service(domain, port, output):
    _init_db_dir()
    path = _get_path(domain)
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


def load_web_services(domain):
    _init_db_dir()
    path = _get_path(domain)
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


def load_subdomains(domain):
    _init_db_dir()
    path = _get_path(domain)
    if not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subdomains (
                    subdomain TEXT,
                    discovered_at TEXT,
                    method TEXT
                )
            """)
            rows = conn.execute(
                "SELECT subdomain, discovered_at, method FROM subdomains ORDER BY discovered_at"
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def exists(domain):
    _init_db_dir()
    return os.path.isfile(_get_path(domain))


def delete_domain(domain):
    _init_db_dir()
    path = _get_path(domain)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except (PermissionError, OSError):
        pass


def list_all():
    _init_db_dir()
    result = []
    for fname in os.listdir(_DB_DIR):
        if fname.startswith("dom_") and fname.endswith(".dbs"):
            result.append(fname[4:-4])
    return result


def delete_all():
    _init_db_dir()
    for fname in os.listdir(_DB_DIR):
        if fname.startswith("dom_") and fname.endswith(".dbs"):
            try:
                os.remove(os.path.join(_DB_DIR, fname))
            except (PermissionError, OSError):
                pass
