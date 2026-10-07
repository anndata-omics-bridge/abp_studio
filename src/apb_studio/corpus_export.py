"""Acquisition-side export of existing files for independent corpus execution."""

from collections.abc import Collection, Iterable
from pathlib import Path

from apb_studio.corpus.tables import CORPUS_COLUMNS, read_rows, write_rows
from apb_studio.fixture_store import Store
from apb_studio.zenodo_fixtures import ZenodoRecord, corpus_rows


def _local_inputs(store: Store, entries: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Describe unambiguous local vendor inputs, with their parameter file when present."""
    rows: list[dict[str, str]] = []
    for entry in entries:
        folder = store.submission_dir(entry["repo_name"], entry["intermediate_hash"])
        inputs = [path for path in folder.glob("input_file.*") if path.is_file()]
        parameters = [path for path in folder.glob("param_0.*") if path.is_file()]
        if len(inputs) != 1 or len(parameters) > 1:
            continue
        rows.append({
            "input_file": inputs[0].relative_to(store.root).as_posix(),
            "vendor_parameter_file": (
                parameters[0].relative_to(store.root).as_posix() if parameters else ""
            ),
            "module": entry["module"],
            "software_name": entry["software_name"],
        })
    return rows


def export_all_corpus(store: Store, target: Path, records: Collection[ZenodoRecord]) -> Path:
    """Rebuild all from acquired ProteoBench inputs and complete configured Zenodo datasets.

    Source metadata and files are authoritative; an older generated inventory is never
    reused. A local vendor input may have no parameters, as may a configured Zenodo input.
    """
    entries = read_rows(store.catalog_csv) if store.catalog_csv.is_file() else []
    rows = _local_inputs(store, entries)
    rows.extend(row for record in records for row in corpus_rows(store, record))
    by_input: dict[str, dict[str, str]] = {}
    for row in rows:
        by_input.setdefault(row["input_file"], row)
    write_rows(target, CORPUS_COLUMNS, [by_input[key] for key in sorted(by_input)])
    return target


def export_corpus(
    store: Store,
    target: Path,
    *,
    modules: Collection[str],
    selection_column: str | None = None,
) -> Path:
    """Export the named modules' existing input/parameter pairs, optionally flag-selected."""
    entries = (
        entry
        for entry in read_rows(store.catalog_csv)
        if entry["module"] in modules
        and (selection_column is None or _catalog_flag(entry, selection_column))
    )
    rows = [row for row in _local_inputs(store, entries) if row["vendor_parameter_file"]]
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
