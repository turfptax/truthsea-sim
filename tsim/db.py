"""SQLite database connection and initialization."""

import sqlite3
import os

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "truthsea.db")


def get_db(path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Return a connection with row_factory and foreign keys enabled."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Create all tables from schema.sql. Returns the connection."""
    conn = get_db(path)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def reset_db(path: str = DEFAULT_DB) -> sqlite3.Connection:
    """Drop and recreate the database."""
    if os.path.exists(path):
        os.remove(path)
    # Remove WAL/SHM files if present
    for suffix in ("-wal", "-shm"):
        p = path + suffix
        if os.path.exists(p):
            os.remove(p)
    return init_db(path)


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)
