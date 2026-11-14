"""Simple performance measurement: per-stage timings for the two balance strategies."""
from __future__ import annotations

import json
import platform
import sqlite3
import tempfile
import time
from pathlib import Path

from .balances import rebuild_balances
from .db import connect, get_state
from .generator import generate_dataset
from .ingest import run_pipeline


def run_benchmark(records: int, seed: int, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {"records_requested": records, "seed": seed, "python": platform.python_version(),
                    "sqlite": sqlite3.sqlite_version, "strategies": {}}
    with tempfile.TemporaryDirectory() as tmp:
        t = time.perf_counter()
        # larger dimension space so pairs-per-day is realistic: 200 products x 25 locations, 90 days
        summary = generate_dataset(tmp, seed=seed, records=records, products=200, locations=25, days=90)
        result["generate_seconds"] = round(time.perf_counter() - t, 2)
        result["rows_in_files"] = {k: v["rows_read"] for k, v in summary["files"].items()}
        for strategy in ("naive", "grouped"):
            db = Path(tmp) / f"bench_{strategy}.db"
            t = time.perf_counter()
            res = run_pipeline(db, [Path(tmp) / "incoming"], reference_dir=Path(tmp) / "reference", strategy=strategy)
            total = time.perf_counter() - t
            files = {}
            for f in res.files:
                files[f.source_file] = {**{k: round(v, 3) for k, v in f.timings_s.items()},
                                        "rows_read": f.rows_read, "rows_loaded": f.rows_loaded,
                                        "pairs_rebuilt": f.pairs_rebuilt, "balance_rows_written": f.balance_rows_written,
                                        "rows_per_second_total": round(f.rows_read / max(sum(f.timings_s.values()), 1e-9))}
            result["strategies"][strategy] = {"status": res.status, "total_seconds": round(total, 2), "files": files}

        # Optimization evidence: tail-only (incremental) rebuild vs recomputing every pair from day 1.
        # Run inside a transaction that is rolled back, so the DB is left untouched.
        conn = connect(Path(tmp) / "bench_grouped.db")
        end = get_state(conn, "balance_end_date")
        starts = {(p, l): d for p, l, d in conn.execute(
            "SELECT product_id, location_id, MIN(effective_date) FROM inventory_leg GROUP BY 1,2")}
        conn.execute("BEGIN")
        t = time.perf_counter()
        pairs, rows = rebuild_balances(conn, starts, end, end, "bench_full", "grouped")
        full_s = time.perf_counter() - t
        conn.execute("ROLLBACK")
        conn.close()
        late = result["strategies"]["grouped"]["files"].get("movements_batch_002_late.csv", {})
        inc_s = late.get("rebuild_balances")
        result["tail_only_vs_full_rebuild"] = {
            "late_batch_incremental": {"seconds": inc_s, "pairs": late.get("pairs_rebuilt"),
                                        "balance_rows_written": late.get("balance_rows_written")},
            "full_recompute_all_pairs": {"seconds": round(full_s, 3), "pairs": pairs, "balance_rows_written": rows},
            "speedup_x": round(full_s / inc_s, 2) if inc_s else None}
    (out_dir / "benchmark.json").write_text(json.dumps(result, indent=2))
    return result
