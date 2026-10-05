# APB Studio

APB Studio downloads ProteoBench and Zenodo fixtures, runs concrete Python workflows over existing files, and serves two local JavaScript viewers.

## Start

```bash
uv sync --frozen --extra dev --group docs
uv run fixture corpus smallest-per-module
uv run corpus run routine
uv run corpus view
```

The `aggregate` workflow runs the private `apb-aggregate` command, which APB Studio does not install. Install it once with `uv tool install --editable ../apb-aggregate`, or pass `--aggregate-executable`; every other workflow runs without it.

The corpus viewer is at http://127.0.0.1:8766/. `uv run corpus view` starts it or safely restarts the matching managed process; another viewer or service on the port is refused. `uv run corpus view stop` stops it. The viewer shows saved settings, the absolute server artifact directory, exact CSV inputs, workflow source, live dataset/step progress, stdout, stderr, errors, runtime, peak memory, and input/output-size charts. Input, parameter, TOML/FASTA resource, generated artifact, and frozen snapshot links retain complete filenames. Folders open as browsable listings in new tabs; text and HTML display inline. JSON opens directly as `application/json`, unchanged by the server, using the browser's native display. Binary files such as H5MU, H5AD, DuckDB and individual Parquet files download instead of opening preview tabs; APB Parquet directories remain browsable. Large files stream from disk. It reads persisted files and remains useful after the runner exits. Refresh polling happens every two seconds. `uv run fixture view` starts the fixture viewer on port 8765.

The executables declared by the selected workflow must be on `PATH`. The development extra installs the workspace checkouts for local integration testing; Studio invokes them only through subprocesses.

## Inputs

The `fixture` entry point owns acquisition, corpus construction, and the fixture viewer. `fixture corpus all` downloads every catalogued submission and writes `all.csv`. The bounded alternatives download the smallest submission by feature count for each module, module/software pair, or module/software/version tuple and write that selection to `routine.csv`:

```bash
uv run fixture corpus all
uv run fixture corpus smallest-per-module
uv run fixture corpus smallest-per-software
uv run fixture corpus smallest-per-software-version
uv run fixture corpus maxquant-entrapment
uv run fixture corpus directlfq
uv run fixture view
```

`maxquant-entrapment` and `directlfq` download the Zenodo records described in [docs/datasets.md](docs/datasets.md) and write `maxquant_entrapment.csv` and `directlfq.csv`.

Every generated corpus has the same minimal schema:

```csv
input_file,vendor_parameter_file,module,software_name
```

Inventories live in `corpuses/`: `all.csv` contains every available file pair, `proteobench.csv` contains the ion-level subset used by the ProteoBench/pMultiQC workflow, and `routine.csv` contains the most recently requested bounded strategy. The flat `corpuses.json` config maps short names to inventory paths relative to the config file; edit it to add another named corpus. There is no separate selection file: the strategy is explicit in the `fixture corpus` command, and the resulting CSV is the runner input.

Both row paths are relative to the `test_data_root` in Studio's settings JSON, not the CSV directory. Each input file is unique. Execution joins only `input_file_path` and `input_file_size_bytes` from `downloads.csv` under that root; acquisition status remains outside pipeline state.

Workflow-specific resources live in `workflow_tables/`. The exact conventional `workflow_<name>.csv` is selected automatically when present; a workflow may declare `WORKFLOW_TABLE` to read a sibling workflow's table instead. The workflow declares its join columns explicitly and uses a validated many-to-one lookup. `workflow_aggregate.csv` contains exactly `software_name,method` and joins on `software_name`; `workflow_proteobench.csv` contains exactly `module,fasta,level` and joins on `module`, and all ProteoBench workflows read it. Workflow tables are edited by hand; `fixture corpus` never writes `workflow_tables/`. Resource paths are relative to the same data root. `module` is passed to `apb-proteobench` as a packaged module name; Studio neither fetches nor stores module definitions. Conversion needs no companion CSV and records `workflow_table: null`.

## Execution settings and stable runs

Execution settings explicitly record `corpus_name`, `corpus`, optional `workflow_table`, optional acquisition `downloads`, `data_root`, `workflow`, `format`, a `tools` map holding one resolved path per executable the workflow declared, and `cores`. Each corpus/workflow/format directory saves its current settings as `execution_settings.json`; there is no separate settings store or settings hash. Source paths are absolute. When `<data_root>/downloads.csv` exists it is selected automatically.

```bash
# Show each source file together with the values read from it.
uv run corpus configure
```

`corpus configure` is read-only. Its compact JSON names the main settings file, effective settings, run defaults, corpus config and resolved corpus mappings, acquisition metadata, and workflow-table directory. The viewer has one selector labelled `corpus · workflow · format`. Its `GET /api/catalog` endpoint scans the stable output folders on every poll, so a newly running operation appears and a cleaned operation disappears without rebuilding a static index. Current settings and CSV snapshots live inside that combination directory and are rewritten only when their contents change. Legacy hashed directories, directories without operation state, and cleaned operations stay out of the selector.

