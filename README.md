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
| Corpus app | `src/apb_studio/dashboard.py` | Plotly Dash corpus overview |
| Test-data app | `src/apb_studio/testdata_app.py` | catalog, select, download, and inspect ProteoBench fixtures |

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
make app              # open the corpus dashboard
make testdata-app     # open the ProteoBench test-data application
```

The test-data application's **Storage** tab selects one root directory for the
catalog, selection and manifest CSVs, downloaded metadata/raw files, and Studio
logs. The displayed APB `test_data_download` folder remains the default.
