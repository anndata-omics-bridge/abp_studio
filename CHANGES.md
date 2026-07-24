# Changes

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
