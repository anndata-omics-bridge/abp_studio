# APB Studio

Studio acquires fixtures, executes concrete Python workflows over `corpus.csv`, and serves bundled TypeScript viewers. The current user-approved corpus V2 design replaces the former stage registry and pipeline YAMLs.

## Boundaries

- Acquisition owns `downloads.csv`, `resources.csv`, and downloaded fixtures. `corpus_export.py` publishes existing ProteoBench input/parameter pairs, and `zenodo_fixtures.py` the Zenodo records of `config/zenodo.toml`, as exactly `input_file,vendor_parameter_file,module,software_name`. A Zenodo row may name a dataset folder as `input_file` and leave `vendor_parameter_file` empty.
- Execution settings explicitly name an inventory in `corpuses/`, an optional `workflow_<name>.csv`, and an independent data root. CSV row paths are relative to that data root, never the CSV directory. Download status never enters execution.
- The viewer selects one stable corpus/workflow/format combination. `configure` groups effective values under their exact source files, expands selection and workflow-table rows, and never writes configuration or creates a run. Current snapshots preserve both the full inventory and selected rows; do not infer unrecorded provenance for older runs.
- Each concrete `workflows/workflow_<name>.py` uses the common CLI and shared `corpus/runner.py`. Scripts own their linear APB commands and explicit CSV joins.
- Each workflow declares the executables it needs in a module-level `TOOLS` tuple, and `corpus/discovery.py` reads it. Generic code never names a workflow or its tools: settings, manifests and the workflow CLI carry `tools`/`tool_versions` maps keyed by declared names, and the public runner resolves each declared tool from `PATH`. A convert run therefore never looks for `apb-aggregate`.
- A workflow reaches an executable through `context.tool("<name>")`, which refuses any tool absent from its own `TOOLS`. A tool name is also its distribution name; distribution metadata and editable sources are rule dependencies.
- A workflow reads `workflow_tables/workflow_<name>.csv` by default and may declare `WORKFLOW_TABLE` to share a sibling workflow's table. Adding a workflow means adding one `workflows/workflow_<name>.py`; see [docs/workflows.md](docs/workflows.md).
- Studio drives APB through subprocesses; proteomics work and supported-level detection belong to APB.
- Corpus scheduling belongs to Snakemake. Its dataset output is one JSON report. APB failures are recorded results; framework failures fail jobs.
- `run.json` and copied CSV/source files expose settings before execution. Progress snapshots expose running steps. The final `corpus_index.json` links completed reports.
- The corpus viewer is a TypeScript application built with Vite and served by a small read server. The Runs Output column and Run overview Output summary display actual extensions from observed scientific artifacts; the storage-format label does not imply `.h5ad` or `.h5mu`. `GET /api/catalog` derives selectable stable combinations from live run directories on every request; all run evidence remains static JSON, CSV and text, and the viewer computes no proteomics metrics.
- Both viewers use one strict TypeScript/Vite project in `viewer/`: Lit light-DOM shells, shared npm dependency adapters, pure model/panel projections, renderer adapters, and small `app.ts` composition roots. Keep shared modules independent of either viewer. Edit TypeScript sources, then run `make build-web`; the Python web roots contain generated bundles. Do not introduce a second UI stack or edit generated assets directly.
- Keep module dependencies acyclic. Keep `__init__.py` empty. Use annotated Python, Ruff and strict Pyright.
- Never remove fixture inputs during run cleanup. Every ordinary run defaults to force, and all three Fish scripts explicitly pass `--force`. Explicit clean deletes both stable and legacy hashed run directories; force deletes the selected combination's previous generated results and any legacy history before rerunning, without archiving.

## Commands

