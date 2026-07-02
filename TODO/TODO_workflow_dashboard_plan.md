# Plan: apb_studio — corpus dashboard + Snakemake pipeline over the `apb` CLI

**Date:** 2026-06-25 · **Revised:** 2026-06-30 (GUI reworked to **kanban baskets** — decision 10
rewritten, §8 replaces the old two-level grid + scope×stage matrix; earlier 2026-06-29 revision
aligned the plan to the real `apb` CLI, made the registry executable, and gave the phases acceptance
criteria).
**Status:** Buildable plan. §2 is the locked rationale; §5–§6 are the contract; **§7 is the
registry-driven core that must be built first**; §8 is the GUI (kanban baskets); §11 is the phased
build with acceptance tests; §13 records how the linear kanban extends to optional / branching stages.
**Companion:** the (separate, later) matrix-visualization track,
[Archive/TODO_viewer.md](../../anndata_proteomics_bridge/TODO/Archive/TODO_viewer.md).

---

## 1. What this is (and isn't)

A **corpus-management dashboard** over the `apb` conversion pipeline. The mental model is **not**
"convert one file in a GUI" (that tool was deliberately removed). It is:

> *"I have ~90 vendor outputs across ~10 ProteoBench modules. Show me how far each one has
> progressed through the pipeline, and let me run or clean the missing/stale work — by single
> dataset, by module, or all at once."*

So it is primarily a **doer**: it drives `apb convert` (+ annotate/fasta) over the whole corpus and
shows coverage. Scale-aware *visualization* of the resulting matrices (Datashader, Perspective,
Vitessce, 800k-feature views) is a **separate downstream track** — out of scope here. The doer gets
only a *light* "did it work?" peek (§8.4).

---

## 2. Decision spine (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Doer first**, viewer later & separate | Keep it shippable; viewer complexity stays downstream. |
| 2 | **Separate sibling repo** | Dependency direction is `apb_studio → apb`, never reverse; keeps apb a focused library; heavy deps (Snakemake, marimo) don't bloat apb. |
| 3 | **Snakemake** is the engine | A declarative DAG natively answers "N done, M to do", reruns idempotently, and rebuilds only what a changed rule touches. We don't hand-write bookkeeping. |
| 4 | **Filesystem is the database** | At ~90 datasets, *a declared output exists ⇒ that stage is done*. No SQLite/Postgres; coverage is a glob. |
| 5 | **Registry is the single source of truth — *as code*** | One declarative stage list (`config/registry.yaml`) is loaded by **one Python module** (`pipeline.py`, §7) that renders every command and output path. The Snakefile and the dashboard both call that module — neither restates stage knowledge. Drift is structurally impossible, not merely discouraged. |
| 6 | **apb exposed via its CLI** | The CLI is the contract: clean process boundary, parallel-safe under Snakemake, one well-defined public surface. There is **one conversion command** (`apb convert`). |
| 7 | **Hierarchical output layout, by module** | `output_root/<module>/<dataset>/<artifact>` is the one shared contract for `--output`, registry globs, grid state, and clean/run scoping. |
| 8 | **Corpus config is authored input** | A hand-authored YAML declares the corpus; the dashboard reads it. *Write-back / round-trip is a later, optional convenience (§11 phase 6), kept off the critical path because round-tripping YAML through a GUI loses comments and churns order.* |
| 9 | **GUI triggers runs** (not read-only) | Run/clean from the baskets (§8) is what makes it a doer; marimo background-jobs stream live logs. |
| 10 | **Kanban baskets — a dataset lives in exactly ONE basket (its furthest *contiguous* completed stage)** | The pipeline is a flow: `inputs → converted → sample annotated → fasta annotated` (these four spaced strings are the canonical basket labels). Each dataset sits in the **one** basket for the furthest stage whose whole prefix is done, and *advances* to the next basket when run. The **basket is the verb** — no stage dropdown: Run on **inputs** = convert, on **converted** = annotate, on **sample annotated** = fasta. A dataset with no next-stage Target is **terminal** (shown done, not runnable). Selection inside a basket is one-by-one *or* by `module`/`software` filter + "select all shown". This **replaces** the old two-level grid and the scope×stage×verb matrix (§8). |
| 11 | **Single analyst, local (marimo)** | No server/auth; `make ui`. |
| 12 | **One `convert` → the multi-level MuData, single read** | `apb convert <data>` reads the file once and emits `mudata.h5mu` (every level a modality on a shared run axis). `--level X` is the cheap single-`.h5ad` opt-in. **No `assemble-mudata`** — nothing re-reads per level. |
| 13 | **Registry & corpus config in YAML** | Snakemake-native; consistent across the repo. |
| 14 | **A module is the benchmark; `vendor`/`level` are PER DATASET** | A module is a ProteoBench benchmark (the shared raw runs); its datasets are different tools' outputs of those runs, so `vendor` (declared, not sniffed at run time) and `level` live on each **dataset**. `annotation`/`fasta` are module-level (shared runs). `make scaffold` bootstraps the declaration by scanning a data tree. |
| 15 | **`annotate` / `fasta` are container-agnostic** | They enrich whatever object they're given: `obs` (annotate) or protein `var` (fasta), on a level `.h5ad` or the `.h5mu` alike — one implementation each. |
| 16 | **`convert` artifact is deterministic from config: declare `level` unless the vendor is multi-level** | apb's `convert` has **three** outcomes, not two: multi-level vendor + no `--level` → `mudata.h5mu`; any vendor + `--level X` → `<level>.h5ad`; **single-level vendor + no `--level` → a fallback `.h5ad`** (apb writes a plain AnnData, [cli.py](../../apb/src/anndata_proteomics/scripts/cli.py) `len(levels)==1`). To stay deterministic, a **dataset** **omits `level` only for the multi-level vendors (DIA-NN, Spectronaut); every single-level vendor (MaxQuant, FragPipe, PEAKS, WOMBAT) MUST declare its `level`** → the studio passes `--level` and the artifact is exactly `<level>.h5ad`. `validate_dataset` checks this and errors early. apb writes to `--output` **verbatim** (no suffix↔content check), so the studio always sets the output extension to match what convert will write (`.h5mu` only when no level). |
| 17 | **apb_studio owns provenance — written by the Snakefile** | apb stores parsed *search parameters* in the result's `uns` but writes **no sidecar**. Each Snakemake rule appends `python -m apb_studio.provenance` to its shell, dropping a `provenance.json` next to every artifact (keyed by stage: the rendered command — which carries `--software`/`--params` — the inputs, the apb version `apb --version` e.g. `0.1.0`, and a timestamp). Writing it in the engine that produces the artifact means **CLI and dashboard runs both get sidecars**; `clean` prunes the cleaned stage's entry. |

