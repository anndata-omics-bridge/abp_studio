"""Focused tests for the compact corpus dashboard's pure interaction helpers."""

from pathlib import Path
from types import SimpleNamespace

from apb_studio import dashboard
from apb_studio.registry import load_registry

_ROW_ID = '["module-a","dataset-a","ion"]'


def _selection() -> dict[str, str]:
    return {
        "module": "module-a",
        "dataset": "dataset-a",
        "level": "ion",
        "row_id": _ROW_ID,
        "stage": "convert",
    }


def _row(state: str = "failed") -> dict:
    return {
        "module": "module-a",
        "dataset": "dataset-a",
        "level": "ion",
        "_row_id": _ROW_ID,
        "_stage_details": {
            "convert": {
                "state": state,
                "artifact": "/known/ion.h5ad",
            }
        },
    }


def test_columns_are_one_compact_branch_table() -> None:
    columns = dashboard._column_definitions(load_registry())

    assert [column["headerName"] for column in columns] == [
        "Module",
        "Dataset",
        "Software",
        "Level",
        "Converted",
        "Annotated",
        "FASTA annotated",
    ]
    assert [column["field"] for column in columns[-3:]] == [
        "convert",
        "annotate",
        "fasta",
    ]
    failed_style = columns[-1]["cellStyle"]["styleConditions"][0]
    assert "FAILED" in failed_style["condition"]
    assert failed_style["style"]["color"] == "#b42318"
    styled_states = {
        condition["condition"]
        for condition in columns[-1]["cellStyle"]["styleConditions"]
    }
    assert any("UNSUPPORTED" in condition for condition in styled_states)
    assert any("BLOCKED" in condition for condition in styled_states)


def test_cell_click_keeps_identity_but_discards_client_paths() -> None:
    cell = {
        "colId": "convert",
        "rowId": _ROW_ID,
        "rowIndex": 0,
        "value": "DONE",
        "data": {
            "module": "forged-module",
            "_stage_details": {"convert": {"log": "/etc/passwd"}},
        },
    }
    rows = [_row("completed")]

    assert dashboard._selection_from_click(cell, load_registry(), rows) == _selection()
    assert (
        dashboard._selection_from_click(
            {**cell, "colId": "dataset"}, load_registry(), rows
        )
        is None
    )


def test_failed_log_download_must_resolve_from_authoritative_row(
    tmp_path: Path,
) -> None:
    log = tmp_path / "ion.h5ad.log"
    log.write_text("ValueError: conversion failed\n", encoding="utf-8")
    rows = [
        {
            "module": "module-a",
            "dataset": "dataset-a",
            "level": "ion",
            "_row_id": _ROW_ID,
            "_stage_details": {
                "convert": {
                    "state": "failed",
                    "display": "FAILED",
                    "log": str(log),
                }
            },
        }
    ]

    assert dashboard._downloadable_log(rows, _selection()) == log
    forged = {**_selection(), "dataset": "different-dataset"}
    assert dashboard._downloadable_log(rows, forged) is None


def test_completed_cell_describes_exact_artifact(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "ion.h5ad"
    artifact.touch()
    described: list[Path] = []

    def fake_describe(path: Path) -> dict:
        described.append(path)
        return {"quantification": {"n_runs": 4, "n_features": 12}}

    monkeypatch.setattr(dashboard, "describe_path", fake_describe)
    children = dashboard._artifact_detail(
        {"state": "completed", "artifact": str(artifact)},
        _selection(),
        load_registry(),
    )

    assert described == [artifact]
    assert '"n_runs": 4' in children[-1].children


def test_unsupported_detail_has_no_rule_log() -> None:
    children = dashboard._status_detail(
        {
            "state": "unsupported",
            "error": "No APB parsing rule matches this fixture.",
            "log": "/forged/not-a-rule.log",
        },
        _selection(),
        load_registry(),
    )

    assert "UNSUPPORTED" in children[0].children
    assert len(children) == 2


def test_create_app_registers_run_poll_detail_and_download_callbacks() -> None:
    app = dashboard.create_app()

    assert len(app.callback_map) == 3
    callbacks = " ".join(app.callback_map)
    assert "corpus-grid.rowData" in callbacks
    assert "stage-detail.children" in callbacks
    assert "log-download.data" in callbacks
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )
    assert {item["id"] for item in detail_callback["inputs"]} == {
        "corpus-grid",
        "grid-revision",
    }
    layout_ids = [getattr(child, "id", None) for child in app.layout.children]
    assert layout_ids.index("corpus-grid") < layout_ids.index("stage-detail-panel")
    assert layout_ids.index("stage-detail-panel") < layout_ids.index("global-log-panel")
    grid = next(
        child
        for child in app.layout.children
        if getattr(child, "id", None) == "corpus-grid"
    )
    assert grid.getRowId == "params.data._row_id"