The main Datasets tab is one compact table with the last observed scientific output from a succeeded step and a Show more button per dataset; failed or skipped steps never contribute the summary output. Its Ion vars column reads the persisted ion-level `var` dimension from that output's APB representation, not the vendor table's row count. Show more opens with an Inputs & outputs tab containing every planned and observed input, output and intermediate path with its available size, including an artifact written before a later output or sidecar publication failed. APB metadata is a separate top-level tab with nested MuData and modality tabs which render each owning object’s tool namespaces under `uns["apb"]`; another top-level tab exposes the complete representation JSON which drives the viewer. Every quantification-level or annotation-table modality has an AnnData tab containing only scientific tables and nested tabs for its axes, individual layers, and aligned structures. This prevents an intermediate converted level from being repeated beside the same level in the final aggregate. Known JSON-text provenance fields render as structured trees, while invalid text remains inspectable. Quantitative layers use Plotly box traces from bounded persisted per-observation quartiles with explicit observation and quantity axes; categorical layers show fixed-size category and missing-value counts without treating their codes as numbers. The complete execution report remains an expandable diagnostic in Inputs & outputs. The Visualizations tab creates a Workflow tab plus one tab for every recorded step/tool pair. The X axis selector switches between vendor input size and the persisted ion `var` dimension; points without an ion count are omitted rather than shown at zero. Each tab contains runtime, peak process-tree RSS and scientific artifact size; the Workflow tab sums observed step runtimes, takes their maximum memory and retains distinct step/software artifact series. Partial failed-workflow evidence remains visible, missing values are not zero, and JSON representation sidecars are excluded.

The Structure tab depicts physical AnnData ownership using representation version 4. H5AD shows one AnnData with combined tool namespaces directly under `uns["apb"]`; H5MU provides a MuData-container subtab and one subtab per embedded AnnData, including annotation modalities. MuData stores common `provenance` under each tool once, while each AnnData stores its own rules, roles and results. ProteoBench keeps `annotation` matching evidence beside `scoring[quantity_name]`; FASTA keeps operation-specific validation summaries. There are no shared/level wrappers or client-side ownership reconstruction. The viewer shows actual trees, scalar values and object paths, with primary quantity names such as `Intensity · X`. Root metadata and cross-modality relations appear only in the container subtab. The physical reconstruction descriptor is explicitly noted as omitted, never displayed as a fabricated value. Older representation versions are rejected; existing saved artifacts are not migrated.

## Run

```bash
uv run corpus workflows
uv run corpus configure                                # inspect file-driven configuration
uv run corpus run routine                              # routine corpus, convert, HDF5
uv run corpus run routine --workflow convert_ion --cores 1
uv run corpus run routine --workflow aggregate --format duckdb
uv run corpus run routine --workflow proteobench --format parquet
uv run corpus run routine --workflow proteobench_run
uv run corpus run routine --workflow proteobench_pmultiqc
uv run corpus run proteobench --workflow proteobench_pmultiqc
uv run corpus run plasma --workflow plasma_run
uv tool install --editable ../apb-export  # once; apb-export stays out of Studio's lock
uv run corpus run routine --workflow export_prolfqua
uv run corpus run entrapment --workflow proteobench_entrapment
uv run corpus run all --workflow convert               # full corpus, one workflow
uv run corpus run routine --dry-run                    # confirm the routine run settled
```

`convert_ion` requests only the ion level from APB2 and keeps its separate conversion timings. HDF5 output is a single-level `converted.h5ad`; Parquet and DuckDB use their selected formats. The original `convert` workflow still converts all compatible levels. The complete `all` corpus includes peptidoform-only datasets, which correctly fail an ion-only request.

The `run` surface takes one corpus name plus `--workflow`, `--format`, `--cores`, `--dry-run`, and `--force`. `corpus run --help` reads `corpuses.json` and shows every available corpus with its resolved target plus every discovered packaged workflow. Roots come from Studio's settings JSON; required executables resolve from `PATH`.

`workflow_convert.py` invokes `apb2 convert` once for all compatible levels and writes the selected format directly. It also requests a separate `converted.timings.json` artifact: the convert step's Visualizations tab shows Studio timings and APB2 internal phases in separate subtabs when that file is present. Studio's subprocess runtime and memory remain independent. `workflow_aggregate.py` converts, then runs one `aggregate-<method>` step per `;`-separated entry in the table's `method` cell; each step aggregates to the coarsest reachable identity and adds its layers to the previous step's result. The table runs `all` for every vendor and adds `rlm_confidence_case` and `rlm_confidence_precision` for AlphaPept, DIA-NN, MaxQuant and Spectronaut, whose every rule variant catalogues ion identification confidence. Conversion includes all compatible levels; aggregation starts at the finest level present in the persisted hierarchy.

