# ARCHIVED: Review of workflow dashboard handoff / phase 8 changes

Status: findings resolved; archived 2026-07-20.

Review target: [HANDOFF_workflow_dashboard_plan.md](HANDOFF_workflow_dashboard_plan.md)

Scope: review of the implemented `apb_studio` workflow-dashboard changes described in the
handoff, checked against the live code, tests, current APB CLI, and local commands. This is a
review artifact only; implementation files were not changed.

## Findings

### High: Clean safety guard uses `assert`, so optimized Python disables it

`pipeline.reject_input_paths()` is the guard that prevents Clean from deleting anything under
`input_root`, and both `clean_paths()` and `execution.clean_targets()` rely on it. The guard is an
`assert` at [pipeline.py](../src/apb_studio/pipeline.py#L326-L338), called from
[execution.py](../src/apb_studio/execution.py#L109-L127). Running Python with `-O` removes this
check entirely.

Observed locally:

```text
normal mode:
raised refusing to clean /tmp/in/raw.tsv: it is under input_root /private/tmp/in
optimized mode:
NO RAISE
```

This is a destructive-action guard, so it should raise a real exception, e.g. `ValueError` or a
small domain exception, not use `assert`.

### High: Dashboard run state can block valid reruns and allows concurrent jobs

The dashboard stores `get_last_key` / `set_last_key` at
[dashboard.py](../src/apb_studio/dashboard.py#L133-L138), sets it when a job starts, and then blocks
the same key forever with "This selection is already the active run" at
[dashboard.py](../src/apb_studio/dashboard.py#L177-L184). Nothing clears the key when the job
finishes or fails. In the same UI session, a user cannot rerun the same selection after a failed
Snakemake job, after cleaning outputs, or after changing input files if the target path set is
unchanged.

The inverse problem also exists: a different selection can launch a second Snakemake process while
the first is still running. The run path always uses the same log file,
`<output_root>/.apb_studio/run.log` ([dashboard.py](../src/apb_studio/dashboard.py#L181-L182)), so a
second job can race the first and truncate/reuse the same log.

Recommended correction: derive "active" from `inspect_job(get_job()).running`, block Run and Clean
while a job is running, and clear or ignore `last_key` once the job reaches a terminal state. If
deduping is still needed, dedupe only the currently running job, not all historical runs.

### Medium: Clean can still leave downstream orphan artifacts in holey states

The handoff says the contiguous-basket model fixed the non-contiguous/Clean orphan problem. The
current implementation lowers a dataset's displayed basket when an earlier artifact is missing
([pipeline.py](../src/apb_studio/pipeline.py#L254-L296)), and Clean deletes only the selected
basket's defining target ([execution.py](../src/apb_studio/execution.py#L117-L127)).

That still leaves an orphan case:

1. `convert` exists.
2. `annotate` is missing.
3. `fasta` exists, e.g. from a manual copy or partial/stale output tree.
4. The dataset appears in `converted` because the contiguous prefix stops at `convert`.
5. Cleaning the `converted` basket deletes only `mudata.h5mu` / `<level>.h5ad`, leaving
   `annotated_fasta.*` behind.

I verified this with a synthetic target set: convert + fasta present, annotate absent -> basket is
`converted`. The current Clean path would delete only the convert target for that row.

Recommended correction: either cascade-delete known downstream outputs for the selected dataset, or
detect "later artifacts exist beyond the contiguous prefix" and expose a repair/stale-output clean
path before allowing normal basket Clean.

### Medium: The advertised `make dag` review command fails with the checked-in example config

The handoff says `make dag` should resolve the example corpus
([handoff](HANDOFF_workflow_dashboard_plan.md#L93-L101)). The Makefile default uses
`CONFIG ?= config/corpus.example.yaml` and runs Snakemake against it
([Makefile](../Makefile#L1-L3), [Makefile](../Makefile#L21-L22)). That example config intentionally
contains placeholder roots such as `/path/to/vendor_outputs`
([corpus.example.yaml](../config/corpus.example.yaml#L6-L7)).

Observed locally:

```text
make dag
MissingInputException in rule convert
affected files:
    /path/to/vendor_outputs/quant_lfq_ion_DIA_AIF/run1/report.log.txt
    /path/to/vendor_outputs/quant_lfq_ion_DIA_AIF/run1/report.tsv
```

The `tests/test_snakemake_dag.py` dry-run is useful because it creates real fixture inputs, but the
developer-facing `make dag` command currently fails out of the box. Either change the handoff/docs
to say `make scaffold` or `CONFIG=... make dag` is required, or make the default `CONFIG` point to a
generated/local fixture that actually exists.

### Low: `ruff check src tests` is not reproducible from the declared environment

The handoff marks `ruff check src tests` as clean
([handoff](HANDOFF_workflow_dashboard_plan.md#L15-L21)), but `pyproject.toml` declares only
`pytest` in the dev extra ([pyproject.toml](../pyproject.toml#L16-L17)). Running the stated command
through the project environment fails:

```text
uv run ruff check src tests
error: Failed to spawn: `ruff`
Caused by: No such file or directory
```

Add `ruff` to the dev dependencies if it is part of the acceptance contract, or remove the command
from the handoff/checklist.

### Low: APB install hint still points at the old sibling path

`pyproject.toml` and the scaffold error message still tell developers to install
`../anndata_proteomics_bridge` ([pyproject.toml](../pyproject.toml#L12-L13),
[scaffold.py](../src/apb_studio/scaffold.py#L54-L58)). In this workspace the active APB repo is
`../apb`, and the current CLI check was run from there. This is small, but it makes first-run setup
look broken after the repo rename/reorganization.

## Positive Checks

- `uv run pytest -q` passes: `69 passed`.
- `uv run marimo export script src/apb_studio/dashboard.py` succeeds; the marimo graph exports.
- The current APB CLI exposes `apb convert DATA [LEVEL]`, and Cyclopts also shows `LEVEL --level`,
  so the generated `--level <level>` command form is accepted by the current parser.
- `tests/test_snakemake_dag.py` covers Snakemake dry-run resolution using temporary real input
  files; this is stronger than relying on the placeholder example config.

## Recommended Corrections

1. Replace the `assert` clean guard with a normal exception and test it under `python -O`.
2. Gate dashboard Run/Clean on the current job status; block concurrent jobs and allow rerun after
   a job finishes or fails.
3. Decide how Clean should handle non-contiguous downstream artifacts: cascade, repair, or explicit
   stale-output cleanup.
4. Make `make dag` reproducible from a checkout, or document the required `CONFIG=...`/scaffold
   prerequisite in the handoff and Makefile help.
5. Add `ruff` to dev dependencies if it remains an advertised check.
6. Update APB sibling-install hints from `../anndata_proteomics_bridge` to the current `../apb`
   path, unless this repo is meant to support both names.

## Validation Notes

Commands run from `/Users/wolski/projects/anndata_bridge/apb_studio`:

```bash
uv run pytest -q
uv run ruff check src tests
uv run marimo export script src/apb_studio/dashboard.py
uv run --project ../apb apb convert --help
make dag
```

`pytest` and Marimo export passed. `ruff` and `make dag` failed for the reasons described above.
