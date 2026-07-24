# Corpus Runner alignment

**Status:** Completed 2026-07-24.

## Product boundary

Corpus Runner is a thin observer and operator for the packaged Snakemake
workflow. It must:

1. show Snakemake-managed outputs and their state;
2. trigger only whole-corpus Snakemake run and clean operations;
3. load persisted Snakemake runs and logs from the output root;
4. present global and per-rule logs, failures, and diagnostics;
5. present APB-owned artifact summaries, including `uns`, plus persisted rule
   runtimes when Snakemake recorded them.

It must not invent row-, branch-, or stage-scoped execution controls. The grid
is for inspection, not execution selection.

## Confirmed current gaps

- `Clear selected stage…` resolves a clicked cell and deletes paths directly
  from the Dash callback through `execution.clean_targets`.
- Existing run discovery is process-local. After a server restart, persisted
  `run.json` and `snakemake.log` files are ignored and the UI incorrectly says
  that no corpus run log exists.
- Snakemake benchmarks are already declared and the grid can render
  `DONE · <duration>`, but the current output root contains 556 artifacts and
  zero benchmark files. Those runtimes cannot be reconstructed retroactively.

## Implementation plan

### 1. Make the boundary durable

- Add the product boundary above to `AGENTS.md`.
- Update README/architecture text that currently describes stage-scoped
  clearing.

### 2. Replace stage clearing with whole-corpus Snakemake cleaning

- Remove `Clear selected stage…`, its selection-dependent enablement, and the
  dashboard helpers that resolve downstream targets.
- Add one confirmed `Clear corpus…` control beside `Run corpus`.
- Add a packaged Snakemake `clean` target that invokes the existing guarded
  cleanup primitive for every target in the frozen snapshot, including managed
  artifacts, rule logs, failure markers, benchmarks, and provenance entries.
- Launch clean as the same kind of background Snakemake job as run. Disable
  both operation buttons while either job is active.
- Preserve fixture inputs, output-alias metadata, and
  `.apb_studio/runs/<run-id>/` history.

### 3. Recover persisted Snakemake runs

- Discover the newest valid run directory below
  `<output_root>/.apb_studio/runs/`.
- Persist operation state (`run` or `clean`, timestamps, terminal status) next
  to `run.json`; let Snakemake lifecycle hooks update terminal success/failure
  so state survives a Dash restart.
- On startup, reload, or output-root change, show the newest persisted snapshot,
  status, and `snakemake.log` even when no in-memory process exists.
- Keep active in-memory jobs pinned to their immutable snapshot until they
  finish.

### 4. Make timing visible and honest

- Keep Snakemake benchmark files as the runtime source of truth.
- Continue rendering timed stages as `DONE · <duration>` and show the runtime
  in artifact detail.
- For completed artifacts without benchmark metadata, explicitly say that
  timing is unavailable because the artifact predates recorded benchmarks.
- Add runtime coverage to the corpus summary so it is apparent how many
  completed stages have persisted timing.

### 5. Preserve inspection and diagnostics

- Keep stage-cell inspection for APB `describe_path()` summaries and `uns`.
- Keep per-rule failure log display/download and the global Snakemake log.
- Add a compact corpus summary of stage-state counts, produced artifacts, and
  timing coverage; do not duplicate APB proteomics summary logic in Studio.

### 6. Verification

- Replace stage-clear tests with whole-corpus Snakemake-clean tests.
- Add restart/persisted-run recovery tests and timing-unavailable/coverage
  tests.
- Exercise the packaged Snakefile for run, clean, benchmark creation, and
  lifecycle status recording.
- Run Ruff, strict Pyright, the full pytest suite, and the 100% coverage gate.
- Validate `AGENTS.md` structure, references, and commands with the agent-rules
  verification scripts.

## Completion

Implemented, verified, and archived.
