# APB Studio

APB Studio provides two local applications around the APB2 toolchain:

- **Fixture Manager** catalogs, selects, downloads, and inspects ProteoBench fixtures and their
  module and FASTA resources.
- **Corpus Runner** derives every branch supported by APB2, launches the complete runnable corpus,
  and shows stage progress, artifact summaries, and exact failure logs.

## Sources of truth

| Information | Owner |
| --- | --- |
| Catalog, download queue, report, and cached fixture files | Fixture Manager via `apb-testdata` |
| Active test-data root | Fixture Manager setting |
| ProteoBench module TOMLs and FASTA resources | Fixture Manager downloads/resource inventory |
| MuData and standalone levels | APB2 rules resolved against local inputs and parameters |
| Output root | Corpus Runner setting |
| Scope and provenance of one launch | Corpus Runner-generated `run.json` |
| Completion and runtime failure | Artifacts and authoritative rule failure markers |

The applications share typed settings stored in the operating system's application-config
directory. The corpus is every complete local fixture under the active test-data root; the
selection CSV controls the download queue only. A complete fixture has exactly one `input_file.*`
and one `param_0.*`. The conventional test-data root in this workspace is
`apb_studio/test_data_download/` — gitignored, downloaded and re-downloadable by the Fixture
Manager, and never assumed present by any consumer (apb2's corpus-backed unit tests read it via
`APB2_TEST_DATA` and skip when it is absent).

There is no user-maintained `corpus.yaml`. No fixture table or application setting declares a
level such as `ion`: APB2 parses the parameter version and input headers, then resolves the matching
packaged parsing-rule JSON.

## Pipelines

A **pipeline** says which converters a run exercises and which stages it runs. It is one small
YAML document in `src/apb_studio/config/pipelines/`, selecting from the stage catalogue in
`src/apb_studio/config/registry.yaml` — it never restates a stage's command, so the two cannot
drift. Both entry points take the same names:

| `--pipeline` | CLI calls | Result |
| --- | --- | --- |
| `full` (default) | `apb2 convert` → `apb-fasta verify-peptides` → conditional `apb-aggregate` calls → `apb-proteobench benchmark` | inspectable artifacts at every boundary |
| `direct` | `apb-proteobench run` | one final scored MuData artifact per fixture |
| `convert` | `apb2 convert` | conversion only |
| `apb2-convert` | same as `convert` | compatibility name |
| `apb2-full` | same as `full` | compatibility name |

```bash
make corpus-runner CORPUS_PIPELINE=apb2-convert    # app opens on that pipeline
make corpus-run    CORPUS_PIPELINE=apb2-convert    # headless, same target set
make corpus-check  CORPUS_PIPELINE=apb2-convert    # dry-run it
make corpus-clean  CORPUS_PIPELINE=apb2-convert    # clean only its artifacts
```

The picker beside the output path switches pipeline in the running app; the grid's columns follow.
While a run is active the table stays pinned to that run's own pipeline, so a switch applies to the
next resolution rather than relabelling work already under way.

Three things worth knowing:

- **The staged pipelines share conversion artifact names.** That is what makes `convert` followed
  by `full` incremental rather than repeated work. The direct pipeline intentionally writes a
  distinct `mudata.raw-proteobench.h5mu`. Pass `--force` (or a
  separate `--output-root`) when the point is to time the work again:
  `uv run python scripts/run_corpus.py --pipeline apb2-convert --force`.
- **A pipeline must be closed under `depends_on`.** In the staged route, FASTA checking reads the conversion; `apb-aggregate ion protein sum` and `apb-aggregate fragment protein sum` run only when their source levels exist; ProteoBench reads the last aggregate result that was produced.
- **The direct route is MuData-only.** It converts every compatible APB2 level, checks the FASTA, performs the same available ion/fragment-to-protein aggregations in memory, and writes one final h5mu result.

Adding a pipeline is one YAML file. Adding a *stage* is a registry entry plus one Snakemake rule,
because Snakemake rules are top-level declarations and cannot be generated from data.

