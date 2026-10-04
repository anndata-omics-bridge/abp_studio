# Changes

- 2026-10-04: `proteobench_run` and `proteobench_entrapment` write each dataset's ProteoBench datapoint as `scores.json` through `apb-proteobench --scores`; the new `plasma_run` workflow scores the plasma corpus's table-named layers the same way, without pMultiQC. `proteobench_run` and `plasma_run` share one step builder in `workflows/proteobench_scoring.py`.

- 2026-10-04: Studio imports no other anndata_bridge package. `scripts/make_apb2_test_samples.py` moved to apb2 as `scripts/make_test_samples.py`, `polars` left the `samples` extra, and the sibling-import test also scans `scripts/`. `fixture resources` no longer downloads ProteoBench's entrapment pairs file, which apb-proteobench stopped using; the `module_data_urls` setting is gone.

- 2026-10-03: The corpus viewer reads apb-aggregate's history in `uns["apb"]["aggregate"]` as the native JSON list apb-aggregate now writes, and no longer parses `aggregate` as an embedded JSON string; `rule_json`, `plan_json` and `search_parameters` are still expanded.

- 2026-10-02: The `aggregate` workflow's `method` cell takes `;`-separated apb-aggregate selections. Each runs as its own `aggregate-<method>` step and adds its layers to the previous step's result; intermediate results are `aggregated_<method>` with role `aggregated`, the last is `aggregated` with role `result`. `workflow_aggregate.csv` now runs `all` everywhere, and adds `rlm_confidence_case` and `rlm_confidence_precision` for AlphaPept, DIA-NN, MaxQuant and Spectronaut, whose every rule variant catalogues ion identification confidence.

- 2026-10-02: `dia_plasma` forms its own `plasma` corpus (`fixture corpus plasma`) and leaves `all`, `proteobench` and the standard ProteoBench table. The new `plasma` workflow runs the `proteobench_pmultiqc` export and report, now shared in `workflows/proteobench_export.py`, with the layer `workflow_plasma.tsv` names per module and software: DIA-NN and FragPipe (DIA-NN quant) score `Precursor_Quantity`, as upstream's plasma module does; AlphaDIA and PEAKS score `X`. `proteobench_pmultiqc` passes `--layer X` in place of the removed `--x`; `proteobench` and `proteobench_run` now score only `X`, apb-proteobench's new default.

- 2026-10-02: The fixture store and corpus include ProteoBench's plasma module: `config/proteobench.toml` fetches `Results_quant_ion_DIA_plasma` with the HYE FASTA, `ModuleKey` accepts `dia_plasma`, and `workflow_proteobench.csv` gains its row. The ProteoBench workflows score it through apb-proteobench's packaged `dia_plasma` module.

- 2026-10-02: `fixture corpus` no longer overwrites `workflow_tables/workflow_proteobench.csv`. Its export copied only `module,fasta` from `resources.csv`, so every acquisition left a table that all three ProteoBench workflows rejected for lacking `level`. The table is now hand-maintained like the other workflow tables; a test checks it has each ProteoBench workflow's `WORKFLOW_COLUMNS` and the FASTA `config/proteobench.toml` names for every module.

- 2026-10-02: **Breaking:** Studio no longer downloads ProteoBench module TOMLs. The ProteoBench workflows pass the corpus `module` to `apb-proteobench` as a packaged module name, whose TOML and SDRF ship with apb-proteobench. `workflow_proteobench.csv` drops `module_toml`; `resources.csv` and `index.json` drop their module TOML entries; `config/proteobench.toml` drops `settings_revision`, `settings_root`, and `settings_path`; the fixture and corpus viewers no longer show or link module TOMLs.

- 2026-09-21: Added `convert_ion`, a separate single-level APB2 conversion workflow with H5AD output for HDF5 and its own phase-timing artifact. The existing `convert` workflow still converts all compatible levels.

- 2026-09-21: All conversion and integrated ProteoBench workflows pass the single `--software` parameter-grammar hint. FragPipe/DIA-NN compound exports continue to pass `fragpipe`, allowing APB2 to derive plausible result rules from parameter evidence.

- 2026-09-21: The convert workflow declares a separate APB2 timing JSON output; integrated ProteoBench runs declare separate APB2 conversion, FASTA verification, and ProteoBench benchmark timing outputs. Studio keeps subprocess runtime and memory independent and shows each version-1 timing file in its own nested step Visualizations subtab. Tool phases are vertically faceted with independent duration scales and one shared software legend, so the recorded `write` phase is visible without legend scrolling. Timing files are neither scientific output nor artifact-size points.

- 2026-09-18: **Breaking:** the viewer consumes representation 4 and displays tool namespaces directly on their emitted owning objects, without reconstructing shared/level wrappers in JavaScript. H5AD displays one combined tree; MuData root provenance remains only in the container subtab. Each tool shows its exact ownership path and scalar values; omitted storage is described without a placeholder value. Primary matrix cards display the retained quantity name with `X`.

