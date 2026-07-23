APP_PORT ?= 8051
PYTHON ?= python

.DEFAULT_GOAL := help
.PHONY: help corpus-runner fixture-manager test

help:                     ## show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

corpus-runner:            ## run APB Studio — Corpus Runner
	APB_STUDIO_PORT=$(APP_PORT) PYTHONPATH=src $(PYTHON) -m apb_studio.dashboard

fixture-manager:          ## run APB Studio — Fixture Manager
	PYTHONPATH=src $(PYTHON) -m apb_studio.testdata_app

test:                     ## run the test suite
	pytest -q
