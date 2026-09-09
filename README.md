# APB Studio

APB Studio downloads ProteoBench fixtures, runs concrete Python workflows over existing files, and serves two local JavaScript viewers.

## Start

```bash
uv sync --frozen --extra dev --group docs
make corpus-export
make corpus-routine
make corpus-viewer
```

The corpus viewer is at http://127.0.0.1:8766/. Running `make corpus-viewer` again reports the healthy existing server and exits successfully only when that server exposes the exact configured corpus and web roots; another viewer or service on the port is refused. Use `make corpus-viewer-shutdown` to stop the matching managed process or `make corpus-viewer-restart` to replace it. It shows saved settings, the exact CSV inputs, workflow source, live dataset/step progress, stdout, stderr, errors, runtime, peak memory, and input/output-size charts. It reads persisted files and remains useful after the runner exits. Refresh polling happens every two seconds. The fixture viewer remains available through `make fixture-manager` on port 8765.

The APB2 executable must be on PATH or supplied with `--apb-executable /path/to/apb2`. Aggregation runs also require `apb-aggregate` on PATH or `--aggregate-executable /path/to/apb-aggregate`. The development extra installs both workspace checkouts for local integration testing; Studio invokes them only through subprocesses.

## Inputs

`apb-studio-fixtures corpus` exports existing downloaded fixtures without downloading again:

```csv
input_file,vendor_parameter_file,module,software_name
```

Inventories live in `corpuses/`: `all.csv` contains every available file pair; `routine.csv` contains the ten named fixtures. `make corpus-export` writes both, selecting the routine rows using `selections/routine.txt`. Additional named CSVs can be created with `apb-studio-corpus select --corpus corpuses/all.csv --datasets <selection.txt> --output corpuses/<name>.csv`.

Both row paths are relative to the explicit `data_root`, not the CSV directory. `--data-root` defaults to Studio's configured fixture-store root. Each input file is unique. Execution joins only `input_file_path` and `input_file_size_bytes` from the separately configured `downloads.csv`; acquisition status remains outside pipeline state.

Workflow-specific resources live in `workflow_tables/`. The exact conventional `workflow_<name>.csv` is selected automatically when present, or can be supplied with `--workflow-table`. The workflow declares its join columns explicitly and uses a validated many-to-one lookup. `workflow_aggregate.csv` contains exactly `software_name,start_level,method` and joins on `software_name`; `workflow_proteobench.csv` contains exactly `module,module_toml,fasta` and joins on `module`. Resource paths are relative to the same data root. Conversion needs no companion CSV and records `workflow_table: null`.

## Execution settings and saved runs

Execution settings explicitly record `corpus`, optional `workflow_table`, optional acquisition `downloads`, `data_root`, `workflow`, `format`, required executable paths, `cores`, and any additional selection. They contain no run ID, timestamp, or observed tool version. They are saved separately under `<output_root>/corpus/settings/<settings-id>/execution_settings.json`, together with CSV previews. Source paths in generated settings are absolute. When `<data_root>/downloads.csv` exists it is selected by default; `--downloads` can name another table.

```bash
# Save settings and preview the full inventory without running APB.
uv run apb-studio-corpus configure --corpus corpuses/all.csv --cores 2
# Execute a saved configuration; this remains a headless operation.
uv run apb-studio-corpus execute /absolute/path/to/execution_settings.json
```

The viewer first selects execution settings, then one of their saved runs. Settings without runs still show their configuration and inventory preview. Each run freezes its own settings and CSVs; later changes to source tables do not rewrite recorded evidence. Runs without source execution settings are excluded instead of being presented with guessed provenance.

The main Datasets tab is one compact table with the last observed scientific output from a succeeded step and a Show more button per dataset; failed or skipped steps never contribute the summary output. Show more opens with an Inputs & outputs tab containing every planned and observed input, output and intermediate path with its available size, including an artifact written before a later output or sidecar publication failed. APB metadata is a separate top-level tab with nested MuData and modality tabs which render each shared or level-owned provenance scope under `uns["apb"]`; another top-level tab exposes the complete representation JSON which drives the viewer. Every quantification-level or annotation-table modality has an AnnData tab containing only scientific tables and nested tabs for its axes, individual layers, and aligned structures. This prevents an intermediate converted level from being repeated beside the same level in the final aggregate. Known JSON-text provenance fields render as structured trees, while invalid text remains inspectable. Quantitative layers use Plotly box traces from bounded persisted per-observation quartiles with explicit observation and quantity axes; categorical layers show fixed-size category and missing-value counts without treating their codes as numbers. The complete execution report remains an expandable diagnostic in Inputs & outputs. The Visualizations tab plots every available step's runtime and peak process-tree RSS, plus every observed scientific artifact size, against its vendor input size; software is the series and exact dataset evidence is available on hover.

