"""Re-generates docs/execution_evidence.md by actually running everything (no hand-edited output)."""
import json, os, shutil, sqlite3, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
CLI = [sys.executable, "-m", "inventory_pipeline"]
parts: list[str] = []


def sh(title, cmd, lang="text", tail=None, env=None, show=None):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env or ENV)
    out = (p.stdout + ("" if not p.stderr else "")).strip()
    if tail:
        out = "\n".join(out.splitlines()[-tail:])
    shown = show or " ".join(str(c) for c in cmd[1:] if not str(c).startswith("/"))
    parts.append(f"### {title}\n\n`{shown}` (exit code {p.returncode})\n\n```{lang}\n{out}\n```\n")
    return p


def log_lines(title, cmd):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    keep = [l.split(" run_id=")[0][:19] + " " + l.split(" run_id=", 1)[1].split(" ", 1)[1] if " run_id=" in l else l
            for l in p.stderr.splitlines()]
    parts.append(f"### {title}\n\n`(exit code {p.returncode})` - structured log lines:\n\n```text\n" + "\n".join(keep) + "\n```\n")
    return p


for d in ("output", "data/sample"):
    shutil.rmtree(ROOT / d, ignore_errors=True)
(ROOT / "output").mkdir()
parts.append("# Execution evidence\n\nEverything below was produced by `python scripts/make_evidence.py` (real runs, nothing hand-edited).\n")

sh("1. Unit / integration tests", [sys.executable, "-m", "pytest", "-v", "--tb=short", "-p", "no:cacheprovider"], tail=70)
sh("2. Generate the reproducible sample (seed 42)", [*CLI, "generate", "--out", "data/sample", "--records", "1000", "--seed", "42"], "json")

db = "output/inventory.db"
args = ["--db", db, "--output-dir", "output"]
log_lines("3. First run: reference load + 2 files (main batch, then late/backdated batch)",
          [*CLI, "run", *args, "--reference", "data/sample/reference", "--input", "data/sample/incoming"])
log_lines("4. Rerun of the same input (idempotent: every file skipped, state unchanged)",
          [*CLI, "run", *args, "--reference", "data/sample/reference", "--input", "data/sample/incoming"])
log_lines("5. Forced reprocess (--force): row-level idempotency, 0 rows loaded",
          [*CLI, "run", *args, "--input", "data/sample/incoming", "--force"])
log_lines("6. Failure handling: empty batch + unexpected schema change",
          [*CLI, "run", *args, "--input", "data/sample/negative_cases"])
sh("7. Reconciliation (assertions over the DB)", [*CLI, "reconcile", *args])
sh("8. Verification against independent generator labels", [*CLI, "verify", *args, "--labels", "data/sample/labels"])
sh("9. Sample analytical queries", [*CLI, "report", *args])

# backdated-correction demonstration on a separate DB
demo = ROOT / "output" / "backdated_demo.db"
for suffix in ("", "-wal", "-shm"):
    Path(str(demo) + suffix).unlink(missing_ok=True)
subprocess.run([*CLI, "run", "--db", str(demo), "--output-dir", "output/demo_tmp", "--reference", "data/sample/reference",
                "--input", "data/sample/incoming/movements_batch_001.csv"], cwd=ROOT, env=ENV, capture_output=True)
c = sqlite3.connect(demo)
before = {(p, l, d): q for p, l, d, q in c.execute("SELECT product_id, location_id, balance_date, closing_qty FROM daily_balance")}
end_before = c.execute("SELECT value FROM pipeline_state WHERE key='balance_end_date'").fetchone()[0]
c.close()
subprocess.run([*CLI, "run", "--db", str(demo), "--output-dir", "output/demo_tmp",
                "--input", "data/sample/incoming/movements_batch_002_late.csv"], cwd=ROOT, env=ENV, capture_output=True)
c = sqlite3.connect(demo)
after = {(p, l, d): q for p, l, d, q in c.execute("SELECT product_id, location_id, balance_date, closing_qty FROM daily_balance")}
mv = c.execute("SELECT movement_id, movement_type, product_id, location_id, quantity, effective_date, recorded_at "
               "FROM inventory_movement WHERE is_backdated=1 ORDER BY effective_date, movement_id LIMIT 1").fetchone()
