PY ?= python3
export PYTHONPATH := src
DB ?= output/inventory.db

.PHONY: install test sample run reconcile verify report large benchmark evidence clean
install:    ; $(PY) -m pip install -r requirements.txt
test:       ; $(PY) -m pytest -q
sample:     ; $(PY) -m inventory_pipeline generate --out data/sample --records 1000 --seed 42
run:        ; $(PY) -m inventory_pipeline run --db $(DB) --reference data/sample/reference --input data/sample/incoming
reconcile:  ; $(PY) -m inventory_pipeline reconcile --db $(DB)
verify:     ; $(PY) -m inventory_pipeline verify --db $(DB) --labels data/sample/labels
report:     ; $(PY) -m inventory_pipeline report --db $(DB)
large:      ; rm -f output/large.db* && $(PY) -m inventory_pipeline generate --out data/large --records 150000 --products 200 --locations 25 --days 90 --seed 7 \
              && $(PY) -m inventory_pipeline run --db output/large.db --reference data/large/reference --input data/large/incoming \
              && $(PY) -m inventory_pipeline reconcile --db output/large.db --output-dir output/large \
              && $(PY) -m inventory_pipeline verify --db output/large.db --labels data/large/labels --output-dir output/large
benchmark:  ; $(PY) -m inventory_pipeline benchmark --records 100000
evidence:   ; $(PY) scripts/make_evidence.py
clean:      ; rm -rf output/*.db* data/large .pytest_cache
