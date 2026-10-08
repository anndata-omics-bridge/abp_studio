# Adding a workflow

A workflow is one file, `src/apb_studio/workflows/workflow_<name>.py`. It owns the ordered tool calls and their file contract; nothing generic in Studio knows what those calls do. `--workflow <name>` then selects it, and no registry, YAML or `__init__` export needs editing.

## What a workflow file declares

| Declaration | Required | Meaning |
| --- | --- | --- |
| module docstring | yes | One line naming the linear pipeline the file runs |
| `TOOLS` | yes | Tuple of executable names this workflow invokes |
| `steps(context)` | yes | Build `StepSpec` objects in execution order |
| `main("<name>", steps)` under `__main__` | yes | The shared CLI contract; `<name>` must match the file name |
| `WORKFLOW_TABLE` | no | A sibling workflow's resource CSV to reuse, instead of `workflow_<name>.csv` |
| `WORKFLOW_COLUMNS` | no | The exact column tuple this workflow validates in that CSV |
| `PARAMETER_INPUTS` | no | Callable returning parameter dependencies; defaults to `required_parameter_inputs`, with `optional_parameter_inputs` for mixed inventories and `ignored_parameter_inputs` for parameter-free conversion |

## Procedure

1. **Write the file.** Start from `workflow_convert.py` for a single tool, or `workflow_proteobench.py` for a chain that passes intermediate files between tools.
2. **Declare `TOOLS`.** Name only the executables the workflow actually runs. A `convert` run must not require `apb-aggregate` on PATH, so declaring an unused tool is a defect, not caution.
3. **Reach every executable through `context.tool("<name>")`.** Asking for a tool absent from `TOOLS` raises rather than falling back to PATH.
4. **Declare each step's `inputs` and `outputs`.** The viewer reads only these. Chain a step by making the previous step's output artifact its declared input, and pair every scientific result with `representation(path)` from `artifacts.py` so the sidecar is inspectable.
5. **Resolve every file through `resolve_file(context.data_root, value)`.** Paths in a CSV are relative to the data root, never to the CSV's own directory.
6. **Refuse what the tools cannot do.** A workflow needing its table raises when `context.workflow_table` is `None`. Format choice belongs to APB2's public result writer; current APB tools accept HDF5, Parquet, and DuckDB. A real incompatibility surfaces as a failed job rather than being hidden.

## Adding a tool the corpus has never run

A new executable needs one entry in `_EXECUTABLE_OPTIONS` in `cli.py`, mapping the tool name to its `RunOptions` field and `--*-executable` override flag, plus that field on `RunOptions`. This table is the only place in generic code where a tool is named; everything downstream carries `tools` and `tool_versions` maps keyed by the same names.

Two further conditions must hold, or the run fails before scheduling:

- **The tool name is also its distribution name.** Snakemake watches each tool's `dist-info` metadata and, for editable installs, its whole source tree; `apb-fasta` the executable must come from `apb-fasta` the distribution.
- **`<tool> --version` succeeds.** Its output is recorded verbatim in `run.json`.

Add the distribution to `[tool.uv.sources]`, the `samples` extra, and the `DEP002` ignore list in `pyproject.toml`, then `uv lock` and `uv sync`, so the tool is on PATH inside Studio's own environment.

## Resource tables

A workflow that needs per-dataset resources reads `workflow_tables/workflow_<name>.csv`, discovered automatically when present. The runner passes that exact path to the workflow script. The workflow performs the join itself with `join_workflow(row, table, on=(...))`, naming its own key columns, and validates the column tuple against its `WORKFLOW_COLUMNS`.

Sibling workflows that need identical resources declare `WORKFLOW_TABLE` instead of duplicating the CSV — `workflow_proteobench_run.py` and `workflow_proteobench_pmultiqc.py` read `workflow_proteobench.csv` this way. A declared table can be CSV or TSV; `convert_no_param` uses `workflow_no_param.tsv` to map the corpus software label to the actual result producer passed as `--software`.

## Software hints

