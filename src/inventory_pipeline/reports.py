"""Output datasets for the analytical consumer + sample queries / reports."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

SAMPLE_QUERIES: dict[str, str] = {
    "current_inventory_snapshot": (
        "SELECT b.product_id, p.product_name, b.location_id, b.closing_qty "
        "FROM daily_balance b JOIN dim_product p USING(product_id) "
        "WHERE b.balance_date = (SELECT value FROM pipeline_state WHERE key='balance_end_date') "
        "ORDER BY b.closing_qty DESC LIMIT 10"),
    "reject_summary_by_reason": (
        "SELECT reason_code, COUNT(*) AS rejects FROM reject_record GROUP BY reason_code ORDER BY rejects DESC"),
    "run_history": (
        "SELECT run_id, status, files_total, rows_read, rows_loaded, rows_skipped_existing, rows_rejected, "
        "backdated_loaded, pairs_rebuilt, balance_rows_written FROM pipeline_run ORDER BY started_at"),
    "backdated_corrections": (
        "SELECT movement_id, movement_type, product_id, location_id, quantity, effective_date, recorded_at, source_file "
        "FROM inventory_movement WHERE is_backdated=1 ORDER BY recorded_at LIMIT 10"),
    "negative_balance_pairs": (
        "SELECT product_id, location_id, COUNT(*) AS negative_days, MIN(closing_qty) AS worst_closing "
        "FROM daily_balance WHERE closing_qty < 0 GROUP BY 1,2 ORDER BY worst_closing LIMIT 10"),
    "movement_totals_by_type": (
        "SELECT movement_type, COUNT(*) AS movements, SUM(quantity) AS total_qty FROM inventory_movement GROUP BY 1"),
}


def run_sample_queries(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    return {name: [dict(r) for r in conn.execute(sql)] for name, sql in SAMPLE_QUERIES.items()}


def format_table(rows: list[dict]) -> str:
    if not rows:
        return "(no rows)"
    cols = list(rows[0])
    widths = [max(len(str(c)), *(len(str(r[c])) for r in rows)) for c in cols]
    line = lambda vals: "  ".join(str(v).ljust(w) for v, w in zip(vals, widths))
    return "\n".join([line(cols), line(["-" * w for w in widths]), *(line([r[c] for c in cols]) for r in rows)])


def _dump(conn, sql: str, path: Path) -> int:
    cur = conn.execute(sql)
    n = 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([d[0] for d in cur.description])
        for row in cur:
            w.writerow(list(row))
            n += 1
    return n


def export_outputs(conn: sqlite3.Connection, out_dir: Path) -> dict[str, int]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "daily_balance.csv": _dump(conn, "SELECT * FROM daily_balance ORDER BY product_id, location_id, balance_date",
                                   out_dir / "daily_balance.csv"),
        "inventory_snapshot.csv": _dump(conn,
            "SELECT product_id, location_id, closing_qty FROM daily_balance WHERE balance_date="
            "(SELECT value FROM pipeline_state WHERE key='balance_end_date') ORDER BY 1,2",
            out_dir / "inventory_snapshot.csv"),
        "rejects.csv": _dump(conn, "SELECT * FROM reject_record ORDER BY source_file, source_line",
                             out_dir / "rejects.csv"),
        "run_history.csv": _dump(conn, "SELECT * FROM pipeline_run ORDER BY started_at", out_dir / "run_history.csv"),
    }
