# apb_studio dashboard — a KANBAN over the corpus (decision 10, plan §8).
#
# Run from the repo root in the project env (so `apb_studio` is importable):
#     make app           # clean dashboard (marimo run)   ·   make ui  # editor (marimo edit)
#
# A dataset lives in exactly one BASKET = the furthest contiguous stage it has reached
# (inputs → converted → sample annotated → fasta annotated). The basket IS the verb: Run on a
# basket advances the selected rows to that basket's next stage; Clean deletes the artifact that
# put them there, dropping them one basket upstream. Baskets, their order, and their labels are all
# derived from config/registry.yaml (single source of truth) — adding a stage adds a basket, no GUI
# code. Coverage/commands/paths come from apb_studio.pipeline; Run/Clean go through
# apb_studio.execution + jobrunner.

import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium")


@app.cell
def _():
    import shlex
    from pathlib import Path

    import marimo as mo

    import apb_studio
    from apb_studio import execution, jobrunner, pipeline
    from apb_studio.registry import load_registry

    repo_root = Path(apb_studio.__file__).resolve().parents[2]
    snakefile = repo_root / "workflow" / "Snakefile"
    return Path, execution, jobrunner, load_registry, mo, pipeline, shlex, snakefile


@app.cell
def _(mo):
    mo.md("""
    # apb_studio — corpus kanban

    A dataset flows left→right through the baskets; the basket it sits in is the furthest stage it
    has reached. **Run** a basket to advance the selected rows to the next stage; **Clean** drops them
    back one basket. Select rows one-by-one, or use the table's search + header checkbox to grab all
    of a software/module at once. Hit **↻ reload** after a run finishes to see rows move.
    """)
    return


@app.cell
def _(Path, mo):
    # Default to the scanned corpus (`make scaffold` → config/corpus.yaml) when present, else the
    # bundled example. `reload` re-reads the output tree (baskets are a glob of it — decision 4).
    _default = (
        "config/corpus.yaml"
        if Path("config/corpus.yaml").exists()
        else "config/corpus.example.yaml"
    )
    config_path = mo.ui.text(value=_default, label="corpus config", full_width=True)
    reload_button = mo.ui.run_button(label="↻ reload")
    mo.hstack([config_path, reload_button], justify="start", align="center")
    return config_path, reload_button


@app.cell
def _(config_path, execution, load_registry, pipeline, reload_button):
    # Load DEFENSIVELY (never crashes): a bad/old-schema/missing config returns a readable message.
    # Depends on reload_button so a finished run can be reflected on demand (no auto-poll → selections
    # survive). Baskets, their order, and the Clean stage-map all derive from the registry (§8/§13).
    reload_button  # take a dependency: clicking ↻ re-runs this cell
    targets, _rows, corpus, load_error = execution.load_overview(config_path.value)
    registry = load_registry()
    # Per-dataset problems (missing input/params/annotation/fasta; apb param-parse warnings from
    # provenance) surface as a `problem` column in each basket table (§8).
    problems = pipeline.problems(corpus, targets) if corpus else {}
    bk = pipeline.baskets(targets, registry, problems=problems)
    names = pipeline.basket_names(registry)
    stage_of_basket = pipeline.stage_by_basket(registry)
    # For cascade Clean: cleaning a basket removes its stage AND every downstream stage for the
    # selected datasets (so a holey on-disk state can't leave a stray downstream artifact, §8.3).
    clean_stages_of_basket = {
        b: [s, *pipeline.descendants(registry, s)] for b, s in stage_of_basket.items()
    }
    return bk, clean_stages_of_basket, corpus, load_error, names, targets


@app.cell
def _(load_error, mo):
    mo.callout(mo.md(load_error), kind="danger") if load_error else None
    return


@app.cell
def _(bk, mo, names):
    # Flow strip — the kanban-at-a-glance pulse: one count per basket, in flow order.
    _strip = "  →  ".join(f"**{b}** {len(bk[b])}" for b in names)
    mo.md(f"### {_strip}")
    return


@app.cell
def _(bk, mo, names):
    # One multi-select table per basket (native search + header select-all cover "by software / by
    # module / one-by-one"). Batched in a dictionary so selections are reactive across cells.
    tables = mo.ui.dictionary({
        b: mo.ui.table(bk[b], selection="multi", label=b, page_size=15) for b in names
    })
    return (tables,)


@app.cell
def _(mo, names):
    # Per-basket action widgets. Run for every basket except the terminal one (nothing downstream);
    # Clean (behind a confirm) for every basket except `inputs` (which has no artifact).
    runs = mo.ui.dictionary({b: mo.ui.run_button(label="Run ▶") for b in names[:-1]})
    cleans = mo.ui.dictionary({b: mo.ui.run_button(label="Clean 🗑") for b in names[1:]})
    confirms = mo.ui.dictionary({b: mo.ui.checkbox(label="confirm") for b in names[1:]})
    return cleans, confirms, runs