## Corpus Runner

The Corpus Runner shows one compact table with `Module`, `Dataset`, `Software`, `Level`, and then
one stage column per stage of the active pipeline: `Converted`, `FASTA checked`, `Ion aggregated`, `Fragment aggregated`, and `ProteoBench scored` for the staged route, or `Raw to ProteoBench` for the direct route. One row is
one APB2 quantification level. The direct route emits only the MuData row; the staged route fans
out to MuData plus every supported standalone level. Unsupported or invalid local fixtures remain
visible as one unresolved row.

`Run corpus` freezes fixture identities, resolved branches, paths, resources, output aliases, the
active pipeline, and APB/registry versions into:

```text
<output_root>/.apb_studio/runs/<run-id>/run.json
```

That JSON file is internal execution state, not user configuration. Snakemake consumes the frozen
snapshot with `--keep-going`; a fixture downloaded during a run joins only after that run finishes
and the application reloads. Each run directory also stores durable operation state and the
Snakemake log, which Corpus Runner reloads after an application restart.

The stage states have precise meanings:

| State | Meaning |
| --- | --- |
| blank | Runnable or normally waiting for an upstream stage |
| `DONE` | The expected artifact exists |
| `UNSUPPORTED` | APB2 has no registered capability for the software, or no parsing-rule JSON matches |
| `BLOCKED` | A required input/resource is invalid or absent, or an upstream stage terminated |
| `FAILED` | Snakemake attempted that exact rule and its failure marker exists |

Only `FAILED` is red and offers a downloadable rule log. A leftover log alone never means failure,
and an artifact wins over an old failure marker. Clicking `DONE` shows the cumulative artifact
summary, including `uns`; clicking another terminal state shows its diagnostic. `Clear corpus…`
launches the packaged Snakemake clean target for every managed stage. It removes artifacts and
their rule logs, failure markers, benchmarks, and provenance while preserving fixture inputs and
persisted run/log history. Run and clean are disabled while either operation is active.

Newly executed stages include Snakemake's persisted elapsed time directly in their state, for
example `DONE · 2m 14s`. Existing artifacts remain plain `DONE` and report runtime unavailable
until Snakemake records a benchmark for them. The Corpus summary reports stage-state counts,
produced artifacts, and timing coverage.

### Comparing two stage columns

`Compare two stage columns`, the collapsed panel under the grid, scatters any two stage columns
against each other — one point per grid row, coloured by software, with a dotted `y = x` line so
`Converted` against `Converted2` reads as "which converter produced the larger artifact" at a
glance. Two metrics:

| Metric | Source | Available for |
| --- | --- | --- |
| Runtime (s) | the stage's Snakemake benchmark file | stages run under Snakemake |
| Artifact size (MB) | the produced file's own size | every produced artifact |

