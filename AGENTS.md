# APB Studio

Studio acquires fixtures, executes concrete Python workflows over `corpus.csv`, and serves bundled TypeScript viewers. The current user-approved corpus V2 design replaces the former stage registry and pipeline YAMLs.

## Boundaries

- The Fixture Manager downloads and manages; corpora decide what to run. Acquisition owns the store, `resources.csv` and the fixture manifest `downloads.csv`: one row per catalogued ProteoBench submission and configured Zenodo dataset, keyed by `dataset` (`<repo_name>/<intermediate_hash>`), with the stored `input_file_path` and `vendor_parameter_file_path` exactly, `.gz` included. A Zenodo row may name a dataset folder as its input and have no parameter file. `fixture download NAME` reads `corpuses/NAME.csv` and never writes a corpus file.
- Every corpus file in `corpuses/` is hand-curated with exactly `dataset,note`; `note` is for readers only. Its name is its file stem; `all` is reserved for every downloaded dataset. Never generate or overwrite a corpus file from acquisition.
- Execution settings explicitly name an inventory in `corpuses/`, an optional `workflow_<name>.csv`, and an independent data root. CSV row paths are relative to that data root, never the CSV directory. Download status never enters execution.
- The viewer selects one stable corpus/workflow/format combination. `configure` groups effective values under their exact source files, expands selection and workflow-table rows, and never writes configuration or creates a run. Current snapshots preserve both the full inventory and selected rows; do not infer unrecorded provenance for older runs.
- Each concrete `workflows/workflow_<name>.py` uses the common CLI and shared `corpus/runner.py`. Scripts own their linear APB commands and explicit CSV joins.
- Each workflow declares the executables it needs in a module-level `TOOLS` tuple, and `corpus/discovery.py` reads it. Generic code never names a workflow or its tools: settings, manifests and the workflow CLI carry `tools`/`tool_versions` maps keyed by declared names, and the public runner resolves each declared tool from `PATH`. A convert run therefore never looks for `apb-aggregate`.
- A workflow reaches an executable through `context.tool("<name>")`, which refuses any tool absent from its own `TOOLS`. A tool name is also its distribution name; distribution metadata and editable sources are rule dependencies.
- A workflow reads `workflow_tables/workflow_<name>.csv` by default and may declare `WORKFLOW_TABLE` to share a sibling workflow's table. Adding a workflow means adding one `workflows/workflow_<name>.py`; see [docs/workflows.md](docs/workflows.md).
- Studio drives APB through subprocesses; proteomics work and supported-level detection belong to APB.
- Corpus scheduling belongs to Snakemake. Its dataset output is one JSON report. APB failures are recorded results; framework failures fail jobs.
- `run.json` and copied CSV/source files expose settings before execution. Progress snapshots expose running steps. The final `corpus_index.json` links completed reports.
- The corpus viewer is a TypeScript application built with Vite and served by a small read server. The Runs Output column and Run overview Output summary display actual extensions from observed scientific artifacts; the storage-format label does not imply `.h5ad` or `.h5mu`. The viewer reads only files: runs write the catalog `index.json`, `input_kinds.json` and `proteobench_references.json`, and the read server serves `/` (viewer), `/data/` (runs) and `/fixtures/` (fixture store) as files, so `corpus publish` output runs on any plain file server. All run evidence remains static JSON, CSV and text, and the viewer computes no proteomics metrics.
- Both viewers use one strict TypeScript/Vite project in `viewer/`: Lit light-DOM shells, shared npm dependency adapters, pure model/panel projections, renderer adapters, and small `app.ts` composition roots. Keep shared modules independent of either viewer. Edit TypeScript sources, then run `make build-web`; the Python web roots contain generated bundles. Do not introduce a second UI stack or edit generated assets directly.
- Keep module dependencies acyclic. Keep `__init__.py` empty. Use annotated Python, Ruff and strict Pyright.
- Never remove fixture inputs during run cleanup. Every ordinary run defaults to force. Explicit clean deletes both stable and legacy hashed run directories; force deletes the selected combination's previous generated results and any legacy history before rerunning, without archiving.

## Commands

| Task | Command |
| --- | --- |
| Install | `uv sync --frozen --extra dev --group docs` |
| Download every ProteoBench module and Zenodo record | `uv run fixture download all` |
| Download one corpus's datasets | `uv run fixture download routine` |
| Store text vendor tables plain instead of gzipped | add `--no-gzip` to `fixture download` |
| List downloadable corpus names | `uv run fixture download --help` |
| Rebuild FASTA protein databases | `uv run fixture databases` |
| List packaged workflows | `uv run corpus workflows` |
| Inspect configuration | `uv run corpus configure` |
| Run named integration fixtures | `uv run corpus run routine <name>` |
| Run full regular benchmark corpus | `uv run corpus run proteobench proteobench_pmultiqc` |
| Confirm settled | `uv run corpus run routine <name> --no-force --dry-run` |
| Delete every saved run | `uv run corpus clean` |
| Start/restart corpus viewer | `uv run corpus view` |
| Every served run, then the site, one command per line | [scripts/corpus_runs.fish](scripts/corpus_runs.fish) |
| Routine checks and exports, one command per line | [scripts/integration_runs.fish](scripts/integration_runs.fish) |
| Run and publish the public combinations | its "public site" lines |
| Copy viewer and runs for a file server | `uv run corpus publish SITE` |
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


## Verification

[scripts/corpus_runs.fish](scripts/corpus_runs.fish) lists every run we serve, one plain command each, with no loops or functions, all into the configured output root: the site, the manuscript figures and the deciding-proteins comparison read the same runs, and `corpus publish` copies every run of that root; the routine checks and exports are in [scripts/integration_runs.fish](scripts/integration_runs.fish) in the same form. The 13-row routine inventory includes the MaxQuant multifile fixture plus small i2MassChroQ, DIA-NN 2.3 and Sage examples, AlphaDIA 2.1 Parquet, and AlphaDIA 1.12's two-file output (`input_file.tsv` with `input_file_secondary.tsv`). `all` names every downloaded dataset; there is still no routine `all` run, so do not add one to the scripts. A dataset a corpus lists but the fixture has not stored gets a `not_downloaded` report; `--strict` refuses such a run, and an unknown key always fails. The independent 12-row `routine_pb` inventory is scored with the single-call `proteobench_run`; the three-call `proteobench` workflow stays available. General all-quantitative-layer aggregation is deferred and omitted from the scripts. There is no standalone `maxquant_entrapment` execution alias. The routine `aggregate_medpolish` workflow needs no table and runs only median polish on the source level's primary X; the general `aggregate` workflow retains its per-software method table and processes all quantitative layers. `--force` clears previous results without retaining history.

After execution changes, run the configured `routine` corpus and report actual APB outcomes; `fixture download routine` fetches exactly its datasets. Changes to a workflow's tool contract are worth running under both a single-tool and a multi-tool workflow. Confirm an inspection with `--no-force --dry-run` and the same corpus, cores, workflow, and format schedules zero jobs. Use the overview script for deliberate broader benchmark coverage. Keep quality gates at their existing strength.

The fixture and corpus viewers compile strict TypeScript to local ES-module bundles. Dependencies are locked in `viewer/package-lock.json`; no CDN is required. Node is needed for development and CI, while installed viewers need only a file server, such as `corpus view` locally, and a browser. Their servers serve files and do not launch jobs.
