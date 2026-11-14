import csv
from pathlib import Path

import pytest

from inventory_pipeline.config import REQUIRED_COLUMNS
from inventory_pipeline.db import connect
from inventory_pipeline.ingest import run_pipeline


def row(mid, mtype="receipt", product="P1", loc="L1", dest="", qty="10", eff="2026-01-01", rec=None):
    return [mid, mtype, product, loc, dest, str(qty), eff, rec or f"{eff}T10:00:00Z"]


def write_csv(path: Path, rows, header=REQUIRED_COLUMNS):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return path


class Env:
    def __init__(self, root: Path):
        self.root = root
        self.db = root / "t.db"
        self.ref = root / "ref"
        self.ref.mkdir()
        write_csv(self.ref / "products.csv", [["P1", "Prod 1", "EA"], ["P2", "Prod 2", "EA"]],
                  ["product_id", "product_name", "uom"])
        write_csv(self.ref / "locations.csv", [["L1", "Loc 1"], ["L2", "Loc 2"], ["L3", "Loc 3"]],
                  ["location_id", "location_name"])
        self._n = 0

    def file(self, rows, name=None, header=REQUIRED_COLUMNS):
        self._n += 1
        return write_csv(self.root / (name or f"in_{self._n}.csv"), rows, header)

    def run(self, *files, **kw):
        return run_pipeline(self.db, list(files), reference_dir=self.ref, **kw)

    def conn(self):
        return connect(self.db)

    def balances(self):
        c = self.conn()
        rows = [tuple(r) for r in c.execute(
            "SELECT product_id, location_id, balance_date, opening_qty, receipt_qty, issue_qty, transfer_in_qty, "
            "transfer_out_qty, adjustment_qty, closing_qty FROM daily_balance ORDER BY 1,2,3")]
        c.close()
        return rows

    def scalar(self, sql, params=()):
        c = self.conn()
        v = c.execute(sql, params).fetchone()[0]
        c.close()
        return v


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
