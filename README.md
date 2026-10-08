# APB Studio

APB Studio downloads ProteoBench and Zenodo fixtures, runs concrete Python workflows over existing files, and serves two local TypeScript viewers.

## Start

```bash
uv sync --frozen --extra dev --group docs
uv run fixture corpus smallest-per-module
uv run corpus run routine
uv run corpus view
```

The `aggregate` and `aggregate_medpolish` workflows run the private `apb-aggregate` command, which APB Studio does not install. Install it once with `uv tool install --editable ../apb-aggregate` so it is on PATH.

The corpus viewer is at http://127.0.0.1:8766/. `uv run corpus view` starts it or safely restarts the matching managed process; another viewer or service on the port is refused. `uv run corpus view stop` stops it. The viewer shows saved settings, the absolute server artifact directory, exact CSV inputs, workflow source, live dataset/step progress, stdout, stderr, errors, runtime, peak memory, and input/output-size charts. Input, parameter, TOML/FASTA resource, generated artifact, and frozen snapshot links retain complete filenames. Folders open as browsable listings in new tabs; text and HTML display inline. JSON opens directly as `application/json`, unchanged by the server, using the browser's native display. Binary files such as H5MU, H5AD, DuckDB and individual Parquet files download instead of opening preview tabs; APB Parquet directories remain browsable. Large files stream from disk. It reads persisted files and remains useful after the runner exits. Refresh polling happens every two seconds. `uv run fixture view` starts the fixture viewer on port 8765.

The executables declared by the selected workflow must be on `PATH`. The development extra installs the workspace checkouts for local integration testing; Studio invokes them only through subprocesses.

## Inputs

The `fixture` entry point owns acquisition, corpus construction, and the fixture viewer. `fixture corpus all` downloads every catalogued ProteoBench submission, including plasma and entrapment, and publishes `all.csv` with every acquired ProteoBench and configured Zenodo dataset. The bounded alternatives download the smallest submission by feature count for each module, module/software pair, or module/software/version tuple and write that selection to `routine.csv`:

```bash
uv run fixture corpus all
uv run fixture corpus smallest-per-module
uv run fixture corpus smallest-per-software
uv run fixture corpus smallest-per-software-version
uv run fixture corpus maxquant-entrapment
uv run fixture corpus directlfq
uv run fixture corpus proteobench-plasma
uv run fixture view
```

`maxquant-entrapment` and `directlfq` download the Zenodo records described in [docs/datasets.md](docs/datasets.md), write their source inventories, and refresh `all.csv`. MaxQuant entrapment has no standalone execution-corpus alias; its multifile fixture remains in routine and the acquisition inventory.

Every generated corpus has the same minimal schema:

```csv
input_file,vendor_parameter_file,module,software_name
```

Inventories live in `corpuses/`: `all.csv` is the deduplicated acquisition inventory of every vendor dataset, including parameter-free directLFQ inputs; it has no default execution alias or selected stress run; `proteobench.csv` contains the regular ion-level inputs used by the ProteoBench/pMultiQC workflow, and `proteobench_plasma.csv` contains plasma inputs acquired with `fixture corpus proteobench-plasma`. The checked-in `routine.csv` contains 16 bounded datasets, including multifile MaxQuant, i2MassChroQ 1.2.9, DIA-NN 2.3.0 and Sage 0.14.6; invoking a smallest-per-group acquisition command replaces that inventory with its selected strategy. The separate `routine_pb.csv` contains 15 small catalogued ProteoBench datasets from that routine selection, excluding the Zenodo entrapment folder, for three-call quantification scoring. The flat `corpuses.json` config maps short names to inventory paths relative to the config file; edit it to add another named corpus. There is no separate selection file: the strategy is explicit in the `fixture corpus` command, and the resulting CSV is the runner input.

Both row paths are relative to the `test_data_root` in Studio's settings JSON, not the CSV directory. Each input file is unique. Execution joins only `input_file_path` and `input_file_size_bytes` from `downloads.csv` under that root; acquisition status remains outside pipeline state.

