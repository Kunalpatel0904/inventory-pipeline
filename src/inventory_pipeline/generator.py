"""Deterministic synthetic data generator (fixed seed => byte-identical output).

Writes INPUT files and, separately, LABEL files. Labels are computed independently of
the pipeline (own running-stock simulation + known injected defects), so they can be
used to verify pipeline output without sharing any code path with it.

    <out>/reference/{products,locations}.csv
    <out>/incoming/movements_batch_001.csv           main batch (out-of-order, dupes, invalid rows)
    <out>/incoming/movements_batch_002_late.csv      late-arriving backdated corrections + replays
    <out>/negative_cases/{empty_batch,schema_drift}.csv   (not auto-loaded; used for demos/tests)
    <out>/labels/{expected_rejects.csv,expected_closing.csv,expected_summary.json}
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import MAX_QTY, REQUIRED_COLUMNS

MAIN_FILE = "movements_batch_001.csv"
LATE_FILE = "movements_batch_002_late.csv"
COL = {c: i for i, c in enumerate(REQUIRED_COLUMNS)}
INVALID_KINDS = [
    "missing_quantity", "missing_id", "nonnumeric_qty", "negative_receipt", "zero_adjustment",
    "unknown_product", "unknown_location", "same_location_transfer", "bad_date", "bad_type",
    "transfer_missing_dest", "future_date", "bad_timestamp", "ragged",
]


def _row(mid, mtype, product, loc, dest, qty, eff: date, rec: datetime) -> list[str]:
    return [mid, mtype, product, loc, dest, str(qty), eff.isoformat(), rec.strftime("%Y-%m-%dT%H:%M:%SZ")]


def _bad_row(kind: str, base: list[str], n: int) -> tuple[list[str], str]:
    r = list(base)
    r[COL["movement_id"]] = f"BAD{n:07d}"
    if kind == "missing_quantity":
        r[COL["quantity"]] = ""; return r, "MISSING_REQUIRED_FIELD"
    if kind == "missing_id":
        r[COL["movement_id"]] = ""; return r, "MISSING_REQUIRED_FIELD"
    if kind == "nonnumeric_qty":
        r[COL["quantity"]] = "ten"; return r, "INVALID_QUANTITY"
    if kind == "negative_receipt":
        r[COL["movement_type"]], r[COL["dest_location_id"]], r[COL["quantity"]] = "receipt", "", "-5"
        return r, "QUANTITY_OUT_OF_RANGE"
    if kind == "zero_adjustment":
        r[COL["movement_type"]], r[COL["dest_location_id"]], r[COL["quantity"]] = "adjustment", "", "0"
        return r, "QUANTITY_OUT_OF_RANGE"
    if kind == "unknown_product":
        r[COL["product_id"]] = "P9999"; return r, "UNKNOWN_PRODUCT"
    if kind == "unknown_location":
        r[COL["location_id"]] = "L99"; return r, "UNKNOWN_LOCATION"
    if kind == "same_location_transfer":
        r[COL["movement_type"]], r[COL["dest_location_id"]], r[COL["quantity"]] = "transfer", r[COL["location_id"]], "5"
        return r, "SAME_LOCATION_TRANSFER"
    if kind == "bad_date":
        r[COL["effective_date"]] = "2026-13-45"; return r, "INVALID_DATE"
    if kind == "bad_type":
        r[COL["movement_type"]] = "return"; return r, "INVALID_MOVEMENT_TYPE"
    if kind == "transfer_missing_dest":
        r[COL["movement_type"]], r[COL["dest_location_id"]], r[COL["quantity"]] = "transfer", "", "5"
        return r, "MISSING_REQUIRED_FIELD"
    if kind == "future_date":
        rec_day = date.fromisoformat(r[COL["recorded_at"]][:10])
        r[COL["effective_date"]] = (rec_day + timedelta(days=5)).isoformat(); return r, "FUTURE_EFFECTIVE_DATE"
    if kind == "bad_timestamp":
        r[COL["recorded_at"]] = "not-a-timestamp"; return r, "INVALID_TIMESTAMP"
    if kind == "ragged":
        return r + ["unexpected_extra"], "MALFORMED_ROW"
    raise ValueError(kind)


def _conflict_copy(row: list[str]) -> list[str]:
    r = list(row)
    q = int(r[COL["quantity"]])
    cand = q + 1
    if cand == 0 or abs(cand) > MAX_QTY:
        cand = q - 1
    r[COL["quantity"]] = str(cand)
    return r


def _emit(events: list[list[str]], rng: random.Random, *, dup_rate: float, conflict_rate: float,
          invalid_rate: float, bad_start: int, replays: list[tuple[list[str], str | None]] | None = None):
    """Interleave defects around clean events. Returns (rows, labels, counts, next_bad_idx).
    Duplicates are always emitted AFTER their original; labels are (line_no, reason)."""
    n = len(events)
    pending: dict[int, list[tuple[list[str], str | None]]] = defaultdict(list)
    counts = defaultdict(int)
    bad = bad_start
    for i, ev in enumerate(events):
        if rng.random() < dup_rate:
            pending[min(n - 1, i + rng.randint(1, 50))].append((list(ev), "DUPLICATE_EVENT")); counts["dup"] += 1
        if rng.random() < conflict_rate:
            pending[min(n - 1, i + rng.randint(1, 50))].append((_conflict_copy(ev), "DUPLICATE_CONFLICT")); counts["conflict"] += 1
        if rng.random() < invalid_rate:
            row, reason = _bad_row(rng.choice(INVALID_KINDS), rng.choice(events), bad); bad += 1
            pending[rng.randrange(n)].append((row, reason)); counts["invalid"] += 1
    for row, label in (replays or []):
        pending[rng.randrange(n)].append((row, label))
        counts["replay_identical" if label is None else "replay_conflict"] += 1
    rows, labels = [], []
    for i, ev in enumerate(events):
        rows.append(ev)
        for row, label in pending.get(i, []):
            rows.append(row)
            if label:
                labels.append((len(rows) + 1, label))      # +1 for header line
    return rows, labels, counts, bad


def generate_dataset(out_dir: str | Path, *, seed: int = 42, records: int = 1000, products: int = 10,
                     locations: int = 4, start_date: str = "2026-01-01", days: int = 30,
                     late_fraction: float = 0.05, dup_rate: float = 0.01, conflict_rate: float = 0.003,
                     invalid_rate: float = 0.02) -> dict:
    rng = random.Random(seed)
    out = Path(out_dir)
    for sub in ("reference", "incoming", "negative_cases", "labels"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    pids = [f"P{i:04d}" for i in range(1, products + 1)]
    lids = [f"L{i:02d}" for i in range(1, locations + 1)]
    start = date.fromisoformat(start_date)
    last_day = start + timedelta(days=days - 1)

    _write(out / "reference/products.csv", ["product_id", "product_name", "uom"],
           [[p, f"Product {p}", "EA"] for p in pids])
    _write(out / "reference/locations.csv", ["location_id", "location_name"],
           [[l, f"Warehouse {l}"] for l in lids])

    n_late = int(records * late_fraction)
    n_main = records - n_late
    stock: dict[tuple[str, str], int] = defaultdict(int)
    touched: set[tuple[str, str]] = set()
    main: list[tuple[datetime, int, list[str]]] = []
    seq = 0
    for i in range(n_main):
        day = start + timedelta(days=i * days // n_main)
        rec = datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randint(6 * 3600, 20 * 3600))
        p, l = rng.choice(pids), rng.choice(lids)
        mtype = rng.choices(["receipt", "issue", "transfer", "adjustment"], [35, 40, 15, 10])[0]
        dest, qty = "", rng.randint(10, 500)
        if i == 0:                               # boundary values: minimum and maximum quantity
            mtype, p, l, qty = "receipt", pids[0], lids[0], 1
        elif i == 1:
            mtype, p, l, qty = "receipt", pids[0], lids[0], MAX_QTY
        elif mtype == "issue" and stock[(p, l)] < qty:
            mtype = "receipt"
        elif mtype == "transfer":
            dest = rng.choice([x for x in lids if x != l])
            if stock[(p, l)] < qty:
                mtype, dest = "receipt", ""
        elif mtype == "adjustment":
            qty = rng.choice([-1, 1]) * rng.randint(1, 20)
            if qty < 0 and stock[(p, l)] < -qty:
                qty = -qty
        if mtype == "receipt":
            stock[(p, l)] += qty
        elif mtype == "issue":
            stock[(p, l)] -= qty
        elif mtype == "transfer":
            stock[(p, l)] -= qty; stock[(p, dest)] += qty; touched.add((p, dest))
        else:
            stock[(p, l)] += qty
        touched.add((p, l))
        main.append((rec, seq, _row(f"MV{seq:08d}", mtype, p, l, dest, qty, day, rec))); seq += 1
    main.sort(key=lambda t: (t[0], t[1]))
    main_rows = [t[2] for t in main]
    for i in range(len(main_rows) - 1):                      # local out-of-order delivery
        if rng.random() < 0.05:
            main_rows[i], main_rows[i + 1] = main_rows[i + 1], main_rows[i]

    late_rows: list[list[str]] = []
    for _ in range(n_late):
        eff = start + timedelta(days=rng.randrange(0, max(days - 1, 1)))
        rec = datetime(last_day.year, last_day.month, last_day.day) + timedelta(
            days=1, seconds=rng.randint(6 * 3600, 20 * 3600))
        p, l = rng.choice(pids), rng.choice(lids)
        if rng.random() < 0.65:
            mtype, qty = "receipt", rng.randint(5, 200); stock[(p, l)] += qty
        else:
            mtype, qty = "adjustment", rng.choice([-1, 1]) * rng.randint(1, 30); stock[(p, l)] += qty
        touched.add((p, l))
        late_rows.append(_row(f"MV{seq:08d}", mtype, p, l, "", qty, eff, rec)); seq += 1

    m_rows, m_labels, m_counts, nxt = _emit(main_rows, rng, dup_rate=dup_rate, conflict_rate=conflict_rate,
                                            invalid_rate=invalid_rate, bad_start=1)
    replays: list[tuple[list[str], str | None]] = []
    if main_rows and late_rows:
        k = max(1, int(len(main_rows) * 0.002))
        # ONE sample split in two: an event must never be both replayed identically and replayed
        # with changed content in the same file (the first copy would win in-file and flip the other's outcome).
        picked = rng.sample(main_rows, min(2 * k, len(main_rows)))
        half = max(1, len(picked) // 2) if len(picked) > 1 else len(picked)
        for r in picked[:half]:
            replays.append((list(r), None))                    # identical replay -> skipped_existing
        for r in picked[half:]:
            replays.append((_conflict_copy(r), "DUPLICATE_CONFLICT"))   # conflicts with ledger
    l_rows, l_labels, l_counts, _ = (_emit(late_rows, rng, dup_rate=dup_rate, conflict_rate=conflict_rate,
                                           invalid_rate=invalid_rate, bad_start=nxt, replays=replays)
                                     if late_rows else ([], [], defaultdict(int), nxt))
    _write(out / "incoming" / MAIN_FILE, list(REQUIRED_COLUMNS), m_rows)
    if late_rows:
        _write(out / "incoming" / LATE_FILE, list(REQUIRED_COLUMNS), l_rows)

    # negative cases (kept outside incoming/ so a normal run does not trip over them)
    _write(out / "negative_cases/empty_batch.csv", list(REQUIRED_COLUMNS), [])
    drift_header = [c if c != "quantity" else "qty" for c in REQUIRED_COLUMNS] + ["notes"]
    _write(out / "negative_cases/schema_drift.csv", drift_header,
           [[f"DRIFT{0:03d}", "receipt", pids[0], lids[0], "", "10", start_date, f"{start_date}T09:00:00Z", "renamed column"]])

    # labels
    with open(out / "labels/expected_rejects.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["source_file", "source_line", "expected_reason_code"])
        for line, code in m_labels:
            w.writerow([MAIN_FILE, line, code])
        for line, code in l_labels:
            w.writerow([LATE_FILE, line, code])
    _write(out / "labels/expected_closing.csv", ["product_id", "location_id", "expected_closing_qty"],
           [[p, l, stock[(p, l)]] for p, l in sorted(touched)])
    files = {MAIN_FILE: {"rows_read": len(m_rows), "rows_loaded": len(main_rows),
                         "rows_skipped_existing": 0, "rows_rejected": len(m_labels)}}
    if late_rows:
        files[LATE_FILE] = {"rows_read": len(l_rows), "rows_loaded": len(late_rows),
                            "rows_skipped_existing": l_counts["replay_identical"], "rows_rejected": len(l_labels)}
    summary = {"seed": seed, "end_date": last_day.isoformat(), "clean_events": len(main_rows) + len(late_rows),
               "files": files, "injected": {MAIN_FILE: dict(m_counts), LATE_FILE: dict(l_counts)}}
    (out / "labels/expected_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
