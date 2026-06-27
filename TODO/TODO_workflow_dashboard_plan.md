# Plan: APB Workflow Dashboard — functionality & how it's exposed

**Date:** 2026-06-25
**Status:** Functional/architectural plan — *no implementation detail*. Supersedes and replaces
the original APB `TODO_UI.md` seed notes (now removed). Companion to the (separate, later) viewer
track in [Archive/TODO_viewer.md](../../anndata_proteomics_bridge/TODO/Archive/TODO_viewer.md).
**Scope of this doc:** *what functionality we expose, and how* — not how it is coded.

---

## 1. What this is (and isn't)

A **corpus-management dashboard** over the APB conversion pipeline. The mental model is **not**
"convert one file in a GUI." It is:

> *"I have ~90 vendor outputs across ~10 ProteoBench modules. Show me how far each one has
> progressed through the pipeline, and let me run or clean the missing/stale work — by single
> dataset, by module, or all at once."*

So the tool is primarily a **doer**: it drives conversion + annotation over the whole corpus and
shows coverage. Rich, scale-aware *visualization* of the resulting matrices (Datashader,
Perspective, Vitessce, 827k-feature views) is a **separate downstream track** — see
[Archive/TODO_viewer.md](Archive/TODO_viewer.md) — deliberately **out of scope here**. The doer
gets only a *light* "did it work?" peek (§7.4).

---

## 2. The decision spine (settled in discussion)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Doer first**, viewer later & separate | Keep this tool small enough to ship; viewer complexity stays downstream. |
| 2 | **Separate sibling repo** (not inside APB) | Clean dependency direction (pipeline → APB, never reverse); keeps APB a focused library with a minimal surface; mirrors the `annProtSum` / viewer sibling pattern; heavy deps (Snakemake, marimo) don't bloat APB. |
| 3 | **Snakemake** is the pipeline engine | Declarative DAG natively answers "N done, M to do"; idempotent re-runs; change a rule → only affected datasets rebuild. We don't hand-write the bookkeeping. |
| 4 | **Filesystem is the database** | At ~90 datasets, *a file exists ⇒ that stage is done*. No SQLite/Postgres. Optional generated `manifest`/`status.json` (or just glob) for the GUI to read fast. |
| 5 | **Stage registry = single source of truth** | One declarative list of stages; both the Snakefile and the GUI read it. New step = one registry entry (+ one rule + one CLI subcommand). No drift between pipeline and GUI. |
| 6 | **APB exposed via a thin CLI** | The CLI is the contract. Clean process boundary, command string *is* provenance, parallel-safe under Snakemake, gives APB one well-defined public surface. |
| 7 | **Hierarchical output layout, by module** | The shared contract for CLI `--output`, registry globs, GUI grid state, and clean/run scoping all at once. |
| 8 | **Config round-trips (option 3)** | UI loads the corpus config as defaults, you tweak, a run writes it back next to outputs → reproducible record that travels with the data. |
| 9 | **GUI triggers runs** (not read-only) | Run/clean by scope×stage; that's what keeps it a doer. marimo background-jobs handle live logs. |
| 10 | **Two-level coverage grid** | Module summary rows → drill-down to datasets. 90×~5 is too much flat; module is already the unit of operation. |
| 11 | **Single analyst, local (marimo)** | No server/auth; reuses the existing `make ui` marimo path. Framework decision settled: **marimo**. |
| 12 | **Bottom-up: per-level conversion is primary; MuData is an optional `assemble`** | `convert --level X` → `X.h5ad` independently, so "ions only" is cheap; `assemble-mudata` optionally combines existing levels into `mudata.h5mu`. Every output file has one clean producer. |
| 13 | **Registry & corpus config in YAML** | Snakemake-native; consistent across the new repo's config + registry. |
| 14 | **Vendor declared in config** (not auto-detected) | Explicit & reproducible; no fragile file sniffing. |
| 15 | **`annotate` is container-agnostic** | Writes `obs` on whatever it's given — a level `.h5ad` → its `obs`; a `mudata.h5mu` → the shared `obs` **once**. `obs` is identical across levels, so one implementation covers both. |

