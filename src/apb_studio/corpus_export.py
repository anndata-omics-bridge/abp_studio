"""Acquisition-side export of existing files for independent corpus execution."""

from collections.abc import Collection
from pathlib import Path

from apb_studio.corpus.tables import CORPUS_COLUMNS, read_rows, write_rows
from apb_studio.fixture_store import Store


def export_corpus(
    store: Store,
    target: Path,
    *,
    modules: Collection[str],
    selection_column: str | None = None,
) -> Path:
    """Export the named modules' existing input/parameter pairs, optionally flag-selected."""
    rows: list[dict[str, str]] = []
    for entry in read_rows(store.catalog_csv):
        if entry["module"] not in modules:
            continue
        if selection_column is not None and not _catalog_flag(entry, selection_column):
            continue
        folder = store.submission_dir(entry["repo_name"], entry["intermediate_hash"])
        inputs = [path for path in folder.glob("input_file.*") if path.is_file()]
        parameters = [path for path in folder.glob("param_0.*") if path.is_file()]
        if len(inputs) != 1 or len(parameters) != 1:
            continue
        rows.append({
            "input_file": inputs[0].relative_to(store.root).as_posix(),
            "vendor_parameter_file": parameters[0].relative_to(store.root).as_posix(),
            "module": entry["module"],
            "software_name": entry["software_name"],
        })
    write_rows(target, CORPUS_COLUMNS, rows)
    return target


def _catalog_flag(entry: dict[str, str], column: str) -> bool:
    """Read one generated catalog boolean without accepting ambiguous values."""
    if column not in entry:
        raise ValueError(f"Catalog has no selection column {column!r}")
    value = entry[column].casefold()
    if value not in {"true", "false"}:
        raise ValueError(f"Catalog selection {column!r} must contain only true/false values")
    return value == "true"
