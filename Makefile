APP_PORT ?= 8051

.DEFAULT_GOAL := help
.PHONY: help sync corpus-runner fixture-manager test lint check check-full audit package docs docs-serve

help:                     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

corpus-runner:            ## run APB Studio — Corpus Runner
	APB_STUDIO_PORT=$(APP_PORT) uv run --frozen apb-studio-corpus-runner

fixture-manager:          ## run APB Studio — Fixture Manager
	uv run --frozen apb-studio-fixture-manager

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

package:                  ## build and inspect the wheel contract
	uv run --frozen --extra dev python scripts/package_smoke.py

docs:                     ## build strict documentation into public/
	uv run --frozen --group docs mkdocs build --strict

docs-serve:               ## preview docs at http://127.0.0.1:8000
	uv run --frozen --group docs mkdocs serve
