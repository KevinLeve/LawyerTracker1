"""
connection.py

SQLite connection management + schema creation for LawyerTracker.

Design decisions:

1. We use a context-managed `get_connection()` generator instead of one
   long-lived global connection. SQLite connections are cheap to open,
   and short-lived connections avoid "database is locked" issues if the
   UI ever does something on a background thread later.

2. Foreign keys are off by default in SQLite - we turn them on per
   connection with `PRAGMA foreign_keys = ON`, otherwise the FK
   constraints declared in the schema (e.g. cases.search_id) would be
   silently ignored.

3. Schema lives in this file as plain SQL strings rather than an ORM.
   For a capstone project, an ORM (SQLAlchemy) would add a layer the
   user has to learn on top of SQL itself; raw SQL via sqlite3 keeps
   things transparent and is easy to explain line by line.

Tables:
    searches   - one row per search performed (query params + timestamp)
    cases      - one row per case found, linked to the search that found it
    favourites - case CINOs the user has starred, independent of any one search
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config import settings
from app_utils.exceptions import DatabaseError
from app_utils.logger import get_logger

logger = get_logger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    search_type   TEXT NOT NULL,      -- 'cnr' | 'advocate' | 'case_number'
    query_text    TEXT NOT NULL,      -- what the user searched for
    state_code    TEXT,
    dist_code     TEXT,
    court_complex_code TEXT,
    case_status   TEXT,               -- 'PENDING' | 'DISPOSED' filter used, if any
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id           INTEGER REFERENCES searches(id) ON DELETE SET NULL,
    cnr                 TEXT,
    case_number         TEXT,
    case_type           TEXT,
    filing_number       TEXT,
    filing_date         TEXT,
    registration_number TEXT,
    registration_date   TEXT,
    petitioner          TEXT,
    respondent          TEXT,
    petitioner_advocate TEXT,
    respondent_advocate TEXT,
    case_stage          TEXT,
    case_status         TEXT,          -- 'PENDING' | 'DISPOSED' (as returned/searched)
    next_hearing_date   TEXT,          -- original text, e.g. "19th June 2026"
    next_hearing_iso    TEXT,          -- parsed "YYYY-MM-DD", for sorting; NULL if unparseable
    court_name          TEXT,
    judge               TEXT,
    raw_json            TEXT,          -- full parsed record, for fields the UI doesn't show yet
    saved_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS favourites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    added_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(case_id)
);

-- Single-row table: this app is built for one advocate on their own
-- machine, so there's exactly one profile rather than a users table.
CREATE TABLE IF NOT EXISTS profile (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    advocate_name               TEXT NOT NULL,
    default_state_code          TEXT,
    default_state_name          TEXT,
    default_dist_code           TEXT,
    default_dist_name           TEXT,
    default_court_complex_code  TEXT,
    default_court_complex_name  TEXT,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Small generic key/value store for user-editable settings that need to
-- persist (e.g. the KevinOCR folder path set from the Settings screen),
-- kept separate from config/settings.py's compile-time defaults.
CREATE TABLE IF NOT EXISTS app_config (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_cnr ON cases(cnr);
CREATE INDEX IF NOT EXISTS idx_cases_search_id ON cases(search_id);
CREATE INDEX IF NOT EXISTS idx_cases_next_hearing_iso ON cases(next_hearing_iso);
-- A case is only truly unique by CNR when it HAS a CNR; partial index
-- means rows with an empty cnr ('') are exempt from the constraint.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_cnr_unique ON cases(cnr) WHERE cnr != '';
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """
    Yield a SQLite connection configured with foreign keys on and
    row_factory set to sqlite3.Row (so rows can be accessed by column
    name, e.g. row["case_number"], not just by index).

    Usage:
        with get_connection() as conn:
            conn.execute("SELECT * FROM cases")
    """
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        logger.exception("Database operation failed, rolled back.")
        raise DatabaseError(str(exc)) from exc
    finally:
        conn.close()


def init_database() -> None:
    """Create tables/indexes if they don't already exist. Safe to call every startup."""
    try:
        with get_connection() as conn:
            conn.executescript(_SCHEMA)
        logger.info("Database ready at %s", settings.db_path)
    except DatabaseError:
        logger.error("Failed to initialize database schema.")
        raise
