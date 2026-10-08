#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

cd "$(dirname "${BASH_SOURCE[0]}")/.."

for storage_format in hdf5 duckdb parquet; do
    uv run corpus run directlfq_large_per_vendor --workflow convert_no_param \
        --format "$storage_format" --cores 1 --force
done

for storage_format in hdf5 duckdb parquet; do
    uv run corpus run directlfq_large_per_vendor --workflow convert_no_param \
        --format "$storage_format" --cores 1 --no-force --dry-run
done
