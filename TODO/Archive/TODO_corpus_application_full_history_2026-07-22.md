# Archived corpus application plan (2026-07-22)

## Proposed change: fixture-owned corpus

> Status: planning only, awaiting approval. This section supersedes the old `corpus.yaml` ownership
> and failure-state decisions in the implemented branch plan below. No implementation starts until
> this change is approved.

### Decision

Remove `corpus.yaml` completely. The Fixture Manager backend becomes the single owner of fixture
discovery, downloads, and local resource availability. The Corpus Runner reads that shared
inventory directly and runs every complete local fixture; it never offers a second fixture
selection and never asks the Fixture Manager to generate a duplicate dataset-list file.

No user-maintained replacement YAML is needed. The active test-data root and output root are normal,
persisted application settings. Per-module annotation/FASTA availability belongs to the Fixture
Manager's resource inventory. At launch, the Corpus Runner may generate an internal immutable run
snapshot for Snakemake and provenance, but that is an execution artifact rather than user config.

This splits the responsibility cleanly:

| Information | Authoritative owner | Writer/update event | Consumer |
|---|---|---|---|
| Remote ProteoBench fixture catalog | APB `apb-testdata` backend | `Catalog` | Fixture Manager |
| Selected/download queue | APB `apb-testdata` backend | `Select` | Fixture Manager only |
| Download report and cached files | APB `apb-testdata` backend | `Download` | Both apps |
| Module annotation/FASTA resources | Fixture Manager resource inventory | Download or explicit resource assignment | Both apps |
| Complete local fixture inventory | Shared typed inventory reader | Recomputed from catalog plus filesystem | Both apps |
| Supported output branches | APB parsing-rule JSONs plus local input/parameters | APB package or fixture change | Corpus Runner and pipeline |
| Active test-data/output roots | Shared application settings | Explicit settings change | Both apps |
| Exact inputs used by one run | Generated immutable run snapshot | `Run corpus` | Corpus Runner, Snakemake, provenance |
| Stage completion/failure | Artifacts and authoritative failure markers | Snakemake rules | Corpus Runner |

So the answer to “does the download application own this?” is:

- **Fixture Manager:** owns cataloging, selecting for download, downloading, cache freshness, and
  the availability of annotation/FASTA resources.
- **Corpus Runner:** owns output location, execution, progress, summaries, and logs.
- **APB:** owns deciding which branches/levels a local fixture supports.
- No component creates or updates `corpus.yaml`; it is removed.

### Why the current manifest must go

The current local state demonstrates the synchronization bug:

- the full catalog has 178 fixtures;
- 98 fixtures have exactly one local input and one local parameter file;
- `corpus.yaml` contains only 50 datasets.

`make scaffold` scans the cache and omits every fixture whose vendor cannot already be recognized
from its headers. That makes unsupported inputs disappear instead of appearing as `UNSUPPORTED`.
It also rewrites the whole YAML without preserving annotation/FASTA entries. Synchronization is
therefore stale and lossy by construction, not something another reload button can fix.

### Corpus membership and refresh behavior

For this application, “the corpus” means **all complete local fixtures** in the configured test-data
root. The selected CSV remains a download-queue policy and does not filter corpus execution. Remote
catalog entries stay in the Fixture Manager until downloaded, which keeps the Corpus Runner table
focused and compact.

- A complete local fixture has exactly one `input_file.*` and exactly one `param_0.*`.
- Every complete local fixture remains visible, including fixtures for unsupported software or
  versions.
- Reload/polling re-reads the shared inventory, so a newly downloaded fixture appears without
  scaffolding or editing YAML.
- `Run corpus` takes every local, supported, unblocked fixture. There is no row selection.
- A run resolves the current inventory once and writes a run snapshot. Later downloads do not
  mutate a running Snakemake DAG; they join the next run.
- Stable internal identity is `(canonical module, repository name, full intermediate hash)`. Keep
  the current display labels and output-directory aliases during this change so existing artifacts
  are not orphaned.

The shared inventory must keep raw catalog software labels separate from the APB vendor resolved
from input headers. Labels such as `FragPipe (DIA-NN quant)` are display metadata, not valid
conversion identifiers. APB remains the only capability authority; Studio must not add a vendor
support table.