---

## 3. Repository layout (workspace)

```
anndata_bridge/
  anndata_proteomics_bridge/   APB — conversion library + thin inspector (unchanged role)
  anndata_omics_bridge/        design docs
  ProteoBench/                 module folders w/ annotation TOMLs (annotation source)
  <new repo>/                  ← THIS: Snakemake pipeline + stage registry + marimo dashboard
```

**Stays in APB:** the conversion/annotation engine (readers, converters, parsing rules) and the
existing lightweight inspector (`make ui` / `anndataview.py`) as the "did it work?" peek.

**New repo owns:** the corpus config, the stage registry, the Snakefile, the dashboard. It is a
*consumer* of APB (via CLI) and of ProteoBench TOMLs (annotation source).

*Open: repo name (candidates: `apb_pipeline`, `apb_workflow`, `anndata_proteomics_workflow`).*

---

## 4. The corpus config (round-tripped — decision 8)

One authored file (YAML) that declares the corpus. The UI loads it as defaults, you adjust via
widgets, a run writes it back next to the outputs.

Contents (functional, not final schema):
- **input_root** — folder holding the vendor outputs.
- **output_root** — where the hierarchical output tree is written.
- **module mapping** — per module: its dataset(s), vendor, the parsing-rule TOML, and the path to
  that module's **ProteoBench folder** where the annotation TOMLs live. *This directly answers the
  original [TODO_UI.md](TODO_UI.md) question:* the file that maps each mudata/anndata to the
  ProteoBench module whose TOMLs supply the `obs` annotations.

In addition, **per-artifact provenance sidecars** are written next to each output (command, rule
TOML, vendor, APB version, timestamp) — so the corpus config is the *input* and the sidecar is the
*per-result record*.

---

## 5. The pipeline stages (the registry — decision 5)

Each registry entry is declarative, roughly:

```
{ name, scope, output_pattern (glob), produced_by (CLI command template), depends_on }
   scope ∈ { dataset, module, corpus }
```

Initial stages:

| Stage | Scope | Produces | Notes |
|-------|-------|----------|-------|
| `convert` | dataset | per-level `*.h5ad` (`--level ion`; ion now, peptide/protein/… as APB grows) | independent per-level read of the vendor output's quantitative layers — the **primary** artifact |
| `assemble-mudata` | dataset | `mudata.h5mu` | **optional** — combines the existing level `*.h5ad` into a MuData with shared `obs` |
| `annotate` | dataset | `annotated/<object>` | **container-agnostic** `obs` annotation from the module's ProteoBench TOMLs: a level `.h5ad` → its `obs`; a `mudata.h5mu` → shared `obs` written **once** |
| `fasta-annotate` *(future)* | module | annotated protein `var` | one FASTA per organism/module; not built yet — example of the extension path |

Adding `fasta-annotate` later = **one registry entry + one Snakemake rule + one CLI subcommand**;
the GUI grows a column and a picker option with **zero imperative GUI code**. The `scope` field
also drives grid aggregation (convert is per-dataset; fasta-annotate is per-module).

---

## 6. The APB CLI (the contract — decision 6)

Principles:
- **One subcommand per stage** (`apb convert --level <L>`, `apb assemble-mudata`, `apb annotate`,
  later `apb annotate-fasta`). Resist growing past the stages — "keep interfaces minimal."
- **Pure function of its args**: explicit `--input`, `--output`, `--rule <toml>`; no hidden state.
  Snakemake supplies every path → idempotent and parallel-safe.
- **Writes the provenance sidecar** on every invocation (§4).
- **Predictable exit codes + logs to stdout/stderr** → Snakemake failure handling and GUI log
  streaming both just work.

