"""Fixtures published as Zenodo records: what to fetch, where it lands, what it exports.

The records, their files and the corpus rows they become are facts about published data,
so they live in ``config/zenodo.toml`` and are validated here. Every dataset is fetched
with checksum verification and stored decompressed under its own folder, so a corpus row
can name either one vendor table or the folder of related tables APB reads together.
"""

from __future__ import annotations

import gzip
import hashlib
import shutil
import tomllib
from functools import lru_cache, partial
from pathlib import Path
from typing import Self

import requests
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apb_studio.corpus.config import CORPUS_NAME_PATTERN
from apb_studio.fetch import REQUEST_TIMEOUT, fetch_file
from apb_studio.fixture_store import Store

PACKAGED = Path(__file__).parent / "config" / "zenodo.toml"
RECORDS_API = "https://zenodo.org/api/records/"

# downloads.csv keys a Zenodo dataset by ``zenodo/<record>`` and the dataset name, the way
# it keys a ProteoBench submission by results repository and hash.
REPO_PREFIX = "zenodo/"


class ZenodoDataset(BaseModel):
    """One dataset: record files stored in one folder, exported as one corpus row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    module: str = Field(min_length=1)
    software_name: str = Field(min_length=1)
    software_version: str = ""
    files: dict[str, str] = Field(min_length=1)
    input: str | None = None
    parameters: str | None = None

    @model_validator(mode="after")
    def names_are_stored_files(self) -> Self:
        """Require ``input`` and ``parameters`` to name files the dataset stores."""
        for field, value in (("input", self.input), ("parameters", self.parameters)):
            if value is not None and value not in self.files:
                raise ValueError(f"{self.name}: {field} {value!r} is not one of its files")
        for stored in self.files:
            if Path(stored).name != stored:
                raise ValueError(f"{self.name}: stored name {stored!r} must be a plain file name")
        return self


class ZenodoRecord(BaseModel):
    """One published Zenodo record and the datasets it holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=CORPUS_NAME_PATTERN)
    record_id: int = Field(gt=0)
    datasets: tuple[ZenodoDataset, ...] = Field(min_length=1)


