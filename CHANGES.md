# Changes

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
