#!/usr/bin/env fish
# Integration runs that are neither published nor read by the manuscript, one command per line.
# Defaults: --format hdf5, --cores 3, --force. Run from the apb_studio folder.

# routine: after any apb2 or apb_studio change
uv run corpus run routine convert
uv run corpus run routine convert --format duckdb
uv run corpus run routine convert --format parquet
uv run corpus run routine aggregate_medpolish
uv run corpus run routine_pb proteobench_run
uv run corpus run problems convert
uv run corpus run problems proteobench_run
uv run corpus run problems aggregate_medpolish

# exports: apb-export must be on PATH (uv tool install --editable ../apb-export)
uv run corpus run routine export_msmu
uv run corpus run routine export_prolfqua
uv run corpus run routine export_proteopy
uv run corpus run routine export_alphapepttools
uv run corpus run problems export_msmu
uv run corpus run problems export_prolfqua
uv run corpus run problems export_proteopy
uv run corpus run problems export_alphapepttools
