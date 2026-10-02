# APB Studio

Studio acquires fixtures, executes concrete Python workflows over `corpus.csv`, and serves static JavaScript viewers. The current user-approved corpus V2 design replaces the former stage registry and pipeline YAMLs.

## Boundaries

- Acquisition owns `downloads.csv`, `resources.csv`, and downloaded fixtures. `corpus_export.py` publishes existing input/parameter pairs as exactly `input_file,vendor_parameter_file,module,software_name`.
- Execution settings explicitly name an inventory in `corpuses/`, an optional `workflow_<name>.csv`, and an independent data root. CSV row paths are relative to that data root, never the CSV directory. Download status never enters execution.
- The viewer selects one stable corpus/workflow/format combination. `configure` groups effective values under their exact source files, expands selection and workflow-table rows, and never writes configuration or creates a run. Current snapshots preserve both the full inventory and selected rows; do not infer unrecorded provenance for older runs.
- Each concrete `workflows/workflow_<name>.py` uses the common CLI and shared `corpus/runner.py`. Scripts own their linear APB commands and explicit CSV joins.
- Each workflow declares the executables it needs in a module-level `TOOLS` tuple, and `corpus/discovery.py` reads it. Generic code never names a workflow or its tools: settings, manifests and the workflow CLI carry `tools`/`tool_versions` maps keyed by declared names, and the public runner resolves each declared tool from `PATH`. A convert run therefore never looks for `apb-aggregate`.
- A workflow reaches an executable through `context.tool("<name>")`, which refuses any tool absent from its own `TOOLS`. A tool name is also its distribution name, because Snakemake watches that distribution's metadata and editable source tree.
- A workflow reads `workflow_tables/workflow_<name>.csv` by default and may declare `WORKFLOW_TABLE` to share a sibling workflow's table. Adding a workflow means adding one `workflows/workflow_<name>.py`; see [docs/workflows.md](docs/workflows.md).
- Studio drives APB through subprocesses; proteomics work and supported-level detection belong to APB.
- Corpus scheduling belongs to Snakemake. Its dataset output is one JSON report. APB failures are recorded results; framework failures fail jobs.
- `run.json` and copied CSV/source files expose settings before execution. Progress snapshots expose running steps. The final `corpus_index.json` links completed reports.
- The corpus viewer is plain JavaScript served by a small read server. `GET /api/catalog` derives selectable stable combinations from live run directories on every request; all run evidence remains static JSON, CSV and text, and the viewer computes no proteomics metrics.
- Both viewers use the same JavaScript architecture: a Lit light-DOM shell, pinned vendor modules for Tabulator, Plotly and D3-DSV, pure model/panel projections, renderer adapters, and one small composition root. Do not introduce a second UI stack or accumulate panel rendering in a monolithic `app.js`.
- Keep module dependencies acyclic. Keep `__init__.py` empty. Use annotated Python, Ruff and strict Pyright.
- Never remove fixture inputs during run cleanup. Explicit clean deletes both stable and legacy hashed run directories; force may preserve the previous attempt under the active run's `history/`.

## Commands

| Task | Command |
| --- | --- |
| Install | `uv sync --frozen --extra dev --group docs` |
| Acquire full corpus | `uv run fixture corpus all` |
| Acquire routine corpus | `uv run fixture corpus smallest-per-module` |
| Acquire entrapment corpus | `uv run fixture corpus entrapment` |
| Acquire plasma corpus | `uv run fixture corpus plasma` |
| List packaged workflows | `uv run corpus workflows` |
| Inspect configuration | `uv run corpus configure` |
| Run named integration fixtures | `uv run corpus run routine --workflow <name>` |
| Run one workflow, whole corpus | `uv run corpus run all --workflow <name>` |
| Confirm settled | `uv run corpus run routine --workflow <name> --dry-run` |
| Delete every saved run | `uv run corpus clean` |
| Start/restart corpus viewer | `uv run corpus view` |
| Stop corpus viewer | `uv run corpus view stop` |
| Fixture viewer | `uv run fixture view` |
| Fast gate | `make check` |
| Unit tests | `make test` |
| JavaScript tests | `make test-web` |
| Package smoke | `make package` |
| Before push | `make check-full` |

`corpus run <corpus>` requires and resolves its positional name through `corpuses.json`, then runs one workflow, defaulting to `convert` and `hdf5`. The implemented workflows are `convert`, `aggregate`, `proteobench`, `proteobench_run`, the ion-only `proteobench_pmultiqc`, its plasma variant `plasma`, and `proteobench_entrapment` for the `entrapment` corpus; all accept `hdf5`, `duckdb`, and `parquet`, and every APB step in one workflow uses the selected format. Runs expose corpus, workflow, format, cores, dry-run, and force. Corpus names and workflow resources are file-driven, roots live in Studio's settings JSON, and every tool a workflow declares must be on `PATH`. `corpus configure` is read-only and reports those locations and effective values.

## Verification

After execution changes, run the configured `routine` corpus and report actual APB outcomes. `fixture corpus smallest-per-module`, `smallest-per-software`, and `smallest-per-software-version` replace its default inventory with the selected bounded corpus; no separate selection manifest exists. Changes to a workflow's tool contract are worth running under both a single-tool and a multi-tool workflow. Confirm a dry-run with the same corpus, cores, workflow, and format schedules zero jobs. Runs against the configured `all` corpus are for deliberate broader coverage, not routine reassurance. Keep quality gates at their existing strength.

The fixture and corpus viewers use plain ES modules, Lit light-DOM shells, pinned vendor adapters, pure panel projections, and Tabulator. Their servers serve files and do not launch jobs.
