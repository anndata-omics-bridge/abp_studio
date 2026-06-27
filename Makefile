CONFIG ?= config/corpus.example.yaml

.PHONY: ui dag run clean test

ui:                       ## open the marimo dashboard
	marimo edit src/apb_studio/dashboard.py

dag:                      ## dry-run: what the pipeline would do
	snakemake -s workflow/Snakefile --configfile $(CONFIG) -n

run:                      ## bring the whole corpus up to date
	snakemake -s workflow/Snakefile --configfile $(CONFIG) --cores all

clean:                    ## delete all pipeline outputs (Snakemake-tracked)
	snakemake -s workflow/Snakefile --configfile $(CONFIG) --delete-all-output

test:
	pytest -q