The axis choices are the columns the grid is currently showing, so they follow the active pipeline
(and a pinned run's own pipeline). A row missing either value contributes no point — a stage that
never ran, or an artifact predating benchmark metadata, is absent evidence and not a zero — so the
plot titles itself with how many of the rows it could compare. Nothing is recomputed: every value
plotted is already in the row the grid drew.

**Each axis is pinned to its own data**, because the two columns hold the same quantity but not the
same distribution: one column's 2280 s outlier must not rescale the other column's 26 s axis. The
`y = x` line spans both columns and is clipped by those ranges rather than widening them, so when
every row sits on one side of equality the line is still there, at the edge. `Log axes` is worth
switching to whenever a few rows dwarf the rest.

!!! warning "Two columns can come from two different runs"
    A benchmark is written when Snakemake *runs* a stage. If one column's artifacts already
    existed, that column's numbers are from whenever they were last produced — possibly weeks
    earlier, under different load — and comparing them measures the two runs, not the two
    stages. For a comparison you can defend, produce both columns in one session:
    run both measurements in one deliberate `--force` session.

## Fixture Manager

The Fixture Manager owns the canonical cache lifecycle. Its fixture table combines the generated
catalog, selection, and download-report CSVs with live filesystem checks. It downloads
ProteoBench `module_settings.toml` files and FASTA resources, then resolves them without
requiring manual paths. The same module TOML supplies sample annotation and the ProteoBench
experiment-design contract; scoring consumes the `sample_name` and `condition` added by the
ProteoBench benchmark stage.

Its Data workspace retains the fixture file, submission JSON, and parameter views. Its
Configuration workspace catalogs and edits APB parsing-rule JSON documents. Conversion execution
and converted-artifact inspection belong exclusively to Corpus Runner. In Resources, clicking an
annotation or FASTA status/path cell previews the annotation content or the first 40 FASTA lines.

## Quick start

```bash
uv sync --frozen

make fixture-manager   # Fixture Manager, default Dash port 8050
make corpus-runner     # Stop any managed instance, then run Corpus Runner on port 8051
make corpus-runner-stop

make corpus-runner CORPUS_PIPELINE=apb2-convert   # open on one pipeline (see Pipelines above)
make corpus-run    CORPUS_PIPELINE=direct CORPUS_FIXTURES=10
```

`make corpus-clean` runs the packaged Snakemake clean rule without the application, removing
exactly what `Clear corpus…` removes. It deletes immediately, without a confirmation prompt. It
defaults to `CORPUS_PIPELINE=full`; a narrower
pipeline clears only that pipeline's artifacts.

`make corpus-run` runs **everything** the pipeline covers. It takes `CORPUS_PIPELINE` (default
`full`), `CORPUS_CORES` (default 10), and `CORPUS_RUN_FLAGS` for anything else.

### Choosing which datasets run

Name them in a file rather than sampling, so a run can always say what it covered:

```bash
make corpus-routine                                     # selections/routine.txt, one per vendor
make corpus-run CORPUS_RUN_FLAGS="--datasets selections/routine.txt --level ion"
```

```text
# selections/routine.txt — a dataset alias, or module/alias. # comments and blank lines ignored.
Results_quant_ion_DDA/maxquant-00e2f863    # maxquant
diann-300beac4                             # diann
```

A name matching nothing is logged as a warning and the rest still run; if *nothing* matches, the
run stops rather than quietly doing less than you asked. `--level ion --level mudata` restricts
which quantification levels convert (`mudata` is the MuData container). `--fixtures N` still takes a
vendor-spread sample of whatever is selected, and every narrowed run logs the datasets it covers.

For flags without a Make variable, call the script directly:

```bash
uv run --frozen python scripts/run_corpus.py --help
uv run --frozen python scripts/run_corpus.py --pipeline apb2-convert --force --output-root /tmp/apb2
```

The lifecycle targets are scoped by `APP_PORT`; for example, use
`make corpus-runner APP_PORT=8052` and `make corpus-runner-stop APP_PORT=8052`. A restart also
recognizes an older Corpus Runner already listening on that port, but refuses to terminate an
unrelated process. The preferred console commands are `apb-studio-fixture-manager` and
`apb-studio-corpus-runner`.
`apb-studio-testdata` and `apb-studio` remain compatibility aliases.

Bypassing Make, the Corpus Runner takes the same selection directly:

```bash
uv run --frozen apb-studio-corpus-runner --pipeline apb2-convert --port 8052
uv run --frozen apb-studio-corpus-runner --help
```

`--port` falls back to `APB_STUDIO_PORT`, then 8051; `--settings` points at an alternative
settings file.

For development, install all locked checks and run the local CI stages:

```bash
uv sync --frozen --extra dev --group docs
uv run pre-commit run --hook-stage pre-commit --all-files
uv run pre-commit run --hook-stage pre-push --all-files
```

See [docs/development.md](docs/development.md) for the security audit and
individual checks.

## Historical design

[CHANGES.md](CHANGES.md) and `git log` are the record of how the dashboard and the Snakemake
migration reached their current shape. [docs/architecture.md](docs/architecture.md) describes
that shape as it stands.
