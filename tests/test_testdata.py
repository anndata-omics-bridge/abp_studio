import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
from dash import dcc
from dash.exceptions import PreventUpdate
from pydantic import ValidationError

from apb_studio import module_resources, settings, testdata, testdata_app
from apb_studio.jobrunner import Job, JobStatus
from apb_studio.testdata_app import (
    create_app,
    data_panel,
    data_table,
)


def _paths(root: Path) -> testdata.TestDataPaths:
    return testdata.TestDataPaths(data_dir=root)


class _RunningProcess:
    pid = 1

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _row() -> dict[str, Any]:
    return {
        "module": "dia_aif",
        "repo_name": "Results_quant_ion_DIA_AIF",
        "intermediate_hash": "abc",
        "software_name": "DIA-NN",
        "software_version": "2.0",
        "nr_feature": 10,
    }


def _write_catalog(paths: testdata.TestDataPaths) -> None:
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)


def test_catalog_rows_reports_incomplete_until_input_and_parameter_exist(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)
    cached = testdata.dataset_dir(paths, _row())
    cached.mkdir(parents=True)
    (cached / "input_file.tsv").write_text("x\n")

    rows = testdata.catalog_rows(paths)

    assert rows[0]["download_status"] == "incomplete"
    assert rows[0]["fixture_status"] == "incomplete"
    assert rows[0]["local_file"].endswith("input_file.tsv")


def test_catalog_rows_unifies_selection_and_download_status(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)
    pd.DataFrame([_row()]).to_csv(paths.selection_csv, index=False)

    selected = testdata.catalog_rows(paths)[0]

    assert selected["download_status"] == "selected"
    assert "conversion_status" not in selected

    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("Run\tIntensity\n")
    (directory / "param_0.txt").write_text("params\n")

    downloaded = testdata.catalog_rows(paths)[0]

    assert downloaded["download_status"] == "downloaded"


def test_row_details_reads_submission_json_and_parameters(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    metadata = testdata.metadata_path(paths, _row())
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"software_name": "DIA-NN"}))
    cached = testdata.dataset_dir(paths, _row())
    cached.mkdir(parents=True)
    (cached / "param_0..json").write_text(json.dumps({"threads": 8}))

    info, submission, parameters = testdata.row_details(paths, _row())

    assert "intermediate_hash: abc" in info
    assert '"software_name": "DIA-NN"' in submission
    assert '"threads": 8' in parameters


