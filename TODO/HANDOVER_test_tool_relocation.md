# Handover: test-data browser relocated from apb → apb_studio

**Date:** 2026-06-29
**Context:** `apb` (anndata_proteomics) is now a **pure library + `apb` CLI** — all marimo/UI was
moved here. This note hands over what landed, what's verified, and what's left to finish.
**Related:** [TODO_workflow_dashboard_plan.md](TODO_workflow_dashboard_plan.md) (the corpus
dashboard), apb's `TODO/TODO_ui_test_tool.md` (the original tool notes + the relocation log).

## What this delivered

The marimo **test-data browser** (browse ProteoBench corpus → convert → inspect) moved out of apb
into this package. apb_studio drives conversion by **shelling out to `apb convert`** and imports
only apb's pure read-only helpers for catalog/metadata (never converts in-process).

New layout under `src/apb_studio/`:

| File | Role |
|---|---|
| `ui/test_tool.py` | the marimo browser app (`make test-tool`) |
| `ui/panels.py` | marimo status / summary panels (ex-`_ui_panels.py`) |
| `ui/anndataview.py` | standalone `.h5ad` viewer (ex-`anndataview.py`) |
| `conversion/runner.py` | background-subprocess runner (ex-`jobrunner.py`, framework-agnostic) |
| `conversion/subprocess_adapter.py` | **new** — builds the `apb convert` argv + writes a `command.json` sidecar |
| `support.py` | ProteoBench catalog + converted-runs table + result summaries |

`pyproject.toml` gained `anndata-proteomics` (uv path source → `../anndata_proteomics_bridge`) and
`plotly`; `Makefile` gained `test-tool`. Tests: `tests/test_runs_tracking.py`,
`tests/test_subprocess_adapter.py`.

## Verified vs NOT verified

- ✅ **Logic tests green** (`support` + `subprocess_adapter`): 17 passed; ruff clean.
- ✅ apb side: full suite green, `apb convert` smoke produces `.h5mu`, wheel ships no marimo.
- ⚠️ **The marimo apps were relocated on inspection only — never launched.** No env on the
  relocation machine had a runnable marimo. `ui/test_tool.py`, `ui/panels.py`, `ui/anndataview.py`
  need a real `make test-tool` launch to confirm at runtime (see TODO 1).

## How to run it (setup)

```bash
cd apb_studio
uv venv && source .venv/bin/activate
uv pip install -e .                          # brings in marimo, plotly, and apb via the uv path source
uv pip install -e ../anndata_proteomics_bridge   # ensures the `apb` CLI is on PATH
make test-tool                               # marimo run src/apb_studio/ui/test_tool.py
```

The browser reads apb's ProteoBench cache (`anndata_proteomics.test_data` paths, gitignored) — if
the catalog is empty, regenerate it via apb's `test_data_download/Makefile`.

Run the logic tests:
```bash
uv run --extra dev pytest -q   # or, without a studio venv: PYTHONPATH=src python -m pytest tests/ -q  (in apb's venv)
```

## TODO — to finish the relocation

### 1. Runtime smoke-test the marimo browser (`make test-tool`)
The cells were moved with import repoints + a swapped conversion command but not executed. Launch
and verify end to end:
- catalog loads and filters (target / software / size);
- selecting a dataset + **Convert ▶** starts a background job; the status panel shows the live log;
- it writes `logs/ui_converted/<run>/result.h5{ad,mu}` + `command.json` + `console.log`;
- the **Converted outputs** table lists the run (slug/target/status from the run-dir name +
  `command.json`), and the **Result viewer** renders `support.summarize(...)`.
- Watch two spots that changed and aren't unit-tested: the status-panel argv parse in
  `ui/test_tool.py` (reads `--software` for the slug, `_cmd[3]` for the level), and `ui/anndataview.py`
  (moved verbatim, never run here).

### 2. Realign the corpus pipeline to the real `apb` CLI (pre-existing mismatch)
`config/registry.yaml` + `workflow/Snakefile` still call commands the CLI does **not** accept:
- they use `apb convert --input {in} --level {lvl} --rule {rule} --output {out}` and a non-existent
  `apb assemble-mudata`;
- the real contract is **`apb convert <data> [level] --params <p> [--software <slug>] [--rule-toml <t>] --output <out>`**,
  where omitting the level emits a multi-level **MuData** (so `assemble-mudata` ≡ `apb convert <data> --params … --output X.h5mu`).
`conversion/subprocess_adapter.py` already builds the correct argv — mirror it in the Snakefile/
registry (or have the Snakefile call the adapter). Until then the Snakemake pipeline will fail at
runtime even though the browser works.

### 3. (optional) Stand up apb_studio's own venv + CI
The logic tests were run via apb's venv + `PYTHONPATH=src`. Give apb_studio a real venv
(`uv pip install -e .` resolves apb via the path source) so `make test` and CI run independently.

## Key design notes (so the seam is clear)

- **CLI-consumer model:** heavy conversion runs out-of-process via `apb convert`; apb_studio only
  *imports* apb's pure helpers (`converters.pipeline.recognize_software/available_targets/_param_version`,
  `params.anndata_io.read_search_parameters`) for read-only catalog/metadata — no rule logic is
  duplicated here (per the repo's reuse rule).
- **`command.json` sidecar:** `subprocess_adapter.start_conversion` writes
  `{input_file_path, slug, target, param_path}` into each run dir; `support.list_converted_runs`
  reads it (it no longer parses the CLI argv from `console.log`).
- **No reverse dependency:** apb does not import apb_studio. If you need a bit of apb logic here,
  import it from apb — do not copy it back.