### Stage-state contract

Use a small set of states and never infer failure merely from a missing artifact or existing log:

| State | Meaning | Presentation/detail |
|---|---|---|
| blank | Runnable stage has not completed or failed | Quiet cell |
| `DONE` | The expected artifact exists | Click opens that artifact's summary |
| `UNSUPPORTED` | Local fixture was inspected successfully, but no APB JSON rule matches software/version/headers | Neutral; click opens the capability diagnostic |
| `BLOCKED` | A supported stage lacks a required resource or an upstream stage did not complete | Neutral/amber; click opens the prerequisite reason |
| `FAILED` | A concrete Snakemake rule was attempted, exited non-zero, and wrote its failure marker | Red; click opens and can download that rule's log |

Consequences:

- `peaks / 13 20250520 / no matching headers` is `UNSUPPORTED`, not `FAILED`.
- Missing annotation or FASTA is `BLOCKED`, not `FAILED`.
- If conversion fails, annotation and FASTA are `BLOCKED`; they were not attempted.
- A leftover `.log` without an authoritative failure marker does not make a cell red.
- Downstream cells of an unsupported fixture remain empty rather than repeating the same status.

### Required upstream correction

Before the cache becomes authoritative, fix the APB test-data root cause: `apb-testdata catalog`
currently deletes each entire repository cache directory while refreshing metadata, which also
deletes downloaded fixture folders and can leave the download CSV falsely saying `ok`. Catalog
refresh must replace only its metadata snapshot and preserve downloaded hash directories.

Filesystem prerequisites then determine local truth. A manifest row saying `ok` is useful history,
but it cannot override a missing or ambiguous input/parameter file.

### Resource ownership

- FASTA belongs in the Fixture Manager. APB already owns the canonical module-to-FASTA mapping and
  an `apb-testdata fasta` command; expose and generalize those for the configured root rather than
  duplicating the mapping in Studio.
- The existing fixture CSVs contain module/software/version/input facts, but they currently do not
  identify sample-annotation resources. Add a small per-module resource table managed through the
  Fixture Manager UI; do not ask users to edit YAML.
- Sample annotation does not yet have an authoritative downloadable source. Until one is defined,
  the Fixture Manager can record an explicitly assigned annotation file and the Corpus Runner shows
  annotation stages as `BLOCKED` when none is available.
- If a canonical annotation source is defined later, `apb-testdata` can populate the same resource
  inventory automatically.

### Implementation plan

#### 1. Repair and expose the fixture source

- [ ] In APB, make catalog metadata refresh preserve downloaded hash directories and test that a
      refresh cannot remove local inputs or parameters.
- [ ] Generalize APB's existing FASTA resolver to a configured test-data root; add the existing
      FASTA action to the Fixture Manager.
- [ ] Extract a typed shared fixture-inventory API from `testdata.py`. Merge catalog metadata,
      download history, and live filesystem prerequisites without UI-formatted strings.
- [ ] Keep unsupported local fixtures in that inventory and return a structured capability
      diagnostic instead of filtering them out.
- [ ] Make both applications read the same persisted test-data root rather than separate browser-
      local state.

#### 2. Remove the manifest and add a run snapshot

- [ ] Remove `config/corpus.yaml` and its example. Persist the active test-data root and Corpus
      Runner output root as typed application settings, not as a dataset manifest.
- [ ] Add a small Fixture Manager-owned per-module resource table for resolved annotation and FASTA
      paths. Validate its paths and display missing resources explicitly.
- [ ] Remove dataset enumeration from `load_corpus()`, normal runtime use of `scaffold.py`, and the
      `make scaffold` prerequisite. Keep a clearly deprecated migration command only if existing
      users need it.
- [ ] At launch, resolve settings plus the complete local inventory into an immutable, versioned
      run manifest under `output_root/.apb_studio/runs/<run-id>/`.
- [ ] Record stable fixture IDs, resolved paths/vendor/branches/resources, output aliases, stage
      registry/APB versions, and the run log path in that snapshot.
- [ ] Pass the snapshot—not the mutable catalog—to the Snakefile, dashboard job view, and
      provenance writer for the duration of that run.

#### 3. Adapt pipeline and status handling

