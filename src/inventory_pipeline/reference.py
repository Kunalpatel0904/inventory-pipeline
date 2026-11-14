"""Load master data (products, locations). Type-1 (overwrite) dimensions;
the ledger itself is immutable, so history of *movements* is never lost."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .config import Reason
from .csvio import file_sha256, read_csv
from .store import record_rejects

_PRODUCT_UPSERT = (
    "INSERT INTO dim_product(product_id, product_name, uom) VALUES (?,?,?) "
    "ON CONFLICT(product_id) DO UPDATE SET product_name=excluded.product_name, uom=excluded.uom")
_LOCATION_UPSERT = (
    "INSERT INTO dim_location(location_id, location_name) VALUES (?,?) "
    "ON CONFLICT(location_id) DO UPDATE SET location_name=excluded.location_name")


def _load(conn: sqlite3.Connection, path: Path, key: str, name_col: str, extra: dict[str, str],
          upsert_sql: str, run_id: str, log: logging.LoggerAdapter) -> tuple[int, int]:
    """extra = optional columns -> default value, appended to each tuple in order."""
    parsed = read_csv(path, (key, name_col))
    sha = file_sha256(path)
    seen: set[str] = set()
    good: list[tuple] = []
    rejects: list[tuple[int, str, str, dict]] = []
    for line, fields in parsed.rows:
        if len(fields) != len(parsed.header):
            rejects.append((line, Reason.MALFORMED_ROW,
                            f"expected {len(parsed.header)} fields, got {len(fields)}",
                            {"_raw_fields": fields}))
            continue
        raw = dict(zip(parsed.header, (x.strip() for x in fields)))
        if not raw[key] or not raw[name_col]:
            rejects.append((line, Reason.REFERENCE_MISSING_KEY, f"blank {key} or {name_col}", raw))
        elif raw[key] in seen:
            rejects.append((line, Reason.REFERENCE_DUPLICATE_KEY,
                            f"duplicate {key} {raw[key]!r} (first wins)", raw))
        else:
            seen.add(raw[key])
            good.append((raw[key], raw[name_col], *[raw.get(c) or d for c, d in extra.items()]))
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executemany(upsert_sql, good)
        record_rejects(conn, run_id, path.name, sha, rejects)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    log.info("reference %s: loaded=%d rejected=%d", path.name, len(good), len(rejects))
    return len(good), len(rejects)


def load_reference(conn: sqlite3.Connection, reference_dir: Path, run_id: str,
                   log: logging.LoggerAdapter) -> dict[str, int]:
    d = Path(reference_dir)
    p_ok, p_rej = _load(conn, d / "products.csv", "product_id", "product_name",
                        {"uom": "EA"}, _PRODUCT_UPSERT, run_id, log)
    l_ok, l_rej = _load(conn, d / "locations.csv", "location_id", "location_name",
                        {}, _LOCATION_UPSERT, run_id, log)
    return {"products_loaded": p_ok, "products_rejected": p_rej,
            "locations_loaded": l_ok, "locations_rejected": l_rej}
