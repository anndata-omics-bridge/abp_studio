
.DEFAULT_GOAL := help
.PHONY: help sync corpus-run corpus-check corpus-routine corpus-clean corpus-viewer corpus-viewer-shutdown corpus-viewer-restart corpus-export fixture-manager test-web test lint check check-full audit carpets package docs docs-serve

CORPUS_FIXTURES ?= 0
CORPUS_CORES ?= 10
CORPUS_WORKFLOW ?= convert
CORPUS_FORMAT ?= hdf5
CORPUS_CSV ?= corpuses/all.csv
CORPUS_ROUTINE_CSV ?= corpuses/routine.csv
CORPUS_RUN ?=
CORPUS_RUN_FLAGS ?=

help:                     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

corpus-run:               ## run the selected Python workflow over existing corpus.csv files
	uv run --frozen python scripts/run_corpus.py --workflow $(CORPUS_WORKFLOW) --format $(CORPUS_FORMAT) \
		--corpus $(CORPUS_CSV) --fixtures $(CORPUS_FIXTURES) --cores $(CORPUS_CORES) $(CORPUS_RUN_FLAGS)

corpus-check:             ## dry-run the same selection: a fresh snapshot must schedule no jobs
	uv run --frozen python scripts/run_corpus.py --workflow $(CORPUS_WORKFLOW) --format $(CORPUS_FORMAT) \
		--corpus $(CORPUS_CSV) --fixtures $(CORPUS_FIXTURES) --cores $(CORPUS_CORES) $(CORPUS_RUN_FLAGS) --dry-run

corpus-routine:           ## run the named routine gate: selections/routine.txt
	uv run --frozen python scripts/run_corpus.py --workflow $(CORPUS_WORKFLOW) --format $(CORPUS_FORMAT) \
		--corpus $(CORPUS_ROUTINE_CSV) --cores $(CORPUS_CORES) $(CORPUS_RUN_FLAGS)

corpus-clean:             ## move generated results to history: CORPUS_RUN=/absolute/run/directory
	uv run --frozen python scripts/clean_corpus.py "$(CORPUS_RUN)"

corpus-viewer:            ## show persisted settings, CSV inputs, progress, and JSON reports
	uv run --frozen apb-studio-corpus serve

corpus-viewer-shutdown:   ## stop the corpus viewer
	uv run --frozen apb-studio-corpus shutdown

corpus-viewer-restart:    ## restart the corpus viewer
	uv run --frozen apb-studio-corpus restart

corpus-export:            ## export minimal corpus.csv and the separate workflow resource table
	uv run --frozen apb-studio-fixtures corpus
	uv run --frozen apb-studio-corpus select --corpus corpuses/all.csv --datasets selections/routine.txt --output corpuses/routine.csv

fixture-manager:          ## serve the fixture-store viewer (apb-studio-fixtures serve)
	uv run --frozen apb-studio-fixtures serve

test-web:                 ## run the viewer's architecture tests under Node
	@command -v node >/dev/null || { echo "node is required for the viewer tests"; exit 1; }
	node --test "tests/web/*.test.mjs"

sync:                     ## install the frozen development and docs environment
	uv sync --frozen --extra dev --group docs

test:                     ## run the test suite
	uv run --frozen --extra dev pytest -q

lint:                     ## run Ruff over the repository
	uv run --frozen --extra dev ruff check .

check:                    ## run the commit-stage quality gate
	uv run pre-commit run --hook-stage pre-commit --all-files

check-full:               ## run the push-stage quality gate
	uv run pre-commit run --hook-stage pre-push --all-files

audit:                    ## audit locked dependencies
	uv run pre-commit run dependency-audit --hook-stage manual --all-files

carpets:                  ## report carpet diagnostics (3 of 5 checks; pyan3 fails here)
	uv run pre-commit run carpet-scan --hook-stage manual --all-files
	@echo "HTML: build/carpet-report.html"

package:                  ## build and inspect the wheel contract
	uv run --frozen --extra dev python scripts/package_smoke.py

docs:                     ## build strict documentation into public/
	uv run --frozen --group docs mkdocs build --strict

docs-serve:               ## preview docs at http://127.0.0.1:8000
	uv run --frozen --group docs mkdocs serve
