"""Cleanup and forced-rerun preservation for corpus runs."""

import json
import shutil
from pathlib import Path
from uuid import uuid4

from apb_studio.corpus.models import Operation, write_record
from apb_studio.disk import interprocess_file_lock


def saved_run_roots(store: Path) -> list[Path]:
    """Return current and legacy corpus run directories in deterministic order."""
    manifests = {
        *store.glob("*/run.json"),
        *store.glob("*/*/*/run.json"),
    }
    return sorted(
        (manifest.parent for manifest in manifests),
        key=lambda path: str(path.relative_to(store)),
    )


def _data_root(root: Path) -> Path:
    """Read the one manifest field the fixture-overlap guard needs.

    Cleaning must stay available for runs recorded under an older manifest schema, so this
    reads `data_root` directly instead of validating the whole document. An absent or
    non-absolute value is refused rather than assumed safe.
    """
    payload = json.loads((root / "run.json").read_text())
    value = payload.get("data_root")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{root / 'run.json'} records no data_root; refusing to clean")
    data_root = Path(value)
    if not data_root.is_absolute():
        raise ValueError(f"Recorded data_root is not absolute: {value}")
    return data_root.resolve()


def _validated_root(root: Path) -> Path:
    """Resolve one run directory and prove it cannot overlap fixture inputs."""
    requested = root.absolute()
    if requested.is_symlink():
        raise ValueError(f"Refusing a symlinked run directory: {requested}")
    resolved = requested.resolve()
    data_root = _data_root(resolved)
    if resolved == data_root or resolved in data_root.parents or data_root in resolved.parents:
        raise ValueError("Run directory overlaps fixture inputs")
    return resolved


def archive_results(root: Path) -> Path:
    """Move generated results before a forced rerun; called under its execution lock."""
    root = _validated_root(root)
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


def delete_run(root: Path) -> Path:
    """Delete one explicitly selected run without touching fixtures or saved settings."""
    if not (root / "run.json").is_file():
        raise FileNotFoundError(f"No corpus run manifest: {root / 'run.json'}")
    with interprocess_file_lock(root / "run.lock"):
        root = _validated_root(root)
        shutil.rmtree(root)
        return root
