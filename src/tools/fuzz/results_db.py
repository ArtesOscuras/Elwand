import os
import sqlite3
import threading
from src.elwand_paths import databases_dir as _databases_dir

_DB_PATH = None
_LOCK = threading.Lock()


def _ensure_db():
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = os.path.join(str(_databases_dir()), "fuzz_results.dbs")
    return _DB_PATH


def save_result(method, target, word, display):
    path = _ensure_db()
    with _LOCK:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    method TEXT,
                    target TEXT,
                    word TEXT,
                    display TEXT
                )
            """)
            conn.execute(
                "INSERT INTO agent_results (method, target, word, display) "
                "VALUES (?, ?, ?, ?)",
                (method, target, word, display),
            )


def get_results(limit=100):
    path = _ensure_db()
    if not os.path.isfile(path):
        return []
    with sqlite3.connect(path) as conn:
        cur = conn.execute("""
            SELECT method, target, word, display
            FROM agent_results
            ORDER BY id DESC
        """)
        rows = cur.fetchall()
    return rows[:limit]


def clear_results():
    path = _ensure_db()
    if not os.path.isfile(path):
        return
    with _LOCK:
        with sqlite3.connect(path) as conn:
            conn.execute("DELETE FROM agent_results")


def clear_by_target(method, target):
    path = _ensure_db()
    if not os.path.isfile(path):
        return
    with _LOCK:
        with sqlite3.connect(path) as conn:
            conn.execute(
                "DELETE FROM agent_results WHERE method=? AND target=?",
                (method, target),
            )
