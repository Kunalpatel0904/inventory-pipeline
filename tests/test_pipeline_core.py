"""Happy path, empty input, nulls, malformed rows, invalid references, boundaries."""
import pytest

from conftest import row
from inventory_pipeline.reconcile import run_reconciliation


def test_happy_path_balances_and_reconciliation(env):
    f = env.file([
        row("r1", "receipt", qty=100, eff="2026-01-01"),
        row("i1", "issue", qty=30, eff="2026-01-02"),
        row("t1", "transfer", loc="L1", dest="L2", qty=20, eff="2026-01-02"),
        row("a1", "adjustment", loc="L2", qty=-5, eff="2026-01-03"),
    ])
    res = env.run(f)
    assert res.status == "SUCCESS"
    assert res.totals()["rows_loaded"] == 4 and res.totals()["rows_rejected"] == 0
    assert env.balances() == [
        # product, loc, date, open, rcpt, issue, t_in, t_out, adj, close
        ("P1", "L1", "2026-01-01", 0, 100, 0, 0, 0, 0, 100),
        ("P1", "L1", "2026-01-02", 100, 0, 30, 0, 20, 0, 50),
        ("P1", "L1", "2026-01-03", 50, 0, 0, 0, 0, 0, 50),
        ("P1", "L2", "2026-01-02", 0, 0, 0, 20, 0, 0, 20),
        ("P1", "L2", "2026-01-03", 20, 0, 0, 0, 0, -5, 15),
    ]
    c = env.conn()
    rep = run_reconciliation(c)
    assert rep["all_passed"], [x for x in rep["checks"] if not x["passed"]]
    assert env.scalar("SELECT COUNT(*) FROM inventory_leg") == 5   # transfer = 2 legs


def test_empty_batch_header_only_is_noop(env):
    res = env.run(env.file([]))
    assert res.status == "NOOP" and res.files[0].status == "EMPTY_BATCH"
    assert env.scalar("SELECT COUNT(*) FROM inventory_movement") == 0
    assert env.scalar("SELECT COUNT(*) FROM daily_balance") == 0


def test_zero_byte_file_fails_schema_and_no_input_is_noop(env):
    empty = env.root / "zero.csv"
    empty.write_bytes(b"")
    res = env.run(empty)
    assert res.status == "FAILED" and res.files[0].status == "FAILED_SCHEMA"
    assert "no header" in res.files[0].error
    assert env.run().status == "NOOP"                    # no files at all


def test_missing_input_file_is_reported_not_crash(env):
    res = env.run(env.root / "does_not_exist.csv")
    assert res.status == "FAILED" and res.files[0].status == "FAILED_READ"


@pytest.mark.parametrize("col_idx,col", [(0, "movement_id"), (1, "movement_type"), (2, "product_id"),
                                          (3, "location_id"), (5, "quantity"), (6, "effective_date"), (7, "recorded_at")])
def test_missing_required_field_is_rejected(env, col_idx, col):
    r = row("x1", "receipt")
    r[col_idx] = "   "
    res = env.run(env.file([r, row("ok1")]))
    assert res.totals()["rows_loaded"] == 1 and res.totals()["rows_rejected"] == 1
    rej = env.scalar("SELECT reason_detail FROM reject_record WHERE reason_code='MISSING_REQUIRED_FIELD'")
    assert col in rej


