"""Remove every managed corpus artifact through the packaged Snakemake clean rule."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cyclopts import App
from loguru import logger

from apb_studio.execution import SNAKEFILE, prepare_run, snakemake_argv
from apb_studio.pipeline import load_pipeline
from apb_studio.registry import DEFAULT_PIPELINE, available_pipelines

app = App(name="clean-corpus")


@app.default
def clean_corpus(*, pipeline: str = DEFAULT_PIPELINE, settings: Path | None = None) -> None:
    """Clean the whole corpus headlessly.

    The packaged Snakefile refuses to load without a Corpus Runner-generated ``run.json``, and its
    clean rule deletes the target inventory frozen into that snapshot, so the snapshot is minted
    first. Fixture inputs and persisted run history are never part of the clean.

    Parameters
    ----------
    pipeline
        Which pipeline's artifacts to remove. The default clears everything both converters
        can produce; a narrower pipeline clears only its own stages.
    settings
        Alternative settings file. Defaults to the settings shared by both applications.
    """
    if pipeline not in available_pipelines():
        raise SystemExit(
            f"Unknown pipeline {pipeline!r}; available: {', '.join(available_pipelines())}"
        )
    snapshot, run_path, targets = prepare_run(
        pipeline=load_pipeline(pipeline),
        operation="clean",
        settings_path=settings,
    )
    logger.info(
        "Cleaning {} managed stages of pipeline {!r} under {}",
        len(targets),
        pipeline,
        snapshot.output_root,
    )
    command = snakemake_argv(SNAKEFILE, run_path, targets=[Path("clean")], cores=1)
    completed = subprocess.run(command, cwd=SNAKEFILE.parent, check=False)
    if completed.returncode != 0:
        logger.error("Snakemake clean failed with exit code {}", completed.returncode)
        raise SystemExit(completed.returncode)
    logger.success("Corpus clean complete")


if __name__ == "__main__":
    app()