| Task | Command |
| --- | --- |
| Install | `uv sync --frozen --extra dev --group docs` |
| Acquire all ProteoBench fixtures; publish all acquired inputs | `uv run fixture corpus all` |
| Acquire routine corpus | `uv run fixture corpus smallest-per-module` |
| Acquire ProteoBench entrapment corpus | `uv run fixture corpus proteobench-entrapment` |
| Acquire plasma corpus | `uv run fixture corpus proteobench-plasma` |
| Acquire Zenodo MaxQuant entrapment corpus | `uv run fixture corpus maxquant-entrapment` |
| Acquire Zenodo directLFQ corpus | `uv run fixture corpus directlfq` |
| Rebuild FASTA protein databases | `uv run fixture databases` |
| List packaged workflows | `uv run corpus workflows` |
| Inspect configuration | `uv run corpus configure` |
| Run named integration fixtures | `uv run corpus run routine --workflow <name>` |
| Run full regular benchmark corpus | `uv run corpus run proteobench --workflow proteobench_pmultiqc` |
| Confirm settled | `uv run corpus run routine --workflow <name> --no-force --dry-run` |
| Delete every saved run | `uv run corpus clean` |
| Start/restart corpus viewer | `uv run corpus view` |
| Stop corpus viewer | `uv run corpus view stop` |
| Fixture viewer | `uv run fixture view` |
| Fast gate | `make check` |
| Unit tests | `make test` |
| Install viewer dependencies | `make sync-web` |
| TypeScript check | `make check-web` |
| Viewer tests | `make test-web` |
| Build packaged viewers | `make build-web` |
| Bundle freshness | `make check-web-assets` |
| Package smoke | `make package` |
| Before push | `make check-full` |

`corpus run <corpus>` requires and resolves its positional name through `corpuses.json`, then runs one workflow, defaulting to `convert` and `hdf5`. The implemented workflows are `convert`, `aggregate`, `proteobench`, `proteobench_run`, the ion-only `proteobench_pmultiqc`, its plasma variant `proteobench_plasma`, `proteobench_plasma_run` for the plasma scores without the report, `proteobench_entrapment` for the `proteobench_entrapment` corpus, and `export_msmu`, `export_prolfqua`, `export_proteopy` and `export_alphapepttools`, one `apb-export` call per dataset writing the file that tool opens; `proteobench_run`, `proteobench_plasma_run` and `proteobench_entrapment` also write each dataset's ProteoBench datapoint as `scores.json`; all accept the storage selectors `hdf5`, `duckdb`, and `parquet`. Export workflows write their target tool’s native H5AD/H5MU output regardless of the selector. Ion-only benchmark HDF5 outputs are `.h5ad`; full-level conversion outputs are `.h5mu`. Runs expose corpus, workflow, format, cores, dry-run, and force, with force enabled by default. An inspection with `--no-force --dry-run` can confirm that the current selection schedules zero jobs without executing or deleting results. Corpus names and workflow resources are file-driven, roots live in Studio's settings JSON, and every tool a workflow declares must be on `PATH`; the private apb-aggregate and apb-export run from their own environments, for example after `uv tool install --editable ../apb-export`, never through Studio's lock. `corpus configure` is read-only and reports those locations and effective values.

## Verification

The editable run lists are [scripts/routine_corpuses.fish](scripts/routine_corpuses.fish) for routine integration coverage and [scripts/overview_corpuses.fish](scripts/overview_corpuses.fish) for full benchmark corpuses. The 16-row routine inventory includes the MaxQuant multifile fixture plus small i2MassChroQ, DIA-NN 2.3 and Sage examples, AlphaDIA 2.1 Parquet, and AlphaDIA 1.12's two-file output (`input_file.tsv` with `input_file_secondary.tsv`). `all.csv` is freshly published from every acquired ProteoBench and configured Zenodo dataset after acquisition; it remains acquisition metadata, with no default execution alias or selected stress run. Do not recreate the retired all run. The independent 15-row `routine_pb` inventory runs conversion, FASTA peptide verification and ProteoBench scoring as three measured calls. General all-quantitative-layer aggregation is deferred and omitted from the scripts. There is no standalone `maxquant_entrapment` execution alias. The routine `aggregate_medpolish` workflow needs no table and runs only median polish on the source level's primary X; the general `aggregate` workflow retains its per-software method table and processes all quantitative layers. `--plan` prints selected commands without executing them; `--force` clears previous results without retaining history.

After execution changes, run the configured `routine` corpus and report actual APB outcomes. `fixture corpus smallest-per-module`, `smallest-per-software`, and `smallest-per-software-version` replace its default inventory with the selected bounded corpus; no separate selection manifest exists. Changes to a workflow's tool contract are worth running under both a single-tool and a multi-tool workflow. Confirm an inspection with `--no-force --dry-run` and the same corpus, cores, workflow, and format schedules zero jobs. Use the overview script for deliberate broader benchmark coverage. Keep quality gates at their existing strength.

The fixture and corpus viewers compile strict TypeScript to local ES-module bundles. Dependencies are locked in `viewer/package-lock.json`; no CDN is required. Node is needed for development and CI, while installed viewers need only the Python read server and a browser. Their servers serve files and do not launch jobs.