@pytest.mark.parametrize("bad,reason", [
    (row("m1", "receipt", qty="ten"), "INVALID_QUANTITY"),
    (row("m2", "receipt", qty="10.5"), "INVALID_QUANTITY"),
    (row("m3", "receipt", qty="-5"), "QUANTITY_OUT_OF_RANGE"),
    (row("m4", "issue", qty="0"), "QUANTITY_OUT_OF_RANGE"),
    (row("m5", "adjustment", qty="0"), "QUANTITY_OUT_OF_RANGE"),
    (row("m6", "receipt", qty="1000001"), "QUANTITY_OUT_OF_RANGE"),
    (row("m7", "return"), "INVALID_MOVEMENT_TYPE"),
    (row("m8", eff="2026-13-45"), "INVALID_DATE"),
    (row("m9", eff="01/02/2026"), "INVALID_DATE"),
    (row("m10", rec="garbage"), "INVALID_TIMESTAMP"),
    (row("m11", eff="2026-01-10", rec="2026-01-05T10:00:00Z"), "FUTURE_EFFECTIVE_DATE"),
    (row("m12", product="P999"), "UNKNOWN_PRODUCT"),
    (row("m13", loc="L99"), "UNKNOWN_LOCATION"),
    (row("m14", "transfer", loc="L1", dest="L99"), "UNKNOWN_LOCATION"),
    (row("m15", "transfer", loc="L1", dest="L1"), "SAME_LOCATION_TRANSFER"),
    (row("m16", "transfer", dest=""), "MISSING_REQUIRED_FIELD"),
    (row("m17", "receipt", dest="L2"), "UNEXPECTED_DEST_LOCATION"),
    (row("bad id!", "receipt"), "INVALID_MOVEMENT_ID"),
])
def test_invalid_records_are_quarantined_with_reason(env, bad, reason):
    res = env.run(env.file([row("good"), bad]))
    assert res.files[0].rows_loaded == 1 and res.files[0].rows_rejected == 1
    c = env.conn()
    r = c.execute("SELECT * FROM reject_record").fetchone()
    assert r["reason_code"] == reason
    assert r["source_line"] == 3 and r["source_file"].endswith(".csv") and r["raw_record"]  # traceable


def test_malformed_ragged_rows_quarantined(env):
    p = env.root / "rag.csv"
    p.write_text("movement_id,movement_type,product_id,location_id,dest_location_id,quantity,effective_date,recorded_at\n"
                 "ok1,receipt,P1,L1,,5,2026-01-01,2026-01-01T10:00:00Z\n"
                 "short,receipt,P1\n"
                 "long,receipt,P1,L1,,5,2026-01-01,2026-01-01T10:00:00Z,EXTRA\n\n")
    res = env.run(p)
    f = res.files[0]
    assert (f.rows_read, f.rows_loaded, f.rows_rejected) == (3, 1, 2)     # blank line is not a record
    assert env.scalar("SELECT COUNT(*) FROM reject_record WHERE reason_code='MALFORMED_ROW'") == 2


def test_boundary_quantities_accepted(env):
    res = env.run(env.file([row("lo", qty=1), row("hi", qty=1_000_000, eff="2026-01-02"),
                            row("adj_lo", "adjustment", qty=-1_000_000, eff="2026-01-03")]))
    assert res.totals()["rows_loaded"] == 3
    assert env.scalar("SELECT closing_qty FROM daily_balance ORDER BY balance_date DESC LIMIT 1") == 1 + 1_000_000 - 1_000_000


def test_negative_balance_is_flagged_not_rejected(env):
    res = env.run(env.file([row("i1", "issue", qty=50, eff="2026-01-01")]))
    assert res.totals()["rows_loaded"] == 1
    rep = run_reconciliation(env.conn())
    neg = next(c for c in rep["checks"] if c["check"] == "negative_closing_balance_rows")
    assert neg["actual"] == 1 and neg["severity"] == "warning" and rep["all_passed"]


def test_whitespace_and_case_normalised(env):
    res = env.run(env.file([row(" r1 ", " RECEIPT ", product=" P1 ", loc=" L1 ", qty=" 7 ")]))
    assert res.totals()["rows_loaded"] == 1
    assert env.scalar("SELECT movement_type FROM inventory_movement") == "receipt"


def test_gap_days_carry_forward_zero_movement_rows(env):
    env.run(env.file([row("a", qty=10, eff="2026-01-01"), row("b", qty=5, eff="2026-01-05")]))
    rows = env.balances()
    assert [r[2] for r in rows] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    assert [r[9] for r in rows] == [10, 10, 10, 10, 15]
