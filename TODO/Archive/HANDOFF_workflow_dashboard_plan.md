# ARCHIVED: Handoff — kanban dashboard redesign + phase 8 implementation

Status: implemented and superseded by the Plotly Dash applications; archived 2026-07-20.

**Date:** 2026-07-01 · **Author:** Claude (pairing session) · **Reviewer:** witold
**Companion:** [the plan](TODO_workflow_dashboard_plan.md) (authoritative spec — this is the change log for it)

---

## TL;DR

The GUI was redesigned from a **grid + scope×stage dropdown** to a **kanban of baskets**, the design
was hardened by an adversarial critic pass, and then **implemented** (option B — "DAG-insurance baked
in"). All automated checks are green; the only thing not exercised is the live marimo UI, which is
yours to smoke-test (`make app`) per our rule (*I build code + tests, you run the app*).

| Check | Result |
|-------|--------|
| `pytest -q` | **72 passed** (was 55; +17 new) — includes the live `snakemake -n` DAG test |
| `uv run --extra dev ruff check src tests` | clean (ruff now a declared dev dep — reproducible) |
| `marimo export script dashboard.py` | graph valid (no cycles, all refs resolve) |
| marimo APIs relied on | confirmed (`mo.ui.dictionary` value/indexing, `table(selection="multi")`) |
| Interactive `make app` | **NOT run — yours** |

> **Review round 1 addressed (2026-07-01)** — see [REVIEW_workflow_dashboard_plan.md](REVIEW_workflow_dashboard_plan.md) and §8 below.

---

## 1. What you asked for (this session)

1. **Kanban baskets** instead of the confusing stage dropdown: a dataset lives in **one** basket = the
   furthest stage it reached; the basket *is* the verb (Run advances it). `inputs → converted →
   sample annotated → fasta annotated`.
2. Selection by **one row / by software / by module**.
3. Layout: **flow strip + stacked baskets**, full replacement of the old grid.
4. Persist the design in the existing plan (not a new file), "make it my own."
5. Then: think through **branching / DAG** futures; conclude optional stages are *data*.
6. Implement, choosing **option B**: linear kanban **+** bake in the DAG-insurance now.

---

## 2. Design decisions locked (see the plan for detail)

- **Kanban model** — one basket per dataset = furthest **contiguous** completed stage (not bare
  max-done, so a holey on-disk state reports the *lower* basket). Plan decision 10, §8.1.
- **Run / Clean semantics** — Run advances selected **runnable** rows to their next stage; **Clean**
  deletes only the rows *currently in* that basket (their furthest artifact → nothing downstream to
  orphan → no cascade), routed through the row-set selector, never a cross-basket stage match. §8.3.
- **Terminal = no next-stage Target** (per-dataset): covers convert-only modules *and*
  annotation-without-fasta modules with one rule. Terminal gates **Run**, not **Clean**.
- **Topology is data (§13)** — the stage graph is an artifact DAG: **nodes = baskets/artifacts, edges
  = tools/stages**. The kanban renders the *path* case. Optional intermediate stages (e.g. a future
  `proteobench`) are sequential and nearly free; **parallel exporters** (`msstats` + `qpx`) are the
  one *fork* case that would need swimlanes — deferred (§13.2), with two linear escapes documented.
- **Critic pass** fixed three classes of issue before implementation: stale per-module `level`
  wording (the code was already per-dataset), the non-contiguous/Clean-orphan hole, and the missing
  `Target.vendor/level` + row-set selector needed to build it.

---

## 3. What was implemented (files touched)

| File | Change |
|------|--------|
| [config/registry.yaml](../config/registry.yaml) | Each stage gained `basket` (label); non-root stages gained `artifact` (output basename) + `resource` (module key it consumes **and** gates on). Topology is now fully declarative. |
| [src/apb_studio/pipeline.py](../src/apb_studio/pipeline.py) | `Target` + `vendor`/`level` (defaulted). **`expand_targets` rewritten to be registry-driven**: edges from `depends_on`, nearest-emitted **reconnection** over skipped optional stages, artifact/resource from the registry. New: `stage_order` (topo), `basket_names`, `stage_by_basket`, `baskets` (furthest-contiguous + per-dataset `next_stage`/`runnable`), `targets_for` (row-set selector), `reject_input_paths` (shared Clean guard). |
| [src/apb_studio/execution.py](../src/apb_studio/execution.py) | New `clean_targets(targets, input_root=…)` — the row-set Clean primitive (guarded, prunes provenance). `clean_selection` now delegates to it (DRY). |
| [src/apb_studio/dashboard.py](../src/apb_studio/dashboard.py) | **Rewritten** to the kanban: flow strip + registry-derived stacked baskets (dynamic N via `mo.ui.dictionary`), per-basket multi-select table, per-basket **Run**/**Clean**(+confirm), and a **↻ reload** button. No hardcoded stage names — baskets/labels/verbs all follow the registry. |
| [tests/test_pipeline.py](../tests/test_pipeline.py) | +10 tests: `Target` vendor/level, `stage_order`, `basket_names`/`stage_by_basket`, edge-derivation + **reconnection** (synthetic middle stage), and `baskets` (moves downstream, exactly-one-basket, non-contiguous→lower, convert-only terminal, annotation-without-fasta terminal), `targets_for`. |
| [tests/test_execution.py](../tests/test_execution.py) | +2 tests: `clean_targets` deletes only the given rows (downstream/other modules untouched) + input-root guard. |
| [tests/test_registry.py](../tests/test_registry.py) | +2 tests: every stage has a `basket`; non-root stages declare `artifact` + `resource`. |
| [TODO_workflow_dashboard_plan.md](TODO_workflow_dashboard_plan.md) | Decision 10 rewritten; §8 rewritten as the kanban GUI; §7.2 API updated; §13 (Extensibility — DAG) added; phase 8 + status; all critic fixes folded in. |

**Not touched (verified still correct):** `workflow/Snakefile` (outputs/commands unchanged, so its
target lookups still resolve — confirmed by the live `snakemake -n` test), `registry.py`,
`jobrunner.py`, `provenance.py`, `scaffold.py`, `Makefile`.

---

## 4. One deliberate deviation (please review)

The plan's §8.2 designed **explicit `module` / `software` filter dropdowns + a "select all shown"**
control per basket. **I did not build those.** Each basket instead uses the multi-select table's
**native search box + header select-all**:

- **By software:** type `diann` in the basket's search, tick the header checkbox.
- **By module:** type the module name, tick the header.
- **One row:** tick its checkbox.

Rationale: it delivers the same selection outcomes with far fewer fragile reactive widgets, which
matters because the marimo interactivity can only be validated by running the app (I can't). The
dedicated dropdowns are recorded as easy follow-up polish (§8.2 "As built"). **Say the word and I'll
add the real dropdowns.**

---

## 5. How to review / run

```bash
cd apb_studio && source .venv/bin/activate      # or use ./.venv/bin/...
pytest -q                                        # 69 passed
make dag                                          # snakemake -n resolves the example corpus

make scaffold        # REQUIRED: regenerate config/corpus.yaml (the on-disk one is old-schema)
make app             # the kanban: flow strip + 4 baskets; Run one, hit ↻ reload to watch it move
```

Reading order for the diff: `config/registry.yaml` (the new data fields) → `pipeline.py`
(`expand_targets` + `baskets`) → `dashboard.py` (the cells) → the plan's §8 and §13.

---

## 6. Still open / not done

- **Interactive smoke** — `make app` has not been run; the dataflow graph validates and the pure
  logic is unit-tested, but button/table/reload behavior in the browser is unverified. **Yours.**
- **Filter dropdowns** — deferred in favor of native table search (§4 above).
- **Config regeneration** — `config/corpus.yaml` on disk is still the old schema; `make scaffold`
  rewrites it (the dashboard shows a readable banner until you do).
- **Exporters / true fork** — YAGNI; §13.2 records the three modelling options for when they land.
- **Staleness** — basket placement is existence-only (decision 4); a changed input under an existing
  downstream artifact still reads "done" (§12). Acceptable at this scale.

---

## 7. Verdict

Design is tight and on record; the core is DAG-ready (topology is data); phase 8 is implemented and
green on every automated check. The single remaining gate is your `make app` smoke — report anything
that breaks and I'll fix it.

---

## 8. Review round 1 — resolutions (2026-07-01)

All six findings in [REVIEW_workflow_dashboard_plan.md](REVIEW_workflow_dashboard_plan.md) were valid
and fixed at the root:

| # | Sev | Finding | Fix |
|---|-----|---------|-----|
| 1 | High | Clean guard used `assert` (stripped by `python -O`) | `reject_input_paths` now raises `CleanGuardError` (a real exception); regression test runs it under `python -O` and asserts it still raises. |
| 2 | High | Dashboard blocked valid reruns + allowed concurrent jobs | Dropped the sticky `last_key`. "Active" is derived from `inspect_job(get_job()).running`; **Run and Clean are blocked while a job runs** (no log race), and a finished/failed run can be rerun. |
| 3 | Med | Clean could leave a downstream orphan in a holey tree | Clean now **cascades**: it deletes the basket's stage **and all `descendants`** for the selected datasets (`pipeline.descendants`), so a Clean leaves a contiguous prefix from any prior state. New test builds convert+fasta with annotate missing and confirms the stray `annotated_fasta.*` is swept. |
| 4 | Med | `make dag` failed on the placeholder example config | `CONFIG` now prefers `config/corpus.yaml` when it exists (matches the dashboard); Makefile help states the "scaffold first / `CONFIG=`" prerequisite. |
| 5 | Low | `ruff` not in the declared env | Added `ruff` to the `dev` extra; `uv run --extra dev ruff check src tests` now passes reproducibly. |
| 6 | Low | Stale APB path `../anndata_proteomics_bridge` | Confirmed the repo is `../apb` (the other name doesn't exist); updated the hint in `pyproject.toml` and the `scaffold.py` error message. |

Plan updated to match: §7.2 (`reject_input_paths` raises; `descendants`; cascade Clean), §8.3 (one
job at a time; cascade). **Verification after fixes:** `pytest` 72 passed (+3: `-O` guard, `descendants`,
cascade), `ruff` clean via the dev extra, marimo graph valid. `make app` smoke still yours.

The positive checks in the review still hold (pytest, marimo export, `apb convert DATA [LEVEL]` accepts
the generated `--level` form, the DAG test uses real fixture inputs).

---

## 9. Review round 2 — the `make app` smoke run (2026-07-01)

The dashboard **worked** — it launched a real corpus run; **10/51 convert jobs succeeded**. The "kilos
of errors" were `apb convert` jobs *crashing*, not a UI fault. Root cause and fixes:

**Root cause (apb).** Many ProteoBench submissions bundle a param file for the wrong tool — e.g. a
DIA-NN submission whose only param file is a FragPipe `.workflow`. Handed that with `--software diann`,
apb's DIA-NN parser hit `Version("")` → uncaught `packaging.version.InvalidVersion` traceback (and a
second latent `parts[0]` IndexError on an empty command line).

**Fixes:**
| Where | Change |
|-------|--------|
| **apb** `params/parsers/diann.py` | `_version_below()` tolerates a missing/garbage version (→ False, no `InvalidVersion`); empty-token guard in `_parse_cmdline`; `extract_params` raises a clean **`ParamsError`** (new, in `params/model.py`) when the file is not a DIA-NN param file at all. |
| **apb** `converters/assemble.py` | `_attach_search_parameters` **degrades**: a param-parse failure no longer aborts convert — it logs a warning, records `uns['anndata_proteomics']['search_parameters_error']`, and the quant data still converts. |
| **apb_studio** `provenance.py` | `read_params_warning()` lifts that `uns` flag into `provenance.json` (`"warning": …`) at build time. |
| **apb_studio** `pipeline.py` | new `problems(corpus, targets)` — **static** (missing input/params/annotation/fasta) + **runtime** (provenance warnings); `baskets(...)` now carries a `problem` per row → a **problem column** in each basket table. |
| **apb_studio** `execution.py` | `--keep-going` — one bad dataset no longer aborts the ~50-dataset corpus. |

**End-to-end verified:** the exact dataset that crashed now converts (`1 of 1 steps done`), its
`provenance.json` carries `"warning": "ParamsError: not a DIA-NN parameter file …"`, and
`pipeline.problems` returns that message for the row (so the table shows it). **apb** 356 passed / 4
skipped, ruff clean; **apb_studio** 78 passed (+6: `problems` ×3, `--keep-going`, `read_params_warning`
×2), ruff clean, marimo graph valid.

**Net effect in the app:** no more crash spam; the whole corpus completes; a dataset with an
unparsable/mismatched params file lands in **converted** (its quant data is fine) with a visible
**problem** note, and genuinely missing files are flagged *before* a run.

**Env note (not a code bug):** the pipeline calls bare `apb`, so the venv must be active
(`source .venv/bin/activate`) — running `apb` off-PATH exits 127. Your shell's `VIRTUAL_ENV` still
points at the pre-rename `…/anndata_proteomics_bridge/.venv`; re-point or re-activate `apb_studio/.venv`.

---

## 10. Review round 3 — full `make run` + failure visibility (2026-07-01)

Ran the whole corpus (`make run`, now `--keep-going` + bounded `CORES`, `apb` on PATH). **The round-2
fix held: zero crashes; 40 datasets converted (7 with a degrade-warning); the run completed.** The
remaining ~10 failures are a **different, clean** class — apb reporting *no parsing rule for the vendor
version* (a `ValueError`, not a traceback):

| Reason | ~Count | Cause |
|--------|--------|-------|
| `peaks ion: no rule covers version '13 …'` | 6 | apb has no PEAKS 13 rule |
| `fragpipe ion: no rule covers version '22.0' / '23.0'` | 3 | apb has no FragPipe 22/23 rule |
| `wombat ion: no rule covers version '0.9.11'` | 1 | scaffold mislabeled level (see below) |

**Fixes this round (apb_studio only):**
| Where | Change |
|-------|--------|
| `workflow/Snakefile` | each rule gets a per-dataset `log:` and tees to it (`(cmd) 2>&1 \| tee {log}`) — survives failure (snakemake deletes outputs, not logs), still streams to console. |
| `pipeline.problems` | now also surfaces a **convert/annotate/fasta FAILURE**: artifact missing **and** its `<artifact>.log` present ⇒ show the apb error line (e.g. "no rule covers version 23.0") in the `problem` column. Missing + no log ⇒ pending (not flagged). |
| `execution.clean_targets` | removes the sidecar `<artifact>.log` with the artifact, so a cleaned dataset isn't mis-flagged as failed. |
| `scaffold` | level is now the **vendor-native** level (`SINGLE_LEVEL_VENDOR_LEVELS`: maxquant/fragpipe/peaks→ion, **wombat→peptidoform**), not the module-name level — fixes the WOMBAT-in-an-`ion`-module failure. Re-run `make scaffold` to apply. |
| `Makefile` | `run` gains `--keep-going` + a bounded `CORES ?= 3` (big vendor files can OOM `--cores all`). |

**Verified end-to-end:** the FragPipe-23 target fails with no artifact, its `ion.h5ad.log` holds the
`ValueError`, and `problems()` returns `"convert failed: ValueError: fragpipe ion: no rule covers
software version '23.0'"` — so it shows in the **inputs** basket's problem column. apb_studio **82
passed** (+4), ruff clean, marimo graph valid.

**Deferred (a scoped apb task, your call):** add apb parsing rules for FragPipe 22/23 and PEAKS 13 —
this is per-vendor rule authoring (needs each version's column spec), the real substance behind most
remaining failures. Until then those datasets stay in **inputs** with a clear "no rule covers version"
note instead of failing silently.