When vendor parameters exist, conversion commands pass `--params` and `--software` using the dataset's parameter-file software. A `FragPipe (DIA-NN quant)` dataset therefore passes `fragpipe`; APB2 reads its parameters and limits result-rule candidates to FragPipe and the declared DIA-NN quantifier. The full-level `convert`, `aggregate`, and `aggregate_medpolish` workflows accept parameter-free rows and then use the result producer as their software hint; the parameter file is a dependency only when provided. Studio does not detect result formats itself.

`convert_no_param` instead passes the TSV's result-producer software to APB2 without `--params`; `FragPipe (DIA-NN quant)` maps to `DIA-NN`. Its step and Snakemake dependency list omit the vendor parameter file. APB2 owns column-based rule identification, and unresolved evidence appears as a failed dataset report.

## Optional tool timings

A workflow may declare one or more outputs `Artifact(role="tool_timings", path=...)` when its tools can write timing JSON files. Their absence from other workflows needs no placeholder. Each file is tool-owned: Studio records its path and size like any output, but never copies phase values into `StepResult.runtime_seconds` or memory telemetry. In that step's Visualizations tab, Studio timings and each available tool/operation timing file have separate subtabs. A tool subtab facets its phases vertically, with an independent duration scale for each phase, a shared selectable x-axis (vendor input size or the ion `var` dimension), and one software legend whose colors remain consistent between phases. The ion count comes from the same step's APB representation sidecar; a missing ion level omits that point on the ion-variable axis. Timing files do not become the dataset's scientific Output or an artifact-size point.

The version-1 JSON contract is `{"format":"apb-tool-timings","format_version":1,"tool":"apb2","operation":"convert","phases":[{"name":"read","seconds":1.25}]}`. Phase names are unique, and seconds are finite nonnegative numbers. Additional tool-specific details, such as APB2's per-level timings, may coexist with `phases`. The convert workflow passes `--timings-output` to APB2. The integrated `proteobench_run` and `proteobench_pmultiqc` workflows pass `--timings-dir` to `apb-proteobench run quant` (and `proteobench_entrapment` to `run entrapment`), which writes separate APB2 conversion, FASTA verification, and ProteoBench benchmark timing files even though those operations execute in one process. A missing file still fails a step that explicitly declared it; runs and workflows without a timing artifact remain valid.

## Running it through the runners

`convert_ion` is the single-tool ion-only counterpart to `convert`: it passes the positional `ion` level to APB2, writes one H5AD in HDF5 mode, and declares the same representation and timing sidecars. No resource CSV is needed. Unsupported ion inputs remain visible as failed datasets rather than being silently removed.

A workflow needs no runner change to become runnable. `--workflow <name>` selects it; the file's presence in `workflows/` is the whole registration. `corpus workflows` lists what is packaged, with the tools and table each one declares.

| Task | Command |
| --- | --- |
| See what is runnable | `uv run corpus workflows` |
| Inspect configuration | `uv run corpus configure` |
| Run one workflow, routine fixtures | `uv run corpus run routine --workflow <name>` |
| Run full regular benchmark corpus | `uv run corpus run proteobench --workflow proteobench_pmultiqc` |
| Confirm a run settled | `uv run corpus run routine --workflow <name> --no-force --dry-run` |
| Inspect results | `uv run corpus view` |
| Stop the viewer | `uv run corpus view stop` |

`corpus run --help` shows the configured corpus names and their resolved CSV targets, followed by the immediate controls:

- `CORPUS` — required name from `corpuses.json`
- `--workflow` — which workflow; default `convert`
- `--format` — requested backend: `hdf5`, `duckdb`, or `parquet`; native exports retain their target format
- `--cores` — maximum parallel Snakemake jobs, default 3
- `--force`/`--no-force` — force is enabled by default and replaces the selected combination’s previous generated results without archiving
- `--dry-run` — nondestructive preview; combine with `--no-force` to confirm existing results are current

