
DOCS_PORT ?= 8103
SERVE_ON_PORT ?= $(wildcard $(HOME)/projects/bin/serve-on-port)

.DEFAULT_GOAL := help
.PHONY: help sync test-web test lint check check-full audit package docs docs-serve

help:                     ## show this help
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

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

package:                  ## build and inspect the wheel contract
	uv run --frozen --extra dev python scripts/package_smoke.py

docs:                     ## build strict documentation into public/
	uv run --frozen --group docs mkdocs build --strict

docs-serve:               ## preview docs at http://localhost:DOCS_PORT
	SERVE_PORT=$(DOCS_PORT) $(SERVE_ON_PORT) uv run --frozen --group docs mkdocs serve -a localhost:$(DOCS_PORT)
