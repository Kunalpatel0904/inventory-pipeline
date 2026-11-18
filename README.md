# Inventory movement pipeline (72-hour code challenge)

Turns **receipts, issues, transfers and adjustments** into **daily inventory balances**, reconciles movement totals
to balances, and handles **backdated (late-arriving) corrections** by rebuilding only the affected tail of each
product/location history. Standard library only (Python >= 3.10, SQLite); `pytest` for tests.

**Status:** 52 tests pass; the sample and a 150k-event run (155k input rows) reconcile with 0 failed checks, and output matches
independently generated labels (see [`docs/execution_evidence.md`](docs/execution_evidence.md)).

## Quick start (clean environment)

```bash
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                            # only pytest
export PYTHONPATH=src                                      # Windows PowerShell: $env:PYTHONPATH="src"

pytest -q                                                  # 52 passed
python -m inventory_pipeline generate --out data/sample --records 1000 --seed 42     # (sample is already committed)
python -m inventory_pipeline run --db output/inventory.db \
       --reference data/sample/reference --input data/sample/incoming
python -m inventory_pipeline reconcile --db output/inventory.db     # assertions over the DB
python -m inventory_pipeline verify    --db output/inventory.db --labels data/sample/labels
python -m inventory_pipeline report    --db output/inventory.db     # sample analytical queries
```
`make test|sample|run|reconcile|verify|report|large|benchmark|evidence` wraps the same commands.
Larger scale run (150k+ events): `make large`. Exit codes: `0` success/no-op, `2` partial failure, `1` failed.

## Architecture / flow

```
 products.csv  locations.csv                       movements_*.csv  (events, possibly late / duplicated / dirty)
        \            /                                       |
         v          v                                        v
   [reference load] --> dim_product / dim_location    [1 read + header check]   --schema error--> file FAILED_SCHEMA (nothing loaded)
                                 |                          |
                                 | ref sets                 v
                                 +--------------> [2 row validation + in-file dedupe] --bad rows--> reject_record (file, line, reason, raw)
                                                            | accepted
                                                            v
                                 BEGIN IMMEDIATE  (one transaction per file)
                                   [3 ledger check: same id? identical -> skip, different -> reject]
                                   [4 insert inventory_movement + inventory_leg]     (append-only)
                                   [5 rebuild dirty tails of daily_balance]          (derived, idempotent)
                                   [6 file_load audit row]
                                 COMMIT  (any exception -> ROLLBACK, file marked FAILED_PROCESSING, run continues)
                                                            |
                              reconcile / verify / report / CSV exports  <---  pipeline_run + file_load (metrics)
```
Module map (`src/inventory_pipeline/`): `csvio` (read + schema check), `validate` (pure row rules), `ingest` (engine, runs, metrics),
`balances` (incremental rebuild), `reconcile` (checks + label verification), `reports` (queries + exports), `generator`
(synthetic data + labels), `benchmark`, `cli`, `db` (DDL), `config` (rules/constants), `store`, `reference`.

## Business rules (summary - full contract in [`docs/data_dictionary.md`](docs/data_dictionary.md))
- **receipt** `+qty` at `location_id`; **issue** `-qty`; **transfer** `-qty` at source and `+qty` at `dest_location_id` (2 legs, nets to zero);
  **adjustment** signed, non-zero. `closing = opening + receipts - issues + transfer_in - transfer_out + adjustments`.
- `effective_date` is the business date used for balances; `recorded_at` is when the source recorded it. A movement whose
  `effective_date` precedes the current balance end date is **backdated**: it is loaded, flagged `is_backdated`, and every later
  day of that pair is recomputed. History is preserved: the ledger is append-only and corrections arrive as new events.
- **Negative stock is allowed and flagged** (reconciliation warning), not rejected: an issue can legitimately be recorded before the receipt arrives.
- Referential integrity: unknown product/location/destination is rejected (`UNKNOWN_*`). Keys, types, ranges, dates, and
  `effective_date <= recorded_at date` are enforced; each reject carries **one** reason (validation order is documented in `validate.py`).

## Naming and IDs
`snake_case` tables/columns; ISO-8601 dates/UTC timestamps; every ledger and reject row carries `run_id`, `source_file`, `source_line`.
Deterministic IDs: movement IDs from the source, `reject_id = sha1(file_sha256|line|reason)`, file identity = SHA-256 of content.
`run_id` is `run_<UTC time>_<random>` (unique per execution on purpose).

## Idempotency, retry, restart, backfill
| situation | behaviour |
|---|---|
| Same file again | skipped by content hash (`SKIPPED_ALREADY_LOADED`); run status `NOOP`; no writes besides the audit row |
| Same events in a *different* file (at-least-once delivery) | identical `movement_id` + content -> counted as `skipped_existing`; different content -> `DUPLICATE_CONFLICT` reject, ledger untouched (first write wins) |
| `--force` | re-processes the file anyway; row-level idempotency means 0 rows loaded, reject IDs are deterministic so no duplicate rejects; also the way to re-evaluate previously rejected rows after fixing reference data |
| Crash / exception mid-file | whole file rolls back (ledger, legs, rejects, balances), `file_load` records `FAILED_PROCESSING` + error; **restart = run the same command again** - failed files are never skipped, completed ones are |
| One bad file among several | other files still load; run is `PARTIAL_FAILURE` (exit 2) |
| Late/backdated file (backfill) | just ingest it: only affected pairs are rebuilt from the earliest affected date; result is identical to loading everything at once (tested) |
| End date moves later | idle pairs are extended forward so every pair reaches the new end date |

