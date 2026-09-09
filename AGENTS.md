# APB Studio

Studio acquires fixtures, executes concrete Python workflows over `corpus.csv`, and serves static JavaScript viewers. The current user-approved corpus V2 design replaces the former stage registry and pipeline YAMLs.

## Boundaries

- Acquisition owns `downloads.csv`, `resources.csv`, and downloaded fixtures. `corpus_export.py` publishes existing input/parameter pairs as exactly `input_file,vendor_parameter_file,module,software_name`.
- Execution settings explicitly name an inventory in `corpuses/`, an optional `workflow_<name>.csv`, and an independent data root. CSV row paths are relative to that data root, never the CSV directory. Download status never enters execution.
- The viewer selects reusable execution settings, then their saved runs. `configure` saves settings without a run. Run snapshots preserve both the full inventory and selected rows; do not infer unrecorded provenance for older runs.
- Each concrete `workflows/workflow_<name>.py` uses the common CLI and shared `corpus/runner.py`. Scripts own their linear APB commands and explicit CSV joins.
- Each workflow declares the executables it needs in a module-level `TOOLS` tuple, and `corpus/discovery.py` reads it. Generic code never names a workflow or its tools; `corpus/cli.py` only maps a tool name to its `--*-executable` override. A convert run therefore never looks for `apb-aggregate`.
- Studio drives APB through subprocesses; proteomics work and supported-level detection belong to APB.
- Corpus scheduling belongs to Snakemake. Its dataset output is one JSON report. APB failures are recorded results; framework failures fail jobs.
- `run.json` and copied CSV/source files expose settings before execution. Progress snapshots expose running steps. The final `corpus_index.json` links completed reports.
- The corpus viewer is plain JavaScript served by the static server. It reads persisted JSON, CSV and text; it computes no proteomics metrics.
- Keep module dependencies acyclic. Keep `__init__.py` empty. Use annotated Python, Ruff and strict Pyright.
- Never remove fixture inputs during run cleanup. Clean and force preserve generated results under the run's `history/`.

## Commands

| Task | Command |
| --- | --- |
| Install | `uv sync --frozen --extra dev --group docs` |
| Export existing corpus | `make corpus-export` |
| Run named integration fixtures | `make corpus-routine` |
| Confirm settled | `make corpus-check CORPUS_CSV=corpuses/routine.csv` |
| View results/settings/progress | `make corpus-viewer` |
| Stop/restart corpus viewer | `make corpus-viewer-shutdown` / `make corpus-viewer-restart` |
| Fixture viewer | `make fixture-manager` |
| Fast gate | `make check` |
| Unit tests | `make test` |
| JavaScript tests | `make test-web` |
| Package smoke | `make package` |
| Before push | `make check-full` |

`CORPUS_WORKFLOW` defaults to `convert`; `CORPUS_FORMAT` defaults to `hdf5`. The implemented workflows are `convert` and `aggregate`. `CORPUS_CORES`, `CORPUS_FIXTURES`, and `CORPUS_RUN_FLAGS` control scheduling and named selections. APB2 must be on PATH or passed through `--apb-executable`; aggregation also needs `apb-aggregate` on PATH or `--aggregate-executable`.

## Verification

After execution changes, run `corpuses/routine.csv` (exported from the ten named fixtures in `selections/routine.txt`) and report actual APB outcomes. Confirm a dry-run with the same corpus, cores, workflow, and format schedules zero jobs. The selection includes two AlphaDIA versions. Whole-corpus runs are for deliberate broader coverage, not routine reassurance. Keep quality gates at their existing strength.

The existing fixture viewer uses plain ES modules, pinned vendor adapters, pure panel projections, and Tabulator. Follow those conventions for the corpus viewer. Its server serves files and does not launch jobs.
