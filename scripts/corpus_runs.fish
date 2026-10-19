#!/usr/bin/env fish
# The runs we publish, the runs the manuscript figures read, and the contaminant-source
# comparison, one command per line.
# Defaults: --format hdf5, --cores 3, --force. Run from the apb_studio folder.

# public site: apb_publish_site must be empty or absent; deploy as the README says
uv run corpus run routine convert --strict --output-root apb_publish_output
uv run corpus run routine convert --format duckdb --strict --output-root apb_publish_output
uv run corpus run routine convert --format parquet --strict --output-root apb_publish_output
uv run corpus run routine_pb proteobench_run --strict --output-root apb_publish_output
uv run corpus run problems convert --strict --output-root apb_publish_output
uv run corpus run problems proteobench_run --strict --output-root apb_publish_output
uv run corpus run proteobench proteobench_pmultiqc --strict --output-root apb_publish_output
uv run corpus run proteobench_plasma proteobench_plasma --strict --output-root apb_publish_output
uv run corpus run proteobench_entrapment proteobench_entrapment --strict --output-root apb_publish_output
uv run corpus run directlfq convert_no_param --strict --output-root apb_publish_output
uv run corpus publish apb_publish_site --output-root apb_publish_output

# manuscript figures: apb_article/pipeline/scripts read these from apb_outputs
uv run corpus run routine convert
uv run corpus run routine convert --format duckdb
uv run corpus run routine convert --format parquet
uv run corpus run problems convert
uv run corpus run proteobench proteobench_pmultiqc
uv run corpus run proteobench convert_ion
uv run corpus run proteobench_plasma proteobench_plasma
uv run corpus run proteobench_entrapment proteobench_entrapment
uv run corpus run directlfq convert_no_param
uv run corpus run proteobench_f3 convert_ion --cores 1
uv run corpus run proteobench_f3 convert --cores 1
uv run corpus run directlfq_large_per_vendor convert_no_param --cores 1
uv run corpus run directlfq_large_per_vendor convert_no_param --format duckdb --cores 1
uv run corpus run directlfq_large_per_vendor convert_no_param --format parquet --cores 1

# contaminant source: apb-fasta (default) and vendor protein IDs (Cont_), each compared
# with the upstream ProteoBench scores in the corpus viewer
uv run corpus run proteobench proteobench_run
uv run corpus run proteobench proteobench_run_vendor_cont
