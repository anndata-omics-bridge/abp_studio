#!/usr/bin/env fish
# Edit these corpus:workflow:format entries to choose the saved runs Studio should produce.
# Convert in all storage formats, score through three tools, and median-polish primary X;
# run the problems corpus, whose known failures are listed in corpuses/problems.md, the same way.
set -l combinations \
    routine:convert:hdf5 \
    routine:convert:duckdb \
    routine:convert:parquet \
    routine_pb:proteobench:hdf5 \
    routine:aggregate_medpolish:hdf5 \
    problems:convert:hdf5 \
    problems:proteobench:hdf5 \
    problems:aggregate_medpolish:hdf5

argparse --name routine_corpuses h/help p/plan c/clean d/dry-run f/force j/cores= -- $argv
or exit 2

if set -q _flag_help
    printf '%s\n' \
        'Usage: routine_corpuses.fish [--plan] [--clean | --dry-run] [--force] [--cores N]' \
        '  --plan     Print commands without changing any run files' \
        '  --clean    Delete each selected corpus/workflow, across all formats, before running' \
        '  --force    Always enabled: delete previous results and rerun; keep no history' \
        '  --dry-run Ask Snakemake which jobs it would schedule; preserve existing results' \
        '  --cores N Maximum parallel datasets per combination (default: 3)' \
        'Default: force every selected combination, deleting its previous results without archiving; stop on failure.'
    exit 0
end

if test (count $argv) -gt 0
    printf 'Unexpected arguments: %s\n' (string join ' ' -- $argv) >&2
    exit 2
end

set -l modes
for mode in clean dry_run
    if set -q _flag_$mode
        set -a modes $mode
    end
end
if test (count $modes) -gt 1
    printf '%s\n' 'Choose only one of --clean and --dry-run; --plan can preview either mode.' >&2
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

cd (path resolve (status dirname)/..)
or exit 1

function corpus_command --inherit-variable preview
    printf '%s\n' (string join ' ' -- (string escape -- uv run corpus $argv))
    if test "$preview" = no
        uv run corpus $argv
        or return $status
    end
end

set -l cleaned_pairs
set -l run_flags --cores "$cores" --force
if set -q _flag_dry_run
    set -a run_flags --dry-run
end

for combination in $combinations
    set -l parts (string split : -- "$combination")
    set -l pair "$parts[1]:$parts[2]"
    if set -q _flag_clean; and not contains -- "$pair" $cleaned_pairs
        corpus_command clean "$parts[1]" "$parts[2]"
        or exit $status
        set -a cleaned_pairs "$pair"
    end
    corpus_command run "$parts[1]" --workflow "$parts[2]" --format "$parts[3]" $run_flags
    or exit $status
end
