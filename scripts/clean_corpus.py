"""Remove every managed corpus artifact through the packaged Snakemake clean rule."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cyclopts import App
from loguru import logger

from apb_studio.execution import SNAKEFILE, prepare_run, snakemake_argv

app = App(name="clean-corpus")


@app.default
def clean_corpus(*, settings: Path | None = None) -> None:
    """Clean the whole corpus headlessly.

    The packaged Snakefile refuses to load without a Corpus Runner-generated ``run.json``, and its
    clean rule deletes the target inventory frozen into that snapshot, so the snapshot is minted
    first. Fixture inputs and persisted run history are never part of the clean.

    Parameters
    ----------
    settings
        Alternative settings file. Defaults to the settings shared by both applications.
    """
    snapshot, run_path, targets = prepare_run(operation="clean", settings_path=settings)
    logger.info("Cleaning {} managed stages under {}", len(targets), snapshot.output_root)
    command = snakemake_argv(SNAKEFILE, run_path, targets=[Path("clean")], cores=1)
    completed = subprocess.run(command, cwd=SNAKEFILE.parent, check=False)
    if completed.returncode != 0:
        logger.error("Snakemake clean failed with exit code {}", completed.returncode)
        raise SystemExit(completed.returncode)
    logger.success("Corpus clean complete")


if __name__ == "__main__":
    app()
