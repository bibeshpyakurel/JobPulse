import sqlite3
import hashlib
from datetime import datetime
from config import DATABASE_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT    UNIQUE NOT NULL,
                title       TEXT,
                company     TEXT,
                link        TEXT,
                gmail_id    TEXT,
                seen_at     TEXT    NOT NULL
            )
        """)
        conn.commit()


def _fingerprint(title: str, company: str, link: str) -> str:
    raw = f"{title.lower().strip()}|{company.lower().strip()}|{link.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_duplicate(title: str, company: str, link: str) -> bool:
    fp = _fingerprint(title, company, link)
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM jobs WHERE fingerprint = ?", (fp,)
        ).fetchone()
    return row is not None


def save_job(title: str, company: str, link: str, gmail_id: str = "") -> bool:
    """Insert job record. Returns True if inserted, False if already existed."""
    fp = _fingerprint(title, company, link)
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO jobs (fingerprint, title, company, link, gmail_id, seen_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fp, title, company, link, gmail_id, datetime.utcnow().isoformat()),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
