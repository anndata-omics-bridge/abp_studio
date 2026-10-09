#!/usr/bin/env fish
# Run the published corpus:workflow:format combinations into apb_publish_output, then copy the
# corpus viewer and those runs into SITE for a plain file server. The fixture store is served
# beside them as SITE/fixtures, for example: rsync -a test_data_download/ SITE/fixtures/
set -l combinations \
    routine:convert:hdf5 \
    routine:convert:duckdb \
    routine:convert:parquet \
    routine_pb:proteobench:hdf5 \
    problems:convert:hdf5 \
    problems:proteobench:hdf5 \
    proteobench:proteobench_pmultiqc:hdf5 \
    proteobench_plasma:proteobench_plasma:hdf5 \
    proteobench_entrapment:proteobench_entrapment:hdf5 \
    directlfq:convert_no_param:hdf5

argparse --name publish_corpuses h/help p/plan j/cores= -- $argv
or exit 2

if set -q _flag_help
    printf '%s\n' \
        'Usage: publish_corpuses.fish [--plan] [--cores N] SITE' \
        '  --plan     Print commands without changing any run files' \
        '  --cores N Maximum parallel datasets per combination (default: 3)' \
        'Force every combination into apb_publish_output, then publish into the empty folder SITE.'
    exit 0
end

if test (count $argv) -ne 1
    printf '%s\n' 'Name exactly one empty SITE folder' >&2
    exit 2
end

set -l cores 3
if set -q _flag_cores
    set cores $_flag_cores
end
if not string match --quiet --regex '^[1-9][0-9]*$' -- "$cores"
    printf '%s\n' '--cores must be a positive integer' >&2
    exit 2
end

set -l preview no
if set -q _flag_plan
    set preview yes
else if not command -q uv
    printf '%s\n' 'uv is required' >&2
    exit 1
end

set -l site (path resolve -- $argv[1])
cd (path resolve (status dirname)/..)
or exit 1
set -l output_root (path resolve apb_publish_output)

function corpus_command --inherit-variable preview
    printf '%s\n' (string join ' ' -- (string escape -- uv run corpus $argv))
    if test "$preview" = no
        uv run corpus $argv
        or return $status
    end
end

for combination in $combinations
    set -l parts (string split : -- "$combination")
    corpus_command run "$parts[1]" --workflow "$parts[2]" --format "$parts[3]" \
        --cores "$cores" --force --output-root "$output_root"
    or exit $status
end

corpus_command publish "$site" --output-root "$output_root"
