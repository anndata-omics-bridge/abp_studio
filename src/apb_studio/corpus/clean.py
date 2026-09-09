"""Recoverable cleanup of one explicitly selected corpus run."""

import shutil
from pathlib import Path
from uuid import uuid4

from apb_studio.corpus.models import Operation, RunManifest, write_record


def archive_results(root: Path) -> Path:
    """Move generated results into history; called under the run's execution lock."""
    root = root.resolve()
    manifest = RunManifest.model_validate_json((root / "run.json").read_text())
    if (
        root == manifest.data_root
        or root in manifest.data_root.parents
        or manifest.data_root in root.parents
    ):
        raise ValueError("Run directory overlaps fixture inputs")
    paths = [
        root / name
        for name in (
            "reports",
            "artifacts",
            "corpus_index.json",
            "operation.json",
            "snakemake.log",
        )
    ]
    if any(path.is_symlink() for path in paths):
        raise ValueError("Refusing symlinks in managed run paths")
    history = root / "history" / uuid4().hex
    for path in paths:
        if path.exists():
            history.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), history / path.name)
    write_record(root / "operation.json", Operation(status="cleaned"))
    return history
