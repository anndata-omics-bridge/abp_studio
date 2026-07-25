"""Focused tests for the compact corpus dashboard's pure interaction helpers."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dash import no_update

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


def _row(state: str = "failed") -> dict[str, Any]:
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
        "Proteobench scored",
    ]
    assert [column["field"] for column in columns[-4:]] == [
        "convert",
        "annotate",
        "fasta",
        "proteobench",
    ]
    failed_style = columns[-1]["cellStyle"]["styleConditions"][0]
    assert "FAILED" in failed_style["condition"]
    assert failed_style["style"]["color"] == "#b42318"
    styled_states = {
        condition["condition"] for condition in columns[-1]["cellStyle"]["styleConditions"]
    }
    assert any("UNSUPPORTED" in condition for condition in styled_states)
    assert any("BLOCKED" in condition for condition in styled_states)


def test_cell_click_selects_authoritative_row_and_clicked_stage() -> None:
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
            {**cell, "colId": "dataset"},
            load_registry(),
            rows,
        )
        == _selection()
    )
    assert dashboard._selection_from_click(cell, [], rows) is None
    assert (
        dashboard._selection_from_click(
            {**cell, "colId": object()},
            load_registry(),
            rows,
        )
        == _selection()
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


def test_completed_cell_describes_exact_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ion.h5ad"
    artifact.touch()
    described: list[Path] = []

    def fake_describe(path: Path) -> dict[str, Any]:
        described.append(path)
        return {"quantification": {"n_runs": 4, "n_features": 12}}

    monkeypatch.setattr(dashboard, "describe_path", fake_describe)
    children = dashboard._artifact_detail(
        {
            "state": "completed",
            "artifact": str(artifact),
            "command": "apb convert input.tsv --output ion",
        },
        _selection(),
        load_registry(),
    )

    assert described == [artifact]
    assert '"n_runs": 4' in children[-1].children
    assert "Runtime unavailable" in children[1].children
    assert children[2].children[1].children == "apb convert input.tsv --output ion"
    timed = dashboard._artifact_detail(
        {
            "state": "completed",
            "artifact": str(artifact),
            "duration": "2m 14s",
            "command": "apb convert input.tsv --output ion",
        },
        _selection(),
        load_registry(),
    )
    assert "Runtime 2m 14s" in timed[1].children


def test_fasta_artifact_surfaces_coverage_before_full_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "mudata.fasta.h5mu"
    artifact.touch()
    monkeypatch.setattr(
        dashboard,
        "describe_path",
        lambda _path: {
            "modalities": {
                "ion": {
                    "fasta": {
                        "feature_count": 18_182,
                        "matched_feature_count": 18_182,
                        "proteotypic_feature_count": 16_334,
                    }
                },
                "protein": {
                    "fasta": {
                        "feature_count": 3_754,
                        "annotated_feature_count": 3_754,
                    }
                },
            }
        },
    )
    selection = {**_selection(), "stage": "fasta"}

    children = dashboard._artifact_detail(
        {
            "state": "completed",
            "artifact": str(artifact),
            "command": "apb fasta mudata.h5mu proteins.fasta --output result.h5mu",
        },
        selection,
        load_registry(),
    )

    overview = children[3]
    cards = overview.children[1].children
    ion_metrics = [metric.children[1].children for metric in cards[0].children[1:]]
    protein_metrics = [metric.children[1].children for metric in cards[1].children[1:]]
    assert ion_metrics == ["18,182", "18,182 / 18,182", "16,334 / 18,182"]
    assert protein_metrics == ["3,754", "3,754 / 3,754"]
    assert children[4].children[0].children == "Full APB summary (JSON)"


def test_fasta_overview_handles_standalone_and_missing_components() -> None:
    overview = dashboard._fasta_overview(
        {
            "quantification": {"level": "peptide"},
            "fasta": {
                "feature_count": 10,
                "matched_feature_count": 8,
            },
        }
    )

    assert overview is not None
    card = cast(Any, overview).children[1].children[0]
    assert card.children[0].children == "peptide"
    assert (
        dashboard._fasta_overview(
            {"modalities": {"ion": {"quantification": {}}, "bad": "not a summary"}}
        )
        is None
    )
    assert dashboard._fasta_overview({"fasta": {"feature_count": True}}) is None
    assert dashboard._fasta_overview({"fasta": {"feature_count": "unknown"}}) is None


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
    assert "No APB CLI command was generated" in children[2].children[1].children
    assert len(children) == 3


def test_corpus_summary_reports_states_and_timing_coverage() -> None:
    rows = [
        {
            "_stage_details": {
                "convert": {
                    "state": "completed",
                    "duration_seconds": "61.2",
                },
                "annotate": {"state": "completed"},
                "fasta": {"state": "failed"},
                "proteobench": {"state": "pending"},
            }
        }
    ]

    summary = dashboard._corpus_summary(rows, load_registry())

    assert "2 produced · 1 failed" in summary
    assert "1/2 produced stages timed" in summary
    assert "1m 01s recorded runtime" in summary
    untimed = dashboard._corpus_summary(
        [{"_stage_details": {"convert": {"state": "completed"}}}],
        [{"name": "convert"}],
    )
    assert "existing artifacts predate" in untimed
    pending = dashboard._corpus_summary(
        [{"_stage_details": {"convert": {"state": "pending"}}}],
        [{"name": "convert"}],
    )
    assert "No completed-stage timing yet" in pending
    assert dashboard._corpus_summary([], load_registry()) == "No corpus branches resolved."


def test_create_app_registers_run_poll_detail_and_download_callbacks() -> None:
    app = dashboard.create_app()

    assert len(app.callback_map) == 4
    callbacks = " ".join(app.callback_map)
    assert "corpus-grid.rowData" in callbacks
    assert "selected-row.data" in callbacks
    assert "stage-detail.children" in callbacks
    assert "log-download.data" in callbacks
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )
    assert {item["id"] for item in detail_callback["inputs"]} == {
        "selected-row",
        "artifact-stage-tabs",
        "grid-revision",
    }
    layout_ids = [getattr(child, "id", None) for child in app.layout.children]
    assert layout_ids.index("corpus-grid") < layout_ids.index("stage-detail-panel")
    assert layout_ids.index("corpus-grid") < layout_ids.index("corpus-summary-panel")
    assert layout_ids.index("stage-detail-panel") < layout_ids.index("global-log-panel")
    grid = next(
        child for child in app.layout.children if getattr(child, "id", None) == "corpus-grid"
    )
    assert grid.getRowId == "params.data._row_id"
    assert grid.dashGridOptions["rowSelection"]["mode"] == "singleRow"
    panel = next(
        child for child in app.layout.children if getattr(child, "id", None) == "stage-detail-panel"
    )
    tabs = next(
        child for child in panel.children if getattr(child, "id", None) == "artifact-stage-tabs"
    )
    assert [tab.label for tab in tabs.children] == [
        "Convert",
        "Annotate",
        "FASTA",
        "ProteoBench",
    ]
    controls = next(
        child
        for child in app.layout.children
        if isinstance(getattr(child, "children", None), list)
        and any(
            getattr(grandchild, "id", None) == "confirm-clear-corpus"
            for grandchild in child.children
        )
    )
    confirm = next(
        child for child in controls.children if getattr(child, "id", None) == "confirm-clear-corpus"
    )
    assert confirm.children.id == "clear-corpus"
    assert "all Snakemake-managed corpus outputs" in confirm.message


def test_documented_cell_event_selects_row_and_renders_active_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = dashboard.create_app()
    selection_callback = next(
        callback for output, callback in app.callback_map.items() if "selected-row.data" in output
    )["callback"].__wrapped__
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

    assert selection_callback(None, "job-id") == (no_update, no_update)
    selected, active_tab = selection_callback(event, "job-id")
    result = detail_callback(selected, active_tab, 0, "job-id")

    assert selected == _selection()
    assert active_tab == "convert"
    assert result == ("completed", True)


def test_poll_refreshes_the_stored_stage_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = dashboard.create_app()
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )["callback"].__wrapped__
    state = {"value": "pending"}

    def fake_rows(
        _job_id: object,
        **_kwargs: object,
    ) -> tuple[list[dict[str, Any]], object, None]:
        return (
            [_row(state["value"])],
            object(),
            None,
        )

    monkeypatch.setattr(dashboard, "_load_dashboard_rows", fake_rows)
    monkeypatch.setattr(
        dashboard,
        "_render_stage_detail",
        lambda detail, *_args: detail["state"],
    )

    first = detail_callback(_selection(), "convert", 1, "job-id")
    state["value"] = "completed"
    second = detail_callback(_selection(), "convert", 2, "job-id")

    assert first[0] == "pending"
    assert second[0] == "completed"
    assert second[1] is True


def test_refresh_reconnects_browser_to_server_active_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = dashboard.create_app()
    refresh_callback = next(
        callback for output, callback in app.callback_map.items() if "corpus-grid.rowData" in output
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
        lambda job_id, **_kwargs: (seen.append(job_id) or "running", True, "in progress"),
    )
    monkeypatch.setattr(
        dashboard.settings,
        "load_settings",
        lambda _path: SimpleNamespace(test_data_root=Path("/fixtures")),
    )

    result = refresh_callback(0, 0, 1, 0, "/outputs", None, 4)

    assert seen == ["server-active", "server-active"]
    assert result[4] is True  # Run disabled
    assert result[5] is True  # Clear disabled
    assert result[6] is False  # Poll enabled
    assert result[8] == "server-active"
    assert result[9].endswith("· 2 complete · 0 branches")
    assert result[10] == 5


def test_grid_revision_reports_a_selection_missing_after_root_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = dashboard.create_app()
    detail_callback = next(
        callback
        for output, callback in app.callback_map.items()
        if "stage-detail.children" in output
    )["callback"].__wrapped__

    monkeypatch.setattr(
        dashboard,
        "_load_dashboard_rows",
        lambda _job_id, **_kwargs: ([], object(), None),
    )

    result = detail_callback(_selection(), "convert", 2, "job-id")

    assert result == (
        "The selected row is no longer available. Select a row again.",
        True,
    )
