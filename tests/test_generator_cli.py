"""Reproducibility, label-based verification on generated data, CLI exit codes."""
import filecmp

from inventory_pipeline.cli import main
from inventory_pipeline.db import connect
from inventory_pipeline.generator import generate_dataset
from inventory_pipeline.ingest import run_pipeline
from inventory_pipeline.reconcile import run_reconciliation, verify_against_labels


def test_generator_is_deterministic_for_same_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate_dataset(a, seed=11, records=400)
    generate_dataset(b, seed=11, records=400)
    for rel in ("incoming/movements_batch_001.csv", "incoming/movements_batch_002_late.csv",
                "labels/expected_rejects.csv", "labels/expected_closing.csv"):
        assert filecmp.cmp(a / rel, b / rel, shallow=False), rel
    generate_dataset(tmp_path / "c", seed=12, records=400)
    assert not filecmp.cmp(a / "incoming/movements_batch_001.csv", tmp_path / "c/incoming/movements_batch_001.csv", shallow=False)


def test_pipeline_matches_independent_labels_on_generated_data(tmp_path):
    d = tmp_path / "d"
    generate_dataset(d, seed=5, records=3000, products=15, locations=5, days=40)
    db = tmp_path / "g.db"
    res = run_pipeline(db, [d / "incoming"], reference_dir=d / "reference")
    assert res.status == "SUCCESS"
    conn = connect(db)
    assert run_reconciliation(conn)["all_passed"]
    rep = verify_against_labels(conn, d / "labels")
    assert rep["all_passed"], rep
    # rerun of the whole directory is a no-op
    assert run_pipeline(db, [d / "incoming"]).status == "NOOP"


def test_generated_negative_cases(tmp_path):
    d = tmp_path / "d"
    generate_dataset(d, seed=1, records=200)
    db = tmp_path / "n.db"
    res = run_pipeline(db, [d / "negative_cases"], reference_dir=d / "reference")
    by = {f.source_file: f.status for f in res.files}
    assert by == {"empty_batch.csv": "EMPTY_BATCH", "schema_drift.csv": "FAILED_SCHEMA"}


def test_cli_end_to_end_and_exit_codes(tmp_path, capsys):
    d, out = tmp_path / "d", tmp_path / "out"
    assert main(["generate", "--out", str(d), "--records", "300", "--seed", "3"]) == 0
    args = ["run", "--db", str(out / "i.db"), "--reference", str(d / "reference"), "--input", str(d / "incoming"),
            "--output-dir", str(out)]
    assert main(args) == 0
    assert (out / "daily_balance.csv").exists() and (out / "rejects.csv").exists() and (out / "pipeline.log").exists()
    assert main(["reconcile", "--db", str(out / "i.db"), "--output-dir", str(out)]) == 0
    assert main(["verify", "--db", str(out / "i.db"), "--labels", str(d / "labels"), "--output-dir", str(out)]) == 0
    assert main(["report", "--db", str(out / "i.db")]) == 0
    assert main(args) == 0                                           # idempotent rerun -> NOOP, exit 0
    # no file loads successfully and one fails -> run status FAILED -> exit code 1
    assert main(["run", "--db", str(out / "i.db"), "--output-dir", str(out), "--input", str(d / "negative_cases")]) == 1
    # one good + one failed file -> PARTIAL_FAILURE -> exit code 2
    fresh = d / "incoming" / "movements_batch_003.csv"
    fresh.write_text("movement_id,movement_type,product_id,location_id,dest_location_id,quantity,effective_date,recorded_at\n"
                     "NEW1,receipt,P0001,L01,,5,2026-01-05,2026-01-05T10:00:00Z\n")
    assert main(["run", "--db", str(out / "i.db"), "--output-dir", str(out),
                 "--input", str(fresh), str(d / "negative_cases" / "schema_drift.csv")]) == 2


def test_generator_never_replays_same_event_twice_in_late_file(tmp_path):
    """Regression: identical + conflicting replays of one event made labels ambiguous at larger volumes."""
    import csv
    for seed in (7, 8, 9):
        d = tmp_path / f"s{seed}"
        s = generate_dataset(d, seed=seed, records=40_000, products=30, locations=8, days=60)
        ids = {}
        with open(d / "incoming/movements_batch_002_late.csv", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["movement_id"].startswith("MV") and int(r["movement_id"][2:]) < 38_000:
                    ids[r["movement_id"]] = ids.get(r["movement_id"], 0) + 1
        assert ids and max(ids.values()) == 1
        db = tmp_path / f"s{seed}.db"
        assert run_pipeline(db, [d / "incoming"], reference_dir=d / "reference").status == "SUCCESS"
        assert verify_against_labels(connect(db), d / "labels")["all_passed"]
