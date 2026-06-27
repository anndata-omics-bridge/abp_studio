# apb_studio dashboard — corpus coverage + run/clean triggers.
#
# Run from the repo root in the project env (so `apb_studio` is importable):
#     make ui            # -> marimo edit src/apb_studio/dashboard.py
#
# Scaffold: reads the registry + corpus config and shows coverage from the output tree
# (filesystem-as-database). Wiring scope/stage into specific Snakemake targets and executing
# them as a background job with a live log stream is the next phase (see the plan doc).

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path

    from apb_studio.registry import load_corpus, load_registry

    return Path, load_corpus, load_registry, mo


@app.cell
def _(mo):
    mo.md(
        """
        # apb_studio — corpus dashboard

        Coverage of the conversion pipeline across the corpus, with run/clean triggers.
        State is read from the output tree — a file exists ⇒ that stage is done.
        """
    )
    return


@app.cell
def _(mo):
    # Always shown; its default is used as-is in script mode.
    config_path = mo.ui.text(
        value="config/corpus.example.yaml", label="corpus config", full_width=True
    )
    config_path
    return (config_path,)


@app.cell
def _(Path, config_path, load_corpus, load_registry):
    # The registry is the same file the Snakefile reads — single source of truth.
    registry = load_registry()
    corpus = load_corpus(config_path.value)
    output_root = Path(corpus["output_root"])
    return corpus, output_root, registry


@app.cell
def _(output_root):
    # Expected per-dataset artifacts → existence = done (filesystem-as-database).
    def coverage_rows(corpus):
        rows = []
        for module, m in corpus["modules"].items():
            for ds in m["datasets"]:
                base = output_root / module / ds["name"]
                for level in m["levels"]:
                    rows.append({
                        "module": module, "dataset": ds["name"], "stage": "convert",
                        "artifact": f"{level}.h5ad", "done": (base / f"{level}.h5ad").exists(),
                    })
                rows.append({
                    "module": module, "dataset": ds["name"], "stage": "assemble-mudata",
                    "artifact": "mudata.h5mu", "done": (base / "mudata.h5mu").exists(),
                })
                rows.append({
                    "module": module, "dataset": ds["name"], "stage": "annotate",
                    "artifact": "annotated/*", "done": (base / "annotated").exists(),
                })
        return rows

    return (coverage_rows,)


@app.cell
def _(corpus, coverage_rows):
    rows = coverage_rows(corpus)
    return (rows,)


@app.cell
def _(mo, rows):
    # Top level of the two-level grid: one row per module, per-stage done/total.
    def summarise(rows):
        modules = {}
        for r in rows:
            agg = modules.setdefault(r["module"], {})
            done, total = agg.get(r["stage"], (0, 0))
            agg[r["stage"]] = (done + int(r["done"]), total + 1)
        return [
            {"module": mod, **{st: f"{d}/{t}" for st, (d, t) in stages.items()}}
            for mod, stages in modules.items()
        ]

    summary_table = mo.ui.table(summarise(rows), selection="single", label="Modules")
    mo.vstack([mo.md("## Modules — select one to drill down"), summary_table])
    return (summary_table,)


@app.cell
def _(mo, rows, summary_table):
    # Bottom level: datasets of the selected module.
    selected_module = summary_table.value[0]["module"] if summary_table.value else None
    detail = [r for r in rows if r["module"] == selected_module]
    mo.vstack([
        mo.md(f"## Datasets — {selected_module or '(select a module above)'}"),
        mo.ui.table(detail),
    ])
    return


@app.cell
def _(mo, registry):
    # Controls: scope × stage × verb. Stage options come from the registry (extensible).
    scope = mo.ui.dropdown(["all", "module", "dataset"], value="all", label="scope")
    stage = mo.ui.dropdown(
        ["all"] + [s["name"] for s in registry], value="all", label="stage"
    )
    verb = mo.ui.dropdown(["run", "clean"], value="run", label="verb")
    mo.hstack([scope, stage, verb], justify="start")
    return scope, stage, verb


@app.cell
def _(config_path, mo, scope, stage, verb):
    # Dry-run preview of the command (no execution in the scaffold).
    cmd = ["snakemake", "-s", "workflow/Snakefile", "--configfile", config_path.value]
    cmd += ["--delete-all-output"] if verb.value == "clean" else ["--cores", "all", "-n"]
    mo.vstack([
        mo.md(f"**Would run** (`{scope.value}` / `{stage.value}`):"),
        mo.md(f"```\n{' '.join(cmd)}\n```"),
        mo.callout(
            "Next phase: map scope/stage to concrete targets and execute as a background "
            "job with a live log stream (marimo-background-jobs).",
            kind="info",
        ),
    ])
    return


if __name__ == "__main__":
    app.run()
