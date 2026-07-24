"""Persist Corpus Runner operation state beside each immutable run snapshot."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from apb_studio.disk import atomic_write_text

OperationKind = Literal["run", "clean"]
OperationStatus = Literal["starting", "running", "succeeded", "failed"]
OPERATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class OperationRecord:
    """Durable state for one Snakemake run or clean operation."""

    schema_version: int
    operation: OperationKind
    status: OperationStatus
    started_at: str
    finished_at: str | None = None
    pid: int | None = None


def operation_path(run_path: Path | str) -> Path:
    """Return the operation-state path adjacent to one generated ``run.json``."""
    return Path(run_path).parent / "operation.json"


def start_operation(
    run_path: Path | str,
    operation: OperationKind,
    *,
    started_at: str | None = None,
) -> OperationRecord:
    """Create the initial durable record for a Snakemake operation."""
    record = OperationRecord(
        schema_version=OPERATION_SCHEMA_VERSION,
        operation=operation,
        status="starting",
        started_at=started_at or _now(),
    )
    _write_record(run_path, record)
    return record


def set_operation_pid(run_path: Path | str, pid: int) -> OperationRecord:
    """Persist the launched Snakemake process ID without changing its status."""
    record = _required_record(run_path)
    updated = replace(record, pid=pid)
    _write_record(run_path, updated)
    return updated


def mark_operation(
    run_path: Path | str,
    status: OperationStatus,
    *,
    finished_at: str | None = None,
) -> OperationRecord | None:
    """Update an existing operation record; plain CLI runs without one remain untouched."""
    record = load_operation(run_path)
    if record is None:
        return None
    terminal = status in {"succeeded", "failed"}
    updated = replace(
        record,
        status=status,
        finished_at=(finished_at or _now()) if terminal else None,
    )
    _write_record(run_path, updated)
    return updated


def load_operation(run_path: Path | str) -> OperationRecord | None:
    """Load and validate one operation record, returning ``None`` for legacy runs."""
    path = operation_path(run_path)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Operation record must contain one JSON object: {path}")
    version = data.get("schema_version")
    if version != OPERATION_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported operation schema version {version!r}; "
            f"expected {OPERATION_SCHEMA_VERSION}."
        )
    operation = data.get("operation")
    if operation not in {"run", "clean"}:
        raise ValueError(f"Invalid corpus operation {operation!r}: {path}")
    status = data.get("status")
    if status not in {"starting", "running", "succeeded", "failed"}:
        raise ValueError(f"Invalid corpus operation status {status!r}: {path}")
    started_at = data.get("started_at")
    if not isinstance(started_at, str) or not started_at:
        raise ValueError(f"Operation record has no start time: {path}")
    finished_at = data.get("finished_at")
    if finished_at is not None and not isinstance(finished_at, str):
        raise ValueError(f"Operation record has an invalid finish time: {path}")
    pid = data.get("pid")
    if pid is not None and (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0):
        raise ValueError(f"Operation record has an invalid process ID: {path}")
    return OperationRecord(
        schema_version=OPERATION_SCHEMA_VERSION,
        operation=operation,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        pid=pid,
    )


def reconcile_operation(run_path: Path | str) -> OperationRecord | None:
    """Mark a recorded active operation failed when its process no longer exists."""
    record = load_operation(run_path)
    if record is None or record.status not in {"starting", "running"}:
        return record
    if record.pid is not None and _process_exists(record.pid):
        return record
    return mark_operation(run_path, "failed")


def _required_record(run_path: Path | str) -> OperationRecord:
    record = load_operation(run_path)
    if record is None:
        raise ValueError(f"No operation record exists beside {Path(run_path)}.")
    return record


def _write_record(run_path: Path | str, record: OperationRecord) -> None:
    path = operation_path(run_path)
    source = json.dumps(asdict(record), indent=2, sort_keys=True)
    atomic_write_text(path, f"{source}\n")


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _now() -> str:
    return datetime.now(UTC).isoformat()
