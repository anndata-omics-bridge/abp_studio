# Architecture

Studio has three boundaries: acquisition writes fixture files and the minimal corpus table; concrete Python workflows execute APB subprocesses and write reports; the JavaScript viewer reads those reports.

## Modules

| Component | Responsibility |
| --- | --- |
| `proteobench_fixtures.py`, `fixture_store.py` | `fixture` CLI, downloads, subset construction, acquisition history |
| `corpus_export.py` | Export explicit existing input/parameter paths and workflow resource mappings |
| `corpus/tables.py` | Exact CSV schema and explicit joins |
| `corpus/models.py` | Versioned JSON records |
| `corpus/runner.py` | Linear subprocess execution, telemetry, logs, progress and final reports |
| `workflows/workflow_<name>.py` | Workflow-owned ordered APB commands; see [Adding a workflow](workflows.md) |
| `workflows/artifacts.py`, `workflows/software.py` | Declarations shared by every concrete workflow |
| `corpus/runs.py`, `corpus/cli.py` | Snapshot preparation and Snakemake invocation |
| `workflow/Snakefile` | One dataset rule and one index rule |
| `corpus/clean.py` | Recoverable archiving of one run's generated results |
| `corpus_viewer/web/` | JavaScript rendering of persisted settings, tables and execution state |

The workflow scripts depend on the shared corpus runner. The corpus runner never imports APB domain packages or computes proteomics summaries. The server serves static files and performs no workflow actions. The stage registry and pipeline YAMLs have been removed.

## Inputs and snapshots

Named inventories in `corpuses/` have four columns: `input_file,vendor_parameter_file,module,software_name`. Paths are relative to an independently configured data root, never the CSV directory. A workflow receives the selected file path and the CSV paths, locates its row, and performs any join itself. `workflow_proteobench.csv` uses `module` and supplies `fasta` and quantification `level`; `module` itself names apb-proteobench's packaged module; the pMultiQC workflow requires `ion` and therefore emits H5AD for HDF5 storage. `workflow_aggregate.csv` uses `software_name` and supplies `start_level`, optional `fallback_level`, and `method`. A workflow reads `workflow_<name>.csv` unless it declares `WORKFLOW_TABLE` to share a sibling's table, as `proteobench_run` and `proteobench_pmultiqc` share `proteobench`'s.

`fixture corpus all` writes the complete inventory. The three smallest-per-group commands write `routine.csv` directly from catalog flags, so there is no second selection manifest. `corpuses.json` maps path-safe CLI short names to inventory paths relative to that config file; acquisition creates the default mapping if it is absent. `ExecutionSettings` explicitly names that corpus alias, the resolved corpus, optional workflow table, optional acquisition downloads table, data root, workflow, format, a `tools` map holding one resolved path per executable the workflow declared, cores, and any selection. Run launch publishes the resolved settings and CSV snapshots inside the stable combination directory; the read-only `configure` command reports the main settings file, corpus config, effective roots, and immediate defaults.

At launch, the full source inventory, selected rows, one-row dataset CSVs, selected input-size metadata, optional workflow table, settings, and workflow source are copied into `<output_root>/corpus/<corpus>/<workflow>/<format>/`; content-identical snapshots keep their mtimes. Input size is joined explicitly from `corpus.input_file` to `downloads.input_file_path`; acquisition status is not consulted. Each dataset rule declares its own CSV, input and parameter files, workflow/runtime sources, workflow table, tool launcher, distribution metadata, and editable tool sources. Its command, row, and observed tool versions are Snakemake parameters. `run.json` links the current snapshots and expected reports before execution. The viewer selects the one live stable combination directly; schema-1 hashed directories remain on disk but stay hidden.

## Reporting and progress

Each APB step records its name, argv, inputs, outputs, timestamps, runtime in seconds, peak process-tree RSS in bytes, exit code, separate stdout/stderr, warnings and errors. Present inputs and successfully generated file or directory artifacts also record their byte sizes. The runner writes atomic progress snapshots during execution and a final report after all attempted steps settle. Subsequent steps become skipped after an APB failure.

An APB failure produces a failed report and a successful workflow-process exit. An inability to run the reporting framework fails the Snakemake rule. The index is published only after all final reports validate. Scheduler completion and APB success remain separate visible fields.

The viewer uses only JSON/CSV/text URLs. It shares the Fixture Viewer frontend architecture: a Lit light-DOM shell, pure projections, focused panel controllers, renderer adapters, and the same pinned Tabulator, Plotly, and D3-DSV modules; `app.js` is only the composition root. Its identity endpoint hashes the canonical store and web roots, allowing `corpus view` and `corpus view stop` to distinguish the requested viewer from another store or service on the same port; stopping also requires the recorded PID to own the exact localhost listening socket before signaling. File responses stream from disk. Generated-artifact links stay inside the corpus store, while the source-download endpoint resolves only input and parameter paths named by the selected combination's current corpus snapshot. The catalog exposes the absolute store root so the Run manifest panel can show the server artifact directory. The viewer polls at two-second intervals and reads progress until a final report becomes available. A new operation invalidates cached reports. It displays interrupted work when the operation ended before a dataset produced a final result. The dataset table exposes only the last observed scientific output of a succeeded step. Show more retains all declared paths, distinguishes missing outputs from existing failed-step artifacts through independently observed sizes, and selects the representation sidecar belonging to that displayed output, falling back to the last readable representation. Its top-level tabs separate files and execution diagnostics, APB-owned metadata scopes, every AnnData modality represented by a quantification level or annotation table, and the complete representation JSON. The metadata projection preserves shared MuData and level-specific AnnData ownership and renders each as `uns["apb"]`; it does not move missing shared provenance out of a modality. Each AnnData panel contains nested axes, one-tab-per-layer, and aligned-structure scientific views only. Both tab levels render lazily so Plotly measures a visible container. Known embedded provenance JSON is decoded defensively for older sidecars. It renders categorical counts and Plotly summaries only for quantitative layers without computing proteomics statistics. The execution report remains a secondary diagnostic in the files tab. Its corpus visualization projection creates a workflow summary followed by dynamic tabs for each recorded step/tool pair. Every tab plots runtime, peak RSS and non-representation artifact size against vendor input size. Workflow runtime is the sum of observed step runtimes, workflow memory is their maximum peak RSS, and its artifact series remain separated by step and software; partial failed-workflow evidence remains visible and absent measurements remain absent.

## Verification

Unit tests exercise CSV validation, explicit join failures, workflow step construction, subprocess logs, unavailable commands, missing files, skipped steps and failed report publication. Integration checks run the named vendor fixtures through the actual APB2, apb-aggregate, apb-fasta, apb-proteobench and MultiQC CLIs. Node tests exercise viewer state projection.
