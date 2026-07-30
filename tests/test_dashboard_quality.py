"""Behavior and failure-path coverage for the corpus dashboard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dash import no_update

from apb_studio import dashboard, pipeline, run_history, settings


def _registry() -> list[dict[str, Any]]:
    return [{"name": "convert", "basket": "converted"}]


def _row(tmp_path: Path, *, state: str = "failed") -> dict[str, Any]:
    log = tmp_path / "failure.log"
    log.write_text("failure details", encoding="utf-8")
    row: dict[str, Any] = {
        "module": "dda",
        "dataset": "fixture",
        "level": "ion",
        "convert": state.upper(),
        "_stage_details": {
            "convert": {
                "state": state,
                "error": "conversion failed",
                "log": str(log),
            }
        },
    }
    row["_row_id"] = dashboard._row_id(row)
    return row


def _selection(row: dict[str, Any]) -> dict[str, str]:
    return {
        "module": "dda",
        "dataset": "fixture",
        "level": "ion",
        "row_id": cast(str, row["_row_id"]),
        "stage": "convert",
    }


def _callback(app: Any, output_fragment: str) -> Any:
    return next(
        entry["callback"].__wrapped__
        for key, entry in app.callback_map.items()
        if output_fragment in key
    )


def test_dashboard_row_loading_and_identity_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dashboard.execution,
        "load_overview",
        lambda *_args, **_kwargs: ([], {}, None, "broken"),
    )
    assert dashboard._load_dashboard_rows() == ([], None, "broken")

    monkeypatch.setattr(
        dashboard.execution,
        "load_overview",
        lambda *_args, **_kwargs: ([], {}, None, None),
    )
    assert "resolve the fixture inventory" in cast(str, dashboard._load_dashboard_rows()[2])

    snapshot = cast(pipeline.RunSnapshot, SimpleNamespace())
    monkeypatch.setattr(
        dashboard.execution,
        "load_overview",
        lambda *_args, **_kwargs: (["target"], {}, snapshot, None),
    )
    monkeypatch.setattr(
        dashboard.pipeline,
        "branch_rows",
        lambda _snapshot, _targets: [{"module": "m", "dataset": "d", "level": "ion"}],
    )
    rows, returned, error = dashboard._load_dashboard_rows()
    assert returned is snapshot
    assert error is None
    assert rows[0]["_row_id"] == '["m","d","ion"]'

    monkeypatch.setattr(
        dashboard.pipeline,
        "branch_rows",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad rows")),
    )
    assert "ValueError: bad rows" in cast(str, dashboard._load_dashboard_rows()[2])


def test_dashboard_selection_resolution(tmp_path: Path) -> None:
    registry = _registry()
    row = _row(tmp_path)
    cell = {"colId": "convert", "rowId": row["_row_id"]}
    assert dashboard._selection_from_click(cell, registry, [row]) == _selection(row)
    assert dashboard._selection_from_click(None, registry, [row]) is None
    assert dashboard._selection_from_click({"colId": "unknown"}, registry, [row]) is None
    assert (
        dashboard._selection_from_click(
            {"colId": "convert", "rowId": object()},
            registry,
            [row],
        )
        is None
    )
    assert (
        dashboard._selection_from_click(
            {"colId": "convert", "rowId": "missing"},
            registry,
            [row],
        )
        is None
    )
    malformed = {**row, "module": ""}
    assert dashboard._selection_from_click(cell, registry, [malformed]) is None

    selection = _selection(row)
    assert cast(dict[str, str], dashboard._find_stage_detail([row], selection))["state"] == "failed"
    assert dashboard._find_stage_detail([row], None) is None
    assert dashboard._find_stage_detail([row], {**selection, "stage": ""}) is None
    assert dashboard._find_stage_detail([], selection) is None
    not_a_detail = {**row, "_stage_details": {"convert": "bad"}}
    assert dashboard._find_stage_detail([not_a_detail], selection) is None


def test_dashboard_stage_rendering_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry()
    row = _row(tmp_path)
    selection = _selection(row)
    detail = cast(dict[str, str], row["_stage_details"]["convert"])

    assert "Converted" in dashboard._stage_heading(selection, registry)
    assert len(dashboard._status_detail({"state": "unsupported"}, selection, registry)) == 3
    assert len(dashboard._status_detail({"state": "failed"}, selection, registry)) == 3
    empty_log = tmp_path / "empty.log"
    empty_log.write_text("", encoding="utf-8")
    failed = dashboard._status_detail(
        {"state": "failed", "log": str(empty_log)},
        selection,
        registry,
    )
    assert len(failed) == 4
    assert len(dashboard._status_detail(detail, selection, registry)) == 5

    artifact = tmp_path / "artifact.h5ad"
    completed = {"state": "completed", "artifact": str(artifact)}
    monkeypatch.setattr(dashboard, "describe_path", lambda _path: {"n_obs": 3})
    assert len(dashboard._render_stage_detail(completed, selection, registry)) == 4
    monkeypatch.setattr(
        dashboard,
        "describe_path",
        lambda _path: (_ for _ in ()).throw(OSError("corrupt")),
    )
    assert len(dashboard._artifact_detail(completed, selection, registry)) == 4
    assert len(dashboard._render_stage_detail(detail, selection, registry)) == 5
    assert len(dashboard._render_stage_detail({"state": "unavailable"}, selection, registry)) == 2
    assert len(dashboard._render_stage_detail({"state": "pending"}, selection, registry)) == 3

    assert dashboard._downloadable_log([row], selection) == Path(detail["log"])
    assert dashboard._downloadable_log([], selection) is None
    assert (
        dashboard._downloadable_log(
            [{**row, "_stage_details": {"convert": {"state": "unsupported"}}}],
            selection,
        )
        is None
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, "Corpus not running"),
        (SimpleNamespace(running=True, success=False, returncode=None, log_text=""), "in progress"),
        (SimpleNamespace(running=False, success=True, returncode=0, log_text="done"), "completed"),
        (SimpleNamespace(running=False, success=False, returncode=2, log_text="bad"), "failed"),
    ],
)
def test_live_log_labels(
    status: object,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dashboard.execution, "inspect_corpus_job", lambda _job_id: status)
    monkeypatch.setattr(dashboard.execution, "corpus_operation", lambda _job_id: None)
    monkeypatch.setattr(dashboard.execution, "latest_persisted_run", lambda _root: None)
    monkeypatch.setattr(
        dashboard.settings,
        "load_settings",
        lambda _path=None: settings.StudioSettings(
            test_data_root=tmp_path / "fixtures",
            output_root=tmp_path / "outputs",
        ),
    )
    assert expected in dashboard._live_log("job", settings_path=tmp_path / "settings.json")[2]


def test_live_log_recovers_persisted_clean_and_legacy_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = settings.StudioSettings(
        test_data_root=tmp_path / "fixtures",
        output_root=tmp_path / "outputs",
    )
    run_path = active.output_root / ".apb_studio/runs/run/run.json"
    log_path = run_path.parent / "snakemake.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("persisted output", encoding="utf-8")
    record = run_history.OperationRecord(
        schema_version=1,
        operation="clean",
        status="running",
        started_at="now",
        pid=123,
    )
    persisted = dashboard.execution.PersistedRun(
        snapshot=cast(pipeline.RunSnapshot, SimpleNamespace()),
        run_path=run_path,
        log_path=log_path,
        operation=record,
    )
    monkeypatch.setattr(dashboard.execution, "inspect_corpus_job", lambda _job_id: None)
    monkeypatch.setattr(dashboard.settings, "load_settings", lambda _path=None: active)
    monkeypatch.setattr(dashboard.execution, "latest_persisted_run", lambda _root: persisted)

    text, running, label = dashboard._live_log(None)
    assert text == "persisted output"
    assert running is True
    assert label == "Corpus clean in progress"

    legacy = dashboard.execution.PersistedRun(
        snapshot=persisted.snapshot,
        run_path=run_path,
        log_path=tmp_path / "missing.log",
        operation=None,
    )
    monkeypatch.setattr(dashboard.execution, "latest_persisted_run", lambda _root: legacy)
    text, running, label = dashboard._live_log(None)
    assert "no Snakemake log" in text
    assert running is False
    assert label == "Loaded persisted Snakemake run"


def test_clear_callback_refreshes_status_and_reports_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = dashboard.create_app(settings_path=tmp_path / "settings.json")
    refresh = _callback(app, "corpus-grid.rowData")
    row = _row(tmp_path)
    snapshot = SimpleNamespace(fixtures=(1,))
    active = settings.StudioSettings(
        test_data_root=tmp_path / "fixtures",
        output_root=tmp_path / "output",
    )
    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda *_args, **_kwargs: ([row], snapshot, None),
    )
    monkeypatch.setattr(
        dashboard,
        "_live_log",
        lambda _job_id, **_kwargs: ("log", True, "Corpus clean in progress"),
    )
    monkeypatch.setattr(dashboard.settings, "load_settings", lambda _path=None: active)
    monkeypatch.setattr(dashboard.execution, "active_corpus_job_id", lambda: None)
    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="confirm-clear-corpus"))
    monkeypatch.setattr(dashboard.settings, "update_settings", lambda **_kwargs: active)
    monkeypatch.setattr(dashboard.execution, "clear_corpus", lambda **_kwargs: "clean-job")

    result = refresh(None, None, 0, 1, str(active.output_root), None, 3)

    assert result[4] is True
    assert result[5] is True
    assert result[7] == "Corpus clean in progress"
    assert result[8] == "clean-job"

    monkeypatch.setattr(
        dashboard.execution,
        "clear_corpus",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("clean failed")),
    )
    result = refresh(None, None, 0, 2, str(active.output_root), None, 4)
    assert "Could not launch corpus clean: clean failed" in result[1]


def test_dashboard_callbacks_and_main(  # noqa: PLR0915 - exercises one callback family
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = dashboard.create_app(settings_path=tmp_path / "settings.json")
    refresh = _callback(app, "corpus-grid.rowData")
    select = _callback(app, "selected-row.data")
    show = _callback(app, "stage-detail.children")
    fixture_detail = _callback(app, "fixture-detail.children")
    download = _callback(app, "log-download.data")
    row = _row(tmp_path)
    snapshot = SimpleNamespace(fixtures=(1, 2))

    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda *_args, **_kwargs: ([row], snapshot, None),
    )
    monkeypatch.setattr(
        dashboard,
        "_live_log",
        lambda _job_id, **_kwargs: ("log", False, "Corpus run completed"),
    )
    active = settings.StudioSettings(
        test_data_root=tmp_path / "fixtures",
        output_root=tmp_path / "output",
    )
    monkeypatch.setattr(dashboard.settings, "load_settings", lambda _path=None: active)
    monkeypatch.setattr(dashboard.execution, "active_corpus_job_id", lambda: None)
    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id=None))
    result = refresh(None, None, 0, None, str(active.output_root), "job", None)
    assert result[0] == [row]
    assert result[-1] == 1

    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="run-corpus"))
    monkeypatch.setattr(dashboard.settings, "update_settings", lambda **_kwargs: active)
    monkeypatch.setattr(dashboard.execution, "launch_corpus", lambda **_kwargs: "new-job")
    assert refresh(None, 1, 0, None, str(active.output_root), None, 2)[8] == "new-job"
    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="reload"))
    assert refresh(1, None, 0, None, str(active.output_root), None, 0)[1] == ""

    monkeypatch.setattr(
        dashboard.settings,
        "update_settings",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("read only")),
    )
    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="run-corpus"))
    assert (
        "Could not launch corpus"
        in refresh(
            None,
            1,
            0,
            None,
            str(active.output_root),
            None,
            0,
        )[1]
    )
    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="reload"))
    assert (
        "Could not save settings"
        in refresh(
            1,
            None,
            0,
            None,
            str(active.output_root),
            None,
            0,
        )[1]
    )

    selection = _selection(row)
    selected = select(
        {"colId": "convert", "rowId": row["_row_id"]},
        "job",
    )
    assert selected == (selection, "convert")
    shown = show(selection, "convert", 1, "job")
    assert shown[1] is False
    monkeypatch.setattr(
        dashboard,
        "_fixture_detail_text",
        lambda current, _selection, tab: f"{tab}:{len(current.fixtures)}",
    )
    assert fixture_detail(selection, "parameters", 1, "job") == "parameters:2"
    assert fixture_detail(None, "file", 1, "job") == "Select a row."

    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda *_args, **_kwargs: ([], None, "load failed"),
    )
    assert select(None, "job") == (no_update, no_update)
    assert show(selection, "convert", 1, "job") == ("load failed", True)
    assert fixture_detail(selection, "file", 1, "job") == "load failed"
    assert download(1, selection, "convert", "job") is no_update

    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda *_args, **_kwargs: ([row], snapshot, None),
    )
    assert show(None, "convert", 2, "job") == (no_update, no_update)
    missing = {**selection, "row_id": "gone"}
    assert show(missing, "convert", 2, "job")[1] is True
    assert download(1, missing, "convert", "job") is no_update
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dashboard.dcc,
        "send_file",
        lambda path, *, filename: sent.append((path, filename)) or "download",
    )
    assert download(1, selection, "convert", "job") == "download"
    assert sent[0][1] == "failure.log"

    run_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(dashboard.app, "run", lambda **kwargs: run_calls.append(kwargs))
    monkeypatch.setenv("APB_STUDIO_PORT", "9000")
    dashboard.main()
    assert run_calls == [{"debug": True, "port": 9000, "use_reloader": False}]
