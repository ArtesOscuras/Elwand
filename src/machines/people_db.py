import sqlite3
import os
from src.elwand_paths import databases_dir

_DB_PATH = None


def _init_db_path():
    global _DB_PATH
    if _DB_PATH is None:
        d = str(databases_dir())
        _DB_PATH = os.path.join(d, "people.dbs")
    return _DB_PATH


def _connect():
    path = _init_db_path()
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except (PermissionError, OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        raise


def _migrate(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            company TEXT DEFAULT '',
            domain TEXT DEFAULT '',
            username TEXT DEFAULT '',
            role TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            interests TEXT DEFAULT ''
        )
    """)
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(people)").fetchall()}
    for col, col_type in [
        ("username", "TEXT DEFAULT ''"),
        ("linkedin_url", "TEXT DEFAULT ''"),
        ("source", "TEXT DEFAULT ''"),
        ("interests", "TEXT DEFAULT ''"),
    ]:
        if col not in existing:
            cursor.execute(f"ALTER TABLE people ADD COLUMN {col} {col_type}")
    conn.commit()


def save_person(first_name, last_name="", company="", domain="",
                username="", role="", linkedin_url="", source="", interests=""):
    try:
        conn = _connect()
        _migrate(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO people (first_name, last_name, company, domain, "
            "username, role, linkedin_url, source, interests) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (first_name, last_name, company, domain,
             username, role, linkedin_url, source, interests),
        )
        pid = cursor.lastrowid
        conn.commit()
        conn.close()
        return pid
    except (PermissionError, OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def load_people():
    try:
        conn = _connect()
        _migrate(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, first_name, last_name, company, domain, "
            "username, role, linkedin_url, source, interests "
            "FROM people ORDER BY last_name, first_name"
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "first_name": r[1],
                "last_name": r[2],
                "company": r[3],
                "domain": r[4],
                "username": r[5],
                "role": r[6],
                "linkedin_url": r[7],
                "source": r[8],
                "interests": r[9],
            }
            for r in rows
        ]
    except (PermissionError, OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def load_person(person_id):
    try:
        conn = _connect()
        _migrate(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, first_name, last_name, company, domain, "
            "username, role, linkedin_url, source, interests "
            "FROM people WHERE id = ?",
            (int(person_id),),
        )
        r = cursor.fetchone()
        conn.close()
        if r:
            return {
                "id": r[0],
                "first_name": r[1],
                "last_name": r[2],
                "company": r[3],
                "domain": r[4],
                "username": r[5],
                "role": r[6],
                "linkedin_url": r[7],
                "source": r[8],
                "interests": r[9],
            }
        return None
    except (PermissionError, OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def update_person(person_id, first_name=None, last_name=None, company=None,
                  domain=None, username=None, role=None, linkedin_url=None,
                  source=None, interests=None):
    try:
        conn = _connect()
        _migrate(conn)
        cursor = conn.cursor()
        fields = {
            "first_name": first_name, "last_name": last_name,
            "company": company, "domain": domain, "username": username,
            "role": role, "linkedin_url": linkedin_url,
            "source": source, "interests": interests,
        }
        set_clause = ", ".join(
            f"{k} = ?" for k, v in fields.items() if v is not None
        )
        values = [v for v in fields.values() if v is not None]
        if set_clause:
            cursor.execute(
                f"UPDATE people SET {set_clause} WHERE id = ?",
                values + [int(person_id)],
            )
        conn.commit()
        conn.close()
        return True
    except (PermissionError, OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        return False


def delete_person(person_id):
    try:
        conn = _connect()
        _migrate(conn)
        conn.execute("DELETE FROM people WHERE id = ?", (int(person_id),))
        conn.commit()
        conn.close()
        return True
    except (PermissionError, OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        return False


def delete_all():
    _init_db_path()
    try:
        if os.path.isfile(_DB_PATH):
            os.remove(_DB_PATH)
    except (PermissionError, OSError):
        pass
