# APB Studio

APB Studio is a consumer of `anndata_proteomics` (APB). Dependency direction is
`apb_studio → APB`, never the reverse. It provides two applications:

- **Fixture Manager** owns the local ProteoBench fixture and resource inventory.
- **Corpus Runner** derives APB-supported branches, launches Snakemake, and reports progress.

## Architecture

The Fixture Manager runs `apb-testdata` to create and update catalog, selection, download-report,
cache, ProteoBench module-annotation TOMLs, and FASTA artifacts. Both applications read one typed
fixture-inventory API and shared disk-backed settings. The selection CSV is a download queue, not a
corpus filter; every complete local fixture is part of the Corpus Runner inventory.

APB's packaged parsing-rule JSONs resolved against each local input and parameter file are the only
source of supported MuData/standalone levels. Never add a Studio vendor/level map. There is no
user-maintained `corpus.yaml`, replacement YAML, or scaffold workflow.

At launch, the Corpus Runner freezes the resolved fixtures, branches, resources, aliases, paths,
and versions into `<output_root>/.apb_studio/runs/<run-id>/run.json`. This is versioned internal
execution state and must never become accepted user configuration. While a run is active, keep its
table pinned to that snapshot.

The stage registry (`config/registry.yaml`) owns stage topology and command templates. Snakemake
owns execution. Each discovered branch follows `convert → annotate → fasta`; a missing later-stage
resource must not suppress an earlier runnable target.

## Engineering rules

- **Reuse before duplicate.** Call APB for conversion, annotation, FASTA handling, capability
  resolution, and summaries. Use Snakemake for orchestration and Plotly Dash for the applications.
- **Keep `__init__.py` empty** (a module docstring is acceptable), matching APB.
- **Use stable fixture identity:** `(canonical module, repository name, full intermediate hash)`.
- **Preserve existing output associations.** Resolve the app-owned fixture-to-output alias before
  constructing `output_root/<module>/<alias>/<stage-files>`.
- **Inventory from live files.** A manifest status is history and cannot override absent or
  ambiguous `input_file.*`/`param_0.*` files.
- **Resolve all branches from APB.** Do not copy parsing-rule capabilities into fixture tables,
  settings, or run configuration.
- **Keep summaries in APB.** Render `describe_path()` output; do not derive proteomics metrics in
  Studio.
- **Keep interfaces consistent.** Both applications use the same settings, fixture records,
  resources, and identifiers.

## Status contract

- blank: runnable/pending, including a downstream stage normally waiting for its upstream output.
- `DONE`: the expected artifact exists.
- `UNSUPPORTED`: APB has no registered capability for the software, or no parsing-rule JSON
  matches.
- `BLOCKED`: a required input/resource is absent or invalid, or an upstream stage terminated.
- `FAILED`: Snakemake attempted that concrete rule, it exited non-zero, and its failure marker
  exists.

Unreadable input or parameters are `BLOCKED`, not `UNSUPPORTED`. A log alone never means failure.
An artifact wins over an old marker. If conversion fails, its unattempted descendants are
`BLOCKED`. Only an actual `FAILED` cell offers a log download.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
uv pip install -e ../apb
make fixture-manager
make corpus-runner
make test
```

Preferred console scripts are `apb-studio-fixture-manager` and `apb-studio-corpus-runner`.
`make testdata-app`/`make app` and `apb-studio-testdata`/`apb-studio` are compatibility aliases.

See [TODO/TODO_corpus_application.md](TODO/TODO_corpus_application.md) for the approved migration
plan and [TODO/Archive/TODO_workflow_dashboard_plan.md](TODO/Archive/TODO_workflow_dashboard_plan.md)
for the original dashboard design.