changed = [k for k in before if before[k] != after.get(k)]
lines = [f"Batch 1 loaded: {len(before)} balance rows, end date {end_before}.",
         f"Batch 2 (late file) loaded: {len(after)} balance rows, {len(changed)} pre-existing rows rewritten, "
         f"{c.execute('SELECT COUNT(*) FROM inventory_movement WHERE is_backdated=1').fetchone()[0]} movements flagged is_backdated.",
         f"Example backdated movement: id={mv[0]} type={mv[1]} product={mv[2]} location={mv[3]} qty={mv[4]} "
         f"effective_date={mv[5]} recorded_at={mv[6]}", "", "closing_qty for that product/location, before -> after the late batch:"]
for d, in c.execute("SELECT balance_date FROM daily_balance WHERE product_id=? AND location_id=? AND balance_date>=? ORDER BY 1 LIMIT 6",
                    (mv[2], mv[3], mv[5])):
    k = (mv[2], mv[3], d)
    lines.append(f"  {d}: {before.get(k)} -> {after[k]}")
c.close()
shutil.rmtree(ROOT / "output/demo_tmp", ignore_errors=True)
parts.append("### 10. Backdated correction demonstration\n\n```text\n" + "\n".join(lines) + "\n```\n")

p = subprocess.run([*CLI, "benchmark", "--records", "100000", "--seed", "7", "--output-dir", "output"], cwd=ROOT,
                   capture_output=True, text=True, env=ENV)
b = json.loads(p.stdout)
rows = ["| strategy | total s | batch 1 read+validate s | batch 1 load s | batch 1 rebuild s | batch 2 (late) rebuild s |", "|---|---|---|---|---|---|"]
for name, v in b["strategies"].items():
    f1, f2 = list(v["files"].values())
    rows.append(f"| {name} | {v['total_seconds']} | {f1['read_validate']} | {f1['load']} | {f1['rebuild_balances']} | {f2['rebuild_balances']} |")
t = b["tail_only_vs_full_rebuild"]
parts.append("### 11. Performance (100k clean events, 200 products x 25 locations x 90 days; "
             f"{b['rows_in_files']} rows in files)\n\nPython {b['python']}, SQLite {b['sqlite']}, single thread.\n\n" + "\n".join(rows) +
             f"\n\nTail-only vs full rebuild for the late batch: incremental {t['late_batch_incremental']['seconds']}s "
             f"({t['late_batch_incremental']['pairs']} pairs, {t['late_batch_incremental']['balance_rows_written']} rows) vs full recompute "
             f"{t['full_recompute_all_pairs']['seconds']}s ({t['full_recompute_all_pairs']['pairs']} pairs, "
             f"{t['full_recompute_all_pairs']['balance_rows_written']} rows) -> **{t['speedup_x']}x**.\n")

# scale run: 150k clean events -> reconcile + verify against labels
for d in ("data/large",):
    shutil.rmtree(ROOT / d, ignore_errors=True)
Path(ROOT / "output/large.db").unlink(missing_ok=True)
sh("12. Scale run: 150k clean events (155,569 input rows) - generate, run, reconcile, verify",
   [sys.executable, "-c",
    "import subprocess,sys;C=[sys.executable,'-m','inventory_pipeline'];"
    "r=lambda a:subprocess.run(C+a,capture_output=True,text=True);"
    "g=r(['generate','--out','data/large','--records','150000','--products','200','--locations','25','--days','90','--seed','7']);"
    "u=r(['run','--db','output/large.db','--output-dir','output/large','--reference','data/large/reference','--input','data/large/incoming']);"
    "print(*[l.split(' run_id=')[1].split(' ',1)[1] for l in u.stderr.splitlines() if 'file=' in l or 'run finished' in l],sep='\\n');"
    "c=r(['reconcile','--db','output/large.db','--output-dir','output/large']);print('reconcile:',c.stdout.strip().splitlines()[-1],'| failed checks:',c.stdout.count('FAIL  '));"
    "v=r(['verify','--db','output/large.db','--labels','data/large/labels','--output-dir','output/large']);print('verify vs labels:',v.stdout.strip().splitlines()[-1],'| failed checks:',v.stdout.count('FAIL  '))"],
   show="make large  (generate -> run -> reconcile -> verify)")
shutil.rmtree(ROOT / "data/large", ignore_errors=True)
for f in (ROOT / "output").glob("large.db*"):
    f.unlink()
for suffix in ("-wal", "-shm"):
    for f in (ROOT / "output").glob(f"*.db{suffix}"):
        f.unlink()
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/execution_evidence.md").write_text("\n".join(parts))
print("wrote docs/execution_evidence.md")
