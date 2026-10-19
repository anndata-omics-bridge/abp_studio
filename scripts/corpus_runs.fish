#!/usr/bin/env fish
# Every run we serve, one command per line, all into the configured output root; the
# manuscript figures read the same runs. Run from the apb_studio folder.
# Defaults: --format hdf5, --cores 3, --force. --strict refuses a corpus with missing datasets.

# conversion
uv run corpus run routine convert --strict
uv run corpus run routine convert --format duckdb --strict
uv run corpus run routine convert --format parquet --strict
uv run corpus run problems convert --strict
uv run corpus run directlfq convert_no_param --strict
uv run corpus run proteobench convert_ion --strict

# ProteoBench scoring
uv run corpus run routine_pb proteobench_run --strict
uv run corpus run problems proteobench_run --strict
uv run corpus run proteobench proteobench_pmultiqc --strict
uv run corpus run proteobench_plasma proteobench_plasma --strict
uv run corpus run proteobench_entrapment proteobench_entrapment --strict

# contaminant source: apb-fasta (default) and vendor protein IDs (Cont_), each compared
# with the upstream ProteoBench scores in the corpus viewer
uv run corpus run proteobench proteobench_run --strict
uv run corpus run proteobench proteobench_run_vendor_cont --strict

# manuscript F3: one dataset at a time
uv run corpus run proteobench_f3 convert_ion --cores 1 --strict
uv run corpus run proteobench_f3 convert --cores 1 --strict
uv run corpus run directlfq_large_per_vendor convert_no_param --cores 1 --strict
uv run corpus run directlfq_large_per_vendor convert_no_param --format duckdb --cores 1 --strict
uv run corpus run directlfq_large_per_vendor convert_no_param --format parquet --cores 1 --strict

# public site: copies every run of the output root; apb_publish_site must be empty or absent
uv run corpus publish apb_publish_site
