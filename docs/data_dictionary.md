# Data dictionary

Conventions: `snake_case` names; dates `YYYY-MM-DD`; timestamps ISO-8601 UTC with `Z` (`2026-01-05T10:15:00Z`);
quantities are whole units (`INTEGER`). IDs are stable and deterministic: movement IDs come from the source
(`MV00000042` in the generator), `reject_id = sha1(file_sha256|line|reason)[:16]`, `run_id = run_<UTC ts>_<8 hex>`.

## Source files (input contract)

**`movements_*.csv`** - one row per business event. Header is validated; missing required column = file rejected
(`FAILED_SCHEMA`), extra columns = warning only. Column order is irrelevant, names are case/space-insensitive.

| column | type | required | rule |
|---|---|---|---|
| `movement_id` | text | yes | unique event key, `[A-Za-z0-9_-]{1,64}` |
| `movement_type` | text | yes | `receipt`, `issue`, `transfer`, `adjustment` (case-insensitive) |
| `product_id` | text | yes | must exist in `dim_product` |
| `location_id` | text | yes | must exist in `dim_location`; the *source* location for transfers |
| `dest_location_id` | text | transfer only | must exist, must differ from `location_id`; must be blank for other types |
| `quantity` | integer | yes | receipt/issue/transfer: 1..1,000,000; adjustment: signed, non-zero, \|q\| <= 1,000,000 |
| `effective_date` | date | yes | business date the stock changed; >= 2000-01-01; must not be after the `recorded_at` date |
| `recorded_at` | timestamp | yes | when the source system recorded the event; offsets normalised to UTC |

**`products.csv`**: `product_id`, `product_name`, optional `uom` (default `EA`). **`locations.csv`**: `location_id`, `location_name`.

## Target tables

Grain and key of each table; `NN` = NOT NULL.

### `inventory_movement` - immutable event ledger (grain: one accepted source event; PK `movement_id`)
`movement_id`, `movement_type`, `product_id` (FK), `location_id` (FK), `dest_location_id` (FK, null unless transfer),
`quantity`, `effective_date`, `recorded_at`, **derived/lineage:** `content_hash` (sha256 of normalised fields, used to tell a
replay from a conflicting duplicate), `is_backdated` (1 if `effective_date` < balance end date at load time), `run_id`,
`source_file`, `source_line`, `loaded_at`. Never updated or deleted by the pipeline.

### `inventory_leg` - stock-affecting side of a movement (PK `movement_id, leg_no`)
`product_id`, `location_id`, `effective_date`, `leg_type` (`receipt`,`issue`,`transfer_in`,`transfer_out`,`adjustment`),
`signed_qty` (+ adds stock, - removes). A transfer produces two legs, so legs = movements + transfers.

### `daily_balance` - derived analytical table (grain: product x location x day; PK `product_id, location_id, balance_date`)
Dense: one row per day from the pair's first movement to the global end date (idle days carry the balance forward).
`opening_qty`, `receipt_qty`, `issue_qty` (positive magnitude), `transfer_in_qty`, `transfer_out_qty` (positive magnitude),
`adjustment_qty` (signed), `closing_qty = opening + receipt - issue + transfer_in - transfer_out + adjustment`, `run_id` (last writer).
Opening of day *d* = closing of day *d-1*; the first row of a pair opens at 0.

### `reject_record` - quarantine (PK `reject_id`)
`run_id`, `source_file`, `file_sha256`, `source_line`, `reason_code`, `reason_detail`, `raw_record` (JSON of the original fields),
`rejected_at`. Reject reasons: `MALFORMED_ROW`, `MISSING_REQUIRED_FIELD`, `INVALID_MOVEMENT_ID`, `INVALID_MOVEMENT_TYPE`,
`UNEXPECTED_DEST_LOCATION`, `INVALID_QUANTITY`, `QUANTITY_OUT_OF_RANGE`, `INVALID_DATE`, `INVALID_TIMESTAMP`,
`FUTURE_EFFECTIVE_DATE`, `UNKNOWN_PRODUCT`, `UNKNOWN_LOCATION`, `SAME_LOCATION_TRANSFER`, `DUPLICATE_EVENT`,
`DUPLICATE_CONFLICT`, `REFERENCE_MISSING_KEY`, `REFERENCE_DUPLICATE_KEY`.

### Operations tables
- `pipeline_run` (PK `run_id`): `started_at`, `ended_at`, `status` (`SUCCESS` / `PARTIAL_FAILURE` / `FAILED` / `NOOP`), file and row counters, `backdated_loaded`, `pairs_rebuilt`, `balance_rows_written`, `error`, `params_json`.
- `file_load` (PK `run_id, source_file`): per-file `file_sha256`, `status` (`SUCCESS`, `EMPTY_BATCH`, `SKIPPED_ALREADY_LOADED`, `FAILED_SCHEMA`, `FAILED_READ`, `FAILED_PROCESSING`), counters, `error`. Append-only history of every attempt.
- `pipeline_state` (PK `key`): `balance_end_date`.
- `dim_product` (`product_id` PK, `product_name` NN, `uom` NN), `dim_location` (`location_id` PK, `location_name` NN) - overwrite-in-place dimensions.

## Exported files (`output/`)
`daily_balance.csv`, `inventory_snapshot.csv` (closing at end date), `rejects.csv`, `run_history.csv`,
`reconciliation_report.{md,json}`, `label_verification.{md,json}`, `benchmark.json`, `pipeline.log`, `run_summaries/<run_id>.json`.
