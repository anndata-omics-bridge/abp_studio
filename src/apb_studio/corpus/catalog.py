"""Filesystem-backed catalog for the corpus viewer."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

_VISIBLE_OPERATION_STATUSES = frozenset({"running", "succeeded", "failed", "interrupted"})
_SCIENTIFIC_OUTPUT_ROLES = frozenset({"result", "converted", "aggregated", "export"})


def build_catalog(root: Path) -> dict[str, Any]:
    """Describe visible stable corpus/workflow/format run directories."""
    runs = sorted(path for path in root.glob("*/*/*/run.json") if _is_visible(path))
    return {
        "schema_version": 2,
        "store_root": str(root.resolve()),
        "runs": [str(path.relative_to(root)) for path in runs],
        "output_extensions": {
            str(path.relative_to(root)): _run_output_extensions(path) for path in runs
        },
    }


@lru_cache(maxsize=16384)
def _report_output_extensions(path: Path, _mtime_ns: int, _size: int) -> tuple[str, ...]:
    """Read one report once per file revision; logs need not be parsed on every poll."""
    report = _read_object(path)
    if report is None or not isinstance(report.get("steps"), list):
        return ()
    latest: str | None = None
    for step in report["steps"]:
        if not isinstance(step, dict) or step.get("status") != "succeeded":
            continue
        outputs = step.get("outputs")
        if not isinstance(outputs, list):
            continue
        for artifact in outputs:
            if not isinstance(artifact, dict):
                continue
            size = artifact.get("size_bytes")
            output = artifact.get("path")
            role = artifact.get("role")
            if (
                isinstance(role, str)
                and role in _SCIENTIFIC_OUTPUT_ROLES
                and isinstance(output, str)
                and isinstance(size, (int, float))
                and not isinstance(size, bool)
                and math.isfinite(size)
                and size >= 0
            ):
                latest = Path(output.rstrip("/")).suffix.lower()
    return (latest,) if latest else ()


def _extensions_for_report(directory: Path, reference: object) -> tuple[str, ...] | None:
    """Resolve a saved report inside this run, distinguishing absent and empty evidence."""
    if not isinstance(reference, str) or not reference:
        return None
    path = (directory / reference).resolve()
    if not path.is_relative_to(directory.resolve()):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return _report_output_extensions(path, stat.st_mtime_ns, stat.st_size)


def _run_output_extensions(manifest: Path) -> list[str]:
    """Summarize the final observed scientific output of each dataset, including live progress."""
    run = _read_object(manifest)
    if run is None or not isinstance(run.get("reports"), list):
        return []
    extensions: set[str] = set()
    for report in run["reports"]:
        if not isinstance(report, dict):
            continue
        found = _extensions_for_report(manifest.parent, report.get("path"))
        if found is None:
            found = _extensions_for_report(manifest.parent, report.get("progress"))
        if found is not None:
            extensions.update(found)
    return sorted(extensions)


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
