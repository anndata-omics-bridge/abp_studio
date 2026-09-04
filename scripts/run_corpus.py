"""Run managed corpus stages headlessly through the packaged Snakemake workflow."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from loguru import logger

from apb_studio import settings as studio_settings
from apb_studio.execution import SNAKEFILE, prepare_run, snakemake_argv
from apb_studio.pipeline import (
    Target,
    dataset_names,
    level_names,
    level_targets,
    load_pipeline,
    sample_fixture_targets,
    selected_dataset_targets,
)
from apb_studio.registry import DEFAULT_PIPELINE, available_pipelines

app = App(name="run-corpus")

WHOLE_CORPUS = 0
DEFAULT_CORES = 10


@dataclass(frozen=True, slots=True)
class CorpusRunOptions:
    """Flat Cyclopts option group for the headless corpus runner.

    Grouped rather than spelled as nine parameters, matching ``apb2.cli.ConvertCliOptions``.
    """

    pipeline: str = DEFAULT_PIPELINE
    datasets: Path | None = None
    level: tuple[str, ...] = ()
    fixtures: int = WHOLE_CORPUS
    cores: int = DEFAULT_CORES
    dry_run: bool = False
    force: bool = False
    output_root: Path | None = None
    settings: Path | None = None


DEFAULT_CORPUS_RUN_OPTIONS = CorpusRunOptions()


@app.default
def run_corpus(
    options: Annotated[CorpusRunOptions, Parameter(name="*")] = DEFAULT_CORPUS_RUN_OPTIONS,
) -> None:
    """Run one pipeline headlessly over the corpus, or over a named part of it.

    With no selection this runs everything the pipeline covers. Narrow it by naming datasets in a
    file (--datasets), by level (--level ion --level mudata, repeatable), or both; --fixtures N
    still takes a vendor-spread sample of whatever is selected, and every narrowed run logs the
    datasets it covered so a result can be repeated.

    --datasets takes one name per line, either a dataset alias (diann-300beac4) or a
    module-qualified one (Results_quant_ion_DDA/diann-300beac4); # comments and blank lines are
    ignored. A name matching nothing is reported and the rest still run.

    --pipeline selects the converters and stages. --force re-runs selected work whose artifacts
    already exist, which is how an already-converted corpus can be timed again. --dry-run resolves
    the DAG without executing it. --output-root sets the output root shared by both applications,
    the same field the Corpus Runner's path box edits. --settings points at an alternative settings
    file. --cores is Snakemake's core count.

    The packaged Snakefile refuses to load without a Corpus Runner-generated run.json, so the
    snapshot is minted first and always describes the complete inventory; only the requested
    Snakemake targets are narrowed, which is the same mechanism the dashboard's whole-corpus launch
    uses.
    """
    if options.pipeline not in available_pipelines():
        raise SystemExit(
            f"Unknown pipeline {options.pipeline!r}; available: {', '.join(available_pipelines())}"
        )
    if options.output_root is not None:
        studio_settings.update_settings(output_root=options.output_root, path=options.settings)
    selection = load_pipeline(options.pipeline)
    snapshot, run_path, all_targets = prepare_run(
        pipeline=selection,
        operation="run",
        settings_path=options.settings,
    )
    selected = _narrow(
        all_targets,
        datasets=options.datasets,
        levels=list(options.level),
        fixtures=options.fixtures,
    )
    if not selected:
        raise SystemExit("No runnable corpus stages were selected.")

    covered = dataset_names(selected)
    logger.info(
        "{} pipeline {!r} ({} × {}) — {} stage(s), {} dataset(s), level(s) {} under {}",
        "Checking" if options.dry_run else "Running",
        selection.name,
        " · ".join(selection.stage_names),
        " · ".join(selection.converters),
        len(selected),
        len(covered),
        ", ".join(level_names(selected)),
        snapshot.output_root,
    )
    if len(selected) < len(all_targets):
        # Always say which datasets ran. A sample nobody can name is a result nobody can repeat.
        for name in covered:
            logger.info("  {}", name)

    command = snakemake_argv(
        SNAKEFILE,
        run_path,
        targets=[target.output for target in selected],
        cores=options.cores,
        dry_run=options.dry_run,
        force=options.force,
    )
    # Inherit the caller's working directory rather than running from SNAKEFILE.parent.
    # Snakemake keeps its incremental metadata in ``.snakemake`` beside the working
    # directory, and the dashboard runs from the project root (see "Working directory" in
    # any dashboard log). Running from the package directory would keep a second, divergent
    # copy, so each entry point would treat the other's outputs as stale. Every path in
    # run.json is absolute, so the working directory has no other effect.
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        logger.error("Snakemake run failed with exit code {}", completed.returncode)
        raise SystemExit(completed.returncode)
    logger.success("Corpus run complete")


def _narrow(
    targets: list[Target],
    *,
    datasets: Path | None,
    levels: list[str] | None,
    fixtures: int,
) -> list[Target]:
    """Apply the requested selections in order: named datasets, then levels, then sampling."""
    selected = targets
    if datasets is not None:
        selected, unmatched = selected_dataset_targets(selected, read_dataset_names(datasets))
        for name in unmatched:
            logger.warning("No dataset named {!r} is in this corpus", name)
        if not selected:
            raise SystemExit(f"No dataset in {datasets} matches this corpus.")
    if levels:
        selected = level_targets(selected, levels)
        if not selected:
            raise SystemExit(f"No selected dataset converts level(s) {', '.join(levels)}.")
    return sample_fixture_targets(selected, fixtures)


def read_dataset_names(path: Path) -> list[str]:
    """Read one dataset name per line, ignoring blank lines and ``#`` comments."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [stripped for line in lines if (stripped := line.split("#", 1)[0].strip())]


if __name__ == "__main__":
    app()
