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
templates; the packaged `src/apb_studio/workflow/Snakefile` owns execution. Annotation and FASTA
are children of conversion; ProteoBench scoring is a child of annotation because it requires
`sample_name` and `condition`. A missing FASTA resource must not suppress the annotation/scoring
chain, and a missing annotation resource must not suppress FASTA. Every annotated branch is
scored: the level declared in a ProteoBench module TOML never restricts which branches enter the
scoring stage.

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

- blank: runnable/pending, or a downstream stage made irrelevant by an unsupported/failed
  conversion. Irrelevant downstream cells are excluded from pending counts.
- `DONE`: the expected artifact exists.
- `UNSUPPORTED`: the stage cannot run with the current software, version, input schema, or required
  resource. This includes absent parsing rules and missing annotation, FASTA, or module settings.
  Rule-document presence is checked before reading the fixture input or parameter file.
- `FAILED`: input/parameter inspection or an attempted workflow stage failed. A workflow failure
  requires a non-zero exit and its failure marker.

Every `UNSUPPORTED` or `FAILED` cell exposes its exact diagnostic when clicked. A log alone never
means failure. An artifact wins over an old marker. If conversion is unsupported or fails, its
unattempted descendants stay blank. Only a workflow-stage `FAILED` cell offers a log download.

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

### Corpus verification scope

**The routine corpus check is roughly ten fixtures, not the whole catalogue.** Run it headlessly
with `make corpus-run`; the Dash app still triggers whole-corpus run and clean only (see the product
boundary above), so never add a scoped Run control to a callback.

| Command | Scope | Jobs | When |
| --- | --- | --- | --- |
| `make corpus-run` | 10 fixtures (default) | ~88 | Default after any refactor. This is the integration gate. |
| `make corpus-check` | same sample, `--dry-run` | — | Confirm a fresh snapshot schedules no jobs. |
| `make corpus-run CORPUS_FIXTURES=0` | whole selection | 965 | Release-level checks and deliberate artifact-parity comparisons only (~1 hour at `--cores 10`). |

`CORPUS_FIXTURES` and `CORPUS_CORES` (both default 10) are Make variables set on the command
line — `make corpus-run CORPUS_CORES=20` — and reach `run_corpus.py` as `--fixtures`/`--cores`.

`scripts/run_corpus.py` mints the run snapshot exactly as the dashboard does — the snapshot
always describes the complete inventory — and narrows only the Snakemake targets it
requests, which is the same mechanism `launch_corpus` uses. `sample_fixture_targets` takes
fixtures round-robin by vendor so ten fixtures exercise ten parsers rather than ten
submissions from one tool, and is deterministic so two runs of the same limit compare
directly. A fixture spans several branches, so ten fixtures is ~88 stages, not ~40.

Do not propose a full-catalogue run as the verification step for a refactor, and do not treat one
as a prerequisite for merging. If a change genuinely needs the full corpus — a parsing-rule change
touching many vendors, or an artifact-parity diff against a previous revision — say why, and run it
once at the end rather than after each step.

Preferred console scripts are `apb-studio-fixture-manager` and `apb-studio-corpus-runner`.
`apb-studio-testdata`/`apb-studio` are compatibility aliases.

See [TODO/Archive/TODO_corpus_application.md](TODO/Archive/TODO_corpus_application.md) for the
implemented migration history and
[TODO/Archive/TODO_workflow_dashboard_plan.md](TODO/Archive/TODO_workflow_dashboard_plan.md) for
the original dashboard design. The current observer/operator boundary is recorded in
[TODO/Archive/TODO_corpus_runner_alignment.md](TODO/Archive/TODO_corpus_runner_alignment.md).

## Scoped AGENTS.md

- [GitHub workflows](./.github/workflows/AGENTS.md)
