# Corpus Runner

> Status: implemented and verified on 2026-07-22; archived 2026-07-24.

## Decision

Remove `corpus.yaml` from the architecture. The Fixture Manager does **not** generate it, and the
Corpus Runner does not read it.

The two applications are named:

- **APB Studio — Fixture Manager**: catalog, select for download, download, manage FASTA/sample
  annotation resources, inspect fixtures, and report cache health.
- **APB Studio — Corpus Runner**: derive every APB-supported branch, run all available fixtures,
  monitor progress, and show artifact summaries or rule logs.

The generated fixture tables and local cache supply fixture facts. The APB parsing-rule JSONs,
resolved against each local input and parameter file, supply supported branches. Therefore fields
such as `level: ion` never belong in a corpus file or a generated table.

## Sources of truth and ownership

| Information | Owner/writer | Consumer |
|---|---|---|
| ProteoBench catalog and download queue | Fixture Manager via `apb-testdata` | Fixture Manager |
| Download report and cached input/parameter files | Fixture Manager via `apb-testdata` | Both apps |
| Active test-data root | Fixture Manager setting | Both apps |
| Module annotation and FASTA availability | Fixture Manager resource inventory | Both apps |
| Supported MuData/standalone levels | APB JSON rules + local headers/version | Corpus Runner |
| Output root | Corpus Runner setting | Corpus Runner/Snakemake |
| Exact scope of one launched run | Corpus Runner-generated JSON snapshot | Corpus Runner/Snakemake/provenance |
| Completion and runtime failure | Output artifacts and rule failure markers | Corpus Runner |

The active roots are stored in one typed, disk-backed application settings file, for example
`platformdirs.user_config_path("apb-studio") / "settings.json"`. A shared settings service performs
validated atomic updates:

- Fixture Manager writes `test_data_root`.
- Corpus Runner writes `output_root`.
- Neither setting requires users to maintain a config file.

ProteoBench's per-module `module_settings.toml` files are the authoritative observation
annotations. Fixture Manager downloads and resolves them by canonical module. An app-owned
`module_resources.csv` under the test-data root retains optional resource overrides; APB's existing
downloader supplies FASTA entries.

## Corpus and run semantics

For Corpus Runner, the corpus is **every complete local fixture** in the active test-data root. The
download selection CSV controls the download queue only; it is not another Corpus Runner filter.
Remote catalog entries remain in Fixture Manager until downloaded.

A complete local fixture has exactly one `input_file.*` and exactly one `param_0.*`. Every such
fixture remains visible, including unsupported software/version/header combinations.

Corpus Runner does this on reload:

1. Read the shared typed fixture inventory.
2. Resolve the APB vendor/version and branches from local input/parameters and APB JSON rules.
3. Show one unresolved row for a local unsupported or invalid fixture.
4. Fan each supported fixture out to MuData plus every supported standalone level.
5. Derive stage state from resources, artifacts, and authoritative failure markers.

`Run corpus` submits every runnable **stage target**, not only fixtures whose whole three-stage chain
is ready. Conversion still runs when annotation is unavailable; annotation still runs when only
FASTA is unavailable. There is no row selection or per-row Run action.

At launch, Corpus Runner freezes the resolved fixtures, branches, paths, resources, registry/APB
versions, and output aliases into:

```text
<output_root>/.apb_studio/runs/<run-id>/run.json
```

This is versioned internal execution state, never accepted as user configuration. While a job is
active, the table remains pinned to its fixture/branch snapshot while artifact cells update. New
downloads join after that job finishes and the Corpus Runner reloads for the next run.

Stable internal fixture identity is `(canonical module, repository name, full intermediate hash)`.
Do not change existing output paths in this work. Persist an app-owned fixture-ID-to-output-alias
map under the output metadata directory, seeding it from existing directories by their unique
hash suffix. A later APB vendor-recognition change must not move an existing fixture's outputs.

## Status contract

Only a rule that was actually attempted can fail:

| State | Exact meaning | Detail behavior |
|---|---|---|
| blank | Pending/runnable, including a downstream stage waiting for a normal upstream run | Quiet |
| `DONE` | Expected artifact exists | Open the exact artifact summary |
| `UNSUPPORTED` | APB has no registered capability for the software, or no parsing-rule JSON matches | Show capability diagnostic; no log download |
| `BLOCKED` | Required input/resource is absent or invalid, or an upstream stage ended `FAILED`/`BLOCKED` | Show prerequisite diagnostic; no log download |
| `FAILED` | Snakemake attempted this concrete rule, it exited non-zero, and its failure marker exists | Red; show and download that rule's log |

An unreadable header or unparseable parameter file is `BLOCKED`, not `UNSUPPORTED` and not
`FAILED`. A leftover log alone never means failure. An artifact wins over an old marker. If
conversion fails, its annotation/FASTA descendants are `BLOCKED`; they were not attempted.

For the reported example:

```text
No APB parsing rule matches software 'peaks', version '13 20250520', and the input headers.
```

the Converted cell is `UNSUPPORTED`, neutral rather than red. Its downstream cells remain empty.
The bottom panel heading becomes **Artifact summary or status**. Only actual `FAILED` details offer
a log download.

