# Reconciliation report

- balance end date: `2026-01-30`
- overall: **PASS**

| check | severity | expected | actual | result |
|---|---|---|---|---|
| file_row_accounting | error | 0 | 0 | PASS |
| ledger_count_equals_loaded_rows | error | 1000 | 1000 | PASS |
| ledger_rows_traceable | error | 0 | 0 | PASS |
| rejects_traceable | error | 0 | 0 | PASS |
| referential_integrity_movements | error | 0 | 0 | PASS |
| referential_integrity_legs | error | 0 | 0 | PASS |
| leg_count | error | 1136 | 1136 | PASS |
| transfer_conservation | error | 34097 | 34097 | PASS |
| aggregate_receipt | error | 1118024 | 1118024 | PASS |
| aggregate_issue | error | 70145 | 70145 | PASS |
| aggregate_transfer_in | error | 34097 | 34097 | PASS |
| aggregate_transfer_out | error | 34097 | 34097 | PASS |
| aggregate_adjustment | error | 487 | 487 | PASS |
| balance_arithmetic | error | 0 | 0 | PASS |
| balance_continuity | error | 0 | 0 | PASS |
| first_day_opening_is_zero | error | 0 | 0 | PASS |
| balance_dense_to_end_date | error | 0 | 0 | PASS |
| closing_equals_ledger_sum | error | 0 | 0 | PASS |
| pair_coverage | error | 40 | 40 | PASS |
| negative_closing_balance_rows | warning | 0 | 0 | PASS |
| backdated_movements_loaded | info | None | 50 | PASS |
