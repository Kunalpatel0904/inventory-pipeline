"""Ingestion engine: validate -> quarantine -> load ledger -> rebuild balances.

Atomic unit = one input file. Ledger inserts, legs, rejects, balance rebuild and the
file_load audit row commit together or not at all. A failure rolls the file back,
records FAILED_* for it, and the run continues with the next file.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from .balances import rebuild_balances
from .csvio import SchemaError, file_sha256, read_csv
from .db import connect, get_state, init_schema, set_state
from .reference import load_reference
from .store import record_rejects, utc_now
from .validate import Movement, Rejection, to_legs, validate_row

log = logging.getLogger("inventory_pipeline")
_CHUNK = 500


@dataclass
class FileResult:
    source_file: str
    file_sha256: str = ""
    status: str = C.FILE_FAILED_PROCESSING
    rows_read: int = 0
    rows_loaded: int = 0
    rows_skipped_existing: int = 0
    rows_rejected: int = 0
    backdated_loaded: int = 0
    pairs_rebuilt: int = 0
    balance_rows_written: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    timings_s: dict[str, float] = field(default_factory=dict)


@dataclass
class RunResult:
    run_id: str
    status: str
    started_at: str
    ended_at: str
    reference: dict[str, int] = field(default_factory=dict)
    files: list[FileResult] = field(default_factory=list)
    error: str | None = None

    def totals(self) -> dict[str, int]:
        keys = ("rows_read", "rows_loaded", "rows_skipped_existing", "rows_rejected",
                "backdated_loaded", "pairs_rebuilt", "balance_rows_written")
        return {k: sum(getattr(f, k) for f in self.files) for k in keys}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["totals"] = self.totals()
        return d


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]


def _record_file(conn, run_id: str, r: FileResult, started: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO file_load(run_id, source_file, file_sha256, status, rows_read, "
        "rows_loaded, rows_skipped_existing, rows_rejected, backdated_loaded, pairs_rebuilt, "
        "balance_rows_written, error, started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, r.source_file, r.file_sha256, r.status, r.rows_read, r.rows_loaded,
         r.rows_skipped_existing, r.rows_rejected, r.backdated_loaded, r.pairs_rebuilt,
         r.balance_rows_written, r.error, started, utc_now()))


def _existing_hashes(conn, ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        q = ",".join("?" * len(chunk))
        for mid, h in conn.execute(
                f"SELECT movement_id, content_hash FROM inventory_movement WHERE movement_id IN ({q})", chunk):
            out[mid] = h
    return out


def process_file(conn, path: Path, run_id: str, products: set[str], locations: set[str],
                 lg: logging.LoggerAdapter, *, force: bool = False,
                 strategy: str = "naive") -> FileResult:
    started = utc_now()
    res = FileResult(source_file=path.name)
    t0 = time.perf_counter()

    # ---- 1. read + schema check (no DB writes yet) --------------------------------
    try:
        res.file_sha256 = file_sha256(path)
        if not force and conn.execute(
                "SELECT 1 FROM file_load WHERE file_sha256=? AND status IN (?,?) LIMIT 1",
                (res.file_sha256, C.FILE_SUCCESS, C.FILE_EMPTY)).fetchone():
            res.status = C.FILE_SKIPPED
            lg.info("file=%s skipped: identical content (sha256 %s...) already loaded",
                    path.name, res.file_sha256[:12])
            _record_file(conn, run_id, res, started)
            return res
        parsed = read_csv(path, C.REQUIRED_COLUMNS)
    except Exception as exc:  # noqa: BLE001 - any read failure is a file-level failure
        res.status = C.FILE_FAILED_SCHEMA if isinstance(exc, SchemaError) else C.FILE_FAILED_READ
        res.error = f"{type(exc).__name__}: {exc}"
        lg.error("file=%s %s: %s", path.name, res.status, res.error)
        _record_file(conn, run_id, res, started)
        return res
    if parsed.extra_columns:
        res.warnings.append(f"unexpected extra columns ignored: {parsed.extra_columns}")
        lg.warning("file=%s schema drift (tolerated): extra columns %s", path.name, parsed.extra_columns)
    if parsed.blank_lines_skipped:
        res.warnings.append(f"{parsed.blank_lines_skipped} blank line(s) skipped")

    # ---- 2. row validation + in-file de-duplication --------------------------------
    n_cols = len(parsed.header)
    accepted: list[tuple[Movement, dict]] = []
    rejects: list[tuple[int, str, str, dict]] = []
    seen: dict[str, str] = {}
    for line, fields in parsed.rows:
        if len(fields) != n_cols:
            rejects.append((line, C.Reason.MALFORMED_ROW,
                            f"expected {n_cols} fields, got {len(fields)}", {"_raw_fields": fields}))
            continue
        raw = dict(zip(parsed.header, fields))
        out = validate_row(raw, line, products, locations)
        if isinstance(out, Rejection):
            rejects.append((line, out.code, out.detail, raw))
            continue
        prev = seen.get(out.movement_id)
        if prev is None:
            seen[out.movement_id] = out.content_hash
            accepted.append((out, raw))
        elif prev == out.content_hash:
            rejects.append((line, C.Reason.DUPLICATE_EVENT, "identical event already seen earlier in this file", raw))
        else:
            rejects.append((line, C.Reason.DUPLICATE_CONFLICT,
                            "same movement_id with different content earlier in this file (first wins)", raw))
    res.rows_read = len(parsed.rows)
    res.timings_s["read_validate"] = time.perf_counter() - t0

    if res.rows_read == 0:
        res.status = C.FILE_EMPTY
        lg.info("file=%s empty batch (header only): nothing to do", path.name)
        _record_file(conn, run_id, res, started)
        return res

    # ---- 3. atomic load ------------------------------------------------------------
    try:
        conn.execute("BEGIN IMMEDIATE")
        t1 = time.perf_counter()
        existing = _existing_hashes(conn, [m.movement_id for m, _ in accepted])
        to_insert: list[Movement] = []
        skipped = 0
        for m, raw in accepted:
            h = existing.get(m.movement_id)
            if h is None:
                to_insert.append(m)
            elif h == m.content_hash:
                skipped += 1                                  # idempotent replay
            else:
                rejects.append((m.source_line, C.Reason.DUPLICATE_CONFLICT,
                                "movement_id already in ledger with different content", raw))

        old_end = get_state(conn, "balance_end_date")
        now = utc_now()
        backdated = 0
        mrows, lrows = [], []
        affected: dict[tuple[str, str], str] = {}
        max_eff = old_end or ""
        for m in to_insert:
            is_bd = 1 if (old_end is not None and m.effective_date < old_end) else 0
            backdated += is_bd
            mrows.append((m.movement_id, m.movement_type, m.product_id, m.location_id, m.dest_location_id,
                          m.quantity, m.effective_date, m.recorded_at, m.content_hash, is_bd,
                          run_id, path.name, m.source_line, now))
            for leg_no, p, l, leg_type, q in to_legs(m):
                lrows.append((m.movement_id, leg_no, p, l, m.effective_date, leg_type, q))
                key = (p, l)
                if key not in affected or m.effective_date < affected[key]:
                    affected[key] = m.effective_date
            max_eff = max(max_eff, m.effective_date)
        conn.executemany("INSERT INTO inventory_movement VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", mrows)
        conn.executemany("INSERT INTO inventory_leg VALUES (?,?,?,?,?,?,?)", lrows)
        record_rejects(conn, run_id, path.name, res.file_sha256, rejects)
        res.timings_s["load"] = time.perf_counter() - t1

        t2 = time.perf_counter()
        if to_insert:
            res.pairs_rebuilt, res.balance_rows_written = rebuild_balances(
                conn, affected, old_end, max_eff, run_id, strategy)
            set_state(conn, "balance_end_date", max_eff)
        res.timings_s["rebuild_balances"] = time.perf_counter() - t2

        res.rows_loaded = len(to_insert)
        res.rows_skipped_existing = skipped
        res.rows_rejected = len(rejects)
        res.backdated_loaded = backdated
        res.status = C.FILE_SUCCESS
        res.error = None
        assert res.rows_read == res.rows_loaded + res.rows_skipped_existing + res.rows_rejected, \
            "row accounting mismatch"
        _record_file(conn, run_id, res, started)
        conn.execute("COMMIT")
    except Exception as exc:  # noqa: BLE001
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        res = FileResult(source_file=path.name, file_sha256=res.file_sha256,
                         status=C.FILE_FAILED_PROCESSING, rows_read=res.rows_read,
                         error=f"{type(exc).__name__}: {exc}", warnings=res.warnings)
        lg.error("file=%s FAILED_PROCESSING, transaction rolled back: %s", path.name, res.error)
        _record_file(conn, run_id, res, started)
        return res

    lg.info("file=%s status=%s read=%d loaded=%d skipped_existing=%d rejected=%d backdated=%d "
            "pairs_rebuilt=%d balance_rows=%d", path.name, res.status, res.rows_read, res.rows_loaded,
            res.rows_skipped_existing, res.rows_rejected, res.backdated_loaded, res.pairs_rebuilt,
            res.balance_rows_written)
    return res


def expand_inputs(paths: list[str | Path]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files.extend(sorted(p.glob("*.csv")) if p.is_dir() else [p])
    return files


def run_pipeline(db_path: str | Path, input_paths: list[str | Path], *,
                 reference_dir: str | Path | None = None, run_id: str | None = None,
                 force: bool = False, strategy: str = "naive") -> RunResult:
    run_id = run_id or new_run_id()
    lg = logging.LoggerAdapter(log, {"run_id": run_id})
    conn = connect(db_path)
    init_schema(conn)
    started = utc_now()
    params = {"input_paths": [str(p) for p in input_paths],
              "reference_dir": str(reference_dir) if reference_dir else None,
              "force": force, "strategy": strategy}
    conn.execute("INSERT INTO pipeline_run(run_id, started_at, status, params_json) VALUES (?,?,?,?)",
                 (run_id, started, "RUNNING", json.dumps(params)))
    result = RunResult(run_id=run_id, status=C.RUN_FAILED, started_at=started, ended_at=started)
    lg.info("run started params=%s", params)
    try:
        if reference_dir:
            result.reference = load_reference(conn, Path(reference_dir), run_id, lg)
        products = {r[0] for r in conn.execute("SELECT product_id FROM dim_product")}
        locations = {r[0] for r in conn.execute("SELECT location_id FROM dim_location")}
        if not products or not locations:
            raise RuntimeError("reference data missing: dim_product/dim_location are empty "
                               "(pass --reference with products.csv and locations.csv)")
        files = expand_inputs(input_paths)
        if not files:
            lg.warning("no input files found: nothing to do")
        for f in files:
            result.files.append(process_file(conn, f, run_id, products, locations, lg,
                                             force=force, strategy=strategy))
        failed = [f for f in result.files if f.status in C.FILE_FAILED]
        loaded = [f for f in result.files if f.status == C.FILE_SUCCESS]
        if failed and not loaded:
            result.status = C.RUN_FAILED
        elif failed:
            result.status = C.RUN_PARTIAL
        elif loaded:
            result.status = C.RUN_SUCCESS
        else:
            result.status = C.RUN_NOOP
        if failed:
            result.error = "; ".join(f"{f.source_file}: {f.error}" for f in failed)
    except Exception as exc:  # noqa: BLE001
        result.status = C.RUN_FAILED
        result.error = f"{type(exc).__name__}: {exc}"
        lg.error("run failed: %s", result.error)
    result.ended_at = utc_now()
    t = result.totals()
    conn.execute(
        "UPDATE pipeline_run SET ended_at=?, status=?, files_total=?, files_succeeded=?, files_failed=?, "
        "files_skipped=?, rows_read=?, rows_loaded=?, rows_skipped_existing=?, rows_rejected=?, "
        "backdated_loaded=?, pairs_rebuilt=?, balance_rows_written=?, error=? WHERE run_id=?",
        (result.ended_at, result.status, len(result.files),
         sum(f.status == C.FILE_SUCCESS for f in result.files),
         sum(f.status in C.FILE_FAILED for f in result.files),
         sum(f.status == C.FILE_SKIPPED for f in result.files),
         t["rows_read"], t["rows_loaded"], t["rows_skipped_existing"], t["rows_rejected"],
         t["backdated_loaded"], t["pairs_rebuilt"], t["balance_rows_written"], result.error, run_id))
    lg.info("run finished status=%s totals=%s error=%s", result.status, t, result.error)
    conn.close()
    return result
