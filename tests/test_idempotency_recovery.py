"""Duplicates, reruns, schema drift, partial failure + retry, backdated corrections."""
import pytest

import inventory_pipeline.ingest as ingest_mod
from conftest import row
from inventory_pipeline.reconcile import run_reconciliation

BASE = [row("r1", qty=100, eff="2026-01-01"), row("i1", "issue", qty=30, eff="2026-01-02"),
        row("r2", qty=40, eff="2026-01-03")]


def test_duplicate_in_file_identical_and_conflicting(env):
    res = env.run(env.file([row("d1", qty=10), row("d1", qty=10), row("d1", qty=11), row("d2", qty=1)]))
    assert res.totals()["rows_loaded"] == 2
    reasons = sorted(r[0] for r in env.conn().execute("SELECT reason_code FROM reject_record"))
    assert reasons == ["DUPLICATE_CONFLICT", "DUPLICATE_EVENT"]
    assert env.scalar("SELECT quantity FROM inventory_movement WHERE movement_id='d1'") == 10   # first wins


def test_rerun_same_file_is_skipped_and_state_unchanged(env):
    f = env.file(BASE + [row("bad", qty="x")])
    r1 = env.run(f)
    snap = (env.balances(), env.scalar("SELECT COUNT(*) FROM inventory_movement"),
            env.scalar("SELECT COUNT(*) FROM reject_record"))
    r2 = env.run(f)
    assert r2.status == "NOOP" and r2.files[0].status == "SKIPPED_ALREADY_LOADED"
    assert snap == (env.balances(), env.scalar("SELECT COUNT(*) FROM inventory_movement"),
                    env.scalar("SELECT COUNT(*) FROM reject_record"))
    assert r1.status == "SUCCESS"


def test_forced_rerun_is_row_level_idempotent(env):
    f = env.file(BASE + [row("bad", qty="x")])
    env.run(f)
    snap = (env.balances(), env.scalar("SELECT COUNT(*) FROM inventory_movement"),
            env.scalar("SELECT COUNT(*) FROM reject_record"))
    r = env.run(f, force=True)
    assert r.files[0].rows_loaded == 0 and r.files[0].rows_skipped_existing == 3 and r.files[0].rows_rejected == 1
    assert snap == (env.balances(), env.scalar("SELECT COUNT(*) FROM inventory_movement"),
                    env.scalar("SELECT COUNT(*) FROM reject_record"))     # reject_id is deterministic -> no dupes


def test_same_event_in_new_file_is_skipped_and_conflict_is_rejected(env):
    env.run(env.file(BASE))
    res = env.run(env.file([row("r1", qty=100, eff="2026-01-01"), row("i1", "issue", qty=31, eff="2026-01-02"),
                            row("new", qty=1, eff="2026-01-03")]))
    f = res.files[0]
    assert (f.rows_loaded, f.rows_skipped_existing, f.rows_rejected) == (1, 1, 1)
    assert env.scalar("SELECT quantity FROM inventory_movement WHERE movement_id='i1'") == 30   # ledger untouched
    assert env.scalar("SELECT reason_code FROM reject_record") == "DUPLICATE_CONFLICT"


def test_unexpected_schema_change_fails_file_but_other_files_load(env):
    drifted = env.file([["x", "receipt", "P1", "L1", "", "5", "2026-01-01", "2026-01-01T10:00:00Z"]],
                       header=["movement_id", "movement_type", "product_id", "location_id", "dest_location_id",
                               "qty", "effective_date", "recorded_at"])
    good = env.file(BASE)
    res = env.run(drifted, good)
    assert res.status == "PARTIAL_FAILURE"
    assert [f.status for f in res.files] == ["FAILED_SCHEMA", "SUCCESS"]
    assert "quantity" in res.files[0].error and env.scalar("SELECT COUNT(*) FROM inventory_movement") == 3
    assert env.scalar("SELECT status FROM file_load WHERE source_file=?", (drifted.name,)) == "FAILED_SCHEMA"


def test_extra_column_is_tolerated_with_warning(env):
    f = env.file([r + ["note"] for r in BASE],
                 header=[*["movement_id", "movement_type", "product_id", "location_id", "dest_location_id",
                           "quantity", "effective_date", "recorded_at"], "notes"])
    res = env.run(f)
    assert res.status == "SUCCESS" and "extra columns" in res.files[0].warnings[0]


