"""Artifact declarations shared by the concrete corpus workflows."""

from __future__ import annotations

from pathlib import Path

from apb_studio.corpus.models import Artifact, StorageFormat

REPRESENTATION_SUFFIX = ".apb.json"
_RESULT_SUFFIXES: dict[StorageFormat, str] = {
    "hdf5": ".h5mu",
    "parquet": ".parquet",
    "duckdb": ".duckdb",
}
_SINGLE_LEVEL_SUFFIXES: dict[StorageFormat, str] = {
    **_RESULT_SUFFIXES,
    "hdf5": ".h5ad",
}


def result_path(directory: Path, stem: str, storage_format: StorageFormat, /) -> Path:
    """Build one multi-level APB result path in the selected storage format."""
    return directory / f"{stem}{_RESULT_SUFFIXES[storage_format]}"


def single_level_result_path(
    directory: Path,
    stem: str,
    storage_format: StorageFormat,
    /,
) -> Path:
    """Build one single-level APB result path in the selected storage format."""
    return directory / f"{stem}{_SINGLE_LEVEL_SUFFIXES[storage_format]}"


def representation(path: Path, /) -> Artifact:
    """Declare the APB JSON sidecar emitted beside one scientific result."""
    return Artifact(
        role="representation",
        path=path.with_name(f"{path.name}{REPRESENTATION_SUFFIX}"),
    )