Workflow-specific resources live in `workflow_tables/`. The exact conventional `workflow_<name>.csv` is selected automatically when present; a workflow may declare `WORKFLOW_TABLE` to read a sibling workflow's table instead. The workflow declares its join columns explicitly and uses a validated many-to-one lookup. `workflow_aggregate.csv` contains exactly `software_name,method` and joins on `software_name`; `workflow_proteobench.csv` contains exactly `module,fasta,level` and joins on `module` for regular quantification benchmarks; plasma workflows use `workflow_proteobench_plasma.tsv`, and entrapment uses `workflow_proteobench_entrapment.csv`. Workflow tables are edited by hand; `fixture corpus` never writes `workflow_tables/`. Resource paths are relative to the same data root. `module` is passed to `apb-proteobench` as a packaged module name; Studio neither fetches nor stores module definitions. Conversion needs no companion CSV and records `workflow_table: null`.

## Execution settings and stable runs

Execution settings explicitly record `corpus_name`, `corpus`, optional `workflow_table`, optional acquisition `downloads`, `data_root`, `workflow`, `format`, a `tools` map holding one resolved path per executable the workflow declared, and `cores`. Each corpus/workflow/format directory saves its current settings as `execution_settings.json`; there is no separate settings store or settings hash. Source paths are absolute. When `<data_root>/downloads.csv` exists it is selected automatically.

```bash
# Show each source file together with the values read from it.
uv run corpus configure
```

`corpus configure` is read-only. Its compact JSON names the main settings file, effective settings, run defaults, corpus config and resolved corpus mappings, acquisition metadata, and workflow-table directory. Runs uses a Saved runs header for the catalog. Run overview and File details show a sticky selected-run banner naming Corpus, Workflow, Format, the observed Output extension and dataset progress. Change run opens a compact corpus/workflow/format selector; run search lives in the Runs sidebar. The Runs tab has a left search and corpus, workflow and format facets with counts, beside the sortable run catalog. Filters narrow both the catalog and selector; an opened combination stays available when it falls outside those filters. Both Runs and Run overview show the actual scientific Output extension from recorded artifacts; Format remains the requested backend. A missing or pending output appears as `—`, and the viewer never guesses H5AD or H5MU from `hdf5`. Its `GET /api/catalog` endpoint scans the stable output folders on every poll, so a newly running operation appears and a cleaned operation disappears without rebuilding a static index. Current settings and CSV snapshots live inside that combination directory and are rewritten only when their contents change. Legacy hashed directories, directories without operation state, and cleaned operations stay out of the selector.

Run overview places dataset search and multi-select software, module and result dropdowns in a left pane, beside Datasets, Visualizations, Settings & inputs and Scheduler log subtabs. Dataset filters apply to the table, charts and file chooser; settings and scheduler logs describe the full run. Each settings subtab contains its own snapshot links, including both corpus snapshots in Corpus and the saved Python source in Workflow script. The Datasets subtab is one compact table with the last observed scientific output from a succeeded step and a frozen Open column containing Show more per dataset; failed or skipped steps never contribute the summary output. Its Ion vars column reads the persisted ion-level `var` dimension from that output's APB representation, not the vendor table's row count. Show more opens File details directly on AnnData, with Structure alongside it and individual AnnData objects in nested subtabs. File details keeps the same dataset search above its left file chooser, with additional dropdowns under a collapsed Filter options control. Each chooser entry shows the software name, an actual file or folder icon, and the persisted input size. Repeated software names also show their module, determined from the full run so labels remain stable when filtering; full paths remain available on hover and in Inputs & outputs. Filtering a file out of the chooser leaves its scientific view open, and the next refresh supplies its newest report. Inputs & outputs shows ordered step cards with input and output files, status, sizes and explicit handoffs between steps. Handoffs match exact recorded paths, so identical basenames in different locations remain separate. Full paths and exact byte counts expand per file; supporting representations and timing files expand within their owning step. Planned outputs remain visible as Not observed until their sizes are recorded, including partial failed-step artifacts when present. APB metadata is a separate top-level tab with nested MuData and modality tabs which render each owning object’s tool namespaces under `uns["apb"]`; another top-level tab exposes the complete representation JSON which drives the viewer. Every quantification-level or annotation-table modality has an AnnData object subtab containing only scientific tables and nested tabs for its axes, individual layers, and aligned structures. This prevents an intermediate converted level from being repeated beside the same level in the final aggregate. Known JSON-text provenance fields render as structured trees, while invalid text remains inspectable. Quantitative layers use Plotly box traces from bounded persisted per-observation quartiles with explicit observation and quantity axes; categorical layers show fixed-size category and missing-value counts without treating their codes as numbers. The complete execution report remains an expandable diagnostic in Inputs & outputs. The Visualizations tab creates a Workflow tab plus one tab for every recorded step/tool pair. The X axis selector switches between vendor input size and the persisted ion `var` dimension; points without an ion count are omitted rather than shown at zero. Each tab contains runtime, peak process-tree RSS and scientific artifact size; the Workflow tab sums observed step runtimes, takes their maximum memory and retains distinct step/software artifact series. Partial failed-workflow evidence remains visible, missing values are not zero, and JSON representation sidecars are excluded.

