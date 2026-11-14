-- Run with:  sqlite3 output/inventory.db < docs/sample_queries.sql      (or: python -m inventory_pipeline report)

-- 1. Current inventory by product/location (latest balance date)
SELECT b.product_id, p.product_name, b.location_id, b.closing_qty
FROM daily_balance b JOIN dim_product p USING (product_id)
WHERE b.balance_date = (SELECT value FROM pipeline_state WHERE key = 'balance_end_date')
ORDER BY b.closing_qty DESC LIMIT 10;

-- 2. Daily balance timeline for one pair (opening + movements = closing)
SELECT balance_date, opening_qty, receipt_qty, issue_qty, transfer_in_qty, transfer_out_qty, adjustment_qty, closing_qty
FROM daily_balance WHERE product_id = 'P0002' AND location_id = 'L02' ORDER BY balance_date LIMIT 10;

-- 3. Movement totals reconcile to balances (should return zero rows)
SELECT 'mismatch' AS problem, b.product_id, b.location_id
FROM daily_balance b
WHERE b.balance_date = (SELECT value FROM pipeline_state WHERE key = 'balance_end_date')
  AND b.closing_qty != (SELECT COALESCE(SUM(signed_qty), 0) FROM inventory_leg l
                        WHERE l.product_id = b.product_id AND l.location_id = b.location_id);

-- 4. Why were rows rejected? (traceable to file + line + raw record)
SELECT reason_code, COUNT(*) AS rejects FROM reject_record GROUP BY reason_code ORDER BY rejects DESC;
SELECT source_file, source_line, reason_code, reason_detail, raw_record FROM reject_record
WHERE reason_code = 'UNKNOWN_PRODUCT' LIMIT 5;

-- 5. Backdated corrections and the run that applied them
SELECT movement_id, movement_type, product_id, location_id, quantity, effective_date, recorded_at, run_id
FROM inventory_movement WHERE is_backdated = 1 ORDER BY effective_date LIMIT 10;

-- 6. Operational history: one row per run, one row per file per run
SELECT run_id, status, rows_read, rows_loaded, rows_skipped_existing, rows_rejected, backdated_loaded FROM pipeline_run ORDER BY started_at;
SELECT run_id, source_file, status, rows_read, rows_loaded, rows_rejected, error FROM file_load ORDER BY started_at;

-- 7. Anomalies kept for review (not rejected): negative stock
SELECT product_id, location_id, COUNT(*) AS negative_days, MIN(closing_qty) AS worst_closing
FROM daily_balance WHERE closing_qty < 0 GROUP BY 1, 2 ORDER BY worst_closing LIMIT 10;
