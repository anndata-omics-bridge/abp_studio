# testdata-app: Convert action + "AnnData" browsing tab

> Let the test-data explorer convert a downloaded ProteoBench fixture with APB and browse the
> produced MuData / AnnData containers, with per-level tables and a **generic, tool-independent**
> descriptive summary.

This is a **plan only** — no code yet. Some decisions are deliberately deferred to
implementation-time observation (see **Open questions**); the design is factored so those can be
settled without rework.

---

## Requirements

**User story.** *"I've downloaded a ProteoBench fixture. Now let me convert it with APB — to a
single level (e.g. ion) or to a multi-level MuData — and then browse what came out: a MuData table,
and per-level tables (ion / peptidoform / peptide / protein), where selecting a row shows a summary
that tells me whether the conversion looks right."*

**Scope**
- **In:** the *testdata-app* only ([src/apb_studio/testdata_app.py](../src/apb_studio/testdata_app.py)) —
  a **Convert** action on the selected fixture, and a new **AnnData** tab that lists produced
  containers with a summary pane.
- **Out:** the corpus app. [dashboard.py](../src/apb_studio/dashboard.py) already batch-converts the
  whole corpus via Snakemake; this is its interactive, single-fixture counterpart. We do not touch
  the corpus pipeline, registry, or Snakefile.
- **Out:** benchmark scoring (see the boundary below). Convert scope is a **single selected
  fixture**; batch stays in the corpus app.

**The summary is descriptive, NOT benchmark scores.** Two different things — this tab is only the
first:

| | **Descriptive summary** (this tab) | **Benchmark scores** (a future APB tool) |
|---|---|---|
| Needs | only the container itself | species ground-truth (HYE/PYE), replicate design |
| Examples | n_runs, n_features; **missingness histogram**; **per-layer intensity range**; proteotypic-feature count *when FASTA validation is present* | `median_abs_epsilon`, per-species bias, `CV_median`, `roc_auc` — the `results` block of a ProteoBench submission JSON |
| Ground truth | none | required |

The scores live in the ProteoBench submission JSON (`results` block, already shown in the existing
detail tab) and are the future tool's job. This tab **never computes** them; if a container ever
carries them, it may display them.

**The summary must be generic — tool-independent.** APB computes it only from its standardized
representation: missingness and intensity from the **layers**; level and software from
`uns['anndata_proteomics']`; the parsed software version via APB's existing
`read_search_parameters()` API; and the proteotypic count from the standardized FASTA-validation
result in `varm['fasta_validation']`. **No vendor-specific columns, no per-`software_name`
branching.** APB persists the resulting, versioned descriptive summary under
`uns['anndata_proteomics']`; apb_studio only reads and renders it.

**Level- and stage-dependent.** What is meaningful depends on the level (proteotypic features only
for peptide-derived levels) and on how far the fixture has progressed. Conversion computes and
stores the immutable quantification component (shape, missingness, intensity); FASTA validation
later computes and merges the FASTA component. A feature is called proteotypic here when its stored
`fasta_matching_protein_count == 1`. The summary is **show-what's-present**: render a component when
its producing stage has written it, omit it otherwise — never error on a missing stage.

**Acceptance ("done")**
- Convert a downloaded fixture to a chosen level or to all available levels from the Actions tab.
  The caller supplies an extensionless output basename; APB chooses `.h5ad` or `.h5mu` from the
  object it actually produced.
- The AnnData tab lists every produced container across a MuData table + per-level tables (see
  Design), with a `mudata` column marking level rows that live inside a `.h5mu`.
- Selecting a row shows a generic descriptive summary; missingness histogram and per-layer intensity
  range are correct against a known fixture.
- `pytest` + `ruff` green in both repos; a `CHANGES.md` entry logged for the work.

## Design

### Convert action (Actions tab)

A second command row under the existing one in `action_panel()`:

```
[ Convert selected → ]  ( ⦿ All levels  ○ ion  ○ fragment  ○ peptidoform  ○ peptide  ○ protein )  [ Convert ]
```

- Operates on the **currently selected** catalog/selection row (its downloaded `input_file.*`),
  using its `param_0.*` params file. `--software` is normally omitted (APB auto-detects the vendor
  from columns); kept as a fallback that logs a clear retry message rather than guessing.
- `--output` accepts an **extensionless basename only**; passing `.h5ad` or `.h5mu` is rejected.
  APB appends `.h5mu` when conversion actually yields MuData and `.h5ad` when it yields AnnData.
- `All levels` → `apb convert <input> --params <param_0> --output <dir>/mudata`. A multi-level
  result becomes `mudata.h5mu`; a source with one convertible level becomes `mudata.h5ad`.
- A specific level →
  `apb convert <input> <level> --params <param_0> --output <dir>/<level>`, producing
  `<level>.h5ad`.
