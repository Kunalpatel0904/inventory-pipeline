"""SQLite storage layer: connection settings and DDL.

Autocommit mode (isolation_level=None) is used on purpose so transaction
boundaries are always explicit BEGIN / COMMIT / ROLLBACK in the pipeline code.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS dim_product (
    product_id    TEXT PRIMARY KEY,
    product_name  TEXT NOT NULL,
    uom           TEXT NOT NULL DEFAULT 'EA'
);
CREATE TABLE IF NOT EXISTS dim_location (
    location_id   TEXT PRIMARY KEY,
    location_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id                 TEXT PRIMARY KEY,
    started_at             TEXT NOT NULL,
    ended_at               TEXT,
    status                 TEXT NOT NULL,
    files_total            INTEGER NOT NULL DEFAULT 0,
    files_succeeded        INTEGER NOT NULL DEFAULT 0,
    files_failed           INTEGER NOT NULL DEFAULT 0,
    files_skipped          INTEGER NOT NULL DEFAULT 0,
    rows_read              INTEGER NOT NULL DEFAULT 0,
    rows_loaded            INTEGER NOT NULL DEFAULT 0,
    rows_skipped_existing  INTEGER NOT NULL DEFAULT 0,
    rows_rejected          INTEGER NOT NULL DEFAULT 0,
    backdated_loaded       INTEGER NOT NULL DEFAULT 0,
    pairs_rebuilt          INTEGER NOT NULL DEFAULT 0,
    balance_rows_written   INTEGER NOT NULL DEFAULT 0,
    error                  TEXT,
    params_json            TEXT
);

CREATE TABLE IF NOT EXISTS file_load (
    run_id                 TEXT NOT NULL REFERENCES pipeline_run(run_id),
    source_file            TEXT NOT NULL,
    file_sha256            TEXT NOT NULL,
    status                 TEXT NOT NULL,
    rows_read              INTEGER NOT NULL DEFAULT 0,
    rows_loaded            INTEGER NOT NULL DEFAULT 0,
    rows_skipped_existing  INTEGER NOT NULL DEFAULT 0,
    rows_rejected          INTEGER NOT NULL DEFAULT 0,
    backdated_loaded       INTEGER NOT NULL DEFAULT 0,
    pairs_rebuilt          INTEGER NOT NULL DEFAULT 0,
    balance_rows_written   INTEGER NOT NULL DEFAULT 0,
    error                  TEXT,
    started_at             TEXT NOT NULL,
    ended_at               TEXT NOT NULL,
    PRIMARY KEY (run_id, source_file)
);
CREATE INDEX IF NOT EXISTS idx_file_load_sha ON file_load(file_sha256, status);

-- Append-only event ledger: never updated or deleted by the pipeline.
CREATE TABLE IF NOT EXISTS inventory_movement (
    movement_id      TEXT PRIMARY KEY,
    movement_type    TEXT NOT NULL CHECK (movement_type IN ('receipt','issue','transfer','adjustment')),
    product_id       TEXT NOT NULL REFERENCES dim_product(product_id),
    location_id      TEXT NOT NULL REFERENCES dim_location(location_id),
    dest_location_id TEXT REFERENCES dim_location(location_id),
    quantity         INTEGER NOT NULL,
    effective_date   TEXT NOT NULL,
    recorded_at      TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    is_backdated     INTEGER NOT NULL DEFAULT 0,
    run_id           TEXT NOT NULL REFERENCES pipeline_run(run_id),
    source_file      TEXT NOT NULL,
    source_line      INTEGER NOT NULL,
    loaded_at        TEXT NOT NULL
);

-- One row per stock-affecting side of a movement (transfer = 2 legs).
CREATE TABLE IF NOT EXISTS inventory_leg (
    movement_id    TEXT NOT NULL REFERENCES inventory_movement(movement_id),
    leg_no         INTEGER NOT NULL,
    product_id     TEXT NOT NULL,
    location_id    TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    leg_type       TEXT NOT NULL CHECK (leg_type IN ('receipt','issue','transfer_in','transfer_out','adjustment')),
    signed_qty     INTEGER NOT NULL,
    PRIMARY KEY (movement_id, leg_no)
);
CREATE INDEX IF NOT EXISTS idx_leg_pair_date ON inventory_leg(product_id, location_id, effective_date);

-- Derived, rebuildable target table (dense: one row per pair per day).
CREATE TABLE IF NOT EXISTS daily_balance (
    product_id        TEXT NOT NULL,
    location_id       TEXT NOT NULL,
    balance_date      TEXT NOT NULL,
    opening_qty       INTEGER NOT NULL,
    receipt_qty       INTEGER NOT NULL,
    issue_qty         INTEGER NOT NULL,
    transfer_in_qty   INTEGER NOT NULL,
    transfer_out_qty  INTEGER NOT NULL,
    adjustment_qty    INTEGER NOT NULL,
    closing_qty       INTEGER NOT NULL,
    run_id            TEXT NOT NULL,
    PRIMARY KEY (product_id, location_id, balance_date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS reject_record (
    reject_id      TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL,
    source_file    TEXT NOT NULL,
    file_sha256    TEXT NOT NULL,
    source_line    INTEGER NOT NULL,
    reason_code    TEXT NOT NULL,
    reason_detail  TEXT NOT NULL,
    raw_record     TEXT NOT NULL,
    rejected_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reject_reason ON reject_record(reason_code);

CREATE TABLE IF NOT EXISTS pipeline_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM pipeline_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO pipeline_state(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