Runs declaring `apb-proteobench` also have a Score comparison subtab in Run overview. It pairs persisted APB score metadata with the downloaded submission JSON for the exact input repository and hash, without rerunning scoring. One scatter facet per score plots ProteoBench on X and APB on Y with identical numeric axis limits and a dashed `y = x` line. The MA plot checkbox switches every facet to the arithmetic mean `(APB + ProteoBench) / 2` on X and the signed difference `APB − ProteoBench` on Y, with a dashed zero line and symmetric difference limits. Switching views preserves dataset and cutoff selections, and hover retains both original scores. Dataset filters narrow the comparisons; a completeness-cutoff selector keeps replicate thresholds aligned. Software colors stay stable within the run, and hover shows both scores, their difference, submission, module and quantity. Missing or non-finite values remain unpaired, with source links and reasons in an expandable list. Entrapment compares scalar summary scores for an explicitly selected APB confidence kind against the downloaded reported-FDR score set; FDP curves are excluded.

File details adds a FASTA check subtab when peptide verification was recorded: the recorded reference FASTA, matched and unmatched feature counts per level, and whether I/L-equivalent matching was used. It reads actual result provenance, including MuData root provenance, and leaves missing sources or matching settings unknown. ProteoBench checks use the module reference, even when a submitter searched a different database; unmatched sequences therefore do not by themselves establish a conversion bug.

Oddities lists every summary entry the producers recorded in the displayed result, root and levels, with its status, value and unit, attention first. The dataset table counts entries needing attention and offers an Oddities filter; an entry recorded as not checked marks partial coverage. Run overview counts affected datasets once per software and producer metric. The final index job writes `oddities.json` version 2 from the displayed scientific output's representation; after a later workflow failure, the summary identifies its earlier successful source.

The Structure tab depicts physical AnnData ownership using representation version 5. Every result keeps a root part and one part per level, never merged: H5AD shows one AnnData with its root part in `uns["apb"]` and its level part in `uns[level]["apb"]`; H5MU provides a MuData-container subtab and one subtab per embedded AnnData, including annotation modalities. MuData stores common `provenance` under each tool once, while each AnnData stores its own rules, roles, results and summaries. ProteoBench keeps `result.scoring[quantity_name]`; FASTA keeps each level's verification result. There are no shared/level wrappers or client-side ownership reconstruction. The viewer shows actual trees, scalar values and object paths, with primary quantity names such as `Intensity · X`. Root metadata and cross-modality relations appear only in the container subtab. The physical reconstruction descriptor is explicitly noted as omitted, never displayed as a fabricated value. Older representation versions are rejected; existing saved artifacts are not migrated.

## Run

```bash
uv run corpus workflows
uv run corpus configure                                # inspect file-driven configuration
uv run corpus run routine                              # routine corpus, convert, HDF5
uv run corpus run routine --workflow convert_ion --cores 1
uv run corpus run routine --workflow aggregate_medpolish --format hdf5
uv run corpus run routine --workflow proteobench --format parquet
uv run corpus run routine --workflow proteobench_run
uv run corpus run routine --workflow proteobench_pmultiqc
uv run corpus run proteobench --workflow proteobench_pmultiqc
uv run corpus run proteobench_plasma --workflow proteobench_plasma_run
uv tool install --editable ../apb-export  # once; apb-export stays out of Studio's lock
uv run corpus run routine --workflow export_prolfqua
uv run corpus run entrapment --workflow proteobench_entrapment
uv run corpus run routine --no-force --dry-run         # confirm the routine run settled
```

