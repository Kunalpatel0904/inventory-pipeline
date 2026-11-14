"""Daily balance (re)build, incremental and backdating-aware.

daily_balance is a *derived* table: for each (product, location) pair it holds one
row per calendar day from the pair's first movement to the global end date, with
closing = opening + receipts - issues + transfer_in - transfer_out + adjustments.

A new (or backdated) movement only dirties its pair from its effective_date
forward, so we delete and regenerate exactly that tail. Pairs that are untouched
but fall behind a newly extended end date get their tail extended (carry-forward).
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

Pair = tuple[str, str]


def _next_day(iso: str) -> str:
    return (date.fromisoformat(iso) + timedelta(days=1)).isoformat()


def _inputs_naive(conn, starts: dict[Pair, str]):
    """One opening-balance query and one aggregate query PER PAIR."""
    openings: dict[Pair, int] = {}
    agg: dict[Pair, dict[str, dict[str, int]]] = {}
    for (p, l), d in starts.items():
        row = conn.execute(
            "SELECT closing_qty FROM daily_balance WHERE product_id=? AND location_id=? "
            "AND balance_date = date(?, '-1 day')", (p, l, d)).fetchone()
        openings[(p, l)] = row[0] if row else 0
        per_day = agg.setdefault((p, l), {})
        for eff, leg_type, qty in conn.execute(
                "SELECT effective_date, leg_type, SUM(signed_qty) FROM inventory_leg "
                "WHERE product_id=? AND location_id=? AND effective_date >= ? "
                "GROUP BY effective_date, leg_type", (p, l, d)):
            per_day.setdefault(eff, {})[leg_type] = qty
    return openings, agg


def _inputs_grouped(conn, starts: dict[Pair, str]):
    """Set-based: affected pairs go into a temp table and are joined once."""
    conn.execute("DROP TABLE IF EXISTS temp.tmp_affected")
    conn.execute("CREATE TEMP TABLE tmp_affected(product_id TEXT, location_id TEXT, "
                 "from_date TEXT, PRIMARY KEY(product_id, location_id)) WITHOUT ROWID")
    conn.executemany("INSERT INTO tmp_affected VALUES (?,?,?)",
                     [(p, l, d) for (p, l), d in starts.items()])
    openings = {(p, l): 0 for (p, l) in starts}
    for p, l, closing in conn.execute(
            "SELECT a.product_id, a.location_id, b.closing_qty FROM tmp_affected a "
            "JOIN daily_balance b ON b.product_id=a.product_id AND b.location_id=a.location_id "
            "AND b.balance_date = date(a.from_date, '-1 day')"):
        openings[(p, l)] = closing
    agg: dict[Pair, dict[str, dict[str, int]]] = {}
    for p, l, eff, leg_type, qty in conn.execute(
            "SELECT g.product_id, g.location_id, g.effective_date, g.leg_type, SUM(g.signed_qty) "
            "FROM inventory_leg g JOIN tmp_affected a ON a.product_id=g.product_id "
            "AND a.location_id=g.location_id AND g.effective_date >= a.from_date "
            "GROUP BY g.product_id, g.location_id, g.effective_date, g.leg_type"):
        agg.setdefault((p, l), {}).setdefault(eff, {})[leg_type] = qty
    return openings, agg


def rebuild_balances(conn: sqlite3.Connection, affected: dict[Pair, str], old_end: str | None,
                     new_end: str, run_id: str, strategy: str = "naive") -> tuple[int, int]:
    """Regenerate dirty tails. Must be called inside the caller's transaction.
    Returns (pairs_rebuilt, balance_rows_written)."""
    starts = dict(affected)

    # Carry-forward: end date moved later -> every pair must reach the new end date.
    if old_end is not None and new_end > old_end:
        for p, l, last in conn.execute(
                "SELECT product_id, location_id, MAX(balance_date) FROM daily_balance "
                "GROUP BY product_id, location_id").fetchall():
            if last < new_end:
                ext = _next_day(last)
                starts[(p, l)] = min(starts.get((p, l), ext), ext)

    if not starts:
        return 0, 0

    inputs = {"naive": _inputs_naive, "grouped": _inputs_grouped}
    if strategy not in inputs:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {sorted(inputs)}")
    openings, agg = inputs[strategy](conn, starts)

    # Drop the dirty tails (explicit per-pair delete keeps both strategies identical).
    conn.executemany(
        "DELETE FROM daily_balance WHERE product_id=? AND location_id=? AND balance_date >= ?",
        [(p, l, d) for (p, l), d in starts.items()])

    end = date.fromisoformat(new_end)
    rows: list[tuple] = []
    for (p, l), d in starts.items():
        opening = openings[(p, l)]
        per_day = agg.get((p, l), {})
        cur = date.fromisoformat(d)
        while cur <= end:
            iso = cur.isoformat()
            day = per_day.get(iso, {})
            receipt = day.get("receipt", 0)
            issue = -day.get("issue", 0)
            t_in = day.get("transfer_in", 0)
            t_out = -day.get("transfer_out", 0)
            adj = day.get("adjustment", 0)
            closing = opening + receipt - issue + t_in - t_out + adj
            rows.append((p, l, iso, opening, receipt, issue, t_in, t_out, adj, closing, run_id))
            opening = closing
            cur += timedelta(days=1)
    conn.executemany("INSERT INTO daily_balance VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute("DROP TABLE IF EXISTS temp.tmp_affected")
    return len(starts), len(rows)
