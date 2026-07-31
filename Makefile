APP_PORT ?= 8051
CORPUS_RUNNER_PID_FILE ?= $(CURDIR)/.apb-studio-corpus-runner-$(APP_PORT).pid

.DEFAULT_GOAL := help
.PHONY: help sync corpus-runner corpus-runner-stop corpus-run corpus-check corpus-clean fixture-manager test lint check check-full audit package docs docs-serve

CORPUS_FIXTURES ?= 10
CORPUS_CORES ?= 10

help:                     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

corpus-runner: corpus-runner-stop  ## restart APB Studio — Corpus Runner
	@trap 'rm -f "$(CORPUS_RUNNER_PID_FILE)"' EXIT; \
		VIRTUAL_ENV= APB_STUDIO_PORT=$(APP_PORT) uv run --frozen sh -c \
		'echo $$$$ > "$(CORPUS_RUNNER_PID_FILE)"; exec apb-studio-corpus-runner'; \
		status=$$?; \
		if test $$status -eq 130 || test $$status -eq 143; then exit 0; fi; \
		exit $$status

corpus-runner-stop:       ## stop the managed Corpus Runner
	@pid_file="$(CORPUS_RUNNER_PID_FILE)"; \
		pids=""; \
		if test -f "$$pid_file"; then \
			pid="$$(tr -d '[:space:]' < "$$pid_file")"; \
			case "$$pid" in \
				''|*[!0-9]*) rm -f "$$pid_file" ;; \
				*) if kill -0 "$$pid" 2>/dev/null; then pids="$$pid"; fi ;; \
			esac; \
		fi; \
		if command -v lsof >/dev/null 2>&1; then \
			for pid in $$(lsof -tiTCP:$(APP_PORT) -sTCP:LISTEN 2>/dev/null || true); do \
				case " $$pids " in *" $$pid "*) ;; *) pids="$$pids $$pid" ;; esac; \
			done; \
		fi; \
		if test -z "$${pids## }"; then \
			rm -f "$$pid_file"; \
			echo "Corpus Runner is not running on port $(APP_PORT)."; \
			exit 0; \
		fi; \
		for pid in $$pids; do \
			command="$$(ps -p "$$pid" -o command= 2>/dev/null || true)"; \
			case "$$command" in \
				*apb-studio-corpus-runner*) ;; \
				*) echo "Refusing to stop PID $$pid on port $(APP_PORT): $$command"; exit 1 ;; \
			esac; \
		done; \
		echo "Stopping Corpus Runner on port $(APP_PORT) (PID$$(test "$$(echo $$pids | wc -w | tr -d ' ')" = 1 || printf 's') $$pids)..."; \
		kill -INT $$pids 2>/dev/null || true; \
		attempt=0; \
		while test $$attempt -lt 50; do \
			alive=""; \
			for pid in $$pids; do \
				if kill -0 "$$pid" 2>/dev/null; then alive="$$alive $$pid"; fi; \
			done; \
			if test -z "$${alive## }"; then break; fi; \
			sleep 0.1; \
			attempt=$$((attempt + 1)); \
		done; \
		if test -n "$${alive## }"; then \
			echo "Corpus Runner did not stop cleanly (PID$${alive})."; \
			exit 1; \
		fi; \
		rm -f "$$pid_file"

corpus-run:               ## run the corpus headlessly over CORPUS_FIXTURES fixtures (0 = all)
	uv run --frozen python scripts/run_corpus.py \
		--fixtures $(CORPUS_FIXTURES) --cores $(CORPUS_CORES)

corpus-check:             ## dry-run the same sample: confirms a fresh snapshot schedules no jobs
	uv run --frozen python scripts/run_corpus.py \
		--fixtures $(CORPUS_FIXTURES) --cores $(CORPUS_CORES) --dry-run

corpus-clean:             ## run the packaged Snakemake clean rule over the whole corpus
	uv run --frozen python scripts/clean_corpus.py

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