---

## 3. Repository layout (workspace)

```
anndata_bridge/
  anndata_proteomics_bridge/   apb — conversion library + `apb` CLI (no GUI)
  anndata_omics_bridge/        design docs
  ProteoBench/                 module folders w/ annotation TOMLs (annotation source)
  apb_studio/                  ← THIS: Snakemake pipeline + stage registry + marimo dashboard
```

**Stays in apb:** the conversion/annotation engine (readers, converters, parsing rules), exposed
through the `apb` CLI. apb ships no GUI/inspector, so the §8.4 peek is built here.

**apb_studio owns:** the corpus config, the stage registry, the registry-driven core (§7), the
Snakefile, the dashboard, and the provenance sidecar. It is a *consumer* of apb (via CLI) and of
ProteoBench TOMLs (annotation source).

---

## 4. The corpus config (authored — decision 8)

`config/corpus.yaml` (copy of `corpus.example.yaml`, or `make scaffold DATA=<root>`).
**Concrete schema (locked):**

```yaml
input_root:  /path/to/vendor_outputs      # root for every dataset `input` / `params`
output_root: /path/to/apb_outputs          # root of the hierarchical output tree (§7.1)

modules:
  <module_name>:                           # a ProteoBench benchmark (shared raw runs)
    annotation: /abs/or/rel/annotation.toml  # OPTIONAL, module-level — the TOML apb annotate joins onto obs
    fasta:      /abs/or/rel/proteome.fasta    # OPTIONAL, module-level — enables the `fasta` stage
    datasets:                              # the different tools' outputs of the SAME runs
      - name:   diann-run1                 # dataset id → output dir segment (unique within module)
        vendor: diann                      # → apb convert --software <vendor>  (PER DATASET)
        level:  ion                        # REQUIRED for single-level vendors (maxquant/fragpipe/peaks/
                                           #   wombat) → <level>.h5ad; OMIT for multi-level (diann/
                                           #   spectronaut) → mudata.h5mu (decision 16)
        input:  rel/to/input_root/report.tsv      # the vendor file
        params: rel/to/input_root/report.log.txt  # parameter file → apb convert --params (gives version)
```

