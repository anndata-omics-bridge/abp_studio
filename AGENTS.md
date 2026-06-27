# apb_studio

Corpus **dashboard + Snakemake pipeline** over the `anndata_proteomics` (APB) conversion CLI.
It drives conversion/annotation across a whole corpus (~90 vendor outputs across ~10 ProteoBench
modules) and shows how far each dataset has progressed.

This repo is a **consumer** of APB — it never reimplements conversion. Dependency direction is
`apb_studio → APB`, never the reverse.

## The plan

Authoritative functional spec (what we expose and how):
[TODO/TODO_workflow_dashboard_plan.md](TODO/TODO_workflow_dashboard_plan.md)

## Architecture in one paragraph

The **stage registry** (`config/registry.yaml`) is the single source of truth for pipeline
stages; both the Snakefile and the dashboard read it. The **corpus config**
(`config/corpus.example.yaml`) declares inputs, outputs, and the module↔dataset↔annotation-TOML
map (round-tripped: UI loads it as defaults, a run writes it back). **Snakemake** owns the doing;
the **filesystem is the database** (a file exists ⇒ that stage is done). The **marimo dashboard**
computes coverage by globbing the output tree and triggers run/clean by scope×stage.

## Stages (registry-driven)

`convert --level X` → `X.h5ad` (primary, independent) · `assemble-mudata` → `mudata.h5mu`
(optional) · `annotate` (container-agnostic, writes `obs`) · `fasta-annotate` (future, `var`).

Adding a stage = **one registry entry + one Snakemake rule + one APB CLI subcommand**. The
dashboard re-derives its grid columns and pickers from the registry — no imperative GUI edits.

## Rules

- **Reuse before duplicate.** Conversion/annotation lives in APB and is called via the `apb` CLI.
  Orchestration is Snakemake; the GUI is marimo; config/registry are YAML. Do not reimplement any
  of these.
- **Keep `__init__.py` empty** (module docstring only), matching APB.
- **Hierarchical output layout, by module:** `output_root/<module>/<dataset>/<stage-files>`.

## Status

Scaffold only — the `apb` CLI it shells out to does not exist yet (APB is mid-rebuild). The
Snakefile `shell:` commands encode the intended contract.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
uv pip install -e ../anndata_proteomics_bridge   # provides the `apb` CLI (when it exists)
make ui     # open the dashboard
make dag    # snakemake dry-run: what's pending
```
