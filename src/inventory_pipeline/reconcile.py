"""Reconciliation checks (run on the DB) and label verification (against generator labels)."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .config import LEG_TYPES

_COLS = {"receipt": "receipt_qty", "issue": "issue_qty", "transfer_in": "transfer_in_qty",
         "transfer_out": "transfer_out_qty", "adjustment": "adjustment_qty"}


def _scalar(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0)


def _check(name: str, expected, actual, detail: str, severity: str = "error") -> dict:
    return {"check": name, "passed": expected == actual, "expected": expected, "actual": actual,
            "severity": severity, "detail": detail}


def run_reconciliation(conn: sqlite3.Connection) -> dict:
    checks: list[dict] = []
    end = conn.execute("SELECT value FROM pipeline_state WHERE key='balance_end_date'").fetchone()
    end_date = end[0] if end else None

    # --- source -> ledger counts --------------------------------------------------------
    bad_files = _scalar(conn, "SELECT COUNT(*) FROM file_load WHERE status='SUCCESS' AND "
                              "rows_read != rows_loaded + rows_skipped_existing + rows_rejected")
    checks.append(_check("file_row_accounting", 0, bad_files,
                         "every SUCCESS file: rows_read = loaded + skipped_existing + rejected"))
    ledger = _scalar(conn, "SELECT COUNT(*) FROM inventory_movement")
    loaded = _scalar(conn, "SELECT COALESCE(SUM(rows_loaded),0) FROM file_load")
    checks.append(_check("ledger_count_equals_loaded_rows", loaded, ledger,
                         "sum(file_load.rows_loaded) == COUNT(inventory_movement)"))
    untraceable = _scalar(conn, "SELECT COUNT(*) FROM inventory_movement m WHERE m.source_file IS NULL "
                                "OR m.source_line IS NULL OR NOT EXISTS (SELECT 1 FROM pipeline_run r WHERE r.run_id=m.run_id)")
    checks.append(_check("ledger_rows_traceable", 0, untraceable, "every movement has run_id + source_file + source_line"))
    rej_untraceable = _scalar(conn, "SELECT COUNT(*) FROM reject_record r WHERE r.source_file='' OR r.source_line<1 "
                                    "OR NOT EXISTS (SELECT 1 FROM pipeline_run p WHERE p.run_id=r.run_id)")
    checks.append(_check("rejects_traceable", 0, rej_untraceable, "every reject has run_id + source_file + line + raw_record"))

    # --- referential integrity ---------------------------------------------------------------
    orphans = _scalar(conn, "SELECT COUNT(*) FROM inventory_movement m WHERE m.product_id NOT IN (SELECT product_id FROM dim_product) "
                            "OR m.location_id NOT IN (SELECT location_id FROM dim_location) "
                            "OR (m.dest_location_id IS NOT NULL AND m.dest_location_id NOT IN (SELECT location_id FROM dim_location))")
    checks.append(_check("referential_integrity_movements", 0, orphans, "movement keys exist in dimensions"))
    leg_orphans = _scalar(conn, "SELECT COUNT(*) FROM inventory_leg g WHERE g.movement_id NOT IN (SELECT movement_id FROM inventory_movement)")
    checks.append(_check("referential_integrity_legs", 0, leg_orphans, "every leg belongs to a movement"))

    # --- movement -> leg ---------------------------------------------------------------------
    transfers = _scalar(conn, "SELECT COUNT(*) FROM inventory_movement WHERE movement_type='transfer'")
    legs = _scalar(conn, "SELECT COUNT(*) FROM inventory_leg")
    checks.append(_check("leg_count", ledger + transfers, legs, "legs = movements + transfers (transfer has 2 legs)"))
    t_in = _scalar(conn, "SELECT COALESCE(SUM(signed_qty),0) FROM inventory_leg WHERE leg_type='transfer_in'")
    t_out = -_scalar(conn, "SELECT COALESCE(SUM(signed_qty),0) FROM inventory_leg WHERE leg_type='transfer_out'")
    checks.append(_check("transfer_conservation", t_out, t_in, "total transferred out == total transferred in"))

    # --- leg -> daily balance aggregates ---------------------------------------------------------
    for leg_type in LEG_TYPES:
        col = _COLS[leg_type]
        leg_sum = _scalar(conn, "SELECT COALESCE(SUM(signed_qty),0) FROM inventory_leg WHERE leg_type=?", (leg_type,))
        leg_sum = -leg_sum if leg_type in ("issue", "transfer_out") else leg_sum
        bal_sum = _scalar(conn, f"SELECT COALESCE(SUM({col}),0) FROM daily_balance")
        checks.append(_check(f"aggregate_{leg_type}", leg_sum, bal_sum, f"sum(leg {leg_type}) == sum(daily_balance.{col})"))

    # --- balance integrity -----------------------------------------------------------------------
    arith = _scalar(conn, "SELECT COUNT(*) FROM daily_balance WHERE closing_qty != opening_qty + receipt_qty - issue_qty "
                          "+ transfer_in_qty - transfer_out_qty + adjustment_qty")
    checks.append(_check("balance_arithmetic", 0, arith, "closing = opening + in - out on every row"))
    cont = _scalar(conn, "SELECT COUNT(*) FROM daily_balance b JOIN daily_balance p ON p.product_id=b.product_id "
                         "AND p.location_id=b.location_id AND p.balance_date = date(b.balance_date,'-1 day') "
                         "WHERE b.opening_qty != p.closing_qty")
    checks.append(_check("balance_continuity", 0, cont, "opening(d) == closing(d-1)"))
    first_open = _scalar(conn, "SELECT COUNT(*) FROM daily_balance b WHERE opening_qty != 0 AND NOT EXISTS ("
                               "SELECT 1 FROM daily_balance p WHERE p.product_id=b.product_id AND p.location_id=b.location_id "
                               "AND p.balance_date = date(b.balance_date,'-1 day'))")
    checks.append(_check("first_day_opening_is_zero", 0, first_open, "a pair's first row opens at 0"))
    gaps = _scalar(conn, "SELECT COUNT(*) FROM (SELECT COUNT(*) c, MIN(balance_date) mn, MAX(balance_date) mx FROM daily_balance "
                         "GROUP BY product_id, location_id) WHERE c != CAST(julianday(mx)-julianday(mn) AS INTEGER)+1 OR mx != ?",
                   (end_date,))
    checks.append(_check("balance_dense_to_end_date", 0, gaps, "no missing days; every pair reaches the global end date"))
    mismatch = _scalar(conn, "SELECT COUNT(*) FROM (SELECT b.closing_qty c, (SELECT COALESCE(SUM(signed_qty),0) FROM inventory_leg l "
                             "WHERE l.product_id=b.product_id AND l.location_id=b.location_id) s FROM daily_balance b "
                             "WHERE b.balance_date = ?) WHERE c != s", (end_date,))
    checks.append(_check("closing_equals_ledger_sum", 0, mismatch, "closing at end date == SUM(signed_qty) per pair (independent path)"))
    pairs_legs = _scalar(conn, "SELECT COUNT(*) FROM (SELECT DISTINCT product_id, location_id FROM inventory_leg)")
    pairs_bal = _scalar(conn, "SELECT COUNT(*) FROM (SELECT DISTINCT product_id, location_id FROM daily_balance)")
    checks.append(_check("pair_coverage", pairs_legs, pairs_bal, "every ledger pair has balance rows"))

    # --- warnings (anomalies, not failures) -------------------------------------------------
    neg = _scalar(conn, "SELECT COUNT(*) FROM daily_balance WHERE closing_qty < 0")
    checks.append({"check": "negative_closing_balance_rows", "passed": True, "expected": 0, "actual": neg,
                   "severity": "warning", "detail": "kept (not rejected): flags oversold / late-recorded data for review"})
    bd = _scalar(conn, "SELECT COUNT(*) FROM inventory_movement WHERE is_backdated=1")
    checks.append({"check": "backdated_movements_loaded", "passed": True, "expected": None, "actual": bd,
                   "severity": "info", "detail": "movements whose effective_date preceded the balance end date at load time"})

    errors = [c for c in checks if c["severity"] == "error"]
    return {"end_date": end_date, "all_passed": all(c["passed"] for c in errors),
            "errors_failed": sum(not c["passed"] for c in errors), "checks": checks}


def verify_against_labels(conn: sqlite3.Connection, labels_dir: Path) -> dict:
    """Compare pipeline output to the generator's independently computed labels."""
    labels_dir = Path(labels_dir)
    out: dict = {"checks": []}

    exp_rej = set()
    with open(labels_dir / "expected_rejects.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            exp_rej.add((r["source_file"], int(r["source_line"]), r["expected_reason_code"]))
    summary = json.load(open(labels_dir / "expected_summary.json"))
    files = tuple(summary["files"])
    q = ",".join("?" * len(files))
    act_rej = {(r[0], r[1], r[2]) for r in conn.execute(
        f"SELECT source_file, source_line, reason_code FROM reject_record WHERE source_file IN ({q})", files)}
    out["checks"].append({"check": "rejects_match_labels", "passed": exp_rej == act_rej,
                          "expected": len(exp_rej), "actual": len(act_rej),
                          "missing_rejects": sorted(exp_rej - act_rej)[:10],
                          "unexpected_rejects": sorted(act_rej - exp_rej)[:10]})

    exp_close = {}
    with open(labels_dir / "expected_closing.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            exp_close[(r["product_id"], r["location_id"])] = int(r["expected_closing_qty"])
    act_close = {(r[0], r[1]): r[2] for r in conn.execute(
        "SELECT product_id, location_id, closing_qty FROM daily_balance WHERE balance_date=?", (summary["end_date"],))}
    diff = {k: (exp_close.get(k), act_close.get(k)) for k in set(exp_close) | set(act_close)
            if exp_close.get(k) != act_close.get(k)}
    out["checks"].append({"check": "closing_balances_match_labels", "passed": not diff,
                          "expected": len(exp_close), "actual": len(act_close), "mismatches": dict(list(diff.items())[:10])})

    for fname, exp in summary["files"].items():
        row = conn.execute("SELECT rows_read, rows_loaded, rows_skipped_existing, rows_rejected FROM file_load "
                           "WHERE source_file=? AND status='SUCCESS' ORDER BY ended_at LIMIT 1", (fname,)).fetchone()
        act = dict(row) if row else None
        want = {k: exp[k] for k in ("rows_read", "rows_loaded", "rows_skipped_existing", "rows_rejected")}
        out["checks"].append({"check": f"file_counts_match_labels[{fname}]", "passed": act == want,
                              "expected": want, "actual": act})
    out["all_passed"] = all(c["passed"] for c in out["checks"])
    return out


def write_report(report: dict, out_dir: Path, name: str = "reconciliation_report") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [f"# Reconciliation report", "", f"- balance end date: `{report.get('end_date')}`",
             f"- overall: **{'PASS' if report['all_passed'] else 'FAIL'}**", "",
             "| check | severity | expected | actual | result |", "|---|---|---|---|---|"]
    for c in report["checks"]:
        res = "PASS" if c["passed"] else "FAIL"
        lines.append(f"| {c['check']} | {c.get('severity','error')} | {c.get('expected')} | {c.get('actual')} | {res} |")
    (out_dir / f"{name}.md").write_text("\n".join(lines) + "\n")