Rules: each **dataset** needs `vendor` + `name`/`input`/`params`; `level` is **required for
single-level vendors, omitted for multi-level** — decision 16; `validate_dataset` checks both that
it is present where required *and* that its value is one of `ion/fragment/peptidoform/peptide/
protein`, so a misdeclared dataset fails fast. `annotation` and `fasta` are **optional and
module-level** (the runs — hence the obs annotation — are shared across a module's datasets);
annotate/fasta are emitted only for modules that declare them. **Relative `input`/`params`/
`annotation`/`fasta` resolve against `input_root`; absolute paths are used as-is.**

---

## 5. The pipeline stages (the registry — decision 5)

`config/registry.yaml` — ordered list; each entry maps to **one real `apb` subcommand**:

| Stage | Scope | Produces | `apb` command template (plain `{placeholder}` substitution) | Depends |
|-------|-------|----------|-------------------------------------------------------------|---------|
| `convert` | dataset | `mudata.h5mu` *or* `<level>.h5ad` (decision 16) | `apb convert {input} --software {vendor} --params {params} --output {output}` | — |
| `annotate` | dataset | `annotated{suffix}` | `apb annotate {input} {annotation} --output {output}` | `convert` |
| `fasta` *(optional)* | dataset | `annotated_fasta{suffix}` | `apb fasta {input} {fasta} --output {output}` | `annotate` |

`{suffix}` is `.h5mu` or `.h5ad`, matching the convert artifact (annotate/fasta are
container-agnostic, decision 15). **`--level` is deliberately NOT in the template**: `expand_targets`
appends `--level {level}` to the convert argv exactly when the **dataset** declares a `level`
(decisions 14/16 — `level` is per-dataset; no bracket mini-grammar — see §7.2). Always passing an
explicit `--output` overrides apb's default `<stem>.annotated<suffix>` naming, which is why
annotate/fasta land on `annotated{suffix}` rather than `mudata.annotated.h5mu`. Optional stages are
excluded from the default `all` target and only offered for modules that supply their prerequisite
(`fasta` ⇒ the module has a `fasta:` — that gate is genuinely module-level). Optional stages today sit
at the *end* of the chain; §13 generalizes to optional *intermediate* stages (e.g. `proteobench`).

Adding a stage = **one registry entry + one Snakemake rule + one `apb` subcommand**. The grid grows
a column and the picker an option with **zero imperative GUI code** (both are derived in §7).

---

## 6. The apb CLI (the contract — decision 6)

- **One subcommand per stage** — `apb convert`, `apb annotate`, `apb fasta`. There is exactly one
  conversion command; resist growing past the stages ("keep interfaces minimal").
- **Pure function of its args**: positional `<data>` + explicit `--output`, plus the per-stage flags
  above. No hidden state ⇒ idempotent and parallel-safe under Snakemake.
- **Predictable exit codes + stdout/stderr logging** ⇒ Snakemake failure handling and live log
  streaming both work unchanged.
- apb writes parsed search parameters into the result's `uns`; it writes **no** provenance sidecar.
  The Snakefile writes `provenance.json` per rule via `python -m apb_studio.provenance` (decision 17).

The command **templates live only in the registry** and are rendered only by `pipeline.render_command`
(§7) — never duplicated in the Snakefile or dashboard. Two apb behaviors the studio must respect:
`apb convert` chooses MuData-vs-AnnData by **counting resolved levels** (not by the `--output`
suffix) and writes to `--output` **verbatim**, so the studio sets the suffix itself (decision 16);
and `level` is a positional also exposed as `--level` (cyclopts), which `expand_targets` appends
only when declared.

---

## 7. The registry-driven core — `src/apb_studio/pipeline.py` (BUILD FIRST)

This is the module that turns decision 5 from a slogan into a fact. **It is the single place that
knows how to turn (registry + corpus) into concrete paths and commands.** The Snakefile and the
dashboard are thin callers.

### 7.1 Hierarchical output tree (decision 7)

```
<output_root>/<module>/<dataset>/
  mudata.h5mu | <level>.h5ad       convert    — the single convert artifact (decision 16)
  annotated{.h5mu|.h5ad}           annotate   — obs joined on ({suffix} tracks the convert artifact)
  annotated_fasta{.h5mu|.h5ad}     fasta      — protein var (optional)
  provenance.json                  one record per artifact (decision 17), keyed by stage
```

### 7.2 Data model + public API

```python
@dataclass(frozen=True)
class Target:
    module: str
    dataset: str
    stage: str            # registry stage name
    output: Path          # absolute, under output_root
    command: list[str]    # fully rendered argv (ready for Snakemake shell / preview)
    inputs: list[Path]    # upstream artifacts this target consumes (for the DAG)
    vendor: str           # the dataset's software (decision 14) — carried so baskets() can column it
    level: str | None     # the dataset's level (single-level vendor) or None (multi-level)
    #  ↑ vendor/level were NOT on Target pre-rework (they survived only as argv tokens inside
    #    `command`); phase 8 adds them, populated by expand_targets from ds["vendor"]/ds.get("level").

def load_registry(path=...) -> list[dict]            # (exists in registry.py)
def load_corpus(path) -> dict                        # (exists in registry.py)

def convert_artifact(dataset_cfg) -> str
    # "mudata.h5mu" if the DATASET omits `level` else f"{dataset_cfg['level']}.h5ad" (decision 16).
    # PRECONDITION: a DATASET omits `level` ONLY for a multi-level vendor (diann/spectronaut); a
    # single-level vendor without `level` raises (else apb's .h5ad fallback lands under a .h5mu name).

def validate_dataset(module, dataset_cfg) -> None
    # decision 16: dataset has `vendor`; `level` present for single-level vendors and ∈ LEVELS.

def render_command(template: str, ctx: dict) -> list[str]
    # PLAIN {placeholder} substitution only: fill {input}/{output}/{vendor}/{params}/{annotation}/
    # {fasta}; raise on any unfilled {placeholder}; return an argv LIST (no shell quoting). There is
    # no optional-group grammar — the registry templates carry no brackets.

def expand_targets(registry, corpus, output_root=None, input_root=None) -> list[Target]
    # (module × dataset × applicable stage). For each Target: resolve the output path (convert →
    # convert_artifact; annotate/fasta → annotated{suffix}/annotated_fasta{suffix} where {suffix}
    # tracks that DATASET's convert artifact), render the command, and — for convert when the DATASET
    # declares a `level` — APPEND `--level <level>`. Carry the dataset's vendor/level onto each Target.
    # Wire input edges (annotate ⇐ convert; fasta ⇐ annotate). Validate decision 16; emit annotate only
    # when the module declares `annotation:`, fasta only when it ALSO declares `fasta:`.

def coverage(targets: list[Target]) -> list[dict]
    # one row per Target: {module, dataset, stage, artifact, done: output.exists()}

def baskets(targets: list[Target]) -> dict[str, list[dict]]
    # group DATASETS into the kanban baskets (decision 10). A dataset's basket is the furthest stage
    # whose WHOLE prefix is done — a CONTIGUOUS prefix, NOT merely the max done stage — in registry
    # order: none→"inputs", convert→"converted", annotate→"sample annotated", fasta→"fasta annotated".
    # So a non-contiguous state (annotate present but convert missing — reachable via a partial run or
    # a manual delete) reports the LOWER basket (needs rebuild), never a basket whose defining artifact
    # is absent. Each row: {module, dataset, software(=t.vendor), level(=t.level), basket,
    # next_stage|None, runnable, problem}. `problem` is a per-dataset issue string (from `problems()`,
    # below) surfaced as a table column: missing input/params/annotation/fasta, or an apb param-parse
    # warning captured post-convert. next_stage/runnable are PER-DATASET, from THIS dataset's Target set —
    # NOT global registry order: next_stage = the stage of the first not-yet-done Target for the
    # dataset, else None; runnable = next_stage is not None. (One rule covers every terminal case: a
    # convert-only module — no annotation: — is terminal in "converted"; a module with annotation: but
    # no fasta: is terminal in "sample annotated".) Membership is computed ONLY from per-Target output
    # paths — never a filename glob — so the per-dataset convert basename (mudata.h5mu vs <level>.h5ad)
    # and the shared annotated{suffix} names are unambiguous. Caveat: `done` is existence-only
    # (decision 4) and does NOT detect staleness — a changed input under an existing downstream artifact
    # still reads done; freshness is left to Snakemake's own `-n` (§12).

def problems(corpus, targets) -> dict[(module, dataset), list[str]]
    # NEW: per-dataset issues for the basket `problem` column. Three sources: (1) STATIC — declared
    # files that don't exist (a dataset's input/params, a module's annotation:/fasta:); (2) RUNTIME
    # WARNINGS apb recorded while still producing an artifact (e.g. an unparsable params file →
    # provenance.read_params_warning lifts uns['anndata_proteomics']['search_parameters_error'] into
    # provenance.json); (3) RUNTIME FAILURES — a stage whose artifact is MISSING but whose per-rule log
    # (`<artifact>.log`, tee'd by the Snakefile) exists was attempted and failed, so the apb error line
    # (e.g. "no rule covers version 23.0") is surfaced. A stage never attempted has no log → just
    # pending. (apb degrades param-parse failures rather than crashing — root cause fixed in apb.)

# --- selection (the GUI and the Snakefile share the core; the basket GUI adds a row-set selector) ---
def select_targets(targets, *, scope="all", module=None, dataset=None, stage="all") -> list[Target]
    # the scope×stage selector the Snakefile / clean_paths use (scope ∈ all | module | one dataset).
def targets_for(targets, keys: set[tuple[str,str]], *, stage) -> list[Target]
    # NEW (phase 8): the Targets at `stage` for the selected (module, dataset) ROWS — the arbitrary
    # multi-row basket selection that scope×stage cannot express. Run feeds these .output paths to
    # run_pipeline(targets=...); Clean feeds them (over the cascade stage set) to clean_targets.

def descendants(registry, stage) -> set[str]
    # NEW (phase 8): stages that transitively DEPEND ON `stage` — the downstream a Clean must cascade.

def reject_input_paths(paths, input_root) -> list[Path]     # raises CleanGuardError, NOT assert
    # The single-source Clean guard: no path may be under input_root (resolve()s both sides, catching
    # relative/symlink escapes). A REAL exception — `assert` is stripped by `python -O`, and a guard on
    # a destructive action must never be optimized away. Shared by clean_paths + execution.clean_targets.

def clean_paths(targets, *, input_root, scope="all", module=None, dataset=None, stage="all") -> list[Path]
    # the exact output files a scope×stage Clean would delete — NEVER an input_root path (via
    # reject_input_paths). Basket Clean CASCADES: it deletes the basket's stage AND all `descendants`
    # for the selected datasets, so a Clean leaves a contiguous prefix from ANY prior on-disk state —
    # including a holey tree (a stray annotated_fasta.* whose annotated.* is missing), which cleaning
    # only the one artifact would orphan. The GUI routes Clean through
    # targets_for(selected-rows, stage∈{basket stage}∪descendants) → execution.clean_targets, never a
    # bare stage-name match across baskets.
```

### 7.3 The three thin callers (no stage knowledge of their own)

- **`workflow/Snakefile`** — `rule all` = `[t.output for t in expand_targets(...) if t.stage in
  default_stages]` (the concrete per-dataset artifacts, each with its real `.h5mu`/`.h5ad` suffix).
  Because the convert artifact's basename varies per module (`mudata.h5mu` vs `<level>.h5ad`), a
  single static `output:` **cannot** express it (the suffix is a path literal, not a wildcard) — so
  each stage rule uses a **path-wildcard output** `output_root/{module}/{dataset}/{artifact}` with
  `wildcard_constraints` separating the stages (convert `artifact` matches `mudata\.h5mu` or
  `<level>\.h5ad`; annotate `annotated\.(h5mu|h5ad)`; fasta `annotated_fasta\.(h5mu|h5ad)`), a
  `ruleorder: fasta > annotate > convert`, and **input/params functions** that look the
  `(module, dataset, artifact)` Target up in `expand_targets` to supply the upstream input path and
  the rendered `shell:` argv. No command string or suffix is hardcoded. *(The committed Snakefile is
  the earlier MuData-only stub; rewriting it to this registry-driven form is phase-1 work — §11.)*
- **`dashboard.py`** — basket rows come from `baskets(expand_targets(...))` (§8); the set of baskets
  and each row's `next_stage` derive from `load_registry()`; the "what will this button run" preview
  comes from `render_command(...)`. No hardcoded artifact or stage names (the basket order, columns,
  and per-basket verbs all follow the registry).
- **provenance** — each rule's shell ends with `python -m apb_studio.provenance --config <corpus>
  --output {output}`, which recomputes the Target from the registry+config and writes
  `provenance.json` next to the artifact (keyed by stage: rendered command, inputs, timestamp, apb
  version). Because it runs inside the producing rule, CLI and dashboard runs both get sidecars;
  `clean` prunes the cleaned stage's entry.

### 7.4 Why this matters

Change the `convert` template, add a stage, rename an artifact, or add a vendor with a single level
→ you edit **the registry or the corpus**, and the Snakefile, the baskets, the preview, the clean
scoping, and provenance all follow. That is decision 5, enforced by construction.

---

## 8. The GUI — kanban baskets (decision 10)

The dashboard is a **kanban flow**, not a grid-with-dropdowns. A dataset moves left-to-right through
four baskets as it is processed; the basket it sits in *is* the action you can take on it.

### 8.1 State = glob → basket (decision 4)
Coverage is one `output.exists()` per `Target` (§7.2) — no separate manifest. A dataset's **basket**
is the **furthest stage whose whole prefix is done** (a *contiguous* prefix, computed by
`baskets(...)` §7.2 — never the bare max-done stage, so a partial/holey state shows the lower basket,
not one whose defining artifact is missing):

| Basket | Holds datasets whose contiguous-done prefix ends at… | **Run** advances them by… |
|--------|------------------------------------------------------|---------------------------|
| **inputs** | (nothing converted yet) | `convert` |
| **converted** | `convert` | `annotate` |
| **sample annotated** | `annotate` | `fasta` |
| **fasta annotated** | `fasta` | — (terminal) |

A dataset with **no next-stage Target** is **terminal** in its current basket: rendered with a done
marker, no checkbox, not runnable. This covers *both* terminal cases with one rule — a convert-only
module (no `annotation:`) rests permanently in **converted**, and a module with `annotation:` but no
`fasta:` rests in **sample annotated** — *finished*, not stuck. Terminal-ness is per-dataset (the
dataset's own Target set), not a global property. **Caveat (decision 4):** `done` is existence-only;
it does **not** detect staleness — a changed input under an existing downstream artifact still reads
done. Freshness is left to Snakemake's `-n` (§12).

### 8.2 Selection inside a basket (decision 9)
Each basket carries two filter dropdowns — **module** and **software** (both default *all*) — that
narrow its rows, over a multi-select table:
- **one dataset** — tick its row;
- **by software** — set `software = diann`, then **Select all shown**;
- **by module** — set `module = <m>`, then **Select all shown**;
- the two **compose** (e.g. every `spectronaut` *within* one module).

`module`/`software` are columns, so the filters just project what's already there — the selection
always equals what the eye sees. "Select all shown" is a **derived** control, not a native marimo
widget (assemble it: the effective selection = the ticked rows, or the filtered rows when none is
ticked). A basket mixing **terminal** and runnable rows (e.g. **converted** holding both a
convert-only module's datasets and a full module's): **Run** / "select all shown" operate on the
**runnable** rows only and the "N selected → `<stage>`" count excludes terminal rows; **Clean** acts
on **all** selected rows (terminal rows *are* cleanable — that is how a finished convert-only dataset
gets reset). I.e. terminal-ness gates Run, not Clean.

> **As built (phase 8):** the first implementation uses the multi-select table's **native search +
> header select-all** instead of the explicit `module`/`software` dropdowns — it delivers the same
> "one / by-software / by-module" selection (type `diann`, tick the header) with far fewer fragile
> reactive widgets, which matters because the marimo interactivity can only be smoke-tested by
> running the app. The dedicated dropdowns remain an easy follow-up polish. Run still filters to
> runnable rows; each runnable row advances to *its own* `next_stage` (so heterogeneous-next-stage
> baskets, once optional intermediate stages exist, already work).

### 8.3 Layout — full replacement of the old grid
Top to bottom: **title → config-path box → error banner (if the config is bad) → flow strip → the
four baskets stacked → job log.** Nothing of the prior two-level grid or scope×stage controls
survives; the config box, the load-error banner (`load_overview`), and the live job log do.

1. **Flow strip** — one compact line of counts, the kanban-at-a-glance pulse:
   `inputs 33 → converted 12 → sample annotated 4 → fasta annotated 0` (the canonical basket labels).
2. **Baskets** — the four tables stacked **in flow order** (inputs at top → fasta annotated at
   bottom), each full-width with its own header + count, the §8.2 filters, the multi-select table, a
   **Run ▶** button, and — every basket except **inputs** — a **Clean 🗑** button behind a `confirm`
   tick. Scrolling down = moving downstream.
3. **Run / Clean (decision 9).** **One job at a time:** while a Snakemake job is running, both Run and
   Clean are blocked — they would race the shared log and each other. "Active" is derived from the
   job's own status (`inspect_job(...).running`), *not* a sticky key, so a **finished or failed** run
   can be rerun immediately (no permanent lock). *Run* advances the selected **runnable** rows — each
   to *its own* `next_stage` — as a background job. *Clean* **cascade-deletes** the selected rows'
   basket artifact **and every downstream artifact** for those datasets (`stage ∪ descendants`), then
   drops them upstream. Cascading (not just the one artifact) is what guarantees a contiguous prefix
   from *any* prior on-disk state: a holey tree — a stray `annotated_fasta.*` whose `annotated.*` is
   missing — would otherwise leave an orphan. Clean routes through
   `targets_for(selected-rows, stage∈{basket stage}∪descendants)` → `execution.clean_targets`, guarded
   by `reject_input_paths` (a real `CleanGuardError`, never an `assert` — see §7.2). (**inputs** has no
   artifact, hence no Clean.)
4. **Job log** — background Snakemake job, live log stream + per-target status, without freezing the
   UI (marimo background-job pattern) — the existing log cell, unchanged.

### 8.4 Light "did it work?" peek
Clicking a basket row shows that artifact's `provenance.json` + last log lines, and a **peek** button
that opens a light inspector (shape / obs+var columns / layers / `uns` search parameters). It is the
*only* viewer-ish feature here; everything heavier is the separate viewer track. Built in apb_studio
(apb ships no inspector); `mudata`/`anndata` read the file, no apb import needed.

---

## 9. File & test layout

```
src/apb_studio/
  registry.py     load_registry, load_corpus
  pipeline.py     Target (incl. vendor/level), convert_artifact/convert_suffix, validate_dataset,
                  render_command, expand_targets, coverage, baskets, select_targets/targets_for,
                  clean_paths    (§7 — the core)
  jobrunner.py    start_job/inspect_job/terminate_job — background subprocess + log tail
  execution.py    snakemake_argv, run_pipeline (background job), clean_selection (guarded);
                  + a row-set variant for basket Run/Clean (the ticked (module,dataset) rows, §8.2)
  provenance.py   write_for_target, prune_for_target, main (the Snakefile post-rule CLI)
  dashboard.py    marimo; flow strip + 4 kanban baskets (basket = furthest contiguous stage, §8), per-basket
                  Run/Clean + module/software filters; calls pipeline.baskets/coverage + execution + jobrunner
config/  registry.yaml · corpus.example.yaml
workflow/Snakefile   imports pipeline.{expand_targets,…}; each rule appends the provenance CLI
tests/
  test_registry.py · test_pipeline.py · test_execution.py · test_provenance.py · test_snakemake_dag.py
```

## 10. Test strategy

- **Registry contract** (exists): every stage has required keys + valid scope; `depends_on` resolves.
- **`pipeline.py`** (the bulk):
  - `convert_artifact`: `mudata.h5mu` when `level` is omitted (multi-level vendor); `ion.h5ad` when
    `level: ion`.
  - **decision-16 validation**: a single-level vendor (e.g. `maxquant`) with no `level` **raises**; a
    multi-level vendor with no `level` is accepted.
  - `render_command`: correct substitution; **raises** on an unfilled `{placeholder}`; returns a list
    (no shell-quoting surprises); carries no `--level` (that is appended by `expand_targets`).
  - `expand_targets` on `corpus.example.yaml`: exact output paths + rendered argv (incl. `--level`
    appended for declared-level **datasets** and the `--output` suffix matching the artifact); each
    Target carries the dataset's `vendor`/`level`; optional `fasta` target present only for modules
    with a `fasta:`; annotate/fasta input edges point at the real upstream artifact suffix; dependency
    edges correct.
  - `coverage`: flips `done` as files are `touch`ed under a tmp `output_root`.
  - `baskets` (decision 10): a dataset lands in the basket of its **furthest contiguous-done** stage
    and *moves* as artifacts are `touch`ed (none→**inputs**, convert→**converted**, annotate→**sample
    annotated**); a dataset is in **exactly one** basket; each row carries `software(=vendor)`/`level`.
    **non-contiguous** (annotate present, convert missing) → reports **inputs**, not **sample
    annotated**. `next_stage`/`runnable` are per-dataset from the Target set: a module with **no
    `annotation:`** → its converted datasets `runnable=False` (**terminal** in **converted**); a module
    with `annotation:` **but no `fasta:`** → its annotated datasets terminal in **sample annotated**; a
    full module → runnable with the right `next_stage`.
  - `clean_paths`: returns only paths under `output_root`; **asserts** none is under `input_root`.
- **Decision-5 enforcement:** monkeypatch `render_command`/`convert_artifact` and confirm the
  Snakefile's rendered `shell:`/targets change — i.e. the Snakefile truly imports the core, not just
  conceptually mirrors it.
- **apb contract smoke** (CI): `apb convert --help` exposes `--software/--params/--level/--output`
  (catches an upstream flag rename); `apb --version` returns a bare version string.
- **Snakemake dry-run smoke** (CI): `snakemake -n` on `corpus.example.yaml` with `touch`ed fake
  inputs resolves the DAG — including the single-level (`<level>.h5ad`) module.

## 11. Phased build (acceptance criteria, not just order)

1. **Core + contract.** Build `pipeline.py` (§7); **rewrite the stub Snakefile** to the
   wildcard-output + input-function design (§7.3) and rewire the dashboard to `coverage` /
   `render_command`. *Done when:* `test_pipeline.py` (incl. the decision-16 validation and decision-5
   enforcement tests) is green and `snakemake -n` resolves the example DAG for **both** the
   multi-level (`mudata.h5mu`) and single-level (`<level>.h5ad`) modules.
2. **One module converts end-to-end.** Real `apb convert` on one ProteoBench module from
   `corpus.yaml` → `mudata.h5mu` exists; coverage shows it done. *Done when:* a fresh checkout
   produces the artifact from `make run` (single module) and coverage reflects it (the dataset moves
   from **inputs** to **converted**).
3. **Read-only dashboard** *(superseded by phase 8)*. Two-level grid from `coverage(...)`; no
   triggers. *Done when:* the grid matches the on-disk tree for the example corpus.
4. **Triggers + dry-run + live logs** *(controls superseded by phase 8; the background-run + Clean
   guard machinery it built is reused)*. The scope×stage×{Run, Clean} matrix executes background
   Snakemake with a live log; Clean shows `clean_paths` preview first. *Done when:* run and clean
   work for dataset/module/all scopes and Clean cannot select an input path.
5. **`annotate` stage.** Wired registry→core→UI (the **sample annotated** basket); `apb annotate`
   joins obs. *Done when:* an `annotated.h5mu` is produced and shown, container-agnostic on `.h5mu`
   and `.h5ad`.
6. **Provenance** (done) — `provenance.json` per artifact, written by the Snakefile post-rule
   (decision 17), so every artifact has a sidecar regardless of CLI/dashboard. *Config write-back*
   (decision 8, comment-preserving `corpus.yaml` round-trip) remains deferred — see §12.
7. **Extension proof** (done). `apb fasta` is wired as the optional protein-`var` stage with *no GUI
   code* — a registry entry + a generic Snakefile rule; enabling `fasta:` on a module makes its
   **fasta annotated** basket reachable automatically (the UI derives baskets from the registry).

8. **Kanban basket UI (decision 10) — GUI rework.** Not a pure front-end swap — it touches the core in
   three small, named places (§7.2): (a) add `vendor`/`level` fields to `Target` (populated by
   `expand_targets`) so baskets can column software/level; (b) add `baskets(targets)` (furthest
   *contiguous* stage; per-dataset `next_stage`/`runnable`); (c) add a row-set selector
   (`targets_for(rows, stage)`) so Run/Clean act on an arbitrary ticked set, which scope×stage cannot
   express. Then rewrite `dashboard.py` to: a flow strip, four baskets stacked in flow order with
   module/software filters + "select all shown" (a *derived* control, not a native widget — runnable
   rows only), a per-basket **Run** (advances selected runnable rows to that basket's next stage) and
   **Clean** (drops rows one basket upstream, behind `confirm`; routed through `targets_for`, never a
   cross-basket stage match), and terminal rows marked done/not-runnable. *Done when:* every dataset
   appears in **exactly one** basket = its furthest contiguous artifact (a non-contiguous state reports
   the lower basket); Run advances only the selected runnable rows; terminal rows aren't runnable but
   *are* cleanable; Clean drops a row exactly one basket upstream and never orphans a downstream
   artifact; the page renders **only** the flow strip + baskets + job log (no scope/stage dropdown, no
   module-summary grid). New tests: `baskets` (§10, incl. the non-contiguous and annotation-without-fasta
   cases) and the row-set Run/Clean path in `execution.py`.

**Status (2026-06-29):** phases 1, 3, 4, 6, 7 implemented + tested (`pytest` green, `ruff` clean,
`snakemake -n` resolves, a stubbed `make run` produces convert+annotate artifacts + provenance and
coverage flips to done). Phases 2 & 5 (a *real* apb conversion) are verified at the orchestration
boundary — the Snakefile builds and dispatches the exact `apb convert`/`apb annotate` commands
end-to-end; a successful conversion additionally needs a param file apb recognizes (apb's contract,
covered by apb's own suite). The interactive dashboard's button/log behavior still wants a manual
`make ui` smoke (its dataflow graph validates and the logic it calls is unit-tested).

**GUI rework (2026-06-30):** the two-level grid + scope×stage matrix of phases 3–4 is **superseded**
by the kanban basket UI (decision 10, §8, phase 8) — the current GUI.

**Phase 8 implemented (2026-07-01, option B — DAG-insurance baked in):** core additions in
`pipeline.py` (`Target.vendor`/`.level`; `stage_order`/`basket_names`/`stage_by_basket`/`baskets`;
`targets_for`; `reject_input_paths`) and a fully **registry-driven `expand_targets`** — edges derived
from `depends_on` with nearest-emitted reconnection, artifact basenames + resource-gating read from
the registry (§13.3). `registry.yaml` gained `basket`/`artifact`/`resource` fields. `execution.py`
gained the row-set `clean_targets` (and `clean_selection` now delegates to it). `dashboard.py`
rewritten to the kanban (flow strip + registry-derived stacked baskets + per-basket Run/Clean + ↻
reload). **Verified:** `pytest` 69 green (14 new: baskets contiguity/terminal/non-contiguous,
`targets_for`, `stage_order`, reconnection, `Target` vendor/level, `clean_targets`, registry labels),
`ruff` clean, `marimo export script` graph valid, and the relied-on marimo APIs (`mo.ui.dictionary`
value/indexing, `table(selection="multi")`) confirmed. **Pending:** a `make app` interactive smoke
(the user runs it — the graph validates and the pure logic is unit-tested); dedicated module/software
filter dropdowns (see §8.2 "As built").

---

## 12. Open (genuinely deferred — not blocking phase 1)

- **Comment-preserving config write-back** (phase 6) — needs `ruamel.yaml`; decide then.
- **Big-corpus performance** — if globbing ~90×3 paths per refresh is slow, add a cached
  `status.json` (decision 4 already allows it); not needed at this scale yet.
- **Staleness, not just existence** — `done`/basket placement is existence-only (decision 4); a
  changed input under an existing downstream artifact reads "done" and stays in its basket. If
  freshness ever matters, surface Snakemake's own out-of-date detection (`-n` / mtime) per basket
  rather than the bare glob. Acceptable now (re-runs are explicit, and Snakemake rebuilds on input
  mtime when a basket is Run).

*(Resolved during the critic pass: `apb --version` exists, so provenance captures it directly —
decision 17.)*

---

## 13. Extensibility — branching / DAG (forward-looking)

**The model is an artifact DAG.** Nodes = artifacts (= the baskets): `raw → mudata → annotated →
annotated_fasta → …`. Edges = tools (= the stages): `convert`, `annotate`, `fasta`, `proteobench`,
`prolfqua`, `export`. The kanban renders the **path** case of this DAG. **Naming discipline:** an edge
is a *verb* (the tool, e.g. `fasta` / `apb fasta`); the node it produces is a *noun* (the artifact,
e.g. `annotated_fasta`) — never reuse one name for both. The DAG is already real at the data layer —
Snakemake executes a DAG, the registry's `depends_on` **is** the edge set, and `Target.inputs` **are**
the edges; only `expand_targets`' hardcoded edges and the kanban's path-rendering assume linearity
(§13.3 removes the former). So "linear vs DAG" is a **rendering** question decided by the graph's
*shape*, not a schema the topology is locked into — the topology is data (decision 5).

The kanban is linear. Two futures push on that; they are very different in cost, so keep them apart.

### 13.1 The near-term shape is a *linear order with optional nodes* — not a fork
The realistic near-term growth is more stages on **one chain**, some optional. Concretely:

```
mudata annotated → proteobench → prolfqua → export        # proteobench opted in
mudata annotated →              prolfqua → export        # proteobench skipped
```

Both share the **same total order** (`proteobench` < `prolfqua` < `export`) with `proteobench`
*optional*. So `proteobench` (producing benchresults) and `prolfqua` (producing diff results) are
**optional conversion stages of this dashboard** — each consumes the previous artifact and writes a
new one — *not* a separate downstream tool (this supersedes the earlier "consumer track" guess). Only
truly heavy *visualization* stays the separate viewer track (§1).

**This case is already almost free**, because the design is registry-driven and per-dataset:
- **Baskets are registry-derived.** Adding a stage = one registry entry + one Snakefile rule + one
  `apb`-style subcommand → a new basket appears in flow order and the flow strip grows, with **zero
  GUI code** (decision 5). "4 baskets" was never hardcoded — it is `len(stages) + 1`.
- **`baskets()` is already per-dataset** (§7.2): basket / `next_stage` / `runnable` come from *that
  dataset's own Target set*. A dataset that skips an optional stage simply has **no Target** for it and
  flows past it — "furthest contiguous" is measured over the dataset's **applicable** stages, so a
  skipped optional stage is *transparent*, never a gap. "Exactly one basket" still holds (still a total
  order).

**The one genuinely new mechanic: input reconnection.** Today `expand_targets` hardcodes each stage's
upstream (annotate←convert, fasta←annotate). An optional *intermediate* stage means a successor must
consume its **nearest applicable predecessor** (`prolfqua` ← `proteobench` if the dataset opted in,
else ← `annotate`). That is a small, localized change in `expand_targets` — wire each stage from the
last *emitted* upstream Target for that dataset, not from a fixed stage name. Clean then drops a row to
its nearest *applicable* upstream basket; the no-cascade argument (§8.3) is unchanged (the furthest
artifact still has nothing downstream).

### 13.2 What a *true fork* would change (defer until one exists)
A true fork = one artifact feeding **two independent downstream outputs that never rejoin** — the
canonical case is **multiple exporters**: `prolfqua → export MSstats` **and** `prolfqua → export qpx`,
parallel terminal siblings, neither before the other. (The §13.1 flows are *not* forks — they are
sequential; an optional *intermediate* stage is still a total order.) If real parallel exporters
appear, there are three ways to model them, cheapest first:

1. **One `export` stage that fans out to N formats** (one rule, multiple output files; one "exported"
   basket = *all declared formats written*). Keeps the kanban **linear** — the same trick `convert`
   uses to fan out to N levels in one MuData. Cost: Run/Clean act on the whole export set, not per
   format.
2. **On-demand action, not a stage** — an "Export ▾" (MSstats / qpx) on each terminal row, like the
   §8.4 peek. No basket, no coverage tracking. Right if exports are one-off, not corpus-wide state.
3. **N independent terminal stages** (real fork) — only if you need per-format *coverage* and
   independent Run/Clean ("12/50 exported to MSstats", separate from qpx). This is the one case that
   breaks the kanban's **"exactly one basket"** invariant (a dataset is *done* in one branch, *pending*
   in another — "furthest" is undefined without a total order). Even so: **the engine, the on-disk
   format, and the `Target` + `inputs`-edge graph are already DAG-shaped** — no rework, no migration;
   only the *presentation* changes — swimlanes (one lane per exporter) or a terminal basket that
   sprouts a `Run →` button per format.

Don't build any of this now (YAGNI). If exporters land, **start with option 1 (fan-out) or 2
(on-demand)** — both keep the linear kanban — and escalate to option 3 only when per-format corpus
coverage is a real requirement.

### 13.3 Cheap insurance to bank now (≈ zero cost)
So that 13.1 "just works" and only a true fork ever forces a UI decision:
- Derive stage order in `baskets()` from the registry's **`depends_on` (topological sort)** — never a
  hardcoded linear list (the registry already carries `depends_on`).
- Compute contiguity / `next_stage` over each dataset's **applicable** stages (its Target set), not the
  global stage list; do **not** assume a single global terminal.
- Wire `expand_targets` edges from the **last emitted upstream Target**, so an optional intermediate
  stage reconnects automatically.
- Give each registry stage its **basket display label** (e.g. `convert` → "converted", `annotate` →
  "sample annotated") as a registry field; `baskets()` reads it. Otherwise the past-tense label map is
  hardcoded in `baskets()` and a new stage touches code — with it, a new stage brings its own label and
  the "zero GUI code" claim (13.1) holds literally.

With those three, adding `proteobench` / `prolfqua` / `export` as optional stages is additive
(registry + rule + edge), and the kanban absorbs them with no invariant change.
