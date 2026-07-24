"""Tests for durable Corpus Runner operation records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apb_studio import run_history


def _run_path(tmp_path: Path) -> Path:
    path = tmp_path / "runs" / "run-1" / "run.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


def test_operation_lifecycle_round_trip(tmp_path: Path) -> None:
    run_path = _run_path(tmp_path)

    started = run_history.start_operation(
        run_path,
        "run",
        started_at="2026-07-24T10:00:00+00:00",
    )
    assert started.status == "starting"
    assert run_history.operation_path(run_path) == run_path.parent / "operation.json"

    with_pid = run_history.set_operation_pid(run_path, 123)
    assert with_pid.pid == 123
    running = run_history.mark_operation(run_path, "running")
    assert running is not None
    assert running.status == "running"
    assert running.finished_at is None

    completed = run_history.mark_operation(
        run_path,
        "succeeded",
        finished_at="2026-07-24T10:01:00+00:00",
    )
    assert completed is not None
    assert completed.finished_at == "2026-07-24T10:01:00+00:00"
    assert run_history.load_operation(run_path) == completed


def test_legacy_run_has_no_operation_record(tmp_path: Path) -> None:
    run_path = _run_path(tmp_path)

    assert run_history.load_operation(run_path) is None
    assert run_history.mark_operation(run_path, "failed") is None
    with pytest.raises(ValueError, match="No operation record"):
        run_history.set_operation_pid(run_path, 1)


def test_reconcile_marks_disappeared_process_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_path = _run_path(tmp_path)
    run_history.start_operation(run_path, "clean")
    run_history.set_operation_pid(run_path, 123)
    run_history.mark_operation(run_path, "running")

    monkeypatch.setattr(run_history, "_process_exists", lambda _pid: True)
    active = run_history.reconcile_operation(run_path)
    assert active is not None
    assert active.status == "running"
    monkeypatch.setattr(run_history, "_process_exists", lambda _pid: False)
    failed = run_history.reconcile_operation(run_path)
    assert failed is not None
    assert failed.status == "failed"
    assert run_history.reconcile_operation(tmp_path / "legacy.json") is None


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "one JSON object"),
        ({"schema_version": 9}, "schema version"),
        (
            {
                "schema_version": 1,
                "operation": "erase",
                "status": "running",
                "started_at": "now",
            },
            "Invalid corpus operation",
        ),
        (
            {
                "schema_version": 1,
                "operation": "run",
                "status": "paused",
                "started_at": "now",
            },
            "Invalid corpus operation status",
        ),
        (
            {
                "schema_version": 1,
                "operation": "run",
                "status": "running",
                "started_at": "",
            },
            "no start time",
        ),
        (
            {
                "schema_version": 1,
                "operation": "run",
                "status": "failed",
                "started_at": "now",
                "finished_at": 3,
            },
            "invalid finish time",
        ),
        (
            {
                "schema_version": 1,
                "operation": "run",
                "status": "running",
                "started_at": "now",
                "pid": True,
            },
            "invalid process ID",
        ),
    ],
)
def test_invalid_operation_records_are_rejected(
    tmp_path: Path,
    document: object,
    message: str,
) -> None:
    run_path = _run_path(tmp_path)
    run_history.operation_path(run_path).write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        run_history.load_operation(run_path)


def test_process_probe_handles_missing_and_forbidden_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_history.os, "kill", lambda _pid, _signal: None)
    assert run_history._process_exists(1) is True

    def missing(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(run_history.os, "kill", missing)
    assert run_history._process_exists(1) is False

    def forbidden(_pid: int, _signal: int) -> None:
        raise PermissionError

    monkeypatch.setattr(run_history.os, "kill", forbidden)
    assert run_history._process_exists(1) is True