- [ ] Expand targets from inventory records rather than YAML dataset dictionaries; continue to use
      APB JSON capability discovery for every branch.
- [ ] Preserve current output paths during migration while using the full fixture ID internally.
- [ ] Replace preflight `FAILED` synthesis with the state contract above. Only Snakemake rule
      failure markers create `FAILED`.
- [ ] Keep one unresolved row for unsupported fixtures; do not create fake branches or downstream
      failures.
- [ ] Ensure a new download appears after reload and an active run remains pinned to its snapshot.

#### 4. Name and update the applications

- [ ] Rename the download/test-data UI to **APB Studio — Fixture Manager**. It owns Catalog, Select,
      Download, FASTA, resource assignment, fixture inspection, and cache-health reporting.
- [ ] Rename the corpus UI to **APB Studio — Corpus Runner**. It owns Run corpus, output settings,
      progress, summaries, and rule logs.
- [ ] Replace the corpus YAML path textbox with compact source/output information and an explicit
      Reload; do not add corpus selection controls.
- [ ] Update the table styling/details for `UNSUPPORTED`, `BLOCKED`, and actual `FAILED` states.
- [ ] Replace README, Makefile, example config, provenance, and tests that still describe
      `corpus.yaml` as the fixture inventory.

### Verification and acceptance

- [ ] All 98 currently complete local fixtures reach the shared inventory; the 48 omitted by the
      current scaffold remain visible rather than disappearing.
- [ ] The Peaks example renders `UNSUPPORTED`; it is not red and has no failed-log download.
- [ ] A deliberately failing supported conversion renders red `FAILED` with its exact log.
- [ ] Missing annotation/FASTA and downstream-of-failure cells render `BLOCKED`.
- [ ] Catalog refresh preserves already downloaded fixture directories.
- [ ] A newly downloaded fixture appears in the corpus after reload without changing settings.
- [ ] Adding a fixture during a running job does not change that run's targets or provenance.
- [ ] Existing output artifacts remain associated with the same rows after migration.
- [ ] APB and apb_studio tests, Ruff, and a real Snakemake dry run pass.

### Non-goals

- No dataset, vendor, version, or level list in user settings.
- No user-maintained corpus or run YAML.
- No automatic download triggered by `Run corpus`.
- No duplicate APB support map in Studio.
- No invented annotation data when a module has no canonical annotation resource.
- No output-directory rename in this change.

## Previous implemented branch plan

> This records the already implemented fan-out/dashboard work. Its statements that
> `corpus.yaml` lists datasets and that preflight problems are failures are superseded by the
> proposed change above.

> Turn the corpus dashboard into a compact, corpus-wide progress monitor: one input fans out to
> MuData plus every standalone level supported by APB's parsing-rule JSONs, and Snakemake carries
> every branch through conversion, annotation, and FASTA annotation.

Checked items are implemented; the remaining unchecked items still require integration or manual
verification.

## Requirements

### User story

Run the whole corpus once and watch it progress. For every source dataset, create all outputs APB
can actually produce from that software/version: one MuData and one standalone AnnData for every
supported level. Continue every branch through annotation and FASTA annotation. The application
shows the evolving state in one compact table and lets a stage cell reveal either that artifact's
summary or its failure log.

The corpus application is not a single-dataset conversion tool. There is no dataset selection and
no per-row Run action.

### Source of truth for branches

- The supported branches come from APB's packaged parsing-rule JSONs, resolved against the input
  headers and the software version parsed from its parameter file.
- Reuse APB's existing
  [`available_targets()`](../../apb/src/anndata_proteomics/converters/pipeline.py). It already returns
  the matching standalone levels plus the MuData target without reading the quantitative matrix.
- `corpus.yaml` remains only the local corpus manifest: input/output roots, module and dataset
  identities, vendor input and parameter paths, and annotation/FASTA resource paths. It does **not**
  declare or constrain output levels.
- Remove the old hard-coded distinction between multi-level vendors and single-level vendors from
  apb_studio. The parsing-rule JSONs are the end of the capability decision.

### Fan-out and pipeline behavior

- One dataset fans out into `MuData` plus every standalone level returned by APB. Example: if a
  DIA-NN input supports ion, fragment, and protein, it has four rows: MuData, ion, fragment, protein.
