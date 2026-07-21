import json
import os
from pathlib import Path

import anndata as ad
import mudata
import numpy as np
import pandas as pd
import pytest
from mudata import MuData
from pydantic import ValidationError

from apb_studio import testdata
from apb_studio.jobrunner import JobStatus
from apb_studio.testdata_app import create_app, data_table
from anndata_proteomics.readers.summary import store_quantification_summary


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


def _adata(level: str, prefix: str = "", n_features: int = 2) -> ad.AnnData:
    values = np.arange(2 * n_features, dtype=float).reshape(2, n_features)
    obj = ad.AnnData(
        X=values.copy(),
        obs=pd.DataFrame(index=["run1", "run2"]),
        var=pd.DataFrame(
            index=[f"{prefix}feature{index}" for index in range(n_features)]
        ),
        layers={"intensity": values.copy()},
    )
    obj.uns["anndata_proteomics"] = {
        "quantification_level": level,
        "software_name": "Synthetic",
    }
    store_quantification_summary(obj)
    return obj


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


def test_convert_command_uses_extensionless_output_basename(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
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
    directory = testdata.dataset_dir(paths, _row())
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("x\n")
    (directory / "param_0.txt").write_text("params\n")

    command = testdata.convert_command(paths, _row(), testdata.ALL_LEVELS)

    assert command[1:3] == ["convert", str(directory / "input_file.tsv")]
    assert command[command.index("--output") + 1] == str(directory / "mudata")


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
    assert paths.data_dir not in paths.log_dir.parents


def test_test_data_paths_require_absolute_dedicated_root() -> None:
    with pytest.raises(ValidationError, match="absolute path"):
        testdata.TestDataPaths(data_dir="relative/folder")


def test_dash_app_registers_callbacks() -> None:
    app = create_app()

    assert app.layout is not None
    assert len(app.callback_map) == 10
    callback_outputs = "\n".join(app.callback_map)
    assert "config-section-editor.value" in callback_outputs
    assert "config-section-editor.readOnly" in callback_outputs
    assert "config-effective-editor.value" not in callback_outputs


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


def test_container_rows_expand_mudata_modalities_and_standalone(
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
    assert rows["peptide"][0]["mudata"] is True
    assert rows["peptide"][0]["modality"] == "peptide"
    assert rows["protein"][0]["modality"] == "protein"
    peptide_summary = json.loads(
        testdata.container_summary(directory / "mudata.h5mu", "peptide")
    )
    assert peptide_summary["quantification"]["level"] == "peptide"
    assert "modalities" not in peptide_summary


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
