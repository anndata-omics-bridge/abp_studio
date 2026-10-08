#!/usr/bin/env fish
# Largest acquired directLFQ input for each of MaxQuant, Spectronaut and DIA-NN.
# Run all compatible levels in three formats with one scheduled dataset at a time.
argparse --name directlfq_large_per_vendor_formats h/help p/plan d/dry-run -- $argv
or exit 2

if set -q _flag_help
    printf '%s\n' \
        'Usage: directlfq_large_per_vendor_formats.fish [--plan] [--dry-run]' \
        '  --plan    Print commands without changing run files' \
        '  --dry-run Inspect all three formats with --no-force; preserve saved results' \
        'Default: force HDF5, DuckDB and Parquet sequentially with --cores 1, then check that each run settles.'
    exit 0
end

if test (count $argv) -gt 0
    printf 'Unexpected arguments: %s\n' (string join ' ' -- $argv) >&2
    exit 2
end

set -l preview no
if set -q _flag_plan
    set preview yes
else if not command -q uv
    printf '%s\n' 'uv is required' >&2
    exit 1
end

cd (path resolve (status dirname)/..)
or exit 1

function corpus_command --inherit-variable preview
    printf '%s\n' (string join ' ' -- (string escape -- uv run corpus $argv))
    if test "$preview" = no
        uv run corpus $argv
        or return $status
    end
end

if not set -q _flag_dry_run
    for storage_format in hdf5 duckdb parquet
        corpus_command run directlfq_large_per_vendor --workflow convert_no_param \
            --format "$storage_format" --cores 1 --force
        or exit $status
    end
end

for storage_format in hdf5 duckdb parquet
    corpus_command run directlfq_large_per_vendor --workflow convert_no_param \
        --format "$storage_format" --cores 1 --no-force --dry-run
    or exit $status
end
