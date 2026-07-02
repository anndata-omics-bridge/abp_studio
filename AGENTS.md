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

`convert` → `mudata.h5mu` (one read → the multi-level MuData; `--level X` is the single-`.h5ad`
opt-in) · `annotate` (container-agnostic, writes `obs`, one annotation TOML) · `fasta` (optional,
protein `var`).

Adding a stage = **one registry entry + one Snakemake rule + one `apb` CLI subcommand**. The
dashboard re-derives its grid columns and pickers from the registry — no imperative GUI edits.

## Rules

- **Reuse before duplicate.** Conversion/annotation lives in APB and is called via the `apb` CLI.
  Orchestration is Snakemake; the GUI is marimo; config/registry are YAML. Do not reimplement any
  of these.
- **Keep `__init__.py` empty** (module docstring only), matching APB.
- **Hierarchical output layout, by module:** `output_root/<module>/<dataset>/<stage-files>`.

## Status

The `apb` CLI exists (`apb convert/annotate/fasta/validate/list`); apb is a pure library + CLI. The
pipeline is **implemented** against the real CLI — `pipeline.py` (the registry-driven core: paths +
rendered commands + coverage, the single source of truth), a wildcard-output `Snakefile`, an
`execution.py`/`jobrunner.py` background-run layer, a per-rule `provenance.py` sidecar, and a marimo
`dashboard.py` (coverage grid + Run/Clean triggers). See [the plan](TODO/TODO_workflow_dashboard_plan.md)
(§11 has the per-phase status).

Stages, all driven from `config/registry.yaml`: `apb convert <data> --software <v> --params <p>
--output <o>` → `mudata.h5mu` (one read; `<level>.h5ad` when a module declares `level` — decision
16; **no `assemble-mudata`**) · `apb annotate <data> <toml>` (one annotation TOML, container-agnostic)
· optional `apb fasta` (protein `var`). Each rule appends `python -m apb_studio.provenance` so every
artifact gets a `provenance.json`.

Verified: `pytest` (44) green, `ruff` clean, `snakemake -n` resolves both vendor shapes, and a
stubbed `make run` produces convert+annotate artifacts + provenance with coverage flipping to done.
**Not yet done:** a *real* apb conversion needs a param file apb recognizes (apb's contract); the
interactive dashboard wants a manual `make ui` smoke; and the comment-preserving `corpus.yaml`
write-back (decision 8) is deferred.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
uv pip install -e ../anndata_proteomics_bridge   # provides the `apb` CLI (when it exists)
make ui     # open the dashboard
make dag    # snakemake dry-run: what's pending
```