`convert_ion` requests only the ion level from APB2 and keeps its separate conversion timings. HDF5 output is a single-level `converted.h5ad`; Parquet and DuckDB use their selected formats. The original `convert` workflow still converts all compatible levels. Peptidoform-only datasets in the acquisition inventory correctly fail an ion-only request.

The `run` surface takes one corpus name plus `--workflow`, `--format`, `--cores`, `--dry-run`, and `--force`/`--no-force`. Runs force by default, deleting the selected combination’s previous generated results and legacy history without archiving. `--dry-run` is nondestructive; use `--no-force --dry-run` to confirm a completed run schedules zero jobs. `corpus run --help` reads `corpuses.json` and shows every available corpus with its resolved target plus every discovered packaged workflow. Roots come from Studio's settings JSON; required executables resolve from `PATH`.

Three editable Fish scripts select 13 saved combinations: [routine_corpuses.fish](scripts/routine_corpuses.fish) runs routine conversion in three storage formats, the three-call ProteoBench scoring workflow on `routine_pb` and primary-X median-polish aggregation in HDF5; [overview_corpuses.fish](scripts/overview_corpuses.fish) runs ProteoBench pMultiQC, the `proteobench_plasma` report, entrapment scoring and directLFQ conversion; [export_corpuses.fish](scripts/export_corpuses.fish) runs the four routine native exports. Every script always uses `--force`, deleting previous results without retaining archives. The routine and overview scripts accept `--plan` to print commands without changing files and `--dry-run` to preview forced jobs without deleting results. The export script uses `apb-export` from PATH or the sibling export package's virtual environment. See [selected combinations and actual output extensions](docs/workflows.md#selected-combinations) for the complete list and cleanup controls.

`workflow_convert.py` invokes `apb2 convert` once for all compatible levels and writes the selected format directly. It also requests a separate `converted.timings.json` artifact: the convert step's Visualizations tab shows Studio timings and APB2 internal phases in separate subtabs when that file is present. Studio's subprocess runtime and memory remain independent. `workflow_aggregate.py` converts, then runs one `aggregate-<method>` step per `;`-separated entry in the table's `method` cell; each step aggregates to the coarsest reachable identity and adds its layers to the previous step's result. The table runs `all` for every vendor and adds `rlm_confidence_case` and `rlm_confidence_precision` for AlphaPept, DIA-NN, MaxQuant and Spectronaut, whose every rule variant catalogues ion identification confidence. Conversion includes all compatible levels; aggregation starts at the finest level present in the persisted hierarchy and processes every available quantitative layer with `--layers all`. General all-layer aggregation remains available but is deferred from the selected scripts. HDF5 conversion stores compatible levels together as MuData.

The ProteoBench workflows score the same module by documented routes, so their step telemetry is directly comparable. `proteobench_run`, `proteobench_plasma_run` and `proteobench_entrapment` also write each dataset's ProteoBench datapoint as `scores.json`, in the layout of the upstream datapoints, for comparison with ProteoBench's own scores. `workflow_proteobench.py` runs three separately measured calls — `apb2 convert`, `apb-fasta verify-peptides`, `apb-proteobench benchmark` — passing only the selected HDF5, Parquet, or DuckDB format between them, so every intermediate is on disk and inspectable. `workflow_proteobench_run.py` runs one `apb-proteobench run quant` call that keeps conversion, peptide verification, annotation, and scoring as APB2 `ParsedLevels` values and calls `write_parsed_levels` once for the selected final format. That one process writes three separate timing files for its APB2, FASTA, and ProteoBench operations; the run step's Visualizations tab presents each as its own subtab beside Studio timings. `workflow_proteobench_pmultiqc.py` requires the table's `ion` quantification level, passes `--x` for ProteoBench-compatible primary-layer-only scoring, persists its single-level HDF5 result as `scored.h5ad`, measures the integrated call including `result_performance.csv` and ProteoBot JSON serialization, then measures pMultiQC report generation separately in interactive mode so large result tables are not flattened to static PNGs. All three read `workflow_proteobench.csv` for the FASTA and declared level, and name apb-proteobench's packaged module. `workflow_proteobench_entrapment.py` runs one `apb-proteobench run entrapment` call per entrapment-corpus upload, reading `workflow_proteobench_entrapment.csv` for the module's protein database: the Parquet file `fixture` acquisition writes beside each FASTA with `protein-fasta database`, which also gives every peptide its target/entrapment label and pair. `uv run fixture databases` rebuilds those files after protein_fasta rule changes; a stale file is refused.

