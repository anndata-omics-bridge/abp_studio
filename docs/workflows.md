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
| `USES_VENDOR_PARAMETERS` | no | Set `False` if the workflow neither reads nor depends on vendor parameter files; defaults to `True` |

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

Conversion commands pass `--software` using the dataset's parameter-file software. A `FragPipe (DIA-NN quant)` dataset therefore passes `fragpipe`; APB2 reads its parameters and limits result-rule candidates to FragPipe and the declared DIA-NN quantifier. Studio does not detect result formats itself.

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
| Run one workflow, whole corpus | `uv run corpus run all --workflow <name>` |
| Confirm a run settled | `uv run corpus run routine --workflow <name> --dry-run` |
| Inspect results | `uv run corpus view` |
| Stop the viewer | `uv run corpus view stop` |

`corpus run --help` shows the configured corpus names and their resolved CSV targets, followed by the immediate controls:

- `CORPUS` — required name from `corpuses.json`
- `--workflow` — which workflow; default `convert`
- `--format` — `hdf5`, `duckdb`, or `parquet`, passed through every APB step
- `--cores` — maximum parallel Snakemake jobs, default 3
- `--dry-run` and `--force` — execution controls

`corpus run <corpus>` resolves the name through the flat `corpuses.json` object and runs one selected workflow. Relative inventory paths are resolved beside that config file, so `routine`, `proteobench`, and `all` are ordinary editable mappings rather than CLI branches. The `proteobench` inventory is `all` without the three peptidoform submissions and is the full ion-level input for `proteobench_pmultiqc`. Corpus inventories and workflow resources remain configured in their CSV/text files, roots live in Studio's settings JSON, and required tools resolve from `PATH`. `corpus configure` reports each exact source file together with the values read from it, including configured corpuses and complete workflow-table rows; it never writes configuration.

## Clearing results

Cleaning deletes every current corpus/workflow/format directory and every legacy hash-named run under the configured output root, including reports, artifacts, histories, logs and snapshots. Fixture inputs and the saved-settings store remain untouched. A forced rerun preserves the previous attempt inside the active run's `history/<uuid>/` before starting again.

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
uv run corpus view                                # start or restart the viewer
uv run corpus view stop                           # stop the viewer
```

Add unit coverage for the planned steps — the names, the chaining between declared inputs and outputs, and each refusal — so a workflow is testable without running any tool. `available_workflows()` and `workflow_tools()` are asserted in `tests/test_corpus.py` and will fail until the new name is listed there.
