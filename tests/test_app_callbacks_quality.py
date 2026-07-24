"""Behavior coverage for Fixture Manager Dash callback boundaries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate

from apb_studio import module_resources, testdata, testdata_app
from apb_studio.jobrunner import JobStatus


def _callback(app: Any, output_fragment: str) -> Any:
    return next(
        entry["callback"].__wrapped__
        for key, entry in app.callback_map.items()
        if output_fragment in key
    )


def _status(tmp_path: Path, command: tuple[str, ...], returncode: int | None) -> JobStatus:
    return JobStatus(
        command=command,
        returncode=returncode,
        running=returncode is None,
        log_file=tmp_path / "job.log",
        log_text="job output",
    )


def _app_callbacks(tmp_path: Path) -> tuple[Any, dict[str, Any]]:
    app = testdata_app.create_app(settings_path=tmp_path / "settings.json")
    callbacks = {
        "run": _callback(app, "job-id.data"),
        "open": _callback(app, "job-log-details.open"),
        "storage": _callback(app, "storage-root.data"),
        "storage_paths": _callback(app, "storage-folder.value"),
        "refresh": _callback(app, "catalog-table.rowData"),
        "resource": _callback(app, "resource-fasta.value"),
        "save_resource": _callback(app, "resource-message.children"),
        "preview": _callback(app, "resource-preview.children"),
        "completed": _callback(app, "workspace-tabs.value"),
        "details": _callback(app, "file-info.children"),
    }
    return app, callbacks


def _run_args(tmp_path: Path) -> list[Any]:
    return [
        None,
        None,
        None,
        None,
        None,
        None,
        "all",
        None,
        str(tmp_path),
        None,
    ]


def test_action_callback_dispatch_and_concurrency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, callbacks = _app_callbacks(tmp_path)
    run = callbacks["run"]
    monkeypatch.setattr(
        testdata_app.testdata,
        "job_status",
        lambda _job_id: _status(tmp_path, ("apb", "catalog"), None),
    )
    with pytest.raises(PreventUpdate):
        run(*_run_args(tmp_path))

    monkeypatch.setattr(testdata_app.testdata, "job_status", lambda _job_id: None)
    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id=None))
    with pytest.raises(PreventUpdate):
        run(*_run_args(tmp_path))

    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id="catalog-button"))
    monkeypatch.setattr(
        testdata_app.testdata,
        "launch",
        lambda action, _paths, **_kwargs: f"{action}-job",
    )
    assert run(*_run_args(tmp_path)) == "catalog-job"
    monkeypatch.setattr(
        testdata_app.testdata,
        "launch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(testdata.JobAlreadyRunningError),
    )
    with pytest.raises(PreventUpdate):
        run(*_run_args(tmp_path))

    assert callbacks["open"](None) is False
    assert callbacks["open"]("job") is True


def test_storage_callbacks_cover_validation_io_and_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, callbacks = _app_callbacks(tmp_path)
    apply_storage = callbacks["storage"]
    monkeypatch.setattr(
        testdata_app.testdata,
        "job_status",
        lambda _job_id: _status(tmp_path, ("apb", "catalog"), None),
    )
    assert apply_storage(1, str(tmp_path / "new"), "job")[0] is no_update

    monkeypatch.setattr(testdata_app.testdata, "job_status", lambda _job_id: None)
    assert apply_storage(1, "relative", None)[0] is no_update

    original_create = testdata.TestDataPaths.create

    def fail_create(_paths: testdata.TestDataPaths) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(testdata.TestDataPaths, "create", fail_create)
    assert apply_storage(1, str(tmp_path / "broken"), None)[1] == "disk full"
    monkeypatch.setattr(testdata.TestDataPaths, "create", original_create)
    applied = apply_storage(1, str(tmp_path / "active"), None)
    assert applied[0] == str((tmp_path / "active").resolve())
    assert callbacks["storage_paths"](applied[0])[0] == applied[0]


def test_catalog_and_resource_callbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, callbacks = _app_callbacks(tmp_path)
    catalog = [{"module": "dda"}]
    monkeypatch.setattr(testdata_app.testdata, "catalog_rows", lambda _paths: catalog)
    monkeypatch.setattr(testdata_app.testdata, "read_rows", lambda _path: [{}, {}])
    monkeypatch.setattr(testdata_app.testdata, "job_status", lambda _job_id: None)
    monkeypatch.setattr(
        testdata_app.testdata,
        "job_presentation",
        lambda *_args, **_kwargs: ("ready", "log", "Log", {"color": "red"}),
    )
    inventory = module_resources.ModuleResourceInventory()
    monkeypatch.setattr(
        testdata_app.module_resources,
        "load_module_resources",
        lambda _root: inventory,
    )
    monkeypatch.setattr(
        testdata_app.module_resources,
        "resource_rows",
        lambda _inventory, modules: [{"module": module} for module in modules],
    )
    refreshed = callbacks["refresh"](0, str(tmp_path), None)
    assert refreshed[0] == catalog
    assert refreshed[1] == [{"label": "dda", "value": "dda"}]
    assert refreshed[5]["color"] == "red"

    assert callbacks["resource"](None, str(tmp_path)) == ""
    assert callbacks["resource"]("dda", str(tmp_path)) == ""
    fasta = tmp_path / "db.fasta"
    fasta.write_text(">P1\nAAAA\n", encoding="utf-8")
    assigned = module_resources.ModuleResourceInventory(
        resources=(module_resources.ModuleResource(module="dda", fasta_path=fasta),)
    )
    monkeypatch.setattr(
        testdata_app.module_resources,
        "load_module_resources",
        lambda _root: assigned,
    )
    assert callbacks["resource"]("dda", str(tmp_path)) == str(fasta)

    save = callbacks["save_resource"]
    assert save(1, None, None, str(tmp_path))[0] == "Choose a module."
    monkeypatch.setattr(
        testdata_app.module_resources,
        "set_module_resource",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad FASTA")),
    )
    assert save(1, "dda", str(fasta), str(tmp_path))[0] == "bad FASTA"
    monkeypatch.setattr(
        testdata_app.module_resources,
        "set_module_resource",
        lambda *_args, **_kwargs: assigned,
    )
    assert save(1, "dda", str(fasta), str(tmp_path))[0] == "Assignment saved."


def test_resource_preview_callback_resets_on_storage_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, callbacks = _app_callbacks(tmp_path)
    preview = callbacks["preview"]
    seen: list[dict[str, Any] | None] = []
    monkeypatch.setattr(
        testdata_app,
        "_resource_preview",
        lambda cell, _root: seen.append(cell) or "preview",
    )
    cell = {"colId": "annotation_path", "data": {"module": "dda"}}
    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id="resource-table"))
    assert preview(cell, str(tmp_path)) == "preview"
    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id="storage-root"))
    assert preview(cell, str(tmp_path)) == "preview"
    assert seen == [cell, None]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, (no_update, no_update)),
        ("running", (no_update, no_update)),
        ("failed", ("data", "job")),
        ("annotations", ("resources", "job")),
        ("fasta", ("resources", "job")),
        ("catalog", ("data", "job")),
        ("short", ("data", "job")),
    ],
)
def test_completed_job_routing(
    status: object,
    expected: tuple[object, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, callbacks = _app_callbacks(tmp_path)
    completed = callbacks["completed"]
    if status is None:
        assert completed(0, None, None, str(tmp_path)) == expected
        return
    if status == "running":
        value = _status(tmp_path, ("apb", "catalog"), None)
    elif status == "failed":
        value = _status(tmp_path, ("apb", "catalog"), 1)
    elif status == "short":
        value = _status(tmp_path, ("apb",), 0)
    else:
        value = _status(tmp_path, ("apb", str(status)), 0)
    monkeypatch.setattr(testdata_app.testdata, "job_status", lambda _job_id: value)
    monkeypatch.setattr(
        testdata_app.testdata.fixture_inventory,
        "load_fixture_inventory",
        lambda _root: SimpleNamespace(fixtures=()),
    )
    monkeypatch.setattr(
        testdata_app.module_resources,
        "sync_fasta_resources",
        lambda *_args: module_resources.ModuleResourceInventory(),
    )
    assert completed(0, "job", None, str(tmp_path)) == expected


def test_detail_callbacks_selection_override_and_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, callbacks = _app_callbacks(tmp_path)
    details = callbacks["details"]
    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id="storage-root"))
    assert details([{"module": "dda"}], str(tmp_path)) == (
        "Select a row.",
        "",
        "",
    )
    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id="catalog-table"))
    monkeypatch.setattr(
        testdata_app.testdata,
        "row_details",
        lambda _paths, row: ("file", "submission", f"params:{bool(row)}"),
    )
    row = {"module": "dda"}
    assert details([row], str(tmp_path)) == ("file", "submission", "params:True")
    assert details(None, str(tmp_path)) == ("file", "submission", "params:False")

    run_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(testdata_app.app, "run", lambda **kwargs: run_calls.append(kwargs))
    testdata_app.main()
    assert run_calls == [{"debug": True}]