`corpus run <corpus>` resolves the name through the flat `corpuses.json` object and runs one selected workflow. Relative inventory paths are resolved beside that config file, so `routine`, `routine_pb`, and `proteobench` are ordinary editable mappings rather than CLI branches. The `proteobench` inventory contains regular ProteoBench quantification inputs eligible for `proteobench_pmultiqc`; The acquisition inventory `all.csv` additionally includes peptidoform, plasma, entrapment and acquired Zenodo inputs, but has no default execution alias or selected stress run. Corpus inventories and workflow resources remain configured in their CSV/text files, roots live in Studio's settings JSON, and required tools resolve from `PATH`. `corpus configure` reports each exact source file together with the values read from it, including configured corpuses and complete workflow-table rows; it never writes configuration.

## Selected combinations

Three Fish scripts select 13 corpus/workflow/format combinations. The routine inventory contains 16 bounded datasets, including multifile MaxQuant, i2MassChroQ 1.2.9, DIA-NN 2.3.0, Sage 0.14.6, AlphaDIA 2.1.0 Parquet and two-file AlphaDIA 1.12.1. The independent `routine_pb` inventory contains the 15 catalogued ProteoBench datasets from that small selection, excluding the Zenodo MaxQuant entrapment folder. It runs the three separate calls: conversion, FASTA peptide verification and ProteoBench quantification scoring. The Format column names the requested storage backend; Output names the scientific artifact’s actual extension, which the Runs and Run overview tables read from persisted reports. Missing or pending outputs show `—`; HDF5 alone does not determine H5AD versus H5MU.

| Script | Corpus | Workflow | Format | Output |
| --- | --- | --- | --- | --- |
| routine | routine | convert | hdf5 | `.h5mu` |
| routine | routine | convert | duckdb | `.duckdb` |
| routine | routine | convert | parquet | `.parquet` |
| routine | routine_pb | proteobench | hdf5 | `.h5mu` |
| routine | routine | aggregate_medpolish | hdf5 | `.h5mu` |
| overview | proteobench | proteobench_pmultiqc | hdf5 | `.h5ad` |
| overview | proteobench_plasma | proteobench_plasma | hdf5 | `.h5ad` |
| overview | entrapment | proteobench_entrapment | hdf5 | `.h5ad` |
| overview | directlfq | convert_no_param | hdf5 | `.h5mu` |
| export | routine | export_msmu | hdf5 | `.h5mu` |
| export | routine | export_prolfqua | hdf5 | `.h5ad` |
| export | routine | export_proteopy | hdf5 | `.h5ad` |
| export | routine | export_alphapepttools | hdf5 | `.h5mu` |

APB Parquet outputs are directories. Export workflows write their target’s native H5AD/H5MU artifact independently of the backend label, so running each native export once covers its output contract.

