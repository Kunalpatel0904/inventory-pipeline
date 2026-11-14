"""Command line interface: generate | run | reconcile | verify | report | benchmark."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import config as C
from .db import connect, init_schema
from .generator import generate_dataset
from .ingest import run_pipeline
from .reconcile import run_reconciliation, verify_against_labels, write_report
from .reports import export_outputs, format_table, run_sample_queries

EXIT = {C.RUN_SUCCESS: 0, C.RUN_NOOP: 0, C.RUN_PARTIAL: 2, C.RUN_FAILED: 1}


class _RunIdDefault(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = "-"
        return True


def setup_logging(log_file: Path | None) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s run_id=%(run_id)s %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    root = logging.getLogger("inventory_pipeline")
    root.handlers.clear()
    root.setLevel(logging.INFO)
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(_RunIdDefault())
        root.addHandler(h)


def _cmd_generate(a) -> int:
    s = generate_dataset(a.out, seed=a.seed, records=a.records, products=a.products, locations=a.locations,
                         start_date=a.start_date, days=a.days, late_fraction=a.late_fraction,
                         dup_rate=a.dup_rate, conflict_rate=a.conflict_rate, invalid_rate=a.invalid_rate)
    print(json.dumps(s, indent=2))
    return 0


def _cmd_run(a) -> int:
    out = Path(a.output_dir)
    setup_logging(out / "pipeline.log")
    res = run_pipeline(a.db, a.input, reference_dir=a.reference, force=a.force, strategy=a.strategy)
    summ = out / "run_summaries"
    summ.mkdir(parents=True, exist_ok=True)
    (summ / f"{res.run_id}.json").write_text(json.dumps(res.to_dict(), indent=2))
    conn = connect(a.db)
    export_outputs(conn, out)
    conn.close()
    print(json.dumps({"run_id": res.run_id, "status": res.status, "totals": res.totals(),
                      "files": [{"file": f.source_file, "status": f.status, "read": f.rows_read, "loaded": f.rows_loaded,
                                 "skipped_existing": f.rows_skipped_existing, "rejected": f.rows_rejected,
                                 "error": f.error} for f in res.files], "error": res.error}, indent=2))
    return EXIT[res.status]


def _cmd_reconcile(a) -> int:
    conn = connect(a.db)
    init_schema(conn)
    rep = run_reconciliation(conn)
    write_report(rep, Path(a.output_dir))
    for c in rep["checks"]:
        print(f"{'PASS' if c['passed'] else 'FAIL'}  [{c['severity']}] {c['check']}: expected={c.get('expected')} actual={c.get('actual')}")
    print("OVERALL:", "PASS" if rep["all_passed"] else "FAIL")
    return 0 if rep["all_passed"] else 1


def _cmd_verify(a) -> int:
    conn = connect(a.db)
    rep = verify_against_labels(conn, Path(a.labels))
    write_report({"end_date": None, "all_passed": rep["all_passed"],
                  "checks": [{**c, "severity": "error"} for c in rep["checks"]]}, Path(a.output_dir), "label_verification")
    for c in rep["checks"]:
        print(f"{'PASS' if c['passed'] else 'FAIL'}  {c['check']}: expected={c.get('expected')} actual={c.get('actual')}")
    print("OVERALL:", "PASS" if rep["all_passed"] else "FAIL")
    return 0 if rep["all_passed"] else 1


def _cmd_report(a) -> int:
    conn = connect(a.db)
    for name, rows in run_sample_queries(conn).items():
        print(f"\n== {name} ==\n{format_table(rows)}")
    return 0


def _cmd_benchmark(a) -> int:
    from .benchmark import run_benchmark
    setup_logging(None)
    logging.getLogger("inventory_pipeline").setLevel(logging.WARNING)
    print(json.dumps(run_benchmark(a.records, a.seed, Path(a.output_dir)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="inventory-pipeline", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate reproducible synthetic data + labels")
    g.add_argument("--out", default="data/sample")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--records", type=int, default=1000, help="clean events (before injected duplicates/invalids)")
    g.add_argument("--products", type=int, default=10)
    g.add_argument("--locations", type=int, default=4)
    g.add_argument("--start-date", default="2026-01-01")
    g.add_argument("--days", type=int, default=30)
    g.add_argument("--late-fraction", type=float, default=0.05)
    g.add_argument("--dup-rate", type=float, default=0.01)
    g.add_argument("--conflict-rate", type=float, default=0.003)
    g.add_argument("--invalid-rate", type=float, default=0.02)
    g.set_defaults(fn=_cmd_generate)

    r = sub.add_parser("run", help="ingest files -> ledger -> daily balances (safe to re-run)")
    r.add_argument("--db", default="output/inventory.db")
    r.add_argument("--reference", help="dir with products.csv + locations.csv (optional if already loaded)")
    r.add_argument("--input", nargs="+", required=True, help="CSV files and/or directories")
    r.add_argument("--output-dir", default="output")
    r.add_argument("--force", action="store_true", help="re-process files even if identical content was loaded")
    r.add_argument("--strategy", choices=["grouped", "naive"], default="naive")
    r.set_defaults(fn=_cmd_run)

    for name, fn, h in (("reconcile", _cmd_reconcile, "run reconciliation checks"),
                        ("report", _cmd_report, "print sample analytical queries")):
        s = sub.add_parser(name, help=h)
        s.add_argument("--db", default="output/inventory.db")
        s.add_argument("--output-dir", default="output")
        s.set_defaults(fn=fn)

    v = sub.add_parser("verify", help="compare output with generator labels")
    v.add_argument("--db", default="output/inventory.db")
    v.add_argument("--labels", default="data/sample/labels")
    v.add_argument("--output-dir", default="output")
    v.set_defaults(fn=_cmd_verify)

    b = sub.add_parser("benchmark", help="generate N records and time each pipeline stage")
    b.add_argument("--records", type=int, default=100_000)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--output-dir", default="output")
    b.set_defaults(fn=_cmd_benchmark)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)