- Runs as a background job (reuse [jobrunner.py](../src/apb_studio/jobrunner.py)); log streamed to
  the existing job-log pane. On success, auto-switch to the AnnData tab (mirror `show_completed_job`).
- Re-convert overwrites the existing artifact (idempotent, matches Snakemake semantics). If the
  same basename previously resolved to the other container type, APB removes that stale sibling
  only after the replacement has been written successfully.

### AnnData tab — per-level cross-section + summary pane

Inner `dcc.Tabs`. Each level-bearing object is a **row**; one `.h5mu` therefore appears in the
MuData table **and** in one per-level table per modality it contains:

| Subtab | Rows | Notes |
|---|---|---|
| **MuData** | one per `*.h5mu` | dataset, module, software/version, n_obs, modalities, path |
| **Ion / Fragment / Peptidoform / Peptide / Protein** | one per level-bearing object | a standalone `<level>.h5ad` **or** the matching modality of a `.h5mu` |

- **`mudata` boolean column** in every per-level table: `false` = standalone `<level>.h5ad`;
  `true` = this level is a modality inside a `.h5mu` (the level is "hidden" in a container).
- Example: a `MuData{protein, peptide}` yields **3 rows** — one in MuData, one in Peptide
  (`mudata=true`), one in Protein (`mudata=true`). A standalone `ion.h5ad` yields **1 row** in Ion
  (`mudata=false`).
- Every row carries a stable summary target: `(path, modality=None)` for a standalone AnnData or
  whole-MuData row, and `(path, modality=<name>)` for a level row expanded from MuData.
- Each subtab is the same single-row-select `dag.AgGrid` already used for the catalog (reuse
  `data_table(...)` with per-tab columns). Selecting any row → the summary pane below.

### The summary contract — stage-owned components persisted in `uns`

The metric computation is **generic** and lives in **APB**; **apb_studio only renders**. The stored
payload is versioned and JSON-serializable under
`uns['anndata_proteomics']['descriptive_summary']` (use a JSON string if needed for reliable HDF5
round-tripping).