The registry's `produced_by` is a **command template**
(`apb convert --input {input} --rule {params.rule} --output {output}`) — one template consumed by
three things: the Snakefile `shell:` block, the provenance log, and the GUI's "what will this
button run" preview.

---

## 7. The output layout & GUI — *how* it's exposed

### 7.1 Hierarchical output tree (decision 7)

```
<output_root>/
  <module>/
    <dataset>/
      ion.h5ad              convert          (scope: dataset, per-level — primary)
      protein.h5ad          convert
      mudata.h5mu           assemble-mudata  (scope: dataset, optional)
      annotated/…           annotate         (obs; a level .h5ad or the mudata)
      provenance/…           per-artifact sidecars
    <module>.fasta           fasta input (scope: module)
```

- **GUI state** = one `glob` per registry `output_pattern`.
- **clean module** = delete `<module>/` subtree; **clean stage** = glob that stage's pattern;
  **rerun annotation** = clean that stage's files then run (or `--forcerun`).

### 7.2 The actions matrix (decision 9)

All triggers are **scope × stage × verb**, not bespoke buttons:
- scope: all · module · dataset
- stage: all · convert · assemble-mudata · annotate · (later) fasta-annotate
- verb: **Run** · **Clean**

"Clean module", "clean all", "run module", "rerun annotation" are all cells of this matrix → it
absorbs new stages automatically.

### 7.3 Dashboard zones

1. **Coverage grid (two-level — decision 10):** ~10 **module rows** with per-stage progress
   (e.g. `convert 9/9 · annotate 3/9`), expandable to the dataset rows beneath.
2. **Controls:** the scope×stage×{Run, Clean} matrix, **with a dry-run preview**. Snakemake `-n`
   shows "this will rebuild these 12 / delete these files" *before* committing — turning
   destructive actions (esp. "clean all") into confirmable ones.
3. **Run feedback:** live log stream + per-target status while Snakemake runs, without freezing the
   UI (marimo background-job pattern).

### 7.4 Light bridge to the viewer

Clicking a grid cell shows that artifact's **provenance sidecar** + last log, and a **"peek"**
button that opens the existing APB thin inspector. That is the *only* viewer-ish feature the doer
needs; everything heavier belongs to the separate viewer track.

---

## 8. Extensibility summary

Adding a pipeline capability is always the same three localized edits, never a GUI rewrite:
1. **registry entry** (name, scope, output_pattern, command template, depends_on)
2. **Snakemake rule** producing that output
3. **APB CLI subcommand** implementing the step

The GUI re-derives its grid columns and its scope/stage pickers from the registry.

---

## 9. Open questions (decide before / during build)

- **Corpus config schema specifics:** exact YAML shape, and how the module↔dataset↔annotation-TOML
  mapping is expressed. *(Vendor is declared here — decision 14.)*
- **Registry file location** within the new repo (format settled: YAML — decision 13).
- **Convert granularity:** one `apb convert --level X` call per level (clean per-level rerun, but
  re-reads the vendor report each time) vs. one pass emitting several levels at once (avoids
  re-reads, coarser rerun). Minor; affects only the `convert` rule, not the model.
- **Repo name** (§3).

---

## 10. Suggested capability phasing (not implementation order)

1. **Skeleton contract:** define the registry + hierarchical layout + the `apb convert --level` CLI;
   get one module's ions converting end-to-end from the corpus config (filesystem-as-DB working).
   `assemble-mudata` comes in a later phase.
2. **Read-only dashboard:** two-level coverage grid reading state by glob. No triggers yet.
3. **Triggers + dry-run preview + live logs:** the scope×stage×{Run, Clean} matrix.
4. **`annotate` stage** wired through registry → CLI → grid column.
5. **Provenance sidecars + config round-trip** polished.
6. **Extension proof:** add `fasta-annotate` as a module-scope stage to validate the
   "one entry + one rule + one subcommand" path.
```
