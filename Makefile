
.DEFAULT_GOAL := help
.PHONY: help sync corpus-run corpus-check corpus-routine corpus-clean fixture-manager test-web test lint check check-full audit carpets package docs docs-serve

CORPUS_FIXTURES ?= 0
CORPUS_CORES ?= 10
CORPUS_PIPELINE ?= full
CORPUS_RUN_FLAGS ?=

help:                     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

corpus-run:               ## run whole corpus: CORPUS_PIPELINE=full, CORPUS_CORES=10, CORPUS_RUN_FLAGS="--level ion"
	uv run --frozen python scripts/run_corpus.py --pipeline $(CORPUS_PIPELINE) \
		--fixtures $(CORPUS_FIXTURES) --cores $(CORPUS_CORES) $(CORPUS_RUN_FLAGS)

corpus-check:             ## dry-run the same selection: a fresh snapshot must schedule no jobs
	uv run --frozen python scripts/run_corpus.py --pipeline $(CORPUS_PIPELINE) \
		--fixtures $(CORPUS_FIXTURES) --cores $(CORPUS_CORES) $(CORPUS_RUN_FLAGS) --dry-run

corpus-routine:           ## run the named routine gate: selections/routine.txt
	uv run --frozen python scripts/run_corpus.py --pipeline $(CORPUS_PIPELINE) \
		--datasets selections/routine.txt --cores $(CORPUS_CORES) $(CORPUS_RUN_FLAGS)

corpus-clean:             ## clean one pipeline's managed artifacts: CORPUS_PIPELINE=full (all stages)
	uv run --frozen python scripts/clean_corpus.py --pipeline $(CORPUS_PIPELINE)

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