- The same rule applies to Spectronaut and every other software. There are no vendor-specific UI
  branches.
- One `Run corpus` action launches the Snakefile for the entire corpus with `--keep-going`.
- Every discovered branch continues through `convert -> annotate -> fasta`.
- FASTA applies to all levels APB currently supports: peptide-derived levels receive FASTA
  validation, protein receives FASTA-derived protein annotation, and MuData processes its
  applicable modalities together. Do not mark a supported level `N/A`.
- A missing input, parameters, annotation resource, FASTA resource, or matching parsing rule remains
  visible as a failure; it must not make the dataset silently disappear or abort unrelated datasets.
- Rerunning is ordinary Snakemake behavior: keep successful outputs and retry missing or stale work.

### Compact corpus table

Use one table, not a separate table for every basket:

| Module | Dataset | Software | Level | Converted | Annotated | FASTA annotated |
|---|---|---|---|---|---|---|

- Repeat Module, Dataset, and Software for each output branch; Level is `MuData` or the standalone
  quantification level.
- Remove `Basket`, `Next_stage`, `Runnable`, and the separate `Problem` column. State belongs in the
  corresponding stage cell.
- Use restrained typography and spacing: a normal-sized page title, compact controls, compact table
  rows, and no oversized basket headings.
- Keep pending cells visually quiet. A completed cell is clickable; a failed cell says `FAILED` in
  red.

### Live execution and logs

- Show the live corpus-wide Snakemake log while the job runs.
- Refresh the table automatically during a run. As soon as an artifact appears, its stage cell
  changes to completed without a manual Reload.
- A failed stage is detected from its missing output plus its surviving per-rule log or preflight
  capability/resource error.
- Clicking a red `FAILED` cell shows that exact stage log/error in the bottom detail pane. Include
  the resolved log path and a safe link/download for the known log file.
- Clicking a completed stage cell shows that exact artifact's summary in the same bottom pane.

### Summaries

The summaries are descriptive and deliberately small. They are cumulative by stage and
level-specific as far as useful:

- **Converted:** a few immediately understandable facts already provided by APB, such as
  software/version, level or modalities, runs, features, compact missingness, and intensity range.
- **Annotated:** the converted summary plus a compact overview of the sample annotation, for
  example annotation fields and groups.
- **FASTA annotated:** the preceding summary plus a small level-specific FASTA component: validation
  information for peptide-derived levels and protein-annotation information for protein.

APB owns summary computation and persistence; apb_studio only selects and renders
[`describe_path()`](../../apb/src/anndata_proteomics/readers/summary.py). Prefer less information.
Additional metrics are added only on request, not anticipated in a large summary that nobody can
understand.

### Acceptance

- DIA-NN and Spectronaut fixtures each expand to MuData plus every level supported by their matching
  APB JSON document, regardless of any `level` value in `corpus.yaml`.
- Single-level software expands to a one-modality MuData plus its supported standalone level.
- One `Run corpus` launches all discoverable branches and all three stages with `--keep-going`.
- The single compact table updates while Snakemake runs and preserves failed and successful branches
  side by side.
- Clicking Converted, Annotated, and FASTA annotated cells shows the summary for the exact artifact
  represented by that row and stage.
- Clicking `FAILED` shows the exact per-rule log/error and offers its log link/download.
- A failure in one branch does not prevent independent branches from completing.
- Existing APB and apb_studio tests remain green; Ruff is clean; both repositories receive dated
  `CHANGES.md` entries for implementation changes.

## Design

### 1. Capability discovery

Extract the already implemented capability-resolution path from
[`testdata.py`](../src/apb_studio/testdata.py) into one shared apb_studio helper used by both
applications:

1. Read only the input schema/header (Parquet metadata or a zero-row delimited-table read).
2. Parse the software version with APB's existing parameter parser.
3. Call APB `available_targets(software, version, headers)`.
4. Cache the result by input path/mtime and parameter path/mtime.

Return an ordered branch list with MuData first, followed by APB's stable level order. Return a
structured diagnostic when capability discovery fails so the corpus table can retain an unresolved
row and show `FAILED`, rather than dropping the dataset.

This removes `MULTI_LEVEL_VENDORS`, `SINGLE_LEVEL_VENDOR_LEVELS`, and the requirement that
`corpus.yaml` carry `level`.

