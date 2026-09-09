"""Clean a selected V2 run through Snakemake, preserving results in history."""

import subprocess
import sys
from pathlib import Path

from cyclopts import App

from apb_studio.corpus.discovery import SNAKEFILE
from apb_studio.corpus.models import RunManifest
from apb_studio.disk import interprocess_file_lock

app = App(name="clean-corpus")


@app.default
def clean_corpus(run: Path) -> None:
    """Move one run's reports and artifacts to history, keeping its input snapshots."""
    root = run.resolve()
    RunManifest.model_validate_json((root / "run.json").read_text())
    with interprocess_file_lock(root / "run.lock"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "snakemake",
                "clean",
                "--snakefile",
                str(SNAKEFILE),
                "--configfile",
                str(root / "run.json"),
                "--cores",
                "1",
                "--directory",
                str(root),
            ],
            check=True,
        )


if __name__ == "__main__":
    app()
