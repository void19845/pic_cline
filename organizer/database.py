from __future__ import annotations
"""organizer.database — SQLite logging for processed files."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from integrity import IntegrityRecord


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create (or open) the SQLite database and ensure all tables exist."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS photos (
            id           INTEGER PRIMARY KEY,
            original     TEXT,
            destination  TEXT,
            date         TEXT,
            city         TEXT,
            country      TEXT,
            tags         TEXT,
            people       TEXT,
            lat          REAL,
            lon          REAL,
            processed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS duplicates (
            id          INTEGER PRIMARY KEY,
            path        TEXT,
            original    TEXT,
            kind        TEXT,
            action      TEXT,
            kept        INTEGER,
            detected_at TEXT
        );
        CREATE TABLE IF NOT EXISTS integrity (
            id          INTEGER PRIMARY KEY,
            source      TEXT,
            destination TEXT,
            source_hash TEXT,
            dest_hash   TEXT,
            status      TEXT,
            checked_at  TEXT
        );
    """)
    conn.commit()
    return conn


def log_photo(
    conn: sqlite3.Connection,
    original: str,
    dest: str,
    meta: dict,
    city: str | None,
    country: str | None,
    tags: list,
    people: list,
) -> None:
    """Insert or replace a processed-file record."""
    date_str = meta["date"].isoformat() if meta.get("date") else None
    conn.execute(
        """INSERT OR REPLACE INTO photos
           (original, destination, date, city, country, tags, people,
            lat, lon, processed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (original, dest, date_str, city, country,
         json.dumps(tags), json.dumps(people),
         meta.get("lat"), meta.get("lon"),
         datetime.now().isoformat()),
    )
    conn.commit()


def log_duplicate(
    conn: sqlite3.Connection,
    path: str,
    original: str,
    kind: str,
    action: str,
    kept: bool,
) -> None:
    """Log a duplicate detection event."""
    conn.execute(
        """INSERT INTO duplicates (path, original, kind, action, kept, detected_at)
           VALUES (?,?,?,?,?,?)""",
        (path, original, kind, action, int(kept), datetime.now().isoformat()),
    )
    conn.commit()


def log_integrity(
    conn: sqlite3.Connection,
    record: IntegrityRecord,
) -> None:
    """Log the result of a post-move integrity check."""
    conn.execute(
        """INSERT INTO integrity
           (source, destination, source_hash, dest_hash, status, checked_at)
           VALUES (?,?,?,?,?,?)""",
        (record.source, record.destination,
         record.source_hash, record.dest_hash,
         record.status.value,
         datetime.now().isoformat()),
    )
    conn.commit()
