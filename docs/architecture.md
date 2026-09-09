# Architecture

Studio has three boundaries: acquisition writes fixture files and the minimal corpus table; concrete Python workflows execute APB subprocesses and write reports; the JavaScript viewer reads those reports.

## Modules

| Component | Responsibility |
| --- | --- |
| `proteobench_fixtures.py`, `fixture_store.py` | Downloading, fixture inventory, acquisition history |
| `corpus_export.py` | Export explicit existing input/parameter paths and workflow resource mappings |
| `corpus/tables.py` | Exact CSV schema and explicit joins |
| `corpus/models.py` | Versioned JSON records |
| `corpus/runner.py` | Linear subprocess execution, telemetry, logs, progress and final reports |
| `workflows/workflow_convert.py`, `workflows/workflow_aggregate.py` | Workflow-owned ordered APB commands |
| `corpus/runs.py`, `corpus/cli.py` | Snapshot preparation and Snakemake invocation |
| `workflow/Snakefile` | One dataset rule, one index rule, recoverable clean |
| `corpus_viewer/web/` | JavaScript rendering of persisted settings, tables and execution state |

The workflow scripts depend on the shared corpus runner. The corpus runner never imports APB domain packages or computes proteomics summaries. The server serves static files and performs no workflow actions. The stage registry and pipeline YAMLs have been removed.

## Inputs and snapshots

Named inventories in `corpuses/` have four columns: `input_file,vendor_parameter_file,module,software_name`. Paths are relative to an independently configured data root, never the CSV directory. A workflow receives the selected file path and the CSV paths, locates its row, and performs any join itself. `workflow_proteobench.csv` uses `module`; `workflow_aggregate.csv` uses `software_name` and supplies `start_level` and `method`.

`ExecutionSettings` explicitly names the corpus, optional workflow table, optional acquisition downloads table, data root, workflow, format, required executables, cores, and any selection. A content-derived settings ID groups runs independently of their timestamps or observed software versions. The `configure` CLI publishes settings and CSV previews without a run; `execute` replays a saved settings document.

At launch, the full source inventory, selected rows, selected input-size metadata, optional workflow table, settings, and workflow source are copied into a run directory. Input size is joined explicitly from `corpus.input_file` to `downloads.input_file_path`; the acquisition status column is not consulted. Run identity hashes the Snakefile, corpus modules, selected and shared workflow modules, executable metadata, and editable tool package contents without importing APB. `run.json` links the snapshots and expected reports before execution. The viewer selects settings first, then one of their saved runs, and can also inspect settings without any run. Manifests without a saved settings reference are omitted from the viewer catalog.

## Reporting and progress

Each APB step records its name, argv, inputs, outputs, timestamps, runtime in seconds, peak process-tree RSS in bytes, exit code, separate stdout/stderr, warnings and errors. Present inputs and successfully generated file or directory artifacts also record their byte sizes. The runner writes atomic progress snapshots during execution and a final report after all attempted steps settle. Subsequent steps become skipped after an APB failure.

An APB failure produces a failed report and a successful workflow-process exit. An inability to run the reporting framework fails the Snakemake rule. The index is published only after all final reports validate. Scheduler completion and APB success remain separate visible fields.

The viewer uses only JSON/CSV/text URLs. Its identity endpoint hashes the canonical store and web roots, allowing serve, shutdown and restart to distinguish the requested viewer from another store or service on the same port; shutdown also requires the recorded PID to own the exact localhost listening socket before signaling. It polls at two-second intervals and reads progress until a final report becomes available. A new operation invalidates cached reports. It displays interrupted work when the operation ended before a dataset produced a final result. The dataset table exposes only the last observed scientific output of a succeeded step. Show more retains all declared paths, distinguishes missing outputs from existing failed-step artifacts through independently observed sizes, and selects the representation sidecar belonging to that displayed output, falling back to the last readable representation. Its top-level tabs separate files and execution diagnostics, APB-owned metadata scopes, every AnnData modality represented by a quantification level or annotation table, and the complete representation JSON. The metadata projection preserves shared MuData and level-specific AnnData ownership and renders each as `uns["apb"]`; it does not move missing shared provenance out of a modality. Each AnnData panel contains nested axes, one-tab-per-layer, and aligned-structure scientific views only. Both tab levels render lazily so Plotly measures a visible container. Known embedded provenance JSON is decoded defensively for older sidecars. It renders categorical counts and Plotly summaries only for quantitative layers without computing proteomics statistics. The execution report remains a secondary diagnostic in the files tab. Its corpus visualization projection expands persisted reports into per-step runtime/memory points and per-observed-output size points; Plotly groups them by software and never substitutes zero for absent measurements.

## Verification

Unit tests exercise CSV validation, explicit join failures, workflow step construction, subprocess logs, unavailable commands, missing files, skipped steps and failed report publication. Integration checks run the named vendor fixtures through the actual APB2 and apb-aggregate CLIs. Node tests exercise viewer state projection.