The ProteoBench workflows score the same module by documented routes, so their step telemetry is directly comparable. `proteobench_run`, `plasma_run` and `proteobench_entrapment` also write each dataset's ProteoBench datapoint as `scores.json`, in the layout of the upstream datapoints, for comparison with ProteoBench's own scores. `workflow_proteobench.py` runs three separately measured calls — `apb2 convert`, `apb-fasta verify-peptides`, `apb-proteobench benchmark` — passing only the selected HDF5, Parquet, or DuckDB format between them, so every intermediate is on disk and inspectable. `workflow_proteobench_run.py` runs one `apb-proteobench run quant` call that keeps conversion, peptide verification, annotation, and scoring as APB2 `ParsedLevels` values and calls `write_parsed_levels` once for the selected final format. That one process writes three separate timing files for its APB2, FASTA, and ProteoBench operations; the run step's Visualizations tab presents each as its own subtab beside Studio timings. `workflow_proteobench_pmultiqc.py` requires the table's `ion` quantification level, passes `--x` for ProteoBench-compatible primary-layer-only scoring, persists its single-level HDF5 result as `scored.h5ad`, measures the integrated call including `result_performance.csv` and ProteoBot JSON serialization, then measures pMultiQC report generation separately in interactive mode so large result tables are not flattened to static PNGs. All three read `workflow_proteobench.csv` for the FASTA and declared level, and name apb-proteobench's packaged module. `workflow_proteobench_entrapment.py` runs one `apb-proteobench run entrapment` call per entrapment-corpus upload, reading `workflow_proteobench_entrapment.csv` for the module's protein database: the Parquet file `fixture` acquisition writes beside each FASTA with `protein-fasta database`, which also gives every peptide its target/entrapment label and pair. `uv run fixture databases` rebuilds those files after protein_fasta rule changes; a stale file is refused.

Every workflow uses the same workflow CLI and receives its resolved executables as repeated `--tool NAME=PATH` pairs; the Snakefile parallelizes one workflow script per dataset. `corpus run <corpus>` requires a positional name, resolves it through `corpuses.json`, and runs one workflow, defaulting to `convert`. `corpus workflows` lists the discovered workflows, and `corpus configure` reports the file-driven configuration.

Snakemake schedules one script per dataset. Its only dataset output is the JSON report; APB artifacts are recorded inside that report. A failed APB command stops the linear workflow, records later steps as skipped, writes the report, and returns success to Snakemake. A framework failure fails the job. A successful Snakemake operation therefore does not imply that every APB command succeeded: inspect the report statuses.

The run directory is `<output_root>/corpus/<corpus>/<workflow>/<format>/`. Snakemake alone decides whether each dataset is current. Every rule declares its one-row corpus snapshot, vendor table, parameter file, workflow table and implementation, shared execution modules, tool launcher and distribution metadata, plus editable tool sources when available; tool versions and the effective command are rule parameters. Cores and viewer code do not invalidate scientific results. Use `--force` only for deliberate repeat measurement; previous reports and artifacts move into the stable directory's `history/` folder first.

```bash
uv run corpus run routine --force
uv run corpus clean                                      # every saved run
uv run corpus clean proteobench proteobench_pmultiqc     # this corpus/workflow, all formats
```

Bare `clean` deletes every current or legacy run directory under the configured output root. With both positional names, it deletes only that corpus/workflow combination across its saved formats; legacy hash-named runs remain for bare `clean`. Fixture files and the small saved-settings store remain untouched. Force preserves the previous attempt under the active stable directory before measuring it again.

## Persisted files

| File | Purpose |
| --- | --- |
| `run.json` | Settings and links to every expected dataset report, available before jobs start |
| `execution_settings.json` | Exact reusable configuration used for this run, including both source CSV paths |
| `corpus.csv` | Frozen full copy of the chosen source inventory |
| `selected_corpus.csv` | Exact selected rows displayed and indexed for the current combination |
| `datasets/<key>.csv` | One selected row per Snakemake job, updated independently |
| `input_metadata.csv` | Selected vendor input sizes joined explicitly from the acquisition downloads table |
| `workflow_<name>.csv` | Optional copied workflow table |
| `workflow_<name>.py` | Source snapshot shown by the viewer |
| `operation.json` | Scheduler running/succeeded/failed/interrupted state |
| `reports/<key>.progress.json` | Atomic live step state and recent output |
| `reports/<key>.json` | Complete dataset result with full stdout and stderr |
| `corpus_index.json` | Final validated index pointing to all dataset reports |
| `snakemake.log` | Scheduler output |
| `artifacts/**/*.apb.json` | Compact APB scientific representations for final and intermediate results |

Execution JSON documents have `schema_version: 2`; scientific representation documents have their own `format_version`. Report/index links are relative to the run directory and can be fetched directly by JavaScript. Final reports retain full logs; live progress carries the last 16 KiB of each stream. Memory is sampled every 100 ms as summed RSS across the APB process tree; it is an estimate and can miss short spikes. Declared input artifacts record observed sizes when present, and every output that exists after a command records its total file or recursive-directory byte size independently of the command status.

## Development

```bash
make check
make test
make test-web
make package
make docs
```

Run the configured `routine` corpus after execution changes, report the dataset names and outcomes, and dry-run it again to confirm zero jobs. Runs against the configured `all` corpus are for deliberate broader checks.

See [architecture](docs/architecture.md) for module ownership and [development](docs/development.md) for the quality gates.
