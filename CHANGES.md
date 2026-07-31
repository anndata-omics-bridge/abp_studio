# Changes

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