Every workflow uses the same workflow CLI and receives its resolved executables as repeated `--tool NAME=PATH` pairs; the Snakefile parallelizes one workflow script per dataset. `corpus run <corpus>` requires a positional name, resolves it through `corpuses.json`, and runs one workflow, defaulting to `convert`. `corpus workflows` lists the discovered workflows, and `corpus configure` reports the file-driven configuration.

Snakemake schedules one script per dataset. Its only dataset output is the JSON report; APB artifacts are recorded inside that report. A failed APB command stops the linear workflow, records later steps as skipped, writes the report, and returns success to Snakemake. A framework failure fails the job. A successful Snakemake operation therefore does not imply that every APB command succeeded: inspect the report statuses.

The run directory is `<output_root>/corpus/<corpus>/<workflow>/<format>/`. Snakemake alone decides whether each dataset is current. Every rule declares its one-row corpus snapshot, vendor table, parameter file, workflow table and implementation, shared execution modules, tool launcher and distribution metadata, plus editable tool sources when available; tool versions and the effective command are rule parameters. Cores and viewer code do not invalidate scientific results. Force is enabled by default: it deletes previous generated results and any legacy history for that combination, then reruns every dataset without archiving. `--dry-run` previews that rerun without deleting results; `--no-force --dry-run` checks whether existing results are current.

```bash
uv run corpus run routine                              # force is the default
uv run corpus clean                                      # every saved run
uv run corpus clean proteobench proteobench_pmultiqc     # this corpus/workflow, all formats
```

Bare `clean` deletes every current or legacy run directory under the configured output root. With both positional names, it deletes only that corpus/workflow combination across its saved formats; legacy hash-named runs remain for bare `clean`. Fixture files and the small saved-settings store remain untouched. Force clears only the selected format's generated results and keeps its configuration snapshots for the rerun.

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
| `oddities.json` | Versioned producer summary entries, source provenance and affected-dataset counts |
| `snakemake.log` | Scheduler output |
| `artifacts/**/*.apb.json` | Compact APB scientific representations for final and intermediate results |

Execution JSON documents have `schema_version: 2`; scientific representation documents have their own `format_version`. Report/index links are relative to the run directory and can be fetched directly by the browser. Final reports retain full logs; live progress carries the last 16 KiB of each stream. Memory is sampled every 100 ms as summed RSS across the APB process tree; it is an estimate and can miss short spikes. Declared input artifacts record observed sizes when present, and every output that exists after a command records its total file or recursive-directory byte size independently of the command status.

## Development

```bash
make check
make test
make test-web
make package
make docs
```

Run the configured `routine` corpus after execution changes, report the dataset names and outcomes, and inspect the same selection with `--no-force --dry-run` to confirm zero jobs. The overview script selects the larger benchmark corpuses for deliberate broader checks.

See [architecture](docs/architecture.md) for module ownership and [development](docs/development.md) for the quality gates.

## Viewer development

Both viewers use the same strict TypeScript/Vite setup as rawdiagQC and proptm3d. Sources live in [viewer/src](viewer/src); shared adapters bundle Lit, Tabulator, Plotly, D3-DSV and the JSON tree viewer from locked npm dependencies. The Python package contains generated scripts and styles, so installed users need no Node runtime or CDN.

```bash
make sync-web                 # install locked npm dependencies
make check-web                # strict TypeScript check
make test-web                 # model, navigation and architecture tests
make build-web                # replace packaged bundles from current sources
make check-web-assets         # detect stale packaged bundles
npm --prefix viewer run dev   # Vite development server
```

Vite exposes `/corpus/` and `/fixture/`, proxying reads to the existing local viewers on ports 8766 and 8765. Start them with `uv run corpus view` and `uv run fixture view`. The frontend performs rendering and navigation in the browser; the corpus server also discovers runs and resolves permitted source files. A standalone browser directory loader would be a separate change.