## Run

```bash
make corpus-run CORPUS_WORKFLOW=convert CORPUS_FORMAT=hdf5
make corpus-routine CORPUS_WORKFLOW=aggregate CORPUS_FORMAT=hdf5
make corpus-routine CORPUS_FORMAT=duckdb
make corpus-check CORPUS_CSV=corpuses/routine.csv
uv run apb-studio-corpus run --corpus corpuses/all.csv --data-root /data/vendor-files --workflow convert --format parquet
```

`workflow_convert.py` invokes `apb2 convert` for all compatible levels and, for DuckDB or Parquet, invokes `apb2 reformat` as a separately measured step. `workflow_aggregate.py` has exactly two steps: convert the level selected by `workflow_aggregate.csv`, then aggregate it directly to protein with the configured method. Its initial table uses `mean`, fragment for DIA-NN and Spectronaut, and ion otherwise. Both workflows use the same workflow CLI; the Snakefile only parallelizes one selected workflow script per dataset.

Snakemake schedules one script per dataset. Its only dataset output is the JSON report; APB artifacts are recorded inside that report. A failed APB command stops the linear workflow, records later steps as skipped, writes the report, and returns success to Snakemake. A framework failure fails the job. A successful Snakemake operation therefore does not imply that every APB command succeeded: inspect the report statuses.

The run directory is `<output_root>/corpus/<workflow>-<format>-<fingerprint>/`. Identical inputs/settings reuse completed reports; a missing generated artifact does not cause a rerun when its report still exists. The fingerprint includes input file sizes/mtimes, the Snakefile, selected and shared workflow/runner source, required executable launchers, reported versions, installed-distribution metadata, and editable APB package contents discovered without importing APB. Source changes therefore select a new run even when the command version is unchanged. Use `--force` only for deliberate repeat measurement of the same identity. Previous reports and artifacts are moved into the run's `history/` folder before a forced attempt.

```bash
make corpus-run CORPUS_RUN_FLAGS="--force"
make corpus-clean CORPUS_RUN=/absolute/path/to/run
```

Clean goes through Snakemake and moves generated results into recoverable history. It preserves fixture files and the input snapshots.

## Persisted files

| File | Purpose |
| --- | --- |
| `run.json` | Settings and links to every expected dataset report, available before jobs start |
| `execution_settings.json` | Exact reusable configuration used for this run, including both source CSV paths |
| `corpus.csv` | Frozen full copy of the chosen source inventory |
| `selected_corpus.csv` | Exact selected rows passed to the workflow scripts |
| `input_metadata.csv` | Selected vendor input sizes joined explicitly from the acquisition downloads table |
| `workflow_<name>.csv` | Optional copied workflow table |
| `workflow_<name>.py` | Source snapshot shown by the viewer |
| `operation.json` | Scheduler running/succeeded/failed/interrupted state |
| `reports/<key>.progress.json` | Atomic live step state and recent output |
| `reports/<key>.json` | Complete dataset result with full stdout and stderr |
| `corpus_index.json` | Final validated index pointing to all dataset reports |
| `snakemake.log` | Scheduler output |
| `artifacts/**/*.apb.json` | Compact APB scientific representations for final and intermediate results |

Execution JSON documents have `schema_version: 1`; scientific representation documents have their own `format_version`. Report/index links are relative to the run directory and can be fetched directly by JavaScript. Final reports retain full logs; live progress carries the last 16 KiB of each stream. Memory is sampled every 100 ms as summed RSS across the APB process tree; it is an estimate and can miss short spikes. Declared input artifacts record observed sizes when present, and every output that exists after a command records its total file or recursive-directory byte size independently of the command status.

## Development

```bash
make check
make test
make test-web
make package
make docs
```

Run the named routine corpus after execution changes, report the dataset names and outcomes, and dry-run the same selection to confirm zero jobs. `selections/routine.txt` contains ten fixtures (including two AlphaDIA versions). Whole-corpus runs are for deliberate broader checks.

See [architecture](docs/architecture.md) for module ownership and [development](docs/development.md) for the quality gates.
