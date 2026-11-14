# Execution evidence

Everything below was produced by `python scripts/make_evidence.py` (real runs, nothing hand-edited).

### 1. Unit / integration tests

`-m pytest -v --tb=short -p no:cacheprovider` (exit code 0)

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0 -- /usr/bin/python3
rootdir: /home/claude/inventory-pipeline
configfile: pyproject.toml
testpaths: tests
plugins: platformdirs-4.13.0
collecting ... collected 52 items

tests/test_generator_cli.py::test_generator_is_deterministic_for_same_seed PASSED [  1%]
tests/test_generator_cli.py::test_pipeline_matches_independent_labels_on_generated_data PASSED [  3%]
tests/test_generator_cli.py::test_generated_negative_cases PASSED        [  5%]
tests/test_generator_cli.py::test_cli_end_to_end_and_exit_codes PASSED   [  7%]
tests/test_generator_cli.py::test_generator_never_replays_same_event_twice_in_late_file PASSED [  9%]
tests/test_idempotency_recovery.py::test_duplicate_in_file_identical_and_conflicting PASSED [ 11%]
tests/test_idempotency_recovery.py::test_rerun_same_file_is_skipped_and_state_unchanged PASSED [ 13%]
tests/test_idempotency_recovery.py::test_forced_rerun_is_row_level_idempotent PASSED [ 15%]
tests/test_idempotency_recovery.py::test_same_event_in_new_file_is_skipped_and_conflict_is_rejected PASSED [ 17%]
tests/test_idempotency_recovery.py::test_unexpected_schema_change_fails_file_but_other_files_load PASSED [ 19%]
tests/test_idempotency_recovery.py::test_extra_column_is_tolerated_with_warning PASSED [ 21%]
tests/test_idempotency_recovery.py::test_partial_failure_rolls_back_atomically_then_retry_succeeds PASSED [ 23%]
tests/test_idempotency_recovery.py::test_backdated_correction_rewrites_tail_and_matches_clean_rebuild PASSED [ 25%]
tests/test_idempotency_recovery.py::test_backdated_before_pair_first_day_backfills_leading_rows PASSED [ 26%]
tests/test_idempotency_recovery.py::test_later_file_extends_idle_pairs_forward PASSED [ 28%]
tests/test_idempotency_recovery.py::test_out_of_order_rows_within_file_give_same_result PASSED [ 30%]
tests/test_idempotency_recovery.py::test_naive_and_grouped_strategies_are_equivalent PASSED [ 32%]
tests/test_idempotency_recovery.py::test_run_without_reference_data_fails_cleanly PASSED [ 34%]
tests/test_pipeline_core.py::test_happy_path_balances_and_reconciliation PASSED [ 36%]
tests/test_pipeline_core.py::test_empty_batch_header_only_is_noop PASSED [ 38%]
tests/test_pipeline_core.py::test_zero_byte_file_fails_schema_and_no_input_is_noop PASSED [ 40%]
tests/test_pipeline_core.py::test_missing_input_file_is_reported_not_crash PASSED [ 42%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[0-movement_id] PASSED [ 44%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[1-movement_type] PASSED [ 46%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[2-product_id] PASSED [ 48%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[3-location_id] PASSED [ 50%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[5-quantity] PASSED [ 51%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[6-effective_date] PASSED [ 53%]
tests/test_pipeline_core.py::test_missing_required_field_is_rejected[7-recorded_at] PASSED [ 55%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad0-INVALID_QUANTITY] PASSED [ 57%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad1-INVALID_QUANTITY] PASSED [ 59%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad2-QUANTITY_OUT_OF_RANGE] PASSED [ 61%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad3-QUANTITY_OUT_OF_RANGE] PASSED [ 63%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad4-QUANTITY_OUT_OF_RANGE] PASSED [ 65%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad5-QUANTITY_OUT_OF_RANGE] PASSED [ 67%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad6-INVALID_MOVEMENT_TYPE] PASSED [ 69%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad7-INVALID_DATE] PASSED [ 71%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad8-INVALID_DATE] PASSED [ 73%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad9-INVALID_TIMESTAMP] PASSED [ 75%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad10-FUTURE_EFFECTIVE_DATE] PASSED [ 76%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad11-UNKNOWN_PRODUCT] PASSED [ 78%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad12-UNKNOWN_LOCATION] PASSED [ 80%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad13-UNKNOWN_LOCATION] PASSED [ 82%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad14-SAME_LOCATION_TRANSFER] PASSED [ 84%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad15-MISSING_REQUIRED_FIELD] PASSED [ 86%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad16-UNEXPECTED_DEST_LOCATION] PASSED [ 88%]
tests/test_pipeline_core.py::test_invalid_records_are_quarantined_with_reason[bad17-INVALID_MOVEMENT_ID] PASSED [ 90%]
tests/test_pipeline_core.py::test_malformed_ragged_rows_quarantined PASSED [ 92%]
tests/test_pipeline_core.py::test_boundary_quantities_accepted PASSED    [ 94%]
tests/test_pipeline_core.py::test_negative_balance_is_flagged_not_rejected PASSED [ 96%]
tests/test_pipeline_core.py::test_whitespace_and_case_normalised PASSED  [ 98%]
tests/test_pipeline_core.py::test_gap_days_carry_forward_zero_movement_rows PASSED [100%]

============================== 52 passed in 5.74s ==============================
```

### 2. Generate the reproducible sample (seed 42)

`-m inventory_pipeline generate --out data/sample --records 1000 --seed 42` (exit code 0)

```json
{
  "seed": 42,
  "end_date": "2026-01-30",
  "clean_events": 1000,
  "files": {
    "movements_batch_001.csv": {
      "rows_read": 980,
      "rows_loaded": 950,
      "rows_skipped_existing": 0,
      "rows_rejected": 30
    },
    "movements_batch_002_late.csv": {
      "rows_read": 53,
      "rows_loaded": 50,
      "rows_skipped_existing": 1,
      "rows_rejected": 2
    }
  },
  "injected": {
    "movements_batch_001.csv": {
      "invalid": 17,
      "dup": 13
    },
    "movements_batch_002_late.csv": {
      "conflict": 1,
      "replay_identical": 1,
      "replay_conflict": 1
    }
  }
}
```

### 3. First run: reference load + 2 files (main batch, then late/backdated batch)

`(exit code 0)` - structured log lines:

```text
2026-11-14 10:02:11 run started params={'input_paths': ['data/sample/incoming'], 'reference_dir': 'data/sample/reference', 'force': False, 'strategy': 'naive'}
2026-11-14 10:02:11 reference products.csv: loaded=10 rejected=0
2026-11-14 10:02:11 reference locations.csv: loaded=4 rejected=0
2026-11-14 10:02:11 file=movements_batch_001.csv status=SUCCESS read=980 loaded=950 skipped_existing=0 rejected=30 backdated=0 pairs_rebuilt=40 balance_rows=1162
2026-11-14 10:02:11 file=movements_batch_002_late.csv status=SUCCESS read=53 loaded=50 skipped_existing=1 rejected=2 backdated=50 pairs_rebuilt=23 balance_rows=457
2026-11-14 10:02:11 run finished status=SUCCESS totals={'rows_read': 1033, 'rows_loaded': 1000, 'rows_skipped_existing': 1, 'rows_rejected': 32, 'backdated_loaded': 50, 'pairs_rebuilt': 63, 'balance_rows_written': 1619} error=None
```

### 4. Rerun of the same input (idempotent: every file skipped, state unchanged)

`(exit code 0)` - structured log lines:

```text
2026-11-14 10:02:11 run started params={'input_paths': ['data/sample/incoming'], 'reference_dir': 'data/sample/reference', 'force': False, 'strategy': 'naive'}
2026-11-14 10:02:11 reference products.csv: loaded=10 rejected=0
2026-11-14 10:02:11 reference locations.csv: loaded=4 rejected=0
2026-11-14 10:02:11 file=movements_batch_001.csv skipped: identical content (sha256 5ad7b931ff6d...) already loaded
2026-11-14 10:02:11 file=movements_batch_002_late.csv skipped: identical content (sha256 fdda80137cfe...) already loaded
2026-11-14 10:02:11 run finished status=NOOP totals={'rows_read': 0, 'rows_loaded': 0, 'rows_skipped_existing': 0, 'rows_rejected': 0, 'backdated_loaded': 0, 'pairs_rebuilt': 0, 'balance_rows_written': 0} error=None
```

### 5. Forced reprocess (--force): row-level idempotency, 0 rows loaded

`(exit code 0)` - structured log lines:

```text
2026-11-14 10:02:12 run started params={'input_paths': ['data/sample/incoming'], 'reference_dir': None, 'force': True, 'strategy': 'naive'}
2026-11-14 10:02:12 file=movements_batch_001.csv status=SUCCESS read=980 loaded=0 skipped_existing=950 rejected=30 backdated=0 pairs_rebuilt=0 balance_rows=0
2026-11-14 10:02:12 file=movements_batch_002_late.csv status=SUCCESS read=53 loaded=0 skipped_existing=51 rejected=2 backdated=0 pairs_rebuilt=0 balance_rows=0
2026-11-14 10:02:12 run finished status=SUCCESS totals={'rows_read': 1033, 'rows_loaded': 0, 'rows_skipped_existing': 1001, 'rows_rejected': 32, 'backdated_loaded': 0, 'pairs_rebuilt': 0, 'balance_rows_written': 0} error=None
```

### 6. Failure handling: empty batch + unexpected schema change

`(exit code 1)` - structured log lines:

```text
2026-11-14 10:02:12 run started params={'input_paths': ['data/sample/negative_cases'], 'reference_dir': None, 'force': False, 'strategy': 'naive'}
2026-11-14 10:02:12 file=empty_batch.csv empty batch (header only): nothing to do
2026-11-14 10:02:12 file=schema_drift.csv FAILED_SCHEMA: SchemaError: missing required column(s): ['quantity']; found: ['movement_id', 'movement_type', 'product_id', 'location_id', 'dest_location_id', 'qty', 'effective_date', 'recorded_at', 'notes']
2026-11-14 10:02:12 run finished status=FAILED totals={'rows_read': 0, 'rows_loaded': 0, 'rows_skipped_existing': 0, 'rows_rejected': 0, 'backdated_loaded': 0, 'pairs_rebuilt': 0, 'balance_rows_written': 0} error=schema_drift.csv: SchemaError: missing required column(s): ['quantity']; found: ['movement_id', 'movement_type', 'product_id', 'location_id', 'dest_location_id', 'qty', 'effective_date', 'recorded_at', 'notes']
```

### 7. Reconciliation (assertions over the DB)

`-m inventory_pipeline reconcile --db output/inventory.db --output-dir output` (exit code 0)

```text
PASS  [error] file_row_accounting: expected=0 actual=0
PASS  [error] ledger_count_equals_loaded_rows: expected=1000 actual=1000
PASS  [error] ledger_rows_traceable: expected=0 actual=0
PASS  [error] rejects_traceable: expected=0 actual=0
PASS  [error] referential_integrity_movements: expected=0 actual=0
PASS  [error] referential_integrity_legs: expected=0 actual=0
PASS  [error] leg_count: expected=1136 actual=1136
PASS  [error] transfer_conservation: expected=34097 actual=34097
PASS  [error] aggregate_receipt: expected=1118024 actual=1118024
PASS  [error] aggregate_issue: expected=70145 actual=70145
PASS  [error] aggregate_transfer_in: expected=34097 actual=34097
PASS  [error] aggregate_transfer_out: expected=34097 actual=34097
PASS  [error] aggregate_adjustment: expected=487 actual=487
PASS  [error] balance_arithmetic: expected=0 actual=0
PASS  [error] balance_continuity: expected=0 actual=0
PASS  [error] first_day_opening_is_zero: expected=0 actual=0
PASS  [error] balance_dense_to_end_date: expected=0 actual=0
PASS  [error] closing_equals_ledger_sum: expected=0 actual=0
PASS  [error] pair_coverage: expected=40 actual=40
PASS  [warning] negative_closing_balance_rows: expected=0 actual=0
PASS  [info] backdated_movements_loaded: expected=None actual=50
OVERALL: PASS
```

### 8. Verification against independent generator labels

`-m inventory_pipeline verify --db output/inventory.db --output-dir output --labels data/sample/labels` (exit code 0)

```text
PASS  rejects_match_labels: expected=32 actual=32
PASS  closing_balances_match_labels: expected=40 actual=40
PASS  file_counts_match_labels[movements_batch_001.csv]: expected={'rows_read': 980, 'rows_loaded': 950, 'rows_skipped_existing': 0, 'rows_rejected': 30} actual={'rows_read': 980, 'rows_loaded': 950, 'rows_skipped_existing': 0, 'rows_rejected': 30}
PASS  file_counts_match_labels[movements_batch_002_late.csv]: expected={'rows_read': 53, 'rows_loaded': 50, 'rows_skipped_existing': 1, 'rows_rejected': 2} actual={'rows_read': 53, 'rows_loaded': 50, 'rows_skipped_existing': 1, 'rows_rejected': 2}
OVERALL: PASS
```

### 9. Sample analytical queries

`-m inventory_pipeline report --db output/inventory.db --output-dir output` (exit code 0)

```text
== current_inventory_snapshot ==
product_id  product_name   location_id  closing_qty
----------  -------------  -----------  -----------
P0001       Product P0001  L01          1000332    
P0005       Product P0005  L01          3731       
P0008       Product P0008  L01          3298       
P0007       Product P0007  L03          2375       
P0008       Product P0008  L04          2361       
P0007       Product P0007  L01          2189       
P0002       Product P0002  L03          2130       
P0010       Product P0010  L04          2079       
P0007       Product P0007  L04          1979       
P0001       Product P0001  L03          1911       

== reject_summary_by_reason ==
reason_code             rejects
----------------------  -------
DUPLICATE_EVENT         13     
QUANTITY_OUT_OF_RANGE   4      
MISSING_REQUIRED_FIELD  3      
SAME_LOCATION_TRANSFER  3      
DUPLICATE_CONFLICT      2      
INVALID_MOVEMENT_TYPE   2      
FUTURE_EFFECTIVE_DATE   1      
INVALID_QUANTITY        1      
INVALID_TIMESTAMP       1      
MALFORMED_ROW           1      
UNKNOWN_PRODUCT         1      

== run_history ==
run_id                         status   files_total  rows_read  rows_loaded  rows_skipped_existing  rows_rejected  backdated_loaded  pairs_rebuilt  balance_rows_written
-----------------------------  -------  -----------  ---------  -----------  ---------------------  -------------  ----------------  -------------  --------------------
run_20261114T100211Z_077cc186  SUCCESS  2            1033       1000         1                      32             50                63             1619                
run_20261114T100211Z_54253cf5  NOOP     2            0          0            0                      0              0                 0              0                   
run_20261114T100212Z_ef8d949a  SUCCESS  2            1033       0            1001                   32             0                 0              0                   
run_20261114T100212Z_df340523  FAILED   2            0          0            0                      0              0                 0              0                   

== backdated_corrections ==
movement_id  movement_type  product_id  location_id  quantity  effective_date  recorded_at           source_file                 
-----------  -------------  ----------  -----------  --------  --------------  --------------------  ----------------------------
MV00000958   receipt        P0009       L03          178       2026-01-24      2026-01-31T07:01:11Z  movements_batch_002_late.csv
MV00000994   adjustment     P0010       L01          11        2026-01-13      2026-01-31T07:16:01Z  movements_batch_002_late.csv
MV00000999   receipt        P0010       L01          135       2026-01-12      2026-01-31T07:37:31Z  movements_batch_002_late.csv
MV00000981   receipt        P0008       L01          180       2026-01-05      2026-01-31T07:41:29Z  movements_batch_002_late.csv
MV00000978   receipt        P0007       L01          105       2026-01-02      2026-01-31T07:55:42Z  movements_batch_002_late.csv
MV00000985   receipt        P0006       L04          48        2026-01-16      2026-01-31T08:03:18Z  movements_batch_002_late.csv
MV00000974   receipt        P0001       L01          94        2026-01-09      2026-01-31T08:05:01Z  movements_batch_002_late.csv
MV00000976   receipt        P0002       L03          91        2026-01-08      2026-01-31T09:07:04Z  movements_batch_002_late.csv
MV00000980   adjustment     P0009       L01          19        2026-01-11      2026-01-31T09:36:25Z  movements_batch_002_late.csv
MV00000990   adjustment     P0010       L04          19        2026-01-11      2026-01-31T09:47:27Z  movements_batch_002_late.csv

== negative_balance_pairs ==
(no rows)

== movement_totals_by_type ==
movement_type  movements  total_qty
-------------  ---------  ---------
adjustment     117        487      
issue          297        70145    
receipt        450        1118024  
transfer       136        34097
```

### 10. Backdated correction demonstration

```text
Batch 1 loaded: 1162 balance rows, end date 2026-01-30.
Batch 2 (late file) loaded: 1163 balance rows, 456 pre-existing rows rewritten, 50 movements flagged is_backdated.
Example backdated movement: id=MV00000951 type=adjustment product=P0002 location=L02 qty=14 effective_date=2026-01-01 recorded_at=2026-01-31T14:27:46Z

closing_qty for that product/location, before -> after the late batch:
  2026-01-01: 135 -> 149
  2026-01-02: 159 -> 173
  2026-01-03: 624 -> 638
  2026-01-04: 624 -> 638
  2026-01-05: 1012 -> 1026
  2026-01-06: 1669 -> 1683
```

### 11. Performance (100k clean events, 200 products x 25 locations x 90 days; {'movements_batch_001.csv': 98178, 'movements_batch_002_late.csv': 5549} rows in files)

Python 3.12.3, SQLite 3.45.1, single thread.

| strategy | total s | batch 1 read+validate s | batch 1 load s | batch 1 rebuild s | batch 2 (late) rebuild s |
|---|---|---|---|---|---|
| naive | 4.95 | 1.053 | 1.167 | 1.476 | 0.708 |
| grouped | 5.42 | 1.3 | 1.256 | 1.477 | 0.797 |

Tail-only vs full rebuild for the late batch: incremental 0.797s (3199 pairs, 167946 rows) vs full recompute 1.458s (5000 pairs, 430626 rows) -> **1.83x**.

### 12. Scale run: 150k clean events (155,569 input rows) - generate, run, reconcile, verify

`make large  (generate -> run -> reconcile -> verify)` (exit code 0)

```text
file=movements_batch_001.csv status=SUCCESS read=147265 loaded=142500 skipped_existing=0 rejected=4765 backdated=0 pairs_rebuilt=5000 balance_rows=437217
file=movements_batch_002_late.csv status=SUCCESS read=8304 loaded=7500 skipped_existing=285 rejected=519 backdated=7500 pairs_rebuilt=3870 balance_rows=221526
run finished status=SUCCESS totals={'rows_read': 155569, 'rows_loaded': 150000, 'rows_skipped_existing': 285, 'rows_rejected': 5284, 'backdated_loaded': 7500, 'pairs_rebuilt': 8870, 'balance_rows_written': 658743} error=None
reconcile: OVERALL: PASS | failed checks: 0
verify vs labels: OVERALL: PASS | failed checks: 0
```