- **Convert stage:** compute the quantification component once from the final layers: n_runs,
  n_features, missingness histogram (# features present in exactly 0,1,2,…,n_obs runs, per layer),
  per-layer intensity range (min / median / max), level, and software/version. “Present” and the
  intensity range both use finite values; non-finite cells are treated as missing. Store the
  component on each AnnData modality; MuData also stores its container-level shape and modality
  index.
- **Annotate stage:** these fields do not change, so carry the stored summary through unchanged.
- **FASTA stage:** derive and merge the FASTA component from
  `varm['fasta_validation']['fasta_matching_protein_count']`, including the count equal to one.
  Do not recompute missingness or intensity.
- **APB read API:** `describe(obj) -> dict` assembles the stored components for an in-memory AnnData
  or MuData. `describe_path(path, modality=None)` reads the whole container or the named MuData
  modality. For an older APB container lacking the quantification component, it may compute that
  component from the layers as a compatibility fallback; normal newly converted files do not pay
  this cost. `apb summary <path> [--modality NAME] [--json]` is the thin CLI wrapper.
- **apb_studio:** calls `describe_path(path, modality)` and renders the returned dict. No proteomics
  logic lives in the studio. Selecting the MuData row returns the container plus keyed modality
  summaries; selecting a level row returns only that modality's summary.

**Proteotypic is display-only here.** The FASTA stage already uses Prozor to produce the standardized
match counts. The summary only counts features whose stored match count is one; it never performs
peptide↔protein inference itself.

### Cheap reads and cache invalidation

Normal files already carry their stage-produced summaries, so browsing does not read quantification
matrices:

- **Row tables** (all containers): cheap **backed** metadata only — n_obs, n_var, level, layer
  names, software/version, modalities. Memoized by `(path, mtime)`.
- **Summary pane** (one selected target): read the stored summary from `uns`, memoized by
  `(path, mtime, modality)`. Only the legacy-container fallback reads matrices.

Summary ownership prevents stale mixed-stage data: conversion owns the quantification component;
FASTA owns the FASTA component. Any future stage that changes layers must refresh the
quantification component before writing its output. The container file remains the single unit of
truth and cache invalidation; there is no independent sidecar lifecycle.

### Alternatives considered
- **`*.summary.json` sidecars written at convert time** — rejected: they have an independent
  lifecycle and can drift from the container. Stage-owned components inside the same container are
  updated in the same write as the data they describe.
- **Summarize by reading vendor columns** — rejected: violates tool-independence. Use APB layers,
  standardized metadata, and standardized FASTA-validation results only.
- **Compute metrics in apb_studio** — rejected: proteomics logic belongs in APB (reuse rule); the
  future scores tool must share the descriptive layer.

## Implementation plan

**APB ([apb/](../../apb/))**
- [x] `readers/summary.py` (or similar): versioned summary schema; quantification- and FASTA-component
      producers; `describe(obj) -> dict`; and `describe_path(path, modality=None)`. The normal read
      path uses backed metadata + stored `uns`; only legacy fallback loads matrices.
- [x] Wire quantification-summary storage into AnnData conversion and MuData assembly; wire the FASTA
      component update into the FASTA stage after validation. Annotate preserves both unchanged.
- [x] `scripts/cli.py`:
      - make `convert --output` an extensionless basename and choose `.h5ad` / `.h5mu` after the
        result type is known;
      - add `@app.command summary(path, *, modality=None, json=False)` as a thin wrapper around
        `describe_path`.
- [x] Tests: `describe` shape + values for a `.h5ad` and a `.h5mu` fixture; missingness histogram
      and intensity range against known data; quantification component survives `annotate`
      unchanged; FASTA adds the proteotypic count without recomputing quantification; modality
      selection; extensionless output naming; HDF5 round-trip; tool-independence (same output shape
      across two vendors).
- [x] **Timing benchmark**: on the cached 20,426-row DIA-NN ion fixture, median conversion time over
      five alternating runs was 0.0706 s without summary storage and 0.0728 s with it: +0.0022 s
      (+3.1%).

**apb_studio ([src/apb_studio/](../src/apb_studio/))**
- [x] `testdata.py`:
      - `convert_command(paths, row, level)` → the `apb convert …` command with an extensionless
        output basename (no sidecar step).
      - extend `launch(...)` / add `launch_convert` for the `convert` action + `level`.
      - `converted_dir(paths, row)` → products live beside inputs (`json_dir/<repo>/<hash>/`).
      - `container_rows(paths)` → glob `*.h5mu` / `*.h5ad`, build the MuData table and the
        per-level cross-section (with the `mudata` column) via the `(path, mtime)`-memoized cheap
        read. Level rows from a `.h5mu` are expanded per modality and retain that modality in their
        summary target.
      - `container_summary(path, modality=None)` → call APB's `describe_path` with the full target,
        memoized by `(path, mtime, modality)`, and format it for the pane.
- [x] `testdata_app.py`:
      - `action_panel()`: add the Convert row (level `RadioItems` + Convert button).
      - `anndata_panel()`: inner `dcc.Tabs` (MuData + 5 level subtabs, one `data_table` each) + a
        summary `html.Pre`; register in `create_app()`'s `dcc.Tabs`.
      - callbacks: (a) Convert → `run_action` gains a `convert` branch; (b) `refresh` fills the
        subtab tables from `container_rows` (cheap/memoized); (c) subtab row-select →
        `container_summary(path, modality)` for that exact standalone/container/modality target;
        (d) `show_completed_job` also switches to AnnData after a successful convert.
- [x] Tests: extend `test_testdata.py` — `convert_command` shape, `container_rows` cross-section +
      `mudata` column, memo re-read on mtime change, `container_summary` formatting. Dash callbacks
      stay thin; logic tested in `testdata.py`.

**Corpus-pipeline compatibility**
- [x] Keep Snakemake's declared `.h5ad` / `.h5mu` targets unchanged while rendering only the
      extensionless basename into the root `apb convert --output` command.

**Both repos**
- [x] Add / maintain a **`CHANGES.md`** in each repo touched (`apb` and `apb_studio`): every
      implementation change logs a dated one-line entry. Standing rule for this work, not a one-off.

**Untouched:** `dashboard.py`, `Snakefile`, `config/registry.yaml`.

## Verification
- `pytest` green in `apb` and `apb_studio`; `ruff` clean.
- `apb summary` smoke on one real `.h5mu` and one `.h5ad`; confirm tool-independence, modality
  selection, unchanged quantification after `annotate`, and the added proteotypic count after FASTA.
- Manual `make testdata-app`: download a fixture → Convert (a level, then all levels) → APB chooses
  each output extension → AnnData tab lists it (level row `mudata=false`; MuData contributes rows
  with `mudata=true`) → selecting a MuData modality shows that modality's summary → `clean` removes
  the containers.

## Open questions
- **Convert scope** — single selected fixture for now; batch left to the corpus app. Revisit only if
  browsing many fixtures makes single-convert tedious.
- **annotate / fasta actions in the testdata-app** — not in this cut. Adding them later is what makes
  proteotypic counts appear for containers processed entirely through this app; the
  show-what's-present design already accommodates containers processed elsewhere.
- **`CHANGES.md` placement** — one per repo (assumed) vs. a single workspace-level log. Assumed
  per-repo; adjust if you prefer one.
