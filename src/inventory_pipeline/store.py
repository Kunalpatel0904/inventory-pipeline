"""Small persistence helpers shared by reference loading and ingestion."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reject_id(file_sha: str, line: int, code: str) -> str:
    """Deterministic ID: replaying the same file never creates duplicate rejects."""
    return hashlib.sha1(f"{file_sha}|{line}|{code}".encode()).hexdigest()[:16]


def record_rejects(conn: sqlite3.Connection, run_id: str, source_file: str, file_sha: str,
                   rejects: list[tuple[int, str, str, dict]]) -> None:
    now = utc_now()
    conn.executemany(
        "INSERT OR IGNORE INTO reject_record(reject_id, run_id, source_file, file_sha256, "
        "source_line, reason_code, reason_detail, raw_record, rejected_at) VALUES (?,?,?,?,?,?,?,?,?)",
        [(reject_id(file_sha, line, code), run_id, source_file, file_sha, line, code, detail,
          json.dumps(raw, ensure_ascii=False, sort_keys=True), now)
         for line, code, detail, raw in rejects],
    )
