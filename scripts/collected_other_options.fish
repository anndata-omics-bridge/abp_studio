#!/usr/bin/env fish
# Every corpus run that is not staging, one command per line, into the configured output root.
# Nothing here reaches fgcz-r-035: that site is built by staging_35.fish alone.
# Run the lines you need from the apb_studio folder.
# Defaults: --format hdf5, --cores 3, --force. --strict refuses a corpus with missing datasets.

# routine: after any apb2 or apb_studio change
uv run corpus run routine convert --strict
uv run corpus run routine convert --format duckdb --strict
uv run corpus run routine convert --format parquet --strict
uv run corpus run routine aggregate_medpolish
uv run corpus run routine_pb proteobench_run --strict
uv run corpus run problems convert --strict
uv run corpus run problems proteobench_run --strict
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

# larger conversion corpora
uv run corpus run directlfq convert_no_param --strict
uv run corpus run proteobench convert_peptidoform_ion --strict

# ProteoBench scoring
uv run corpus run proteobench proteobench_pmultiqc --strict
uv run corpus run proteobench_plasma proteobench_plasma --strict
uv run corpus run proteobench_entrapment proteobench_entrapment --strict

# deciding proteins: FASTA matches (default) and the vendor's proteins, each compared
# with the upstream ProteoBench scores in the corpus viewer
uv run corpus run proteobench proteobench_run --strict
uv run corpus run proteobench proteobench_run_vendor --strict

# manuscript Figure 5: one dataset at a time
uv run corpus run proteobench_f3 convert_peptidoform_ion --cores 1 --strict
uv run corpus run proteobench_f3 convert --cores 1 --strict
uv run corpus run large_inputs convert_no_param --cores 1 --strict
uv run corpus run large_inputs convert_no_param --format duckdb --cores 1 --strict
uv run corpus run large_inputs convert_no_param --format parquet --cores 1 --strict
