import json
import os
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import anndata as ad
import mudata
import numpy as np
import pandas as pd
import pytest
from anndata_proteomics.readers.summary import store_quantification_summary
from dash import dcc
from dash.exceptions import PreventUpdate
from mudata import MuData
from pydantic import ValidationError

from apb_studio import settings, testdata, testdata_app
from apb_studio.jobrunner import Job, JobStatus
from apb_studio.testdata_app import (
    CONTAINER_TABLE_IDS,
    _selected_container_row,
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


def _adata(level: str, prefix: str = "", n_features: int = 2) -> ad.AnnData:
    values = np.arange(2 * n_features, dtype=float).reshape(2, n_features)
    obj = ad.AnnData(
        X=values.copy(),
        obs=pd.DataFrame(index=["run1", "run2"]),
        var=pd.DataFrame(index=[f"{prefix}feature{index}" for index in range(n_features)]),
        layers={"intensity": values.copy()},
    )
    obj.uns["anndata_proteomics"] = {
        "quantification_level": level,
        "software_name": "Synthetic",
    }
    store_quantification_summary(obj)
    return obj


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


def test_catalog_rows_unifies_selection_download_and_conversion_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)
    pd.DataFrame([_row()]).to_csv(paths.selection_csv, index=False)

    selected = testdata.catalog_rows(paths)[0]

    assert selected["download_status"] == "selected"
    assert selected["conversion_status"] == "download first"

    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("Run\tIntensity\n")
    (directory / "param_0.txt").write_text("params\n")
    monkeypatch.setattr(
        testdata.capabilities,
        "discover_capabilities",
        lambda *_args: testdata.capabilities.CapabilityDiscovery(("mudata", "ion")),
    )

    downloaded = testdata.catalog_rows(paths)[0]

    assert downloaded["download_status"] == "downloaded"
    assert downloaded["conversion_targets"] == ["all", "ion"]
    assert downloaded["conversion_status"] == "all levels, ion"


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


