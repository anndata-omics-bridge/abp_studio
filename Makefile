CONFIG ?= config/corpus.example.yaml

.PHONY: ui test-tool dag run clean test

ui:                       ## open the marimo corpus dashboard
	marimo edit src/apb_studio/dashboard.py

test-tool:                ## open the marimo test-data browser (convert via the apb CLI)
	marimo run src/apb_studio/ui/test_tool.py

dag:                      ## dry-run: what the pipeline would do
	snakemake -s workflow/Snakefile --configfile $(CONFIG) -n

run:                      ## bring the whole corpus up to date
	snakemake -s workflow/Snakefile --configfile $(CONFIG) --cores all

clean:                    ## delete all pipeline outputs (Snakemake-tracked)
	snakemake -s workflow/Snakefile --configfile $(CONFIG) --delete-all-output

test:
	pytest -q