@app.cell
def _(bk, cleans, confirms, mo, names, runs, tables):
    # Render the baskets stacked in flow order: header + count, its table, then its Run/Clean controls.
    # Run exists for every basket except the terminal one (names[-1]); Clean for every basket except
    # `inputs` (names[0]) — matching the dictionaries built above.
    def _basket_block(b):
        controls = []
        if b != names[-1]:
            controls.append(runs[b])
        if b != names[0]:
            controls += [cleans[b], confirms[b]]
        return mo.vstack([
            mo.md(f"## {b} — {len(bk[b])}"),
            tables[b],
            mo.hstack(controls, justify="start", align="center"),
        ])

    mo.vstack([_basket_block(b) for b in names])
    return


@app.cell
def _(mo):
    # Background-job handle held in state across cells. "Is a job active?" is derived from the job's
    # own status (inspect_job(...).running), NOT a sticky key — so a finished/failed run can be rerun.
    get_job, set_job = mo.state(None)
    return get_job, set_job


@app.cell
def _(
    Path,
    clean_stages_of_basket,
    cleans,
    config_path,
    confirms,
    corpus,
    execution,
    get_job,
    jobrunner,
    mo,
    pipeline,
    runs,
    set_job,
    snakefile,
    tables,
    targets,
):
    # Act on whichever basket button was clicked. Run advances the selected RUNNABLE rows to each
    # row's own next stage (background Snakemake job); Clean cascade-deletes the selected rows' basket
    # artifact + everything downstream (guarded — clean_targets refuses anything under input_root).
    # Only ONE job at a time: while a job is running both are blocked (they'd race the shared log and
    # each other); once it finishes/fails the same selection can be rerun (no sticky-key lock).
    feedback = mo.md("")
    _run = next((b for b, v in runs.value.items() if v), None)
    _clean = next((b for b, v in cleans.value.items() if v), None)
    _job = get_job()
    _busy = _job is not None and jobrunner.inspect_job(_job).running

    if _busy and (_run is not None or _clean is not None):
        feedback = mo.callout("A job is still running — wait for it to finish (log below).", kind="warn")
    elif _run is not None:
        _runnable = [r for r in tables.value.get(_run, []) if r.get("runnable")]
        if not _runnable:
            feedback = mo.callout("Select runnable rows first (terminal rows can't advance).", kind="warn")
        else:
            _outputs = []
            for _ns in {r["next_stage"] for r in _runnable}:
                _keys = {(r["module"], r["dataset"]) for r in _runnable if r["next_stage"] == _ns}
                _outputs += [t.output for t in pipeline.targets_for(targets, _keys, stage=_ns)]
            _log = Path(corpus["output_root"]) / ".apb_studio" / "run.log"
            set_job(execution.run_pipeline(snakefile, config_path.value, _log, targets=_outputs))
            feedback = mo.callout(f"Started {len(_outputs)} target(s) — live log below.", kind="info")
    elif _clean is not None:
        if not confirms.value.get(_clean):
            feedback = mo.callout("Tick ‘confirm’ before Clean — it deletes outputs.", kind="warn")
        else:
            _rows = tables.value.get(_clean, [])
            if not _rows:
                feedback = mo.callout("Nothing selected to clean.", kind="warn")
            else:
                _keys = {(r["module"], r["dataset"]) for r in _rows}
                _to_clean = [
                    t for s in clean_stages_of_basket[_clean]
                    for t in pipeline.targets_for(targets, _keys, stage=s)
                ]
                _deleted = execution.clean_targets(_to_clean, input_root=corpus["input_root"])
                feedback = mo.callout(
                    f"Deleted {len(_deleted)} output(s) — hit ↻ reload to see rows move upstream.",
                    kind="success",
                )
    feedback
    return


@app.cell
def _(mo):
    # Poll while a job runs; the log/status cell below depends on this tick (baskets do NOT — they
    # refresh only on ↻ reload, so selections survive).
    refresh = mo.ui.refresh(default_interval="2s", label="job log auto-refresh")
    refresh
    return (refresh,)


@app.cell
def _(get_job, jobrunner, mo, refresh):
    refresh  # re-run on each tick
    job = get_job()
    if job is None:
        view = mo.md("_No run yet._")
    else:
        status = jobrunner.inspect_job(job)
        state = "running…" if status.running else ("✅ done" if status.success else "❌ failed")
        view = mo.vstack([
            mo.md(f"**Job:** {state}"),
            mo.md(f"```\n{status.log_text or '(no output yet)'}\n```"),
        ])
    view
    return


if __name__ == "__main__":
    app.run()
