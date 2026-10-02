"""Filesystem-backed catalog for the corpus viewer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_VISIBLE_OPERATION_STATUSES = frozenset({"running", "succeeded", "failed", "interrupted"})


def build_catalog(root: Path) -> dict[str, Any]:
    """Describe visible stable corpus/workflow/format run directories."""
    runs = sorted(path for path in root.glob("*/*/*/run.json") if _is_visible(path))
    return {
        "schema_version": 2,
        "store_root": str(root.resolve()),
        "runs": [str(path.relative_to(root)) for path in runs],
    }


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _is_visible(manifest: Path) -> bool:
    run = _read_object(manifest)
    operation = _read_object(manifest.parent / "operation.json")
    if run is None or operation is None:
        return False
    return run.get("schema_version") == 2 and operation.get("status") in _VISIBLE_OPERATION_STATUSES
