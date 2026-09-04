<!-- Managed by agent: keep commands and file references verified -->
<!-- Last updated: 2026-09-03 | Last verified: 2026-09-03 -->

# APB Studio

APB Studio orchestrates APB2, APB FASTA, APB Aggregate, and APB ProteoBench. Dependency direction is from Studio
to those tools, never the reverse. It provides two applications:

**Precedence:** the closest `AGENTS.md` to changed files wins. Explicit user
instructions override repository files.

- **Fixture store** (`apb-studio-fixtures`): one script downloads every ProteoBench submission,
  both FASTAs and all module TOMLs into one store root and summarises them; a plain-JavaScript
  viewer served by `apb-studio-fixtures serve` reads those files and shows tables.
- **Corpus Runner** observes persisted Snakemake runs/outputs and launches whole-corpus Snakemake
  run or clean operations. Its Dash application was removed on 2026-09-04; a viewer built like the
  fixture-store viewer replaces it. The headless path (`scripts/run_corpus.py`) is unchanged.

## Architecture

The fixture store is written only by `apb-studio-fixtures`, and it has three writing
commands: `catalog` writes `catalog.csv` with the three selection strategies as boolean
columns, `download` fetches every submission into `submissions/<repo>/<hash>/` and writes
`downloads.csv`, `resources` fetches `fasta/` and `modules/` and writes `resources.csv`.
`all` runs the three; `clean` empties the store root, leftovers from older layouts included,
because a store is entirely re-downloadable. Nothing filters downloads; the strategies
annotate. The layout lives in `fixture_store.py`.

**Each submission is described by its own `summary.json`, written beside its files the moment
they land** — format, size, rows, columns, column names, parameter file. The viewer composes
that URL from the `submissionSummary` pattern in `index.json` and asks for it: **present means
downloaded, absent means not.** So a submission that lands mid-run needs no table rebuilt and
no listing refreshed, and a page reload shows the truth. `downloads.csv` is consulted only for
what a summary cannot say — a hash the server never served. There is no `summaries.csv`.

**The server serves files and computes nothing.** `index.json` is written by
`fixture_index.py` and names the tables, FASTAs, module TOMLs and that URL pattern; it lists
no submissions, so nothing in it goes stale during a download. The viewer reads the store once,
at page load.

The viewer (`src/apb_studio/fixture_viewer/web/`) follows rawDIAGQC's conventions: plain `.js` ES
modules, no bundler, no npm; vendors pinned by full URL in `web/vendor/*.js`; Lit only in
`web/shell/`; `web/panels/` are pure `(rows) -> view descriptors`; Tabulator is the only table
renderer. `tests/web/architecture.test.mjs` enforces the import graph (`make test-web`).

APB2's packaged parsing-rule JSONs resolved against each local input and parameter file are the only
source of supported MuData/standalone levels. Never add a Studio vendor/level map. There is no
user-maintained `corpus.yaml`, replacement YAML, or scaffold workflow.

At launch, the Corpus Runner freezes the resolved fixtures, branches, resources, aliases, paths,
and versions into `<output_root>/.apb_studio/runs/<run-id>/run.json`. This is versioned internal
execution state and must never become accepted user configuration. While a run is active, keep its
table pinned to that snapshot. Persist the operation state and Snakemake log beside the snapshot so
the application can recover them after a restart.

The packaged stage registry (`src/apb_studio/config/registry.yaml`) owns stage topology and command templates; the packaged `src/apb_studio/workflow/Snakefile` owns execution. The default path is `apb2 convert` → `apb-fasta verify-peptides` → conditional `apb-aggregate ion protein sum` and `apb-aggregate fragment protein sum` → `apb-proteobench benchmark`. The direct path is one `apb-proteobench run` call from vendor files to final MuData. Missing FASTA or module resources block only targets that need them.

## APB2-only execution

The legacy `apb` CLI is not an execution option. New snapshots contain clean APB2 branch names:
`mudata`, `ion`, `peptidoform`, `peptide`, `protein`, and `fragment` when supported. Capability
discovery compiles APB2's own packaged rules; never add a Studio-side vendor or level map.

Studio imports no APB package. It drives `apb2`, `apb-fasta`, `apb-aggregate` and
`apb-proteobench` as command-line tools and checks files itself with the standard library only.
The Corpus Runner's capability discovery still imports `apb2` and is the open exception until
apb2 exposes that as a command.

## Pipelines are selections, never definitions

Which converters and stages a run uses is a **pipeline**: one document in
`config/pipelines/*.yaml` naming converters and catalogue stage names. It never restates a stage's
command, dependencies, or resources — those live once, in `config/registry.yaml`, so the two cannot
drift. `--pipeline` on the app and both scripts, `CORPUS_PIPELINE` in the Makefile.

Rules for changing this area:

- **A selection must be closed under `depends_on`**, and `resolve_pipeline` refuses otherwise. The staged dependency chain is convert → FASTA → ion aggregation → fragment aggregation → ProteoBench; inapplicable aggregation stages reconnect the next stage to the nearest emitted ancestor. The direct stage is an independent root restricted to the MuData branch.
- **The choice enters at four places only:** the entry point, `expand_resolved_targets`,
  `run.json`, and the grid's columns. Do not thread a pipeline into `capabilities.py` — discovery
  answers with everything a fixture supports so its cache stays shared, and filtering happens once,
  at expansion.
- **A grid describes a run**, so its columns come from the snapshot that produced its rows, never
  from the packaged catalogue. A pinned run keeps the pipeline it was minted with.
