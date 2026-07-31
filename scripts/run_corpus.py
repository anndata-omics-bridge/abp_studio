"""Run managed corpus stages headlessly through the packaged Snakemake workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cyclopts import App
from loguru import logger

from apb_studio.execution import SNAKEFILE, prepare_run, snakemake_argv
from apb_studio.pipeline import sample_fixture_targets

app = App(name="run-corpus")

DEFAULT_FIXTURES = 10
DEFAULT_CORES = 10


@app.default
def run_corpus(
    *,
    fixtures: int = DEFAULT_FIXTURES,
    cores: int = DEFAULT_CORES,
    dry_run: bool = False,
    settings: Path | None = None,
) -> None:
    """Run the corpus headlessly over a representative fixture sample.

    The default ten-fixture sample is the routine gate after a refactor: it is minutes of
    wall clock, against about an hour for the whole catalogue. Pass ``--fixtures 0`` for a
    whole-corpus run, which is a release-level check rather than a per-change one.

    The packaged Snakefile refuses to load without a Corpus Runner-generated ``run.json``,
    so the snapshot is minted first and always describes the complete inventory; only the
    requested Snakemake targets are narrowed, which is the same mechanism the dashboard's
    whole-corpus launch uses.

    Parameters
    ----------
    fixtures
        Number of fixtures to run, spread across vendors. ``0`` runs the whole corpus.
    cores
        Snakemake cores.
    dry_run
        Resolve the DAG and report what would run without executing it. Use this after a
        completed run to confirm a fresh snapshot schedules zero jobs.
    settings
        Alternative settings file. Defaults to the settings shared by both applications.
    """
    snapshot, run_path, all_targets = prepare_run(operation="run", settings_path=settings)
    selected = sample_fixture_targets(all_targets, fixtures)
    if not selected:
        raise SystemExit("No runnable corpus stages were selected.")

    sampled_fixtures = {(target.module, target.dataset) for target in selected}
    total_fixtures = {(target.module, target.dataset) for target in all_targets}
    logger.info(
        "{} {} stage(s) across {}/{} fixture(s) under {}",
        "Checking" if dry_run else "Running",
        len(selected),
        len(sampled_fixtures),
        len(total_fixtures),
        snapshot.output_root,
    )
    if len(sampled_fixtures) < len(total_fixtures):
        logger.info(
            "Sampled {} of {} fixtures ({} stage(s) not requested); "
            "pass --fixtures 0 for the whole corpus",
            len(sampled_fixtures),
            len(total_fixtures),
            len(all_targets) - len(selected),
        )

    command = snakemake_argv(
        SNAKEFILE,
        run_path,
        targets=[target.output for target in selected],
        cores=cores,
        dry_run=dry_run,
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


if __name__ == "__main__":
    app()
