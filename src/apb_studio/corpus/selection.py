"""Resolve a corpus's dataset keys against the fixture manifest, ``downloads.csv``.

A corpus names datasets; the fixture manifest says where each one is stored, with what
parameter file, module and software. Every path a run uses therefore comes from the files
the fixture wrote, plain or gzipped, and never from the corpus file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from apb_studio.corpus.models import Dataset
from apb_studio.corpus.tables import read_rows
from apb_studio.fixture_store import DOWNLOAD_COLUMNS, DOWNLOADED


@dataclass(frozen=True, slots=True)
class Selection:
    """The datasets one corpus selects, in corpus order, and which of them are missing."""

    datasets: list[Dataset]
    not_downloaded: frozenset[str]
    """Keys of selected datasets the fixture has not stored."""


def resolve_corpus(keys: Sequence[str] | None, downloads: Path) -> Selection:
    """Resolve corpus keys, or every downloaded dataset when ``keys`` is ``None``.

    A downloaded dataset resolves to its stored input and parameter files. One not
    downloaded resolves to its store folder with no parameter file, so it keeps a stable
    identity in the run while its report says ``not_downloaded``.

    Raises:
        ValueError: The manifest is absent or malformed, or a key is not in it.
    """
    if not downloads.is_file():
        raise ValueError(f"No fixture manifest {downloads}; run `fixture download NAME` first")
    manifest = read_rows(downloads)
    if manifest and tuple(manifest[0]) != DOWNLOAD_COLUMNS:
        raise ValueError(f"{downloads} must have exactly {','.join(DOWNLOAD_COLUMNS)}")
    by_key = {row["dataset"]: row for row in manifest}
    selected = (
        [key for key, row in by_key.items() if row["status"] == DOWNLOADED]
        if keys is None
        else list(keys)
    )
    unknown = [key for key in selected if key not in by_key]
    if unknown:
        raise ValueError(f"Datasets unknown to the fixture manifest {downloads}: {unknown}")
    return Selection(
        datasets=[_dataset(by_key[key]) for key in selected],
        not_downloaded=frozenset(key for key in selected if by_key[key]["status"] != DOWNLOADED),
    )


def _dataset(row: Mapping[str, str]) -> Dataset:
    downloaded = row["status"] == DOWNLOADED
    return Dataset(
        dataset=row["dataset"],
        input_file=row["input_file_path"] if downloaded else row["dataset_dir"],
        vendor_parameter_file=row["vendor_parameter_file_path"] if downloaded else "",
        module=row["module"],
        software_name=row["software_name"],
    )
