# apb_studio

A corpus **dashboard + Snakemake pipeline** over the
[`anndata_proteomics` (APB)](../anndata_proteomics_bridge) conversion CLI.

> *"I have ~90 vendor outputs across ~10 ProteoBench modules. Show me how far each one has
> progressed through the pipeline, and let me run or clean the missing/stale work — by single
> dataset, by module, or all at once."*

## How it fits together

| Piece | File | Role |
|-------|------|------|
| Corpus config | `config/corpus.example.yaml` | declares inputs, outputs, module↔annotation map (round-tripped) |
| Stage registry | `config/registry.yaml` | **single source of truth** for stages; read by both the Snakefile and the dashboard |
| Pipeline | `workflow/Snakefile` | builds the DAG; shells out to the `apb` CLI |
| Dashboard | `src/apb_studio/dashboard.py` | marimo: coverage grid + run/clean triggers |

The **filesystem is the state**: `output_root/<module>/<dataset>/<stage>.h5ad` existing ⇒ that
stage is done. No separate database.

## Stages

`convert --level X` → `X.h5ad` (primary) · `assemble-mudata` → `mudata.h5mu` (optional) ·
`annotate` (container-agnostic `obs`) · `fasta-annotate` (future, `var`).

## The plan

Full functional spec:
[TODO/TODO_workflow_dashboard_plan.md](TODO/TODO_workflow_dashboard_plan.md)

## Quick start

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
cp config/corpus.example.yaml config/corpus.yaml   # edit paths
make dag    # dry-run: what would run
make ui     # open the dashboard
make test-tool  # open the ProteoBench test-data browser
```

## Test-data browser

`make test-tool` opens the marimo browser for the ProteoBench test corpus. It filters by
target, software, and size, launches `apb convert` as a background subprocess, and records
each run under `logs/ui_converted/<timestamp>_<slug>_<target>/`.

Each run directory is the durable state for one conversion. Successful runs contain
`command.json`, `console.log`, and either `result.h5ad` or `result.h5mu`; incomplete or
failed runs usually keep the command and log so they remain inspectable after a marimo
restart. If the catalog is empty, regenerate APB's test-data cache before using the browser.

**Status:** scaffold. The `apb` CLI is not implemented yet (APB is mid-rebuild); the Snakefile
encodes the intended command contract.
