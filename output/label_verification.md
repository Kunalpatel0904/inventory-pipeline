# Reconciliation report

- balance end date: `None`
- overall: **PASS**

| check | severity | expected | actual | result |
|---|---|---|---|---|
| rejects_match_labels | error | 32 | 32 | PASS |
| closing_balances_match_labels | error | 40 | 40 | PASS |
| file_counts_match_labels[movements_batch_001.csv] | error | {'rows_read': 980, 'rows_loaded': 950, 'rows_skipped_existing': 0, 'rows_rejected': 30} | {'rows_read': 980, 'rows_loaded': 950, 'rows_skipped_existing': 0, 'rows_rejected': 30} | PASS |
| file_counts_match_labels[movements_batch_002_late.csv] | error | {'rows_read': 53, 'rows_loaded': 50, 'rows_skipped_existing': 1, 'rows_rejected': 2} | {'rows_read': 53, 'rows_loaded': 50, 'rows_skipped_existing': 1, 'rows_rejected': 2} | PASS |