- **Adding a pipeline is one YAML file. Adding a stage is a registry entry plus one Snakemake
  rule**, because Snakemake rules are top-level declarations and cannot be generated from data.

## Corpus Runner product boundary

Corpus Runner is a thin observer and operator for the packaged Snakemake workflow:

- Show Snakemake-managed artifacts and stage state from the output tree.
- Trigger only two execution operations: whole-corpus Snakemake run and whole-corpus Snakemake
  clean.
- Load persisted `run.json`, operation state, and `snakemake.log` files when they already exist.
- Render global/per-rule logs, errors, and diagnostics without inventing alternate workflow state.
- Render artifact summaries, including `uns`, and Snakemake benchmark runtimes.

The branch grid is for inspection, not execution selection. Do not add row-, branch-, or
stage-scoped Run/Clear controls, and do not delete workflow outputs directly from a viewer action.
Fixture inputs and persisted run/log history are never part of Corpus Runner clean.

The pipeline picker is not an exception to this. It selects which converters and stages the *whole*
corpus operation covers, exactly as `--pipeline` does headlessly; it never selects rows, branches,
or individual stages, and the two operations stay whole-corpus.

## Engineering rules

- **Reuse before duplicate.** Call APB2, APB FASTA, APB Aggregate, and APB ProteoBench for domain work,
  as command-line tools. Orchestrate with Snakemake; browser applications are static viewers served
  by Studio's own `ThreadingHTTPServer`, never Dash.
- **Keep `__init__.py` empty** (a module docstring is acceptable), matching APB.
- **Use stable fixture identity:** `(canonical module, repository name, full intermediate hash)`.
- **Preserve existing output associations.** Resolve the app-owned fixture-to-output alias before
  constructing `output_root/<module>/<alias>/<stage-files>`.
- **Inventory from live files.** A manifest status is history and cannot override absent or
  ambiguous `input_file.*`/`param_0.*` files.
- **Resolve all branches from APB2.** Do not copy parsing-rule capabilities into fixture tables,
  settings, or run configuration.
- **Keep summaries in APB.** Render `describe_path()` output; do not derive proteomics metrics in
  Studio. The comparison panel is not an exception: runtime and artifact size are workflow
  observations Studio already owns, it reads both from the rows the grid drew, and it opens no
  artifact. A comparison that needed a value from inside an `.h5ad` would belong in APB.
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
| Carpet diagnostics | `make carpets` — 3 of 5 checks here; pyan3 fails on this codebase |

The pre-commit configuration is the command source of truth for CI. Do not
lower Ruff, strict Pyright, dependency, or coverage gates without explicit
approval.

### Corpus verification scope

**The routine corpus check is roughly ten fixtures, and they are named, not sampled.** Run it with
`make corpus-routine`, which reads `selections/routine.txt`. Whole-corpus run and clean are
the only execution operations (see the product boundary above), so never add a scoped Run control.

| Command | Scope | Jobs | When |
| --- | --- | --- | --- |
| `make corpus-routine` | the 10 named fixtures | varies by supported levels | Default after any refactor. This is the integration gate. |
| `make corpus-routine CORPUS_PIPELINE=apb2-convert` | the same 10, conversion only | ~12 | Timing or parity work on one converter, with nothing else in the DAG. |
| `make corpus-check CORPUS_RUN_FLAGS="--datasets selections/routine.txt"` | same selection, `--dry-run` | — | Confirm a fresh snapshot schedules no jobs. |
| `make corpus-run` | whole corpus | varies by supported levels | Release-level checks only (~1 hour at `--cores 10`). |

**Name the datasets; do not hand over an anonymous sample.** `--fixtures N` still exists and is
still deterministic, but a reviewer cannot tell which files a sample used, so every narrowed run
logs the datasets it covered and a selection file is preferred for anything anyone else will read.

`CORPUS_PIPELINE` (default `full`), `CORPUS_CORES` (default 10), `CORPUS_FIXTURES` (default **0**,
meaning no sampling) and `CORPUS_RUN_FLAGS` (anything else, e.g.
`--datasets selections/routine.txt --level ion`) are Make variables set on the command line. Every
pipeline writes the same artifact names into the same output root, so a narrower pipeline over an
already-converted corpus schedules nothing; `--force` re-runs it.

`scripts/run_corpus.py` mints the run snapshot exactly as the dashboard does — the snapshot
always describes the complete inventory — and narrows only the Snakemake targets it
requests, which is the same mechanism `launch_corpus` uses. `sample_fixture_targets` takes
fixtures round-robin by vendor so ten fixtures exercise ten parsers rather than ten
submissions from one tool, and is deterministic so two runs of the same limit compare
directly. A fixture may span several APB2 levels, so ten fixtures can create substantially more
than ten jobs.

`make corpus-run` now defaults to the whole corpus, so do not reach for it casually: propose
`make corpus-routine` as the verification step for a refactor, and do not treat a full-catalogue run
as a prerequisite for merging. If a change genuinely needs the full corpus — a parsing-rule change
touching many vendors, or an artifact-parity diff against a previous revision — say why, and run it
once at the end rather than after each step.

The one console script is `apb-studio-fixtures`; `make fixture-manager` runs its `serve` command.

The observer/operator boundary above **is** the record — it is not a summary of a design
document held somewhere else. For how the current shape was arrived at, read `CHANGES.md` and
`git log`; there is no planning document to consult.

## Scoped AGENTS.md

- [GitHub workflows](./.github/workflows/AGENTS.md)
