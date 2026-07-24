<!-- Managed by agent: keep commands and file references verified -->
<!-- Last updated: 2026-07-24 | Last verified: 2026-07-24 -->

# APB Studio

APB Studio is a consumer of `anndata_proteomics` (APB). Dependency direction is
`apb_studio → APB`, never the reverse. It provides two applications:

**Precedence:** the closest `AGENTS.md` to changed files wins. Explicit user
instructions override repository files.

- **Fixture Manager** owns the local ProteoBench fixture and resource inventory.
- **Corpus Runner** observes persisted Snakemake runs/outputs and launches whole-corpus Snakemake
  run or clean operations.

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
table pinned to that snapshot. Persist the operation state and Snakemake log beside the snapshot so
the application can recover them after a restart.

The packaged stage registry (`src/apb_studio/config/registry.yaml`) owns stage topology and command
templates; the packaged `src/apb_studio/workflow/Snakefile` owns execution. Annotation, FASTA, and
ProteoBench scoring are independent children of conversion, so a missing later-stage resource must
not suppress another runnable target.

## Corpus Runner product boundary

Corpus Runner is a thin observer and operator for the packaged Snakemake workflow:

- Show Snakemake-managed artifacts and stage state from the output tree.
- Trigger only two execution operations: whole-corpus Snakemake run and whole-corpus Snakemake
  clean.
- Load persisted `run.json`, operation state, and `snakemake.log` files when they already exist.
- Render global/per-rule logs, errors, and diagnostics without inventing alternate workflow state.
- Render APB-owned artifact summaries, including `uns`, and Snakemake benchmark runtimes.

The branch grid is for inspection, not execution selection. Do not add row-, branch-, or
stage-scoped Run/Clear controls, and do not delete workflow outputs directly from Dash callbacks.
Fixture inputs and persisted run/log history are never part of Corpus Runner clean.

## Engineering rules

- **Reuse before duplicate.** Call APB for conversion, annotation, FASTA handling, capability
  resolution, and summaries. Orchestrate with Snakemake; use Plotly Dash for the applications.
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
- **Keep timing in Snakemake.** Read persisted benchmark files; never infer historical runtime from
  artifact timestamps or dashboard wall-clock time.
- **Keep interfaces consistent.** Both applications use the same settings, fixture records,
  resources, and identifiers.

## Status contract

- blank: runnable/pending, including a downstream stage normally waiting for its upstream output.
- `DONE`: the expected artifact exists.
- `UNSUPPORTED`: APB has no registered capability for the software, or no parsing-rule JSON
  matches.
- `BLOCKED`: a required input/resource is absent or invalid, or an upstream stage terminated.
- `FAILED`: the workflow engine attempted that concrete rule, it exited non-zero, and its
  failure marker exists.

Unreadable input or parameters are `BLOCKED`, not `UNSUPPORTED`. A log alone never means failure.
An artifact wins over an old marker. If conversion fails, its unattempted descendants are
`BLOCKED`. Only an actual `FAILED` cell offers a log download.

## Development

| Task | Command |
| --- | --- |
| Install | `uv sync --frozen --extra dev --group docs` |
| Fast checks | `uv run pre-commit run --hook-stage pre-commit --all-files` |
| Full gate | `uv run pre-commit run --hook-stage pre-push --all-files` |
| Single test | `uv run pytest tests/test_pipeline.py -q` |
| Security audit | `uv run pre-commit run dependency-audit --hook-stage manual --all-files` |

The pre-commit configuration is the command source of truth for CI. Do not
lower Ruff, strict Pyright, dependency, or coverage gates without explicit
approval.

Preferred console scripts are `apb-studio-fixture-manager` and `apb-studio-corpus-runner`.
`apb-studio-testdata`/`apb-studio` are compatibility aliases.

See [TODO/Archive/TODO_corpus_application.md](TODO/Archive/TODO_corpus_application.md) for the
implemented migration history and
[TODO/Archive/TODO_workflow_dashboard_plan.md](TODO/Archive/TODO_workflow_dashboard_plan.md) for
the original dashboard design. The current observer/operator boundary is recorded in
[TODO/Archive/TODO_corpus_runner_alignment.md](TODO/Archive/TODO_corpus_runner_alignment.md).

## Scoped AGENTS.md

- [GitHub workflows](./.github/workflows/AGENTS.md)