def test_documented_cell_event_renders_clicked_stage(monkeypatch) -> None:
    app = dashboard.create_app()
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )["callback"].__wrapped__
    rows = [_row("completed")]
    event = {
        "value": "DONE",
        "colId": "convert",
        "rowIndex": 0,
        "rowId": _ROW_ID,
        "timestamp": 1,
    }

    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="corpus-grid"))
    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda _job_id, **_kwargs: (rows, object(), None),
    )
    monkeypatch.setattr(
        dashboard,
        "_render_stage_detail",
        lambda detail, *_args: detail["state"],
    )

    result = detail_callback(event, 0, "job-id", None)

    assert result == ("completed", _selection(), True)


def test_poll_refreshes_the_stored_stage_selection(monkeypatch) -> None:
    app = dashboard.create_app()
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )["callback"].__wrapped__
    state = {"value": "pending"}

    def fake_rows(_job_id, **_kwargs):
        return (
            [_row(state["value"])],
            object(),
            None,
        )

    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="grid-revision"))
    monkeypatch.setattr(dashboard, "_load_dashboard_rows", fake_rows)
    monkeypatch.setattr(
        dashboard,
        "_render_stage_detail",
        lambda detail, *_args: detail["state"],
    )

    first = detail_callback(None, 1, "job-id", _selection())
    state["value"] = "completed"
    second = detail_callback(None, 2, "job-id", _selection())

    assert first[0] == "pending"
    assert second[0] == "completed"
    assert second[1] == _selection()


def test_refresh_reconnects_browser_to_server_active_job(monkeypatch) -> None:
    app = dashboard.create_app()
    refresh_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "corpus-grid.rowData" in output
    )["callback"].__wrapped__
    seen: list[str | None] = []
    snapshot = SimpleNamespace(fixtures=(object(), object()))

    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="poll-corpus"))
    monkeypatch.setattr(
        dashboard.execution,
        "active_corpus_job_id",
        lambda: "server-active",
    )
    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda job_id, **_kwargs: (seen.append(job_id) or [], snapshot, None),
    )
    monkeypatch.setattr(
        dashboard,
        "_live_log",
        lambda job_id: (seen.append(job_id) or "running", True, "in progress"),
    )
    monkeypatch.setattr(
        dashboard.settings,
        "load_settings",
        lambda _path: SimpleNamespace(test_data_root=Path("/fixtures")),
    )

    result = refresh_callback(0, 0, 1, "/outputs", None, 4)

    assert seen == ["server-active", "server-active"]
    assert result[3] is True  # Run disabled
    assert result[4] is False  # Poll enabled
    assert result[6] == "server-active"
    assert result[7].endswith("· 2 complete · 0 branches")
    assert result[8] == 5


def test_grid_revision_clears_a_selection_missing_after_root_reload(
    monkeypatch,
) -> None:
    app = dashboard.create_app()
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )["callback"].__wrapped__

    monkeypatch.setattr(dashboard, "ctx", SimpleNamespace(triggered_id="grid-revision"))
    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda _job_id, **_kwargs: ([], object(), None),
    )

    result = detail_callback(None, 2, "job-id", _selection())

    assert result == ("Click a completed stage or a status cell.", None, True)
