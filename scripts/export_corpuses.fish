#!/usr/bin/env fish
# Run every routine export from scratch; --force keeps no archived results.
set -l workflows export_msmu export_prolfqua export_proteopy export_alphapepttools

cd (path resolve (status dirname)/..)
or exit 1

if not command -q apb-export
    set -l export_bin (path resolve ../apb-export/.venv/bin)
    if not test -x "$export_bin/apb-export"
        printf '%s\n' 'apb-export is not on PATH and its sibling environment is missing.' >&2
        exit 1
    end
    set -gx PATH $PATH "$export_bin"
end

for workflow in $workflows
    printf 'uv run corpus run routine --workflow %s --format hdf5 --cores 3 --force\n' "$workflow"
    uv run corpus run routine --workflow "$workflow" --format hdf5 --cores 3 --force
    or exit $status
end
