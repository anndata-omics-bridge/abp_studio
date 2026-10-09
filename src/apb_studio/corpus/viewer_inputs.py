"""Fixture facts a run records for the viewer, so a plain file server can serve it.

The viewer cannot inspect the fixture store itself: it learns whether each input is a file or
a folder, and what ProteoBench reported for each submission, from these two run files.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from apb_studio.corpus.models import Dataset
from apb_studio.corpus.tables import resolve_file
from apb_studio.disk import atomic_write_text
from apb_studio.fixture_store import Store

INPUT_KINDS_NAME = "input_kinds.json"
REFERENCES_NAME = "proteobench_references.json"


def write_viewer_inputs(root: Path, rows: Sequence[Dataset], data_root: Path) -> None:
    """Record each selected input's kind and downloaded ProteoBench JSON in the run folder."""
    _write_json(
        root / INPUT_KINDS_NAME,
        {"schema_version": 2, "input_kinds": _input_kinds(rows, data_root)},
    )
    _write_json(
        root / REFERENCES_NAME,
        {"schema_version": 2, "references": _references(rows, data_root)},
    )


def _write_json(path: Path, document: dict[str, object]) -> None:
    atomic_write_text(path, json.dumps(document, indent=2, allow_nan=False) + "\n")


def _input_kinds(rows: Sequence[Dataset], data_root: Path) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for row in rows:
        target = resolve_file(data_root, row.input_file)
        if target.is_file():
            kinds[row.input_file] = "file"
        elif target.is_dir():
            kinds[row.input_file] = "folder"
    return kinds


def _references(rows: Sequence[Dataset], data_root: Path) -> dict[str, dict[str, object]]:
    """Each submission's downloaded JSON, keyed by input; NaN becomes null for browsers."""
    root = data_root.resolve()
    store = Store(root)
    references: dict[str, dict[str, object]] = {}
    for row in rows:
        parts = resolve_file(root, row.input_file).relative_to(root).parts
        if len(parts) < 3 or parts[0] != "submissions":
            continue
        metadata = store.metadata_json(parts[1], parts[2]).relative_to(root).as_posix()
        target = resolve_file(root, metadata)
        if not target.is_file():
            continue
        document: object = json.loads(
            target.read_text(encoding="utf-8"), parse_constant=lambda _value: None
        )
        if not isinstance(document, dict) or document.get("intermediate_hash") != parts[2]:
            continue
        references[row.input_file] = {"path": metadata, "document": document}
    return references