class ZenodoConfig(BaseModel):
    """The complete Zenodo fetch configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    records: tuple[ZenodoRecord, ...] = Field(min_length=1)

    def record(self, name: str) -> ZenodoRecord:
        """Return one record's configuration.

        Raises:
            KeyError: No record is configured under that name.
        """
        for record in self.records:
            if record.name == name:
                return record
        raise KeyError(name)


def load_config(path: Path | None = None) -> ZenodoConfig:
    """Load and validate the Zenodo configuration.

    Raises:
        ValueError: A record or a dataset within one record is declared twice.
    """
    source = path if path is not None else PACKAGED
    with source.open("rb") as handle:
        config = ZenodoConfig.model_validate(tomllib.load(handle))
    names = [record.name for record in config.records]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate record name in {source}")
    for record in config.records:
        datasets = [dataset.name for dataset in record.datasets]
        if len(set(datasets)) != len(datasets):
            raise ValueError(f"duplicate dataset name in record {record.name} of {source}")
    return config


@lru_cache(maxsize=1)
def packaged_config() -> ZenodoConfig:
    """Return the packaged configuration, read once."""
    return load_config()


def dataset_input(store: Store, record: ZenodoRecord, dataset: ZenodoDataset) -> Path:
    """Return what a corpus row points at: the named vendor table, or the dataset folder."""
    folder = store.zenodo_dataset_dir(record.name, dataset.name)
    return folder / dataset.input if dataset.input is not None else folder


def is_present(store: Store, record: ZenodoRecord, dataset: ZenodoDataset) -> bool:
    """Say whether every file of one dataset is stored."""
    folder = store.zenodo_dataset_dir(record.name, dataset.name)
    return all((folder / stored).is_file() for stored in dataset.files)


def _check_md5(expected: str, part: Path) -> None:
    """Refuse finished bytes whose MD5 differs from the record's."""
    digest = hashlib.md5(usedforsecurity=False)
    with part.open("rb") as handle:
        for block in iter(partial(handle.read, 1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        part.unlink()
        raise OSError(f"MD5 mismatch for {part.name}: expected {expected}")


def _record_files(record: ZenodoRecord) -> dict[str, tuple[str, str]]:
    """Return ``{file key: (content URL, md5)}`` for one published record."""
    response = requests.get(f"{RECORDS_API}{record.record_id}", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    files: dict[str, tuple[str, str]] = {}
    for entry in response.json()["files"]:
        algorithm, _, digest = str(entry["checksum"]).partition(":")
        if algorithm != "md5":
            raise ValueError(f"record {record.record_id}: unexpected checksum {entry['checksum']}")
        files[str(entry["key"])] = (str(entry["links"]["self"]), digest)
    return files


def _store_file(source: Path, target: Path) -> None:
    """Decompress a gzipped download into place, or move a plain one; drop the download."""
    if source.suffix != ".gz":
        source.replace(target)
        return
    partial_target = target.with_name(target.name + ".part")
    with gzip.open(source, "rb") as compressed, partial_target.open("wb") as plain:
        shutil.copyfileobj(compressed, plain, 1 << 20)
    partial_target.replace(target)
    source.unlink()


def acquire(store: Store, record: ZenodoRecord) -> None:
    """Fetch every dataset of one record that is not yet completely stored.

    Each record file is checked against the record's MD5 before it is decompressed, and a
    stored file is written under a temporary name first, so an interrupted run leaves no
    file that looks finished.
    """
    remote: dict[str, tuple[str, str]] | None = None
    for dataset in record.datasets:
        if is_present(store, record, dataset):
            logger.info("[{}] already present: {}", record.name, dataset.name)
            continue
        if remote is None:
            remote = _record_files(record)
        folder = store.zenodo_dataset_dir(record.name, dataset.name)
        folder.mkdir(parents=True, exist_ok=True)
        for stored, key in dataset.files.items():
            target = folder / stored
            if target.is_file():
                continue
            if key not in remote:
                raise ValueError(f"record {record.record_id} has no file {key!r}")
            url, md5 = remote[key]
            downloaded = fetch_file(url, folder / key, partial(_check_md5, md5))
            _store_file(downloaded, target)
        logger.info("[{}] stored {}", record.name, folder)


def corpus_rows(store: Store, record: ZenodoRecord) -> list[dict[str, str]]:
    """Return one corpus row per completely stored dataset of one record."""
    rows: list[dict[str, str]] = []
    for dataset in record.datasets:
        if not is_present(store, record, dataset):
            continue
        folder = store.zenodo_dataset_dir(record.name, dataset.name)
        rows.append({
            "input_file": dataset_input(store, record, dataset).relative_to(store.root).as_posix(),
            "vendor_parameter_file": (
                (folder / dataset.parameters).relative_to(store.root).as_posix()
                if dataset.parameters is not None
                else ""
            ),
            "module": dataset.module,
            "software_name": dataset.software_name,
        })
    return rows


def _size(path: Path) -> int:
    """Return a file's size, or the summed size of the files directly inside a folder."""
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.iterdir() if child.is_file())


def download_rows(store: Store, config: ZenodoConfig) -> list[dict[str, str]]:
    """Describe every configured Zenodo dataset in the columns of ``downloads.csv``."""
    rows: list[dict[str, str]] = []
    for record in config.records:
        for dataset in record.datasets:
            present = is_present(store, record, dataset)
            source = dataset_input(store, record, dataset)
            rows.append({
                "module": dataset.module,
                "repo_name": f"{REPO_PREFIX}{record.name}",
                "intermediate_hash": dataset.name,
                "software_name": dataset.software_name,
                "software_version": dataset.software_version,
                "input_file_path": source.relative_to(store.root).as_posix() if present else "",
                "input_file_size_bytes": str(_size(source)) if present else "",
                "status": "ok" if present else "not_selected",
            })
    return rows