- 2026-09-18: Structure now separates a MuData container tab from one subtab per embedded AnnData, including annotation modalities with no X. Metadata panels distinguish result-wide sources/settings from level-specific results, show ownership paths, and explain the omitted storage descriptor without presenting a placeholder as its value. H5AD shows both scopes in its single AnnData; H5MU keeps shared provenance and feature relations at the container root.

- 2026-09-17: The AnnData structure view now gives every `X`/`layers` matrix its own statistics card with shape, dtype, semantics, completeness, zero rate, mean, median, and range. Every aligned `obsm`, `varm`, `obsp`, and `varp` object likewise has its own card with shape, dtypes, keys, aggregate null burden, and column schema.

- 2026-09-17: The result structure view now consumes APB representation version 3 and renders canonical shared and level scopes without merging them. It labels physical `X` separately from additional layers and reports the logical primary name without implying that the primary matrix is duplicated in `layers`.

- 2026-09-17: Added a selectable AnnData structure diagram to every H5AD and H5MU scientific representation. The view is built from the persisted `.apb.json` sidecar and exposes actual dimensions, axis keys and columns, X and layer identities, aligned-slot contents, and APB `uns` namespaces without reopening the scientific artifact.

- 2026-09-17: Logarithmic layer box plots now recalculate from log-safe summaries instead of merely changing the Plotly axis. Observations with non-positive quartiles are omitted, and a non-positive minimum is represented by a lower whisker starting at the first positive quartile, preventing PEP distributions containing zeroes from collapsing into lines.

- 2026-09-17: The corpus table's compact Output link now opens the complete artifact-attempt directory rather than whichever individual output happened to be recorded last. This exposes the scored result, ProteoBench exports, pMultiQC HTML report, and pMultiQC data directory together; Show More retains direct links to each artifact.

- 2026-09-17: The ProteoBench/pMultiQC workflow now passes `--x`, explicitly restricting scoring and compatibility export to the APB primary layer represented by AnnData `X`. General APB ProteoBench scoring remains independent and defaults to every declared abundance layer.

- 2026-09-17: Made the ProteoBench/pMultiQC workflow explicitly ion-only through the shared `workflow_proteobench.csv` quantification-level column. Its integrated APB command now passes `--level ion`; the resulting one-level HDF5 artifact is `scored.h5ad` rather than an H5MU container.

- 2026-09-17: Corpus viewer polling no longer rebuilds the selected dataset's unchanged detail panel every two seconds. Paths and diagnostics now retain their DOM nodes, so ordinary text selection and copy/paste survive background refreshes; changed progress records still rerender.

- 2026-09-17: Corpus viewer folders and browser-readable files open in new tabs, retaining complete filenames. Added TOML/FASTA resource links in dataset details and frozen workflow tables, safe directory listings, and inline text/HTML responses. JSON links serve the unchanged file directly as `application/json` for native browser display. Binary files download without preview pages; APB Parquet directories remain browsable. Raw data endpoints retain their original response formats for application reads.

- 2026-09-17: Removed both Sage submissions from the dedicated `proteobench` corpus because their combined-charge exports are peptidoform-level rather than ion-level. The complete `all` inventory and bounded `routine` inventory remain unchanged.

- 2026-09-16: Added the named `proteobench` corpus for the ion-only ProteoBench/pMultiQC workflow. It mirrors `all.csv` except for the three `dda_peptidoform` submissions, while retaining ion-level WOMBAT coverage. Refreshed module settings from ProteoBench commit `b69dbaa8` so current raw-file aliases are available to annotation matching. pMultiQC reports use interactive rendering to avoid pathological static-plot runtimes on large result tables.

- 2026-09-16: Scientific layer cards now separate a quantitative layer's logical type from its physical matrix dtype, so integer count semantics remain visible when nullable AnnData storage uses `Float64`.

- 2026-09-16: `corpus run --help` now lists every discovered packaged workflow alongside the configured corpus names and targets.

- 2026-09-16: Fixed `corpus clean` to delete legacy hash-named corpus runs as well as current stable runs. These hidden legacy directories could retain hundreds of gigabytes while the command reported that every discovered run was deleted; fixture inputs and saved settings remain protected.

- 2026-09-16: Added the ion-only `proteobench_pmultiqc` corpus workflow for the complete report stack. Its first measured step runs the integrated `apb-proteobench run` path and serializes the scored APB2 result, `result_performance.csv`, and matching ProteoBot JSON; its second measured step runs the pMultiQC ProteoBench plugin and records the HTML report and MultiQC data directory. The samples environment now installs pMultiQC 0.0.48 or newer with MultiQC 1.35, avoiding MultiQC 1.33's incompatible parallel Polars distribution in the APB2 environment.

