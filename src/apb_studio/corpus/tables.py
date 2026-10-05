"""Minimal delimited inputs and explicit workflow-owned joins."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from pathlib import Path

from apb_studio.corpus.models import Dataset, InputMetadata
from apb_studio.disk import atomic_write_text

CORPUS_COLUMNS = ("input_file", "vendor_parameter_file", "module", "software_name")
INPUT_METADATA_COLUMNS = ("input_file", "input_file_size_bytes")
DOWNLOAD_INPUT_COLUMN = "input_file_path"
DOWNLOAD_SIZE_COLUMN = "input_file_size_bytes"


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read CSV or TSV strings without guessing numbers, booleans or missing values."""
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"Missing or duplicate delimited headers: {path}")
        rows: list[dict[str, str]] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed delimited row {reader.line_num}: {path}")
            rows.append(dict(row))
        return rows


def write_rows(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    """Write a CSV atomically, preserving column order and quoting paths."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, stream.getvalue())


def load_corpus(path: Path) -> list[Dataset]:
    """Validate the exact corpus schema and unique input-file key."""
    with path.open(encoding="utf-8", newline="") as stream:
        if next(csv.reader(stream), []) != list(CORPUS_COLUMNS):
            raise ValueError(f"{path} must have exactly {','.join(CORPUS_COLUMNS)}")
    datasets = [Dataset.model_validate(row) for row in read_rows(path)]
    keys = [row.input_file for row in datasets]
    if len(set(keys)) != len(keys):
        raise ValueError(f"Duplicate input_file in {path}")
    return datasets


def resolve_file(root: Path, value: str) -> Path:
    """Resolve a file path within the explicit data root; presence is checked at execution."""
    if not value:
        raise ValueError(f"Empty file path below data root {root}")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"File path escapes data root: {value}")
    return path


def resolve_secondary_inputs(root: Path, value: str) -> tuple[Path, ...]:
    """Find fixture-owned secondary inputs derived from the primary input filename.

    A folder input has none: APB reads the related tables inside it by their own names.
    """
    primary = resolve_file(root, value)
    if primary.is_dir():
        return ()
    return tuple(
        path.resolve()
        for path in sorted(primary.parent.glob(f"{primary.stem}_*"))
        if path.is_file()
    )


def join_workflow(row: Mapping[str, str], table: Path, *, on: Sequence[str]) -> dict[str, str]:
    """Require one matching row using explicit keys and a unique right-hand table."""
    if not on or any(key not in row for key in on):
        raise ValueError(f"Invalid explicit join columns: {list(on)}")
    indexed: dict[tuple[str, ...], dict[str, str]] = {}
    for candidate in read_rows(table):
        if any(not candidate.get(key) for key in on):
            raise ValueError(f"Missing join column/value {list(on)} in {table}")
        key = tuple(candidate[column] for column in on)
        if key in indexed:
            raise ValueError(f"Duplicate workflow join key {key} in {table}")
        indexed[key] = candidate
    wanted = tuple(row[column] for column in on)
    if wanted not in indexed:
        raise ValueError(f"No workflow row for {dict(zip(on, wanted, strict=True))} in {table}")
    return indexed[wanted]


def join_input_metadata(rows: Sequence[Dataset], downloads: Path) -> list[InputMetadata]:
    """Join selected corpus inputs to acquisition sizes using explicit column names."""
    download_rows = read_rows(downloads)
    if not download_rows:
        raise ValueError(f"No download metadata rows in {downloads}")
    required = {DOWNLOAD_INPUT_COLUMN, DOWNLOAD_SIZE_COLUMN}
    missing_columns = required - download_rows[0].keys()
    if missing_columns:
        raise ValueError(f"Missing download columns {sorted(missing_columns)} in {downloads}")
    selected = {row.input_file for row in rows}
    indexed: dict[str, str] = {}
    for candidate in download_rows:
        key = candidate[DOWNLOAD_INPUT_COLUMN]
        if key not in selected:
            continue
        if key in indexed:
            raise ValueError(f"Duplicate download join key {key!r} in {downloads}")
        indexed[key] = candidate[DOWNLOAD_SIZE_COLUMN]
    result: list[InputMetadata] = []
    for row in rows:
        if row.input_file not in indexed:
            raise ValueError(
                f"No download row for corpus input_file={row.input_file!r} "
                f"using downloads.{DOWNLOAD_INPUT_COLUMN} in {downloads}"
            )
        value = indexed[row.input_file]
        try:
            size = int(value)
        except ValueError as error:
            raise ValueError(
                f"Invalid downloads.{DOWNLOAD_SIZE_COLUMN}={value!r} "
                f"for {row.input_file!r} in {downloads}"
            ) from error
        result.append(InputMetadata(input_file=row.input_file, input_file_size_bytes=size))
    return result
