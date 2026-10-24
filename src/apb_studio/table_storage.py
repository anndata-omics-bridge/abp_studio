"""How the fixture store keeps vendor tables: as their tools wrote them, or gzipped.

Writing is chosen once per acquisition (``fixture download NAME``, gzipped unless
``--no-gzip``) and passed down as ``PlainTables`` or ``GzipTables``, so download code never
asks which mode it runs in. Reading
needs no mode: a stored table's own ``.gz`` suffix says how to open it. Parameter files,
summaries and every non-table file stay plain, because APB reads parameters as text.
"""

from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

GZIP_SUFFIX = ".gz"
_TEXT_TABLES = frozenset({".tsv", ".txt", ".csv"})
_ZIP_SIGNATURE = b"PK\x03\x04"
_SUBMISSION_TABLES = "input_file*"
"""ProteoBench submission tables: ``input_file.<ext>`` and companions such as
``input_file_secondary.tsv``."""


# ------------------------------------------------------------------------------- writing


@dataclass(frozen=True, slots=True)
class PlainTables:
    """Store vendor tables as the producing tool wrote them."""

    def keep_extracted(self, folder: Path) -> None:
        """Leave an extracted submission's tables as they are."""

    def keep_download(self, download: Path, target: Path, *, table: bool) -> None:
        """Store one record file as ``target``, decompressing a gzipped download."""
        if download.suffix != GZIP_SUFFIX:
            download.replace(target)
            return
        partial_target = target.with_name(target.name + ".part")
        with gzip.open(download, "rb") as compressed, partial_target.open("wb") as plain:
            shutil.copyfileobj(compressed, plain, 1 << 20)
        partial_target.replace(target)
        download.unlink()


@dataclass(frozen=True, slots=True)
class GzipTables:
    """Store text vendor tables gzipped, as ``<name>.gz``; everything else stays plain."""

    def keep_extracted(self, folder: Path) -> None:
        """Gzip an extracted submission's text tables in place; a workbook stays plain."""
        for path in sorted(folder.glob(_SUBMISSION_TABLES)):
            if path.is_file() and _is_text_table(path):
                _gzip(path)

    def keep_download(self, download: Path, target: Path, *, table: bool) -> None:
        """Keep a table gzipped beside ``target``; store any other file as ``target``.

        A Parquet table stays as written: apb2 refuses gzipped Parquet.
        """
        if not table:
            PlainTables().keep_download(download, target, table=False)
        elif download.suffix == GZIP_SUFFIX:
            download.replace(target.with_name(target.name + GZIP_SUFFIX))
        else:
            download.replace(target)
            if _is_text_table(target):
                _gzip(target)


type TableStorage = PlainTables | GzipTables


def tables_for(gzip_tables: bool) -> TableStorage:
    """Select how one acquisition stores its vendor tables."""
    return GzipTables() if gzip_tables else PlainTables()


def _is_text_table(path: Path) -> bool:
    """Say whether a file is a delimited text table, the only kind stored gzipped."""
    return path.suffix.lower() in _TEXT_TABLES and not _is_workbook(path)


def _is_workbook(path: Path) -> bool:
    """Say whether a file is an Excel workbook, which some submissions name ``.txt``.

    An ``.xlsx`` is a ZIP archive, so it starts with the ZIP signature whatever its name;
    gzipping one gains nothing, and apb2 reads a ``.gz`` only as delimited text.
    """
    with path.open("rb") as stream:
        return stream.read(len(_ZIP_SIGNATURE)) == _ZIP_SIGNATURE


def _gzip(path: Path) -> None:
    """Replace one file by its gzipped copy, written under a temporary name first."""
    target = path.with_name(path.name + GZIP_SUFFIX)
    partial_target = target.with_name(target.name + ".part")
    with path.open("rb") as plain, gzip.open(partial_target, "wb") as compressed:
        shutil.copyfileobj(plain, compressed, 1 << 20)
    partial_target.replace(target)
    path.unlink()


# ------------------------------------------------------------------------------- reading


@dataclass(frozen=True, slots=True)
class PlainTable:
    """A stored table as its tool wrote it."""

    path: Path

    @property
    def name(self) -> str:
        """The file name the tool wrote."""
        return self.path.name

    def open_text(self) -> TextIO:
        """Open the table as UTF-8 text, replacing undecodable bytes."""
        return self.path.open(encoding="utf-8", errors="replace", newline="")


@dataclass(frozen=True, slots=True)
class GzipTable:
    """A stored table gzipped by the fixture store, read as the file its tool wrote."""

    path: Path

    @property
    def name(self) -> str:
        """The file name the tool wrote, without ``.gz``."""
        return self.path.stem

    def open_text(self) -> TextIO:
        """Open the decompressed table as UTF-8 text, replacing undecodable bytes."""
        return gzip.open(self.path, "rt", encoding="utf-8", errors="replace", newline="")


type StoredTable = PlainTable | GzipTable


def stored_table(path: Path) -> StoredTable:
    """Choose how one stored table is read, from its ``.gz`` suffix."""
    return GzipTable(path) if path.suffix == GZIP_SUFFIX else PlainTable(path)


def find_stored_table(folder: Path, name: str) -> StoredTable | None:
    """The table a tool wrote as ``name``, stored plain or gzipped; ``None`` when absent."""
    for candidate in (folder / name, folder / f"{name}{GZIP_SUFFIX}"):
        if candidate.is_file():
            return stored_table(candidate)
    return None