- 2026-09-15: Replaced hashed corpus runs and the separate settings store with one stable `<corpus>/<workflow>/<format>/` directory. Snakemake now watches each dataset row, vendor and parameter file, workflow/runtime source, resource table, executable metadata, and editable tool package; cores and viewer changes do not invalidate results. Snapshots retain mtimes when unchanged, schema 2 records the corpus alias, and the viewer exposes one readable combination selector. Legacy hashed runs remain hidden from the viewer.

- 2026-09-15: Made corpus inputs, parameter files, generated artifacts, and frozen run files downloadable from the viewer. The Run manifest panel now shows the absolute server artifact directory; source downloads are restricted to paths in the frozen corpus snapshot, and file responses stream instead of buffering large proteomics tables in memory.

- 2026-09-15: Replaced the hard-coded routine/full run branches with the flat `corpuses.json` name-to-CSV config. `corpus run <corpus> --workflow <name>` now runs exactly one workflow over any configured corpus, `all` is an ordinary corpus name, acquisition creates the default config when absent, and `corpus run --help` lists every configured name and resolved target.

- 2026-09-13: Added an accessible Linear/Log Y-axis control to every quantitative Plotly chart in the corpus viewer, including corpus resource profiles and AnnData layer summaries. Linear remains the default; logarithmic views identify that non-positive values are hidden, and charts without measurements disable the control. Plotly interaction stays isolated behind one shared renderer adapter.

- 2026-09-12: Rebuilt the corpus viewer on the fixture viewer's JavaScript architecture and visual system: a Lit light-DOM shell, the same pinned D3-DSV/Tabulator/Plotly adapters, focused fetch/render/panel modules, and a small composition root. Removed the monolithic imperative shell and the unrelated green card-based theme while preserving corpus run selection, live polling, tables, charts, scientific representation browsing, and failure state.

- 2026-09-12: Replaced the `apb-studio-fixtures` and Makefile-facing fixture commands with the `fixture` entry point. Its public commands are `corpus`, `clean`, and `view`; catalog, vendor-file, and resource acquisition are internal steps of `fixture corpus`. `fixture corpus all` acquires and writes the full inventory; `smallest-per-module`, `smallest-per-software`, and `smallest-per-software-version` acquire deterministic bounded selections into `routine.csv`. Removed the duplicate `selections/routine.txt`; subset downloads now preserve a complete `downloads.csv` status inventory. Restored `corpus configure` to compact JSON and added the main settings-file path explicitly.

- 2026-09-12: `corpus run all` now means every packaged workflow over every row in `corpuses/all.csv`; its command surface no longer accepts a single workflow selector. Viewer HTTP polling access records moved below DEBUG so `corpus view` reports lifecycle messages, warnings, and errors without request-log spam.

- 2026-09-11: Simplified the corpus CLI around intent. Its complete command surface is `clean`, read-only `configure`, `run`, `view`, and `workflows`; `select`, `execute`, and the old top-level viewer lifecycle commands were removed. `corpus view` starts or restarts the managed viewer and `corpus view stop` stops it, both using the configured output root and fixed viewer port. `corpus clean` deletes every saved run under that root. `corpus run` and `corpus run all` are default/subcommand forms rather than a scope parameter, and their help exposes only workflow, format, cores, dry-run, and force. Corpus scope and workflow resources remain file-driven, while `corpus configure` groups effective values under each exact source file, expands selection and workflow-table rows, and identifies missing files without writing anything.

- 2026-09-10: Replaced Makefile corpus lifecycle targets and the duplicate run/clean scripts with the Cyclopts `corpus` command. `corpus run` defaults to the routine inventory, `corpus run all` selects every row in `corpuses/all.csv`, and `corpus clean` deletes all saved runs unless one explicit run is supplied. APB2 conversion now writes the selected HDF5, Parquet, or DuckDB representation directly, so convert, aggregate, and both ProteoBench workflows pass one format through all process boundaries; the one-call ProteoBench workflow persists its in-memory `ParsedLevels` once through APB2's writer.

- 2026-09-10: Corrected `make corpus-all` semantics: "all" now means every dataset row in `CORPUS_CSV` for the one selected `CORPUS_WORKFLOW`, never every workflow over the routine corpus. The explicit `make corpus-run-all` target forces `CORPUS_FIXTURES=0`; `make corpus-all` is its alias, while `make corpus-routine` remains the small named gate. Spectronaut aggregation now starts at ion because the current 19/20 ProteoBench exports do not contain fragment columns. DIA-NN remains fragment-first and explicitly falls back to ion only when the converted APB result lacks a fragment modality.

- 2026-09-09: The corpus viewer now gets its execution-setting and saved-run selectors from a filesystem-backed `GET /api/catalog` endpoint instead of the persisted `index.json`. Every poll discovers current settings and running/completed operations directly; settings with no live run are excluded from the result selector and exposed separately as configured settings, while manifests without an operation are excluded. Run deletion therefore removes the result and its now-empty selector group; execution repopulates both without stale tables or charts. Corpus projection remains outside the generic HTTP server, which only accepts an injected route resolver; this is also the boundary for future explicit run/clean command endpoints. Explicit clean now deletes the selected run directory rather than preserving a second hidden copy; fixture inputs and separately saved execution settings remain untouched, while force still retains previous-attempt history for repeat measurements.