## Required upstream correction

Before treating the fixture cache as authoritative, fix `apb-testdata catalog`: its metadata refresh
currently deletes the whole repository cache directory, including downloaded fixture hash folders,
and can leave the download report saying `ok` for missing files. Refresh only the repository
metadata snapshot and preserve downloaded directories. Add a regression test at the APB source of
this behavior.

Filesystem prerequisites are local truth. A manifest status is history and cannot override missing
or ambiguous input/parameter files.

## Implementation plan

### 1. Establish Fixture Manager ownership

- [x] Rename the page, Make target/entry point, and documentation to **Fixture Manager**. Prefer
      `make fixture-manager`; retain `make testdata-app` temporarily as a deprecated alias.
- [x] Fix APB catalog refresh so downloaded hash directories survive metadata refresh.
- [x] Extract a typed fixture-inventory API from `testdata.py` and reuse it in both applications.
- [x] Separate raw catalog software labels from the APB vendor resolved from headers; add no Studio
      vendor-support map.
- [x] Define complete/incomplete local state from exactly one input and one parameter file.
- [x] Generalize APB's existing module-to-FASTA resolver to the active test-data root and expose the
      existing FASTA download action in Fixture Manager.
- [x] Add the Fixture Manager-owned resource table and managed ProteoBench annotation downloads.
- [x] Replace browser-only root state with the shared atomic settings service.

### 2. Make Corpus Runner inventory-driven

- [x] Rename the page, Make target/entry point, and documentation to **Corpus Runner**. Prefer
      `make corpus-runner`; retain `make app` temporarily as a deprecated alias.
- [x] Stop reading `config/corpus.yaml`; remove the tracked example and normal `make scaffold`
      workflow. Leave any ignored user-owned `config/corpus.yaml` untouched and report it as
      deprecated.
- [x] Replace YAML dataset expansion with expansion from typed complete-local fixture records.
- [x] Derive all branches exclusively through APB's capability resolver.
- [x] Replace the YAML path textbox with compact Fixture Manager source/output information and
      Reload/Run controls. Add no Corpus Runner selection UI.

### 3. Freeze and execute each run

- [x] Generate the versioned internal `run.json` snapshot and pass it to the Snakefile, active-job
      dashboard, and provenance writer.
- [x] Keep the active table's fixture/branch scope pinned to the snapshot while polling artifacts
      and the live Snakemake log.
- [x] Schedule all runnable stage targets with `--keep-going`; blocked later stages must not suppress
      earlier runnable work.
- [x] Preserve output aliases through the stable mapping before retiring the YAML-derived names.

### 4. Correct statuses and interactions

- [x] Replace every preflight-generated `FAILED` with `UNSUPPORTED` or `BLOCKED` according to the
      status contract.
- [x] Require a rule failure marker for `FAILED`; never infer it from a log alone.
- [x] Keep pending downstream cells blank and mark them `BLOCKED` only after a terminal blocker.
- [x] Use **Artifact summary or status** for the detail panel; enable log download only for actual
      `FAILED` cells.
- [x] Keep one unresolved row for unsupported/invalid fixtures without fake levels or repeated
      downstream errors.

### 5. Migrate tests and documentation

- [x] Replace scaffold/config synchronization tests with shared-inventory, settings, resource-table,
      run-snapshot, and cache-preservation tests.
- [x] Update pipeline/dashboard tests for the exact status truth table and click behavior.
- [x] Update execution/provenance/Snakefile tests to use `run.json` rather than user YAML.
- [x] Update README, Makefile help, architecture text, and change logs with the two application names
      and ownership boundary.

## Acceptance

- [x] No normal command or application creates, updates, or reads `corpus.yaml`.
- [x] No fixture table or application setting contains a level such as `level: ion`.
- [x] All 98 currently complete local fixtures enter the inventory; the 48 omitted by the former
      scaffold remain visible as unsupported/blocked where appropriate.
- [x] DIA-NN and Spectronaut fan out according to APB JSON rules and actual input headers/version.
- [x] The Peaks example shows neutral `UNSUPPORTED`, not red `FAILED`.
- [x] A deliberately failing supported conversion shows red `FAILED` with its exact log; its
      unattempted descendants show `BLOCKED`.
- [x] Missing annotation does not prevent conversion; missing FASTA does not prevent annotation.
- [x] Catalog refresh preserves downloaded inputs/parameters.
- [x] A fixture downloaded during a run does not enter that run, then appears after completion and
      reload without scaffolding.
- [x] Existing artifacts retain their fixture/output association after migration.
- [x] APB and apb_studio tests, Ruff, and a real Snakemake dry run pass.

## Non-goals

- No user-maintained corpus or replacement run YAML.
- No dataset, software, version, or level duplication outside the fixture inventory/APB rules.
- No download initiated by `Run corpus`.
- No invented annotation resource when none is available.
- No output-directory rename in this change.

The previous implemented branch/dashboard plan is archived in
[`TODO_corpus_application_full_history_2026-07-22.md`](TODO_corpus_application_full_history_2026-07-22.md).
