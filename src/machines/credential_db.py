import os
import sqlite3
from datetime import datetime
from src.elwand_paths import credentials_dir as _credentials_dir


_DB_PATH = None


def _init_db_path():
    global _DB_PATH
    if _DB_PATH is None:
        db_dir = _credentials_dir()
        _DB_PATH = os.path.join(db_dir, "credentials.dbs")


def _migrate_cred_table():
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(credentials)").fetchall()]
            for col in ("domain", "hash_nt", "password_origin", "hash_nt_origin"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE credentials ADD COLUMN {col} TEXT DEFAULT ''")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password TEXT,
                domain TEXT,
                hash_nt TEXT,
                password_origin TEXT,
                hash_nt_origin TEXT
            )
        """)


def save_credential(username, password, domain="", hash_nt="", password_origin="", hash_nt_origin=""):
    _init_db_path()
    _migrate_cred_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO credentials (username, password, domain, hash_nt, password_origin, hash_nt_origin) VALUES (?, ?, ?, ?, ?, ?)",
                (username, password, domain, hash_nt, password_origin, hash_nt_origin),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except (PermissionError, OSError, sqlite3.OperationalError):
        return None


def update_credential(cred_id, username, password, domain="", hash_nt="", password_origin="", hash_nt_origin=""):
    _init_db_path()
    _migrate_cred_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "UPDATE credentials SET username=?, password=?, domain=?, hash_nt=?, password_origin=?, hash_nt_origin=? WHERE id=?",
                (username, password, domain, hash_nt, password_origin, hash_nt_origin, cred_id),
            )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_credentials():
    _init_db_path()
    if not os.path.isfile(_DB_PATH):
        return []
    _migrate_cred_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, username, password, domain, hash_nt, password_origin, hash_nt_origin FROM credentials ORDER BY id DESC"
            ).fetchall()
            return [{"id": r[0], "username": r[1], "password": r[2],
                     "domain": r[3], "hash_nt": r[4],
                     "password_origin": r[5], "hash_nt_origin": r[6]} for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def load_credential(cred_id):
    _init_db_path()
    if not os.path.isfile(_DB_PATH):
        return None
    _migrate_cred_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, username, password, domain, hash_nt, password_origin, hash_nt_origin FROM credentials WHERE id = ?",
                (cred_id,),
            ).fetchone()
            if row:
                return {"id": row[0], "username": row[1], "password": row[2],
                        "domain": row[3], "hash_nt": row[4],
                        "password_origin": row[5], "hash_nt_origin": row[6]}
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        pass
    return None


def delete_credential(cred_id):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("DELETE FROM credentials WHERE id = ?", (cred_id,))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def _migrate_users_table():
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            existing = [r[1] for r in conn.execute(
                "PRAGMA table_info(users)").fetchall()]
            if "id" not in existing:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        origin TEXT DEFAULT '',
                        type TEXT DEFAULT '',
                        machine TEXT DEFAULT '',
                        domain TEXT DEFAULT '',
                        groups TEXT DEFAULT ''
                    )
                """)
                try:
                    rows = conn.execute(
                        "SELECT username FROM users"
                    ).fetchall()
                    for (u,) in rows:
                        conn.execute(
                            "INSERT OR IGNORE INTO users_new (username) "
                            "VALUES (?)", (u,))
                except (sqlite3.OperationalError, sqlite3.DatabaseError):
                    pass
                conn.execute("DROP TABLE IF EXISTS users")
                conn.execute("ALTER TABLE users_new RENAME TO users")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                origin TEXT DEFAULT '',
                type TEXT DEFAULT '',
                machine TEXT DEFAULT '',
                domain TEXT DEFAULT '',
                groups TEXT DEFAULT ''
            )
        """)


def save_user(username, origin="", utype="", machine="", domain="", groups=""):
    _init_db_path()
    _migrate_users_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (username, origin, type, machine, "
                "domain, groups) VALUES (?, ?, ?, ?, ?, ?)",
                (username, origin, utype, machine, domain, groups),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except (PermissionError, OSError, sqlite3.OperationalError):
        return None


def update_user(username, origin="", utype="", machine="", domain="", groups=""):
    _init_db_path()
    _migrate_users_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(
                "UPDATE users SET origin=?, type=?, machine=?, domain=?, "
                "groups=? WHERE username=?",
                (origin, utype, machine, domain, groups, username),
            )
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_users():
    _init_db_path()
    if not os.path.isfile(_DB_PATH):
        return []
    _migrate_users_table()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, username, origin, type, machine, domain, groups "
                "FROM users ORDER BY username"
            ).fetchall()
            return [{"id": r[0], "username": r[1], "origin": r[2],
                     "type": r[3], "machine": r[4], "domain": r[5],
                     "groups": r[6]} for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def load_usernames():
    return [u["username"] for u in load_users()]


def delete_user(username):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def save_password(password):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS passwords (
                    password TEXT UNIQUE
                )
            """)
            conn.execute("INSERT OR IGNORE INTO passwords VALUES (?)", (password,))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def load_passwords():
    _init_db_path()
    if not os.path.isfile(_DB_PATH):
        return []
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS passwords (
                    password TEXT UNIQUE
                )
            """)
            rows = conn.execute("SELECT password FROM passwords ORDER BY password").fetchall()
            return [r[0] for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def delete_password(password):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("DELETE FROM passwords WHERE password = ?", (password,))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def delete_all():
    _init_db_path()
    try:
        if os.path.isfile(_DB_PATH):
            os.remove(_DB_PATH)
    except (PermissionError, OSError):
        pass


def save_hash_entry(hash_type, hash_value, salt="", peper="", hascat_mode="", origin=""):
    _init_db_path()
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    hash TEXT,
                    salt TEXT,
                    peper TEXT,
                    hascat_mode TEXT,
                    origin_obteined TEXT,
                    obtained_date_time TEXT
                )
            """)
            conn.execute(
                "INSERT INTO hashes (type, hash, salt, peper, hascat_mode, origin_obteined, obtained_date_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (hash_type, hash_value, salt, peper, hascat_mode, origin, now),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except (PermissionError, OSError, sqlite3.OperationalError):
        return None


def load_hashes():
    _init_db_path()
    if not os.path.isfile(_DB_PATH):
        return []
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    hash TEXT,
                    salt TEXT,
                    peper TEXT,
                    hascat_mode TEXT,
                    origin_obteined TEXT,
                    obtained_date_time TEXT
                )
            """)
            rows = conn.execute(
                "SELECT id, type, hash, salt, peper, hascat_mode, origin_obteined, obtained_date_time FROM hashes ORDER BY id DESC"
            ).fetchall()
            return [{"id": r[0], "type": r[1], "hash": r[2], "salt": r[3],
                     "peper": r[4], "hascat_mode": r[5],
                     "origin_obteined": r[6], "obtained_date_time": r[7]} for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def delete_hash_entry(hash_id):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("DELETE FROM hashes WHERE id = ?", (hash_id,))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def update_hash_value(hash_id, hash_value):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("UPDATE hashes SET hash = ? WHERE id = ?",
                         (hash_value, hash_id))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass


def repair_handshake_hashes():
    """Repair legacy WPA handshake rows.

    They used to store the path to the .hc22000 file in the `hash` column;
    replace it with the last hash line of that file.
    """
    for item in load_hashes():
        if (item.get("type") or "") != "WPA handshake":
            continue
        value = (item.get("hash") or "").strip()
        if not value or value.startswith("WPA*"):
            continue
        if not (os.path.isfile(value) and value.lower().endswith(".hc22000")):
            continue
        try:
            with open(value, "r", errors="replace") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except (PermissionError, OSError):
            continue
        if lines:
            update_hash_value(item["id"], lines[-1])


def _init_tickets_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            principal TEXT,
            realm TEXT,
            service TEXT,
            ticket_type TEXT,
            ticket_data TEXT,
            origin TEXT,
            obtained_date_time TEXT
        )
    """)


def save_ticket(principal, realm, service, ticket_type, ticket_data, origin=""):
    _init_db_path()
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _init_tickets_table(conn)
            conn.execute(
                "INSERT INTO tickets (principal, realm, service, ticket_type, "
                "ticket_data, origin, obtained_date_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (principal, realm, service, ticket_type, ticket_data, origin, now),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except (PermissionError, OSError, sqlite3.OperationalError):
        return None


def load_tickets():
    _init_db_path()
    if not os.path.isfile(_DB_PATH):
        return []
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            _init_tickets_table(conn)
            rows = conn.execute(
                "SELECT id, principal, realm, service, ticket_type, "
                "ticket_data, origin, obtained_date_time "
                "FROM tickets ORDER BY id DESC"
            ).fetchall()
            return [{"id": r[0], "principal": r[1], "realm": r[2],
                     "service": r[3], "ticket_type": r[4],
                     "ticket_data": r[5], "origin": r[6],
                     "obtained_date_time": r[7]} for r in rows]
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return []


def delete_ticket(ticket_id):
    _init_db_path()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    except (PermissionError, OSError, sqlite3.OperationalError):
        pass