### 2. Branch-aware target model and paths

The pipeline identity becomes `(module, dataset, branch, stage)`, where branch is `mudata` or a
standalone level. Extend `Target` with an explicit branch; do not infer it later from a filename.

Use collision-free, self-describing artifacts under the existing dataset directory:

```text
<output_root>/<module>/<dataset>/
  mudata.h5mu
  mudata.annotated.h5mu
  mudata.annotated_fasta.h5mu
  ion.h5ad
  ion.annotated.h5ad
  ion.annotated_fasta.h5ad
  fragment.h5ad
  fragment.annotated.h5ad
  fragment.annotated_fasta.h5ad
  ...
```

Each artifact keeps its existing adjacent `<artifact>.log`. Update provenance identity so repeated
`convert`, `annotate`, and `fasta` stages on different branches cannot overwrite one another; key
records by branch and stage, or use one sidecar per artifact.

### 3. Snakemake fan-out

`expand_targets()` performs capability discovery once per dataset and emits:

- one convert target without a level argument for MuData;
- one convert target with the corresponding level for every standalone branch;
- one annotate target per converted branch;
- one FASTA target per annotated branch.

The stage registry remains the source of stage topology and CLI templates. The Snakefile remains a
thin consumer of concrete targets. Update wildcard constraints/output lookup for branch-qualified
artifact names and make the default corpus goal include every emitted terminal target, including
FASTA when its resource exists.

If a module lacks an annotation or FASTA resource, retain the affected cells as visible static
failures while allowing runnable targets elsewhere into the Snakemake invocation. Do not let one
missing resource fail DAG construction for the whole corpus.

Initially reuse the existing `apb convert` CLI once per branch. This means the same vendor table may
be read more than once. Measure the real corpus before adding an APB multi-output API; do not add a
new wrapper or public command speculatively.

### 4. Row and cell state

Replace basket aggregation with a pure row builder keyed by `(module, dataset, branch)`. Each stage
cell carries hidden artifact and log targets plus a small display state:

- completed: artifact exists;
- failed: artifact missing and its stage log contains a failure, or preflight discovery/resource
  resolution failed;
- pending: neither completed nor failed.

An existing artifact wins over an old failure log. Starting a rule replaces its per-rule log, and
successful completion flips the cell on the next poll. Preserve the filesystem-as-database rule for
completion and let Snakemake own dependency freshness.

### 5. Dashboard interaction

Rebuild [`dashboard.py`](../src/apb_studio/dashboard.py) around:

- the compact config/reload controls;
- one `Run corpus` button;
- one compact `dag.AgGrid`;
- the live global Snakemake log;
- one bottom detail pane for summaries and failed-stage logs;
- a `dcc.Interval` enabled while a job runs, refreshing job state, log text, and corpus rows.

Use AG Grid's cell-click event and the clicked column id to resolve the exact stage target. Apply red
cell styling to `FAILED`; successful cells should look clickable without adding large buttons to
every row. Disable duplicate corpus launches while a job is active.

Serve/download only log paths derived from known Targets. Do not expose an arbitrary filesystem path
route.

### 6. Stage-owned summaries

Keep the existing stored-summary contract in APB:

- conversion owns the quantification component;
- annotation adds a small annotation component without recomputing quantification;
- FASTA adds a small component appropriate to the object's quantification level;
- later artifacts carry earlier components forward.

The exact additional annotation and FASTA fields are intentionally modest and extensible. Implement
only a few agreed, readable values and cover their persistence through `.h5ad` and `.h5mu`
round-trips. The studio must not inspect vendor columns or implement proteomics summary logic.

### Alternatives set aside

- **Levels declared in `corpus.yaml`:** rejected. The APB parsing-rule JSONs, input headers, and
  parsed software version determine support.
- **Separate basket tables:** rejected. They obscure the fan-out and repeat large headings.
- **One row per source dataset:** rejected. It hides MuData and standalone-level branches inside one
  ambiguous status.
- **Per-dataset or per-row Run:** rejected. This application runs the entire Snakefile and monitors
  corpus progress.
- **One exhaustive summary:** rejected. Use small cumulative, level-specific summaries and add more
  only on request.