- 2026-09-09: Corpus resource profiles now use dynamic workflow and step/tool tabs instead of mixing all steps into one chart set. Every tab shows runtime, peak process-tree RSS and scientific artifact size against vendor input size. The workflow view sums observed step runtimes, takes their maximum peak RSS and distinguishes each step/software artifact series; failed workflows retain partial measurements, skipped values remain absent, representation JSON sidecars stay excluded, and the selected tab survives polling refreshes.

- 2026-09-09: Cleaning a run no longer requires a manifest written by the current schema. `delete_run` reads only `data_root`, the single field its fixture-overlap guard needs, and refuses an absent or relative one; `clean_corpus.py` calls it directly under the run lock instead of routing through Snakemake, whose Snakefile validates the whole manifest at parse time. The now-unreachable `rule clean` and its `localrules` line are gone. Without this, `make corpus-clean-all` failed on every run recorded before the `tools` map existed.

- 2026-09-09: Made workflow selection and result clearing discoverable from `make help`, which now prints every target plus every `CORPUS_*` variable and its meaning. Added `make corpus-workflows` (backed by `apb-studio-corpus workflows`, listing each workflow's declared tools and resource table), `make corpus-all` (every workflow in `CORPUS_WORKFLOWS` over the routine gate, stopping at the first failure), and `make corpus-clean-all` (deletes every run under the output root through `clean_corpus.py --all`, reporting each run and exiting non-zero if any could not be deleted). `docs/workflows.md` gained the runner-integration and clearing sections.

- 2026-09-09: Added the two ProteoBench corpus workflows and documented the procedure for adding any workflow in `docs/workflows.md`. `workflow_proteobench.py` scores a module through three separately measured calls (`apb2 convert`, `apb-fasta verify-peptides`, `apb-proteobench benchmark`) with the intermediate H5MU on disk; `workflow_proteobench_run.py` scores it through one `apb-proteobench run` call in memory. Both read `workflow_proteobench.csv` — the second declares the new `WORKFLOW_TABLE` so siblings share one table — and both refuse a non-HDF5 `--format`. Making room for two new tools replaced the named executable fields with `tools`/`tool_versions` maps keyed by the names a workflow declares in `TOOLS`: workflows now call `context.tool("apb2")`, the workflow CLI takes repeated `--tool NAME=PATH` instead of `--apb-executable`/`--aggregate-executable`, and `run.json` and `execution_settings.json` carry the maps. Run snapshots written with the old fields no longer validate in Python and were left in place; the viewer renders them with `tools: null` rather than failing. `--fasta-executable` and `--proteobench-executable` join the override table, `parameter_software()` moved to the shared `workflows/software.py`, and the viewer's saved-run panel shows every tool and version.

- 2026-09-09: Show more now separates Inputs & outputs, APB metadata, every quantification or annotation AnnData modality, and the complete representation JSON into lazy top-level tabs. The APB metadata panel mirrors each physical scope as `uns["apb"]`, opens `parse` by default, and presents the shared MuData scope and every level-owned AnnData scope as nested tabs. AnnData panels contain scientific tables and nested axis/layer/aligned-structure tabs only, so each Plotly chart renders after its individual layer becomes visible. Rule, plan, search-parameter and aggregation JSON text renders as structured values; malformed or scalar text remains unchanged for diagnosis.

- 2026-09-09: Review hardening made persisted evidence truthful across execution and display. Run fingerprints now include shared workflow modules and the actual editable APB/APB Aggregate package contents without importing them. A root-specific viewer identity endpoint makes repeated start idempotent; shutdown and restart additionally correlate the recorded PID with the exact listening socket before signaling. Dataset summaries expose only observed outputs from succeeded steps, while Show more retains every planned path and the measured size of any output that exists even when its step later fails. Scientific representation version 2 renders bounded quantitative summaries through Plotly and categorical layers through fixed-size counts rather than numeric statistics.

- 2026-09-09: Workflows now declare their own required executables. `workflow_convert.py` declares `TOOLS = ("apb2",)` and `workflow_aggregate.py` declares `("apb2", "apb-aggregate")`; `corpus/discovery.py` gained `workflow_tools()` to read that declaration, and `corpus/cli.py` resolves exactly those executables instead of testing `workflow == "aggregate"`. `resolve_apb` and `resolve_aggregate` are gone. A convert run no longer requires `apb-aggregate` on PATH, so Studio can be installed without it. Persisted `run.json` and `execution_settings.json` keep their existing `apb_executable`/`aggregate_executable` fields and values, and the routine corpus reproduces its previous outcomes exactly: convert 10/10, aggregate 7/10 with the same three failures.

- 2026-09-09: Corpus workflows now declare each APB `.apb.json` sidecar as an output, including intermediate conversion results. Show more lazy-loads the versioned documents into scientific overview, axis, layer, aligned-slot, collection and provenance panels; per-observation layer summaries use Plotly with explicit observation and quantity/unit axes. Raw representation JSON and the complete execution report remain expandable diagnostics, while the dataset table and artifact-size chart continue to select scientific outputs rather than sidecars.

- 2026-09-08: Added persisted corpus size evidence and resource-profile charts without expanding `corpus.csv`. Execution settings explicitly reference the acquisition `downloads.csv`; run preparation snapshots an explicit `input_file` to `input_file_path` size join, and successful step artifacts record file or recursive directory byte sizes. The viewer adds an Input sizes sub-tab and a Visualizations tab for runtime, peak process-tree RSS, and generated artifact size against vendor input size, one observation at a time and grouped by software.

- 2026-09-08: Simplified the corpus viewer to a dataset result table plus per-row Show more navigation. The detail view has one sub-tab per workflow step, colors failed dataset/step navigation red, and omits empty stdout, stderr, warning, and error sections. Runs without saved execution settings no longer enter the viewer catalog, and their seven legacy artifact trees were removed from the project output directory.

- 2026-09-08: Added `workflow_aggregate.py` without adding stage knowledge to Snakemake. Each parallel dataset job now performs exactly `apb2 convert <start_level>` followed by `apb-aggregate <start_level> protein <method>`. `workflow_aggregate.csv` joins explicitly on `software_name`, selects `mean`, and starts at fragment for DIA-NN and Spectronaut and ion for every other catalogued software. Execution settings and run fingerprints record both executable paths and versions.

- 2026-09-08: Separate named `corpuses/all.csv` and `corpuses/routine.csv` inventories from downloaded vendor files. Reusable execution settings explicitly record the corpus and workflow-table paths plus an independent data root. The viewer now selects settings first, then their saved runs, and can preview configured inventories without running APB. Each run retains its full source inventory and selected rows separately.

- 2026-09-08: Corpus V2 replaces the stage registry and pipeline YAMLs with concrete Python workflows, a shared subprocess runner, minimal corpus/workflow CSVs, per-dataset JSON reports and a final index. A new static JavaScript corpus viewer shows frozen settings and CSVs, live progress, step telemetry and separate stdout/stderr. APB failures remain inspectable results; force and clean preserve earlier artifacts in run history. The reference conversion workflow supports HDF5 plus DuckDB/Parquet through APB2 reformat.

- 2026-09-04: The conventional test-data root moved into this repo: `apb_studio/test_data_download/` (gitignored). The Fixture Manager setting names it, consumers never assume it exists, and apb2's unit tests read it via `APB2_TEST_DATA`. The legacy `config/corpus.yaml` relic — written by the corpus scaffold removed with the fixture-driven runner and read by nothing since — was deleted along with its `.gitignore` entry, and the README sentence that mentioned it.

- 2026-09-03: The full pipeline now calls the existing `apb-aggregate` CLI after FASTA checking and before ProteoBench: ion-to-protein and fragment-to-protein `sum` run independently when those levels exist, and skipped stages reconnect their successor to the last emitted artifact. The direct `apb-proteobench run` route performs the corresponding in-memory aggregations and still writes one final MuData result.

- 2026-08-28: Added the missing `LICENSE` file (MIT), and the `license` and `authors` fields that
  `pyproject.toml` had never declared.

- 2026-08-26: The integrated corpus environment now resolves Prozor from the authoritative local
  workspace checkout, matching APB's structural protein-record API instead of reinstalling its
  obsolete Git revision. The full ten-dataset routine corpus and its zero-job settling check pass.

- 2026-08-25: `AGENTS.md` and `README.md` no longer point into the workspace's archived planning
  folder for the migration history, the original dashboard design, or the observer/operator
  boundary. The boundary section in `AGENTS.md` is the record; `CHANGES.md`, `git log`, and
  `docs/architecture.md` carry the rest. Documentation only.

- 2026-08-25: apb2's no-level conversion now appears beside APB's on the MuData row as
  `mudata.apb2`. Capability discovery adds that branch whenever apb2 has at least one compatible
  level, the common DAG routes its `.h5mu` artifacts through the same downstream stages, and the
  `apb2-convert` pipeline reruns only apb2's MuData and standalone conversions.

- 2026-08-24: Added the `convert` pipeline — both converters, conversion only — so the grid can
  show `Converted` beside `Converted2` with nothing downstream; `apb-convert` and `apb2-convert`
  each show one chain and could not be compared on one row. The GUI gained a cores field and a
  `force` checkbox (defaulting to 10 cores rather than the hardcoded 3), and the Snakemake log
  panel now pins itself to its newest line — it renders the last 40 KB of a log that can reach
  megabytes, and starting that window at the top made a live run look frozen.

- 2026-08-24: `run_corpus.py` runs the whole corpus by default (`--fixtures` 0) and can be
  narrowed by **name** instead of by anonymous sample: `--datasets FILE` takes one dataset alias
  or `module/alias` per line, `--level ion --level mudata` restricts quantification levels, and
  any narrowed run logs the datasets it covered. A name matching nothing is warned about
  individually and a selection matching nothing fails the run. `selections/routine.txt` names one
  fixture per vendor and `make corpus-routine` runs it — that, not a sample, is now the routine
  gate.

- 2026-08-24: The comparison plot pins each axis to its own data instead of letting the `y = x`
  line drive both: a 2280 s outlier in one column had stretched the other column's axis from 26 s
  to 2300 s, flattening every point against the origin. The reference line now spans both columns
  and is clipped by those ranges, so it survives even when every row sits on one side of equality.
  Added a linear/log axis toggle and a title reporting how many of the grid's rows the plot could
  compare, and axis ranges start at zero because neither a runtime nor a size can be negative.

- 2026-08-24: The Corpus Runner can compare two stage columns as a scatter plot — runtime from
  Snakemake's benchmark files, or artifact size, one point per row with a `y = x` reference line, in
  a collapsed panel under the grid. Axis choices come from the columns the grid is showing, so they
  follow the active pipeline; a row missing either value contributes no point. Completed stages now
  record their artifact's size beside its duration. AG Grid cell-range selection was not an option:
  it is an Enterprise feature, so the axes are explicit pickers. Also fixed: after the run-snapshot
  schema bump, every snapshot from the older schema logged a warning on each dashboard refresh —
  `UnsupportedSnapshotSchema` now separates expected history from a malformed snapshot.

- 2026-08-23: A run now selects a **pipeline** — which converters and which stages — instead of
  always running both generations through all four stages. Five packaged documents in
  `config/pipelines/` (`full`, `apb-convert`, `apb2-convert`, `apb-full`, `apb2-full`) select from
  the stage catalogue without restating any stage, and are refused when a selection is not closed
  under `depends_on`. `--pipeline` on the Corpus Runner (now a cyclopts app with `--port` and
  `--settings`) and on both scripts, `CORPUS_PIPELINE` in every Make corpus target; `run_corpus.py`
  also gained `--output-root` and `--force`. The choice rides in `run.json` (schema 2), so a
  persisted run renders its own grid columns instead of the packaged catalogue's, and a pinned run
  keeps the pipeline it was minted with. Column suffixes are positional, so a single-converter run
  shows `Converted`, not `Converted2`; artifact tabs are now one per stage column, which also fixes
  apb2 columns having had no tab. The Snakefile and `capabilities.py` are unchanged: every pipeline
  is a subset of the four rules, and converter filtering happens once, in
  `expand_resolved_targets`.

- 2026-08-23: `docs/architecture.md` now records the layering, the decision to compute the
  DAG in Python and let Snakemake schedule it (what the single generic Snakefile buys and
  what it costs), the `run.json` contract with the three things it does not yet carry
  (requested target subset, apb2's version, per-target resources), and the status
  contract. No behaviour change.

- 2026-08-22: A corpus run now converts every fixture with **both** generations and runs APB's
  annotate, FASTA and ProteoBench stages on each conversion. The converter rides in the branch
  (`ion` for `apb`, `ion.apb2` for `apb2`), so one extra branch buys the whole comparison: the
  stage DAG and the four Snakemake rules are unchanged. One grid row is one level and each
  converter has its own stage columns — `Converted`/`Annotated`/`FASTA annotated`/`Proteobench
  scored`, then the same four suffixed `2` — so both conversions of a fixture sit on one line.
  The registry's root stage declares one command per converter — `apb` takes the level as an
  option, `apb2` takes it positionally — while every later stage keeps
  its single template, because it reads whatever object it is given. Which levels apb2 supports is
  asked of apb2 (`compile_parsers` over its own packaged rules, headers only); a fixture it cannot
  convert contributes no branch and leaves the APB branches beside it untouched. apb2 is a new
  Studio dependency, and the workflow resolves its console script the same way it resolves apb's.

- 2026-08-13: Follow APB's contract-folder rename in lockstep: `anndata_proteomics.rules` →
  `.vendor_quant_rules` and `.params` → `.vendor_params` across six files. No shims — Studio is
  APB's only consumer, so the old paths are simply gone. 228 tests pass.
- 2026-08-11: Make filesystem paths exact typed boundaries across Studio. Services now accept
  `Path` (or `Path | None`) rather than `Path | str`; Dash strings are converted at callback edges,
  and Pydantic performs serialized settings/CSV conversion before path validators run. This matches
  APB's Path-only parameter, rule, annotation, summary, and result-loading contracts.
- 2026-08-11: Add `make carpets`, running the sibling `carpet_scan` package as a `manual`-stage,
  non-blocking hook. **Only three of the five checks work here:** pyan3 2.6.2 raises
  `ValueError: Unknown scope '...listcomp.0.lambda.0'` on the lambda inside a list comprehension in
  `pipeline/render_command.py`, which kills the public-surface and call-depth tables; vulture, radon,
  ruff and grimp still run. The bug is upstream in pyan3 — do not rewrite that lambda to please it.
  First run: 8 vulture findings, 149 cross-module private accesses (148 `SLF001`, 1 `PLC2701`).
  `build/` is now gitignored, since the report is written there.
- 2026-07-31: Name `CORPUS_CORES` in the `corpus-run` help text and `AGENTS.md`. Both corpus targets
  already passed `--cores $(CORPUS_CORES)`, but only `CORPUS_FIXTURES` was mentioned, so the core
  count looked hardcoded at 10.

- 2026-07-31: Add `make corpus-run` / `make corpus-check` so the corpus gate is reachable without
  the Dash app. There was a target to *start* Corpus Runner and one to *clean* the corpus, but none
  to run it, which is why verification kept meaning "open the UI and launch the whole catalogue".
  `scripts/run_corpus.py` mirrors the existing `clean_corpus.py` composition (`prepare_run` +
  `snakemake_argv`) and defaults to ten fixtures — ~88 stages, minutes — with `--fixtures 0` for the
  whole 965-job selection and `--dry-run` for the zero-pending-jobs check. The run snapshot still
  describes the complete inventory; only the requested Snakemake targets are narrowed, which is the
  same mechanism `launch_corpus` already uses, so the whole-corpus product boundary is untouched.
  `sample_fixture_targets` picks fixtures round-robin by vendor, so a ten-fixture gate exercises ten
  parsers instead of ten submissions from one tool, and sorts within each fixture so the selection is
  independent of input order.

- 2026-07-31: Record the corpus verification scope in `AGENTS.md`: the routine check after a
  refactor is roughly ten fixtures (~88 jobs, minutes), not the full 241-fixture selection
  (965 jobs, ~1 hour at `--cores 10`). Corpus size is a property of the selected fixture set
  rather than a run option, because Corpus Runner deliberately exposes whole-corpus run and
  clean only — so the small gate is reached by selecting fewer fixtures, never by adding a
  scoped Run control that the product boundary forbids. A full-catalogue run is now reserved
  for release-level checks and deliberate artifact-parity diffs, run once at the end.
- 2026-07-31: Fixture Manager: stop the one-second poll from rebuilding the tables. The
  refresh callback now emits both grids' `rowData` and the module dropdowns only when a
  content digest of the inventory actually moves, so an idle tick no longer discards the
  user's selection, scroll offset, sort, or filters; the job log and status still update
  every tick, which is what the poll exists for. The fixture table is also keyed on the
  canonical `(module, repo_name, intermediate_hash)` identity, so a real data change
  applies as a keyed delta rather than a full rebuild. Per-column filters were already
  enabled but reachable only through each header menu — `floatingFilter` puts an inline
  filter row on every column of both tables.
- 2026-07-31: Fixture Manager: the File tab lists the downloaded vendor table's own column
  header beneath the fixture metadata. Columns come from APB's `read_table_columns`, so the
  delimiter is content-detected exactly as during conversion and a comma-delimited `.txt`
  reads as more than one column here too. Absent, ambiguous, and unreadable inputs each
  report their own state instead of guessing a file.
- 2026-07-31: Lower the coverage gate from 100% to 90% at the owner's request.

- 2026-07-31: Implement the APB Studio findings from the verified 2026-07-30 review.
  Delete the retired dict-based corpus model (expander, baskets, problems, descendants,
  and the `branch_rows` compatibility branch), leaving only the resolved-fixture path and
  the full blocked-stage topology. `apb_studio.provenance` moves to Cyclopts and Loguru,
  keeping its `--run`/`--output` spelling. The Snakefile now prefers packages already
  resolved by the active environment and appends a source-checkout fallback only for
  packages that are otherwise unavailable, so an installed `apb` can no longer be shadowed
  by a sibling checkout; the provenance subprocess inherits the same resolution order and
  receives the run path through the environment, so a fresh run ID no longer invalidates
  unchanged targets. `latest_persisted_run` logs each rejected snapshot instead of skipping
  it silently, and `terminate_job` returns `True` only for a confirmed process exit.
  Dash callbacks move to module-level functions bound with `functools.partial`, and broad
  `except Exception` boundaries narrow to the exceptions their callees actually raise.

- 2026-07-30: Upgrade to pandas 3.0.5 and anndata 0.13.2 (also mudata 0.3.10, numpy
  2.5.1) to match APB, which needed the upgrade to pick up an anndata fix. No source
  changes were required. Outputs under `apb_outputs/` predating this were produced on
  the old stack and carry the PEAKS layer defects APB fixed on the same date; regenerate
  them to get correct `Normalized_Area` and `AScore` missingness.
- 2026-07-30: Read capability-probe headers through APB's
  `readers.dispatch.read_table_columns` and delete the private `read_table_headers`
  copy, which hardcoded `.txt` to tab. Comma-delimited `.txt` exports (AlphaPept, some
  PEAKS) read as one column there, so they reported `UNSUPPORTED` even with a correct
  parsing rule while converting fine. Drops the now-unused direct `pyarrow` dependency.
- 2026-07-30: Score every annotated branch with ProteoBench. Drops the
  `module_level` branch policy, its `proteobench_level` snapshot field, and the
  level restriction in the Snakefile's ProteoBench wildcard constraint, so
  `protein`/`fragment` branches are no longer reported `UNSUPPORTED`.
- 2026-07-30: Add `make corpus-clean` over `scripts/clean_corpus.py` (cyclopts +
  loguru), which freezes the run snapshot the packaged Snakefile requires and
  invokes its clean rule headlessly.
- 2026-07-25: Show the exact shell-quoted `apb` CLI command in every Corpus
  Runner stage detail, or state explicitly when capability/prerequisite
  resolution could not generate a command.
- 2026-07-24: Select one Corpus Runner branch and inspect Convert, Annotate,
  FASTA, and ProteoBench artifacts in tabs; surface FASTA matched,
  proteotypic, and annotated feature counts ahead of the full APB JSON summary.
- 2026-07-24: Add server-resolved resource previews to Fixture Manager:
  annotation cells show the assigned file and FASTA cells show a bounded 40-line head.
- 2026-07-24: Remove Fixture Manager conversion controls, status, converted
  container browser, and backend launch helpers now that Corpus Runner owns all
  conversion execution; retain fixture JSON/parameter details and configuration editing.
- 2026-07-24: Persist Snakemake rule benchmarks and show elapsed time in
  completed Corpus Runner stage cells and artifact details.
- 2026-07-24: Add a guarded Corpus Runner action to clear a selected completed
  or failed stage and its downstream branch artifacts after confirmation.
- 2026-07-23: Align local and GitHub quality gates with the FGCZ Python
  reference, package the registry/Snakefile for installed use, and add staged
  Ruff/Pyright/Deptry/coverage hooks, wheel inspection, strict docs, dependency
  audit, typed-package marker, and CI/Pages/security workflows.
- 2026-07-23: Resolve the APB executable from Snakemake's virtual environment so
  Corpus Runner jobs do not depend on the parent shell's `PATH`.
- 2026-07-23: Add a `.pre-commit-config.yaml` (ruff lint+format, then pytest) mirroring apb; the
  repo previously had no pre-commit hooks. pyright/deptry are deferred until existing findings clear.
- 2026-07-23: Remove the deprecated `make app`/`make testdata-app` alias targets from the Makefile
  (the `corpus-runner`/`fixture-manager` targets remain; console-script aliases are unchanged).
- 2026-07-22: Add an independent ProteoBench scoring stage for the module-selected MuData/AnnData
  branches, managed per-tool settings, `.proteobench` artifacts, dashboard status, and Snakemake
  orchestration without making annotation or FASTA prerequisites.
- 2026-07-22: Download ProteoBench `module_settings.toml` observation annotations in Fixture
  Manager and resolve them automatically instead of requesting manual annotation JSON paths.
- 2026-07-22: Name the applications **Fixture Manager** and **Corpus Runner**, replace the
  user-maintained `corpus.yaml`/scaffold workflow with shared settings and fixture inventory, and
  make the Corpus Runner freeze each launch into an internal `run.json` snapshot.
- 2026-07-22: Distinguish neutral `UNSUPPORTED`, prerequisite `BLOCKED`, and attempted-rule
  `FAILED` states; reconnect browser reloads to active runs and harden resources, settings, aliases,
  and failure markers.
- 2026-07-22: Fan out each corpus dataset to every APB JSON-supported MuData/standalone branch,
  carry every branch through conversion, annotation, and FASTA, and monitor the whole run in one
  compact live table with per-cell summaries and failure logs.
- 2026-07-22: Fix corpus stage-cell clicks by resolving Dash AG Grid's stable `rowId`, and place the
  selected artifact summary or failure immediately below the table.
- 2026-07-21: Run the corpus app on configurable port 8051 by default.
- 2026-07-21: Add interactive fixture conversion and distinct standalone-AnnData/MuData browsing.
- 2026-07-21: Add a validated JSON configuration catalog/editor with raw Base/level tabs,
  whole-document validation, stale-write protection, and atomic saves.
- 2026-07-21: Replace the empty Actions workspace and duplicate fixture tables with one
  availability table plus Download/Convert workflow tabs and rule-based conversion status.
