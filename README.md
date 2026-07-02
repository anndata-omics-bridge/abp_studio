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

`convert` → `mudata.h5mu` (one read → the multi-level MuData; `--level X` is the single-`.h5ad`
opt-in) · `annotate` (container-agnostic `obs`, one annotation TOML) · `fasta` (optional, protein
`var`).

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
```

**Status:** scaffold. The `apb` CLI now exists; the dashboard reads coverage from the output
tree, but run/clean execution is not wired yet, and the Snakefile/registry still encode an older
command contract that needs realigning to the real `apb convert` signature.
