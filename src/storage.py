"""SQLite storage for collected posts."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    retweet_count INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    quote_count INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL,
    collected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
)
"""

_COLUMNS = (
    "id, author_id, text, created_at, "
    "retweet_count, reply_count, like_count, quote_count, url"
)


def connect(db_path):
    path = Path(db_path)
    if path.parent != path and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    # Concurrent runs queue on the writer lock instead of racing past it.
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def insert_post(conn, post):
    """Insert one normalized post. Returns True if a new row was stored."""
    cur = conn.execute(
        f"INSERT OR IGNORE INTO posts ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            post["id"],
            post["author_id"],
            post["text"],
            post["created_at"],
            post["retweet_count"],
            post["reply_count"],
            post["like_count"],
            post["quote_count"],
            post["url"],
        ),
    )
    return cur.rowcount > 0


def count_posts(conn):
    return conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
