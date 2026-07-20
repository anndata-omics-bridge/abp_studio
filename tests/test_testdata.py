import json
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from apb_studio import testdata
from apb_studio.jobrunner import JobStatus
from apb_studio.testdata_app import create_app, data_table


def _paths(root: Path) -> testdata.TestDataPaths:
    return testdata.TestDataPaths(data_dir=root)


def _row() -> dict:
    return {
        "module": "dia_aif",
        "repo_name": "Results_quant_ion_DIA_AIF",
        "intermediate_hash": "abc",
        "software_name": "DIA-NN",
        "software_version": "2.0",
        "nr_feature": 10,
    }


def test_catalog_rows_reports_download_as_soon_as_input_exists(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    pd.DataFrame([_row()]).to_csv(paths.catalog_csv, index=False)
    cached = testdata.dataset_dir(paths, _row())
    cached.mkdir(parents=True)
    (cached / "input_file.tsv").write_text("x\n")

    rows = testdata.catalog_rows(paths)

    assert rows[0]["download_status"] == "downloaded"
    assert rows[0]["local_file"].endswith("input_file.tsv")


def test_row_details_reads_submission_json_and_parameters(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
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

    command = testdata.testdata_command(
        "select", paths, strategy="all", module="dia_aif"
    )

    assert command[1] == "select"
    assert command[-4:] == ["--strategy", "all", "--module", "dia_aif"]
    assert str(paths.catalog_csv) in command
    assert str(paths.selection_csv) in command


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


def test_test_data_paths_require_absolute_dedicated_root() -> None:
    with pytest.raises(ValidationError, match="absolute path"):
        testdata.TestDataPaths(data_dir="relative/folder")


def test_dash_app_registers_callbacks() -> None:
    app = create_app()

    assert app.layout is not None
    assert len(app.callback_map) == 6


def test_data_table_uses_continuous_mouse_wheel_scrolling() -> None:
    table = data_table("test-table")

    assert table.dashGridOptions["pagination"] is False
    assert table.dashGridOptions["alwaysShowVerticalScroll"] is True


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