- **Summary computation in apb_studio:** rejected. APB owns generic proteomics semantics; the studio
  renders them.

## Implementation plan

### APB

- [x] Confirm `available_targets()` is the supported public capability API and add any missing tests
      for one-modality MuData plus all JSON-supported standalone levels.
- [x] Extend the stored descriptive-summary schema with a minimal annotation component written by
      `apb annotate` and a minimal level-specific FASTA component written by `apb fasta`.
- [x] Test cumulative summary persistence: Converted < Annotated < FASTA annotated, for standalone
      peptide-derived AnnData, standalone protein AnnData, and MuData modality selection.
- [x] Add the implementation entry to `apb/CHANGES.md`.

### apb_studio capability and pipeline core

- [x] Extract the cached header/version/`available_targets()` resolution currently in `testdata.py`
      into a shared helper; update the test-data application to reuse it.
- [x] Remove hard-coded vendor capability maps and YAML-level validation from `pipeline.py`,
      `scaffold.py`, `corpus.example.yaml`, and their tests.
- [x] Extend `Target` and target lookup with branch identity; expand each dataset into MuData plus all
      supported standalone levels.
- [x] Adopt collision-free branch-qualified converted/annotated/FASTA artifact names and logs.
- [x] Update provenance storage/pruning for repeated stage names across branches.
- [x] Replace basket-row generation with branch-row/stage-cell state generation, including
      unresolved capability and missing-resource failures.
- [x] Update pipeline tests for branch order, collision-free paths, commands, stage edges, partial
      completion, static failures, failed logs, and rerun state.

### Snakemake and execution

- [x] Update the Snakefile's output routing for branch-qualified artifacts while continuing to obtain
      every command and input edge from `pipeline.expand_targets()`.
- [x] Make the corpus goal attempt every terminal branch through FASTA where resources are present;
      keep `--keep-going` so independent failures do not stop the corpus.
- [x] Reuse `execution.run_pipeline()` and `jobrunner` for one background corpus job and its live
      combined log; remove dashboard concepts for selected targets.
- [x] Test the generated Snakemake arguments, whole-corpus target set, keep-going behavior, and a
      mixed success/failure fixture DAG.

### Dashboard

- [x] Replace the stacked basket tables in `dashboard.py` with the one compact branch table and
      restrained typography.
- [x] Add the single `Run corpus` action, active-job protection, live log pane, and polling interval.
- [x] Refresh stage cells as artifacts/logs appear without losing the currently selected detail.
- [x] Route successful stage-cell clicks to APB `describe_path()` for that exact artifact.
- [x] Route failed stage-cell clicks to the exact log/error in the same detail pane and provide a
      safe log link/download.
- [x] Add backend tests for click-target resolution and refresh state; keep Dash callbacks thin.
- [x] Add the implementation entry to `apb_studio/CHANGES.md` and update README/architecture text
      that still describes basket behavior or YAML-declared levels.

### Verification

- [x] Run APB and apb_studio unit/integration tests and Ruff.
- [x] Run `snakemake -n` on a fixture corpus containing DIA-NN, Spectronaut, and a single-level
      software; verify every JSON-supported branch and stage is present.
- [ ] Manual `make app` smoke: start `Run corpus`, watch the live log and table advance, open one
      summary from each stage, and open/download one deliberate failure log.
- [ ] Confirm the compact table remains readable at the corpus's real row count and that no output
      level comes from `corpus.yaml`.

## Implementation notes

- The minimal annotation component records the annotated-run count, field names, and per-field
  group counts. FASTA records total/matched/proteotypic feature counts for peptide-derived levels,
  or total/annotated feature counts for protein. The rule remains “always rather less”; add fields
  only on request.
- Repeated `apb convert` calls trade simplicity and reuse for repeated vendor-table reads. Profile
  before considering a single-read, multi-output APB extension.
- The current local corpus resolves to 121 rows: 104 supported branches plus 17 visible unresolved
  diagnostics. Its manifest has no annotation or FASTA resources yet, so those 104 downstream
  cells correctly remain `FAILED` until the module paths are added.
- The server and Dash layout/callback endpoints respond on port 8051. The full visual/click-through
  smoke remains unchecked because no interactive browser backend was available in this session.