def test_convert_command_uses_extensionless_output_basename(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("x\n")
    (directory / "param_0.txt").write_text("params\n")

    command = testdata.convert_command(paths, _row(), "ion")
    output_index = command.index("--output")

    assert command[2] == str(directory / "input_file.tsv")
    assert command[3] == "ion"
    assert command[output_index + 1] == str(directory / "ion")
    assert Path(command[output_index + 1]).suffix == ""


def test_convert_command_all_levels_omits_level_argument(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("x\n")
    (directory / "param_0.txt").write_text("params\n")

    command = testdata.convert_command(paths, _row(), testdata.ALL_LEVELS)

    assert command[1:3] == ["convert", str(directory / "input_file.tsv")]
    assert command[command.index("--output") + 1] == str(directory / "mudata")


def test_conversion_checkboxes_normalize_multiple_targets() -> None:
    assert testdata._selected_conversion_targets(["protein", "ion"]) == (
        "ion",
        "protein",
    )
    assert testdata._selected_conversion_targets(["ion", "all", "protein"]) == ("all",)


def test_conversion_checkboxes_require_a_target() -> None:
    with pytest.raises(ValueError, match="Select at least one"):
        testdata._selected_conversion_targets([])


def test_launch_convert_starts_each_checked_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("x\n")
    (directory / "param_0.txt").write_text("params\n")
    commands: list[tuple[list[str], Path | str | None]] = []

    def fake_start(
        command: Sequence[str],
        log_file: Path | str,
        *,
        cwd: Path | str | None = None,
    ) -> Job:
        rendered = [str(part) for part in command]
        commands.append((rendered, cwd))
        return Job(tuple(rendered), _RunningProcess(), Path(log_file))

    monkeypatch.setattr(testdata, "start_job", fake_start)
    job_id = testdata.launch_convert(paths, _row(), ["protein", "ion"])
    testdata._JOBS.pop(job_id)

    assert [command[0][3] for command in commands] == ["ion", "protein"]
    assert all(cwd is None for _, cwd in commands)


def test_reads_and_conversion_reject_a_client_row_absent_from_catalog(
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
    with pytest.raises(ValueError, match="not present in the catalog"):
        testdata.convert_command(paths, forged, "ion")


def test_client_row_cannot_escape_fixture_cache(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_catalog(paths)
    forged = {**_row(), "intermediate_hash": "/tmp/outside"}

    with pytest.raises(ValueError, match="safe path component"):
        testdata.row_details(paths, forged)
    with pytest.raises(ValueError, match="safe path component"):
        testdata.convert_command(paths, forged, "ion")


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
    assert len(app.callback_map) == 15
    callback_outputs = "\n".join(app.callback_map)
    assert "config-section-editor.value" in callback_outputs
    assert "config-section-editor.readOnly" in callback_outputs
    assert "config-effective-editor.value" not in callback_outputs
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
            None,
            "all",
            None,
            None,
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


def test_data_panel_uses_one_fixture_table_and_download_convert_subtabs() -> None:
    components = list(_components(data_panel()))
    by_id = {
        _props(component)["id"]: component
        for component in components
        if isinstance(_props(component).get("id"), str)
    }

    assert "catalog-table" in by_id
    assert "selection-table" not in by_id
    assert "data-workflow-tabs" in by_id
    assert "convert-button" in by_id
    assert "annotations-button" in by_id
    assert "job-log-details" in by_id
    assert isinstance(by_id["convert-level"], dcc.Checklist)
    fields = [column["field"] for column in _props(by_id["catalog-table"])["columnDefs"]]
    assert fields[-2:] == ["download_status", "conversion_status"]


def test_data_table_uses_continuous_mouse_wheel_scrolling() -> None:
    table = data_table("test-table")

    options = _props(table)["dashGridOptions"]
    assert options["pagination"] is False
    assert options["alwaysShowVerticalScroll"] is True


def test_active_anndata_tab_does_not_reuse_another_tabs_selection() -> None:
    mudata_row = {"path": "result.h5mu", "modality": None}
    ion_row = {"path": "result.h5mu", "modality": "ion"}
    selections: dict[str, list[dict[str, Any]] | None] = {
        CONTAINER_TABLE_IDS["mudata"]: [mudata_row],
        CONTAINER_TABLE_IDS["ion"]: [ion_row],
    }

    assert _selected_container_row("ion", selections, "anndata-level-tabs") == ion_row
    assert _selected_container_row("protein", selections, "anndata-level-tabs") is None


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


def test_container_rows_separate_mudata_from_standalone_anndata(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)
    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    _adata("ion").write_h5ad(directory / "ion.h5ad")
    with mudata.set_options(pull_on_update=False):
        mdata = MuData(
            {
                "peptide": _adata("peptide", "pep:"),
                "protein": _adata("protein", "prt:"),
            },
            axis=0,
        )
    store_quantification_summary(mdata)
    mdata.write_h5mu(directory / "mudata.h5mu")

    rows = testdata.container_rows(paths)

    assert len(rows["mudata"]) == 1
    assert len(rows["ion"]) == 1
    assert rows["ion"][0]["mudata"] is False
    assert rows["peptide"] == []
    assert rows["protein"] == []
    mudata_summary = json.loads(testdata.container_summary(directory / "mudata.h5mu"))
    assert set(mudata_summary["modalities"]) == {"peptide", "protein"}


def test_container_rows_cache_invalidates_on_mtime_change(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)
    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    path = directory / "ion.h5ad"
    _adata("ion", n_features=2).write_h5ad(path)
    first = testdata.container_rows(paths)
    old_mtime = path.stat().st_mtime_ns

    _adata("ion", n_features=3).write_h5ad(path)
    os.utime(path, ns=(path.stat().st_atime_ns, old_mtime + 1))
    second = testdata.container_rows(paths)

    assert first["ion"][0]["n_var"] == 2
    assert second["ion"][0]["n_var"] == 3


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