def test_testdata_command_uses_explicit_artifact_paths(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    command = testdata.testdata_command("select", paths, strategy="all", module="dia_aif")

    assert command[1] == "select"
    assert command[-4:] == ["--strategy", "all", "--module", "dia_aif"]
    assert str(paths.catalog_csv) in command
    assert str(paths.selection_csv) in command


def test_reads_reject_a_client_row_absent_from_catalog(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    forged = {**_row(), "intermediate_hash": "not-in-catalog"}
    directory = testdata.dataset_dir(paths, forged)
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("x\n")
    (directory / "param_0.txt").write_text("params\n")

    with pytest.raises(ValueError, match="not present in the catalog"):
        testdata.row_details(paths, forged)


def test_client_row_cannot_escape_fixture_cache(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    forged = {**_row(), "intermediate_hash": "/tmp/outside"}

    with pytest.raises(ValueError, match="safe path component"):
        testdata.row_details(paths, forged)


def test_launch_rejects_overlapping_mutating_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)

    def fake_start(
        command: Sequence[str],
        log_file: Path | str,
        *,
        cwd: Path | str | None = None,
    ) -> Job:
        return Job(tuple(command), _RunningProcess(), Path(log_file))

    monkeypatch.setattr(testdata, "_JOBS", {})
    monkeypatch.setattr(testdata, "start_job", fake_start)
    first = testdata.launch("catalog", paths)

    with pytest.raises(testdata.JobAlreadyRunningError, match="already running"):
        testdata.launch("clean", paths)

    assert list(testdata._JOBS) == [first]


def test_clean_command_uses_selected_data_root(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    command = testdata.testdata_command("clean", paths)

    assert command[-2:] == ["--data-dir", str(tmp_path)]


def test_catalog_and_download_commands_use_selected_data_root(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    catalog = testdata.testdata_command("catalog", paths)
    download = testdata.testdata_command("download", paths)

    assert str(paths.catalog_csv) in catalog
    assert str(paths.cache_dir) in catalog
    assert str(paths.selection_csv) in download
    assert str(paths.cache_dir) in download
    assert str(paths.manifest_csv) in download


def test_fasta_command_uses_active_fixture_manager_root(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    command = testdata.testdata_command("fasta", paths)

    assert command[-2:] == ["--fasta-dir", str(paths.fasta_dir)]


def test_annotations_command_uses_active_fixture_manager_root(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    command = testdata.testdata_command("annotations", paths)

    assert command[-2:] == ["--annotation-dir", str(paths.annotation_dir)]


def test_test_data_paths_create_selected_root(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "nested" / "test-data")

    paths.create()

    assert paths.data_dir.is_dir()


def test_storage_summary_displays_all_derived_paths(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    summary = testdata.storage_summary(paths)

    assert str(paths.catalog_csv) in summary
    assert str(paths.selection_csv) in summary
    assert str(paths.manifest_csv) in summary
    assert str(paths.cache_dir) in summary
    assert str(paths.log_dir) in summary
    assert paths.data_dir not in paths.log_dir.parents


def test_test_data_paths_require_absolute_dedicated_root() -> None:
    with pytest.raises(ValidationError, match="absolute path"):
        testdata.TestDataPaths.model_validate({"data_dir": "relative/folder"})


def test_dash_app_registers_callbacks() -> None:
    app = create_app()

    assert app.layout is not None
    assert len(app.callback_map) == 12
    callback_outputs = "\n".join(app.callback_map)
    assert "config-section-editor.value" in callback_outputs
    assert "config-section-editor.readOnly" in callback_outputs
    assert "config-effective-editor.value" not in callback_outputs
    assert "resource-preview.children" in callback_outputs
    assert app.title == "APB Studio — Fixture Manager"


def test_run_action_preserves_tracked_job_while_it_is_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    callback = app.callback_map["job-id.data"]["callback"].__wrapped__
    running = JobStatus(
        command=("apb-testdata", "catalog"),
        returncode=None,
        running=True,
        log_file=tmp_path / "catalog.log",
        log_text="",
    )
    monkeypatch.setattr(testdata_app, "ctx", SimpleNamespace(triggered_id="clean-button"))
    monkeypatch.setattr(testdata, "job_status", lambda _job_id: running)
    launched = False

    def unexpected_launch(*_args: object, **_kwargs: object) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(testdata, "launch", unexpected_launch)

    with pytest.raises(PreventUpdate):
        callback(
            None,
            None,
            None,
            None,
            None,
            1,
            "all",
            None,
            str(tmp_path),
            "active-job",
        )

    assert not launched


def test_resource_editor_refreshes_when_storage_root_changes() -> None:
    app = create_app()
    callback = app.callback_map["resource-fasta.value"]

    assert {item["id"] for item in callback["inputs"]} == {
        "resource-module",
        "storage-root",
    }


def test_dash_app_starts_from_shared_disk_setting(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    fixture_root = tmp_path / "fixtures"
    settings.update_settings(test_data_root=fixture_root, path=settings_file)

    app = create_app(settings_path=settings_file)
    stores = {
        _props(component)["id"]: component
        for component in _components(app.layout)
        if isinstance(component, dcc.Store)
    }

    assert _props(stores["storage-root"])["data"] == str(fixture_root.resolve())
    assert "storage_type" not in _props(stores["storage-root"])


def test_data_panel_keeps_download_controls_and_json_details() -> None:
    components = list(_components(data_panel()))
    by_id = {
        _props(component)["id"]: component
        for component in components
        if isinstance(_props(component).get("id"), str)
    }

    assert "catalog-table" in by_id
    assert "selection-table" not in by_id
    assert "data-workflow-tabs" not in by_id
    assert "convert-button" not in by_id
    assert "convert-level" not in by_id
    assert "annotations-button" in by_id
    assert "job-log-details" in by_id
    assert "submission-json" in by_id
    assert "parameters" in by_id
    fields = [column["field"] for column in _props(by_id["catalog-table"])["columnDefs"]]
    assert fields[-1] == "download_status"
    assert "conversion_status" not in fields


def test_data_table_uses_continuous_mouse_wheel_scrolling() -> None:
    table = data_table("test-table")

    options = _props(table)["dashGridOptions"]
    assert options["pagination"] is False
    assert options["alwaysShowVerticalScroll"] is True


def test_resource_table_marks_preview_cells_as_clickable() -> None:
    app = create_app()
    tables = {
        _props(component)["id"]: component
        for component in _components(app.layout)
        if isinstance(component, testdata_app.dag.AgGrid)
    }
    columns = {column["field"]: column for column in _props(tables["resource-table"])["columnDefs"]}

    assert columns["annotation_path"]["cellStyle"]["cursor"] == "pointer"
    assert columns["fasta_status"]["cellStyle"]["textDecoration"] == "underline"
    assert "cellStyle" not in columns["module"]
    assert _props(tables["resource-table"])["getRowId"] == "params.data.module"


def test_resource_preview_reads_authoritative_annotation_and_fasta_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    annotation = tmp_path / "annotation.toml"
    annotation.write_text("[general]\nlevel = 'ion'\n", encoding="utf-8")
    fasta = tmp_path / "reference.fasta"
    fasta.write_text(
        "".join(f">P{index}\nSEQUENCE{index}\n" for index in range(21)),
        encoding="utf-8",
    )
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    diagnosed = tmp_path / "diagnosed.toml"
    diagnosed.write_text("bad", encoding="utf-8")
    inventory = module_resources.ModuleResourceInventory(
        resources=(
            module_resources.ModuleResource(
                module="dda",
                annotation_path=annotation,
                fasta_path=fasta,
            ),
            module_resources.ModuleResource(
                module="empty",
                annotation_path=empty,
                fasta_path=empty,
            ),
            module_resources.ModuleResource(module="unassigned"),
            module_resources.ModuleResource(
                module="diagnosed",
                annotation_path=diagnosed,
                annotation_error="Invalid annotation resource",
            ),
            module_resources.ModuleResource(
                module="unreadable",
                annotation_path=tmp_path,
            ),
        )
    )
    monkeypatch.setattr(
        testdata_app.module_resources,
        "load_module_resources",
        lambda _root: inventory,
    )

    def cell(module: object, column: str) -> dict[str, Any]:
        return {
            "colId": column,
            "rowId": module,
            "value": "/forged/path",
        }

    prompt = testdata_app._RESOURCE_PREVIEW_PROMPT
    assert testdata_app._resource_preview(None, str(tmp_path)) == prompt
    assert testdata_app._resource_preview(cell("dda", "module"), str(tmp_path)) == prompt
    assert (
        testdata_app._resource_preview(
            {"colId": "annotation_path"},
            str(tmp_path),
        )
        == prompt
    )
    assert testdata_app._resource_preview(cell("", "annotation_path"), str(tmp_path)) == prompt
    assert "No resource assignment" in testdata_app._resource_preview(
        cell("unknown", "annotation_path"),
        str(tmp_path),
    )
    assert "No annotation resource" in testdata_app._resource_preview(
        cell("unassigned", "annotation_status"),
        str(tmp_path),
    )
    assert "Invalid annotation resource" in testdata_app._resource_preview(
        cell("diagnosed", "annotation_path"),
        str(tmp_path),
    )
    assert "Could not read annotation" in testdata_app._resource_preview(
        cell("unreadable", "annotation_path"),
        str(tmp_path),
    )

    annotation_preview = testdata_app._resource_preview(
        cell("dda", "annotation_path"),
        str(tmp_path),
    )
    assert str(annotation) in annotation_preview
    assert "[general]" in annotation_preview
    assert "/forged/path" not in annotation_preview

    fasta_preview = testdata_app._resource_preview(
        cell("dda", "fasta_status"),
        str(tmp_path),
    )
    assert ">P19" in fasta_preview
    assert ">P20" not in fasta_preview
    assert "truncated after 40 lines" in fasta_preview
    assert "(empty file)" in testdata_app._resource_preview(
        cell("empty", "fasta_path"),
        str(tmp_path),
    )
    assert "(empty file)" in testdata_app._resource_preview(
        cell("empty", "annotation_path"),
        str(tmp_path),
    )


def test_failed_job_marks_log_tab_red(tmp_path: Path) -> None:
    status = JobStatus(
        command=("apb-testdata", "catalog"),
        returncode=1,
        running=False,
        log_file=tmp_path / "catalog.log",
        log_text="RuntimeError: archive mismatch",
    )

    message, log_text, label, style = testdata.job_presentation(
        status,
        catalog_count=0,
        selection_count=0,
    )

    assert "failed" in message
    assert "archive mismatch" in log_text
    assert "ERROR" in label
    assert style["color"] == "#b00020"


def _components(component: Any) -> Iterator[Any]:
    """Yield a Dash component tree depth-first."""
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    items = children if isinstance(children, list | tuple) else [children]
    for child in items:
        if hasattr(child, "to_plotly_json"):
            yield from _components(child)


def _props(component: Any) -> dict[str, Any]:
    """Return one Dash component's JSON props with their runtime mapping type."""
    return cast(dict[str, Any], component.to_plotly_json()["props"])