def test_partial_failure_rolls_back_atomically_then_retry_succeeds(env, monkeypatch):
    f = env.file(BASE)
    real = ingest_mod.rebuild_balances

    def boom(*a, **k):
        raise RuntimeError("simulated crash mid-load")
    monkeypatch.setattr(ingest_mod, "rebuild_balances", boom)
    r1 = env.run(f)
    assert r1.status == "FAILED" and r1.files[0].status == "FAILED_PROCESSING"
    assert "simulated crash" in r1.error
    # nothing leaked: ledger, legs, balances and rejects all rolled back
    for t in ("inventory_movement", "inventory_leg", "daily_balance", "reject_record"):
        assert env.scalar(f"SELECT COUNT(*) FROM {t}") == 0
    assert env.scalar("SELECT status FROM pipeline_run ORDER BY started_at DESC LIMIT 1") == "FAILED"

    monkeypatch.setattr(ingest_mod, "rebuild_balances", real)      # operator fixes the cause, re-runs
    r2 = env.run(f)                                                # FAILED files are NOT skipped
    assert r2.status == "SUCCESS" and r2.totals()["rows_loaded"] == 3
    assert run_reconciliation(env.conn())["all_passed"]


def test_backdated_correction_rewrites_tail_and_matches_clean_rebuild(env, tmp_path):
    env.run(env.file(BASE))
    before = {r[2]: r[9] for r in env.balances()}
    assert before == {"2026-01-01": 100, "2026-01-02": 70, "2026-01-03": 110}

    late = env.file([row("late1", "adjustment", qty=-8, eff="2026-01-01", rec="2026-01-04T09:00:00Z")])
    res = env.run(late)
    assert res.files[0].backdated_loaded == 1
    after = {r[2]: r[9] for r in env.balances()}
    assert after == {"2026-01-01": 92, "2026-01-02": 62, "2026-01-03": 102}     # every later day shifts by -8
    assert env.scalar("SELECT is_backdated FROM inventory_movement WHERE movement_id='late1'") == 1
    assert run_reconciliation(env.conn())["all_passed"]

    # Property: incremental result == one-shot build of the same events
    from conftest import Env
    fresh = Env(tmp_path / "fresh") if (tmp_path / "fresh").mkdir() is None else None
    fresh.run(fresh.file(BASE + [row("late1", "adjustment", qty=-8, eff="2026-01-01", rec="2026-01-04T09:00:00Z")]))
    assert fresh.balances() == env.balances()


def test_backdated_before_pair_first_day_backfills_leading_rows(env, tmp_path):
    env.run(env.file([row("a", qty=10, eff="2026-01-05")]))
    env.run(env.file([row("b", qty=3, eff="2026-01-02", rec="2026-01-06T09:00:00Z")]))
    assert [(r[2], r[3], r[9]) for r in env.balances()] == [
        ("2026-01-02", 0, 3), ("2026-01-03", 3, 3), ("2026-01-04", 3, 3), ("2026-01-05", 3, 13)]


def test_later_file_extends_idle_pairs_forward(env):
    env.run(env.file([row("a", "receipt", loc="L1", qty=10, eff="2026-01-01")]))
    env.run(env.file([row("b", "receipt", loc="L2", qty=1, eff="2026-01-04")]))
    l1 = [r for r in env.balances() if r[1] == "L1"]
    assert [r[2] for r in l1][-1] == "2026-01-04" and l1[-1][9] == 10 and len(l1) == 4
    assert run_reconciliation(env.conn())["all_passed"]


def test_out_of_order_rows_within_file_give_same_result(env, tmp_path):
    rows = [row("a", qty=10, eff="2026-01-01"), row("b", "issue", qty=4, eff="2026-01-02"),
            row("c", qty=7, eff="2026-01-03")]
    env.run(env.file(rows))
    from conftest import Env
    (tmp_path / "rev").mkdir()
    other = Env(tmp_path / "rev")
    other.run(other.file(list(reversed(rows))))
    assert env.balances() == other.balances()


def test_naive_and_grouped_strategies_are_equivalent(env, tmp_path):
    from conftest import Env
    (tmp_path / "n").mkdir()
    other = Env(tmp_path / "n")
    files = [BASE, [row("late", qty=5, eff="2026-01-01", rec="2026-01-09T00:00:00Z"),
                    row("t", "transfer", loc="L1", dest="L3", qty=9, eff="2026-01-03", rec="2026-01-09T00:00:00Z")]]
    for fl in files:
        env.run(env.file(fl), strategy="grouped")
        other.run(other.file(fl), strategy="naive")
    assert env.balances() == other.balances()


def test_run_without_reference_data_fails_cleanly(tmp_path):
    from inventory_pipeline.ingest import run_pipeline
    from conftest import write_csv
    f = write_csv(tmp_path / "m.csv", BASE)
    res = run_pipeline(tmp_path / "x.db", [f])
    assert res.status == "FAILED" and "reference data missing" in res.error