ProteoBench FASTA checks use the reference prescribed by the module, rather than a submitter-specific search database. Both [plasma](https://proteobench.readthedocs.io/en/latest/modules/dia/dia-ion-plasma/) and [ZenoTOF](https://proteobench.readthedocs.io/en/latest/modules/dia/dia-ion-zenotof/) prescribe `ProteoBenchFASTA_MixedSpecies_HYE.fasta` (verified 8 October 2026). File details displays the persisted FASTA source beside matched/unmatched counts and the I/L-equivalence setting. A mismatch can indicate a searched sequence variant, an absent reference accession, or strict I/L matching; it is not automatically a parser failure.

Plasma acquisition is `fixture corpus proteobench-plasma`; its corpus and report workflow are both named `proteobench_plasma`. `proteobench_plasma_run` exposes the corresponding scores-only workflow. They use the same ProteoBench scoring engine as regular pMultiQC, but their workflow table selects unnormalised `Precursor_Quantity` for DIA-NN and FragPipe rather than primary X. The generic pMultiQC table has no `dia_plasma` row and always selects X, so those workflows are not interchangeable. DirectLFQ conversion uses producer hints because its fixtures have no vendor parameter files.

```fish
fish scripts/routine_corpuses.fish --plan        # print forced commands without changing files
fish scripts/overview_corpuses.fish --plan       # print forced commands without changing files
fish scripts/export_corpuses.fish               # force every native routine export
fish scripts/routine_corpuses.fish              # replace previous results; keep no archives
fish scripts/routine_corpuses.fish --dry-run    # preview forced jobs; preserve current results
fish scripts/routine_corpuses.fish --plan --clean # preview deleting all formats per pair
```

All three scripts work from any directory, run combinations sequentially and always include `--force`. The routine and overview scripts accept `--cores N` (default 3) and `--plan`; the export script uses 3 cores. An explicit `--force` is harmless and redundant. `--clean` additionally deletes every saved format for each selected corpus/workflow pair, once before that pair’s first run. `--clean` and `--dry-run` cannot be combined; `--plan` previews either without executing it. Script dry-runs pass `--force --dry-run`, which previews a full rerun without deleting results. To check that a saved combination is settled, use the CLI directly with `--no-force --dry-run`. Command failures stop the script; APB failures remain dataset reports, so inspect their statuses even when scheduling succeeds.

`export_corpuses.fish` resolves `apb-export` from PATH first, then the sibling `apb-export/.venv/bin/apb-export`, exposing that environment to its subprocesses.

`aggregate_medpolish` needs no workflow table. It converts every compatible vendor level, then runs only `medpolish --layers primary` on the source level’s X, rolling up to the coarsest reachable identity. A new target uses the median-polish abundance as X; an existing target keeps its vendor X and gains the derived abundance as an additional layer. The general `aggregate` implementation remains available and reads its per-software method table to aggregate every quantitative layer with `--layers all`; it is deferred from the selected scripts. The all conversion stress run is retired; the remaining inventories cover 247 of its 250 input paths, excluding three WOMBAT peptidoform fixtures. Input overlap does not reproduce its full-level conversion coverage because the larger ProteoBench workflows persist ion-only results.

## Clearing results

Cleaning deletes every current corpus/workflow/format directory and every legacy hash-named run under the configured output root, including reports, artifacts, histories, logs and snapshots. Fixture inputs and the saved-settings store remain untouched. Force is enabled by default and deletes previous reports, artifacts, result indexes, logs and any legacy history for the selected corpus/workflow/format before rerunning every dataset. It retains configuration snapshots and scheduler metadata needed for execution, creates no archive, and does not clean other combinations. `--dry-run` previews the forced rerun without deleting results. `--no-force --dry-run` inspects the existing run and should schedule zero jobs once it is settled.

```bash
uv run corpus clean                              # every run under the output root
uv run corpus clean proteobench proteobench_pmultiqc  # selected combination, all formats
```

`corpus clean` reports each run as deleted or not deleted and exits non-zero if any failed. A selected clean requires both positional names and matches current stable run directories exactly; bare clean also deletes legacy hash-named runs. Cleaning deliberately does not validate the whole manifest — it reads only `data_root`, for the guard that refuses to touch a run overlapping the fixture store — so a run recorded under an older manifest schema can still be deleted.

The corpus viewer does not read the published `index.json` for its selector. Its `GET /api/catalog` endpoint scans current stable run operation files on every request. Running, succeeded, failed and interrupted combinations are selectable; prepared manifests without an operation and legacy hashed directories are not. Consequently the two-second viewer poll reflects both run creation and run deletion without a catalog rewrite.

## Verifying a new workflow

```bash
make test                                         # unit gate
uv run corpus run routine --workflow <name> --dry-run
uv run corpus run routine --workflow <name>
uv run corpus run routine --workflow <name> --no-force --dry-run  # confirm zero jobs
uv run corpus view                                # start or restart the viewer
uv run corpus view stop                           # stop the viewer
```

Add unit coverage for the planned steps — the names, the chaining between declared inputs and outputs, and each refusal — so a workflow is testable without running any tool. `available_workflows()` and `workflow_tools()` are asserted in `tests/test_corpus.py` and will fail until the new name is listed there.