## Observability
Structured log lines (`run_id=...`) to stderr and `output/pipeline.log`; `pipeline_run` + `file_load` tables hold run ID, start/end,
input/loaded/skipped/rejected counts, backdated count, pairs rebuilt, rows written, status and failure reason;
`output/run_summaries/<run_id>.json` per run; stage timings in the benchmark.

## Testing (52 tests, ~6 s)
Happy path with exact expected balances; empty batch (header-only, zero-byte, no files); malformed/ragged rows; 7 missing-field variants;
18 invalid-record rules; boundary quantities (1 / 1,000,000); duplicates (in-file identical/conflicting, cross-file replay, conflict vs ledger);
schema change (renamed column -> file fails, others load; extra column tolerated); rerun and forced rerun (state unchanged);
partial failure with injected crash + atomic rollback + successful retry; backdated correction (== clean one-shot rebuild);
backdated before a pair's first day; end-date extension; out-of-order rows; negative stock flagged; naive vs grouped equivalence;
generator determinism and no-ambiguous-replay regression; end-to-end on 3,000 generated events checked against **independent labels**; CLI exit codes.

## Reconciliation and validation evidence
`reconcile` runs 19 hard assertions plus 2 warning/info counters (zero failures on the sample and the 150k-event run): row accounting per file, ledger count == loaded rows, traceability of
ledger and rejects, referential integrity, legs == movements + transfers, transfer in == out, per-type aggregates ledger == balances,
balance arithmetic, opening(d) == closing(d-1), dense days to the end date, closing == SUM(ledger) per pair (independent path).
`verify` compares against generator labels kept in `data/sample/labels/` (separate from inputs): expected reject (file, line, reason),
expected closing per pair, expected per-file counts. Sample queries: `docs/sample_queries.sql`.

## Performance (100k events, 200 products x 25 locations x 90 days; details in `docs/execution_evidence.md`)
~5 s end to end (~20k input rows/s; read+validate 1.1 s, ledger load 1.2 s, balance rebuild 1.4 s for 430k balance rows).
**Optimization that matters: tail-only rebuild.** A late batch of 5,000 backdated events rebuilt 3,199 pairs / ~168k rows in ~0.7-0.8 s versus
~1.5 s for recomputing every pair (~2x; the gap grows with history length and with the share of untouched pairs).
**Negative result, kept honest:** a set-based (temp-table join) variant of the rebuild reads was no faster than per-pair indexed queries
(4.9-5.2 s both), so the simpler `naive` path is the default; `--strategy grouped` stays as a tested alternative.

## Assumptions
Quantities are whole units; one event stream is the source of truth (no cost/valuation, lots or serials); transfers are instantaneous (no in-transit state);
`effective_date` is already a business date in the warehouse's calendar; duplicates: first occurrence wins; dimensions are overwrite-in-place (type 1).

## Known limitations / next steps
- A file is parsed into memory (fine to a few million rows); next: chunked streaming validation.
- SQLite = single writer, one process; next: Postgres/warehouse target with the same SQL, partitioned `daily_balance`.
- Dense balances grow with pairs x days; a sparse + as-of-view variant would shrink storage for slow-moving SKUs.
- No explicit reversal event type (corrections are adjustments); no in-transit stock; rows rejected for an unknown product are only
  re-evaluated with `--force` after the master data is fixed (their old reject rows stay as history).
- Add scheduling/alerting on `pipeline_run.status`, and data-contract checks on the reference files.

## Design / trade-off note
See [`docs/DESIGN.md`](docs/DESIGN.md).

## Additive Halcer Idea Board platform

The requested AI-first Idea Board implementation lives in
[`platform/`](platform/README.md) so this repository's inventory pipeline
remains backward-compatible. It includes a FastAPI/PostgreSQL backend, React
frontend, Docker Compose, Kubernetes manifests, provider-specific Terraform
modules, AI safety boundaries, monitoring starter files, and CI workflow.

### Platform quick start

```powershell
cd platform
copy .env.example .env
# Set POSTGRES_PASSWORD to a local-only value.
docker compose up --build
```

Open `http://localhost:5173`; API documentation is at
`http://localhost:8000/docs`. Docker, PostgreSQL, Kubernetes, AWS and GCP
validation or deployment require the corresponding local CLI and credentials.
No cloud infrastructure is provisioned or applied by this repository setup.

Without Docker Desktop, the Compose application cannot be built or started
locally. The platform may also be run for API/frontend development without
Docker:

```powershell
python -m pip install -r platform/backend/requirements.txt
$env:PYTHONPATH="platform/backend"
python -m uvicorn app.main:app --app-dir platform/backend --reload
```

In a second terminal:

```powershell
cd platform/frontend
npm ci
npm run dev
```

For Terraform, Kubernetes, CI/CD and AI-provider details, see
[`platform/README.md`](platform/README.md) and [`FINAL_REVIEW.md`](FINAL_REVIEW.md).
