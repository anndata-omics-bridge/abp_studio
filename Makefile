# Prefer the scaffolded corpus when it exists (matches the dashboard), else the bundled example.
# The example has placeholder roots, so `dag`/`run` only resolve after `make scaffold` (or CONFIG=).
CONFIG ?= $(if $(wildcard config/corpus.yaml),config/corpus.yaml,config/corpus.example.yaml)
OUT    ?= config/corpus.yaml
DATA   ?= ../apb/test_data_download/json_dir
CORES  ?= 3   # bounded by default: some vendor files are ~600 MB, so `--cores all` can exhaust RAM

.DEFAULT_GOAL := help
.PHONY: help scaffold app ui dag run clean test

scaffold:                 ## scan DATA (default: apb ProteoBench cache) → corpus.yaml (OUT, DATA to override); needs apb
	PYTHONPATH=src python -m apb_studio.scaffold --data $(DATA) --output $(OUT)

help:                     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

app:                      ## run the dashboard as an app (clean UI, no code cells)
	marimo run src/apb_studio/dashboard.py

ui:                       ## edit the dashboard notebook (cells + code, for development)
	marimo edit src/apb_studio/dashboard.py

dag:                      ## dry-run the pipeline (needs a real corpus: `make scaffold` first, or CONFIG=your.yaml — the example config has placeholder paths)
	snakemake -s workflow/Snakefile --configfile $(CONFIG) -n

run:                      ## bring the whole corpus up to date (same corpus prerequisite as `dag`)
	snakemake -s workflow/Snakefile --configfile $(CONFIG) --cores $(CORES) --keep-going

clean:                    ## delete all pipeline outputs (Snakemake-tracked)
	snakemake -s workflow/Snakefile --configfile $(CONFIG) --delete-all-output

test:                     ## run the test suite
	pytest -q
