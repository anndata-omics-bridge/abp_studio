"""Tests for Studio's shared fixture, settings, and module-resource stores."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from apb_studio import fixture_inventory, settings


def _update_setting(path: str, field: str, value: str) -> None:
    """Update one setting in a child process for the RMW regression test."""
    settings.update_settings(path=Path(path), **{field: Path(value)})


def _catalog_row(
    *,
    module: str = "dia_aif",
    repo_name: str = "Results_quant_ion_DIA_AIF",
    intermediate_hash: str = "abc123",
    software_name: str = "DIA-NN / Spectronaut",
) -> dict[str, object]:
    return {
        "module": module,
        "repo_name": repo_name,
        "intermediate_hash": intermediate_hash,
        "software_name": software_name,
        "software_version": "catalog version",
        "nr_feature": 42,
    }


def _write_catalog(root: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(root / "raw_file_db_full.csv", index=False)


def test_inventory_retains_every_catalog_fixture_and_raw_software(
    tmp_path: Path,
) -> None:
    rows = [
        _catalog_row(intermediate_hash="supported"),
        _catalog_row(intermediate_hash="unsupported", software_name="Mystery Tool"),
    ]
    _write_catalog(tmp_path, rows)
    for row in rows:
        directory = tmp_path / "json_dir" / str(row["repo_name"]) / str(row["intermediate_hash"])
        directory.mkdir(parents=True)
        (directory / "input_file.tsv").write_text("Run\n")
        (directory / "param_0.txt").write_text("params\n")

    inventory = fixture_inventory.load_fixture_inventory(tmp_path)

    assert len(inventory.fixtures) == 2
    assert len(inventory.complete_local) == 2
    assert inventory.fixtures[0].catalog_software_name == "DIA-NN / Spectronaut"
    assert inventory.fixtures[1].catalog_software_name == "Mystery Tool"


def test_inventory_uses_live_files_over_stale_download_report(tmp_path: Path) -> None:
    row = _catalog_row()
    _write_catalog(tmp_path, [row])
    pd.DataFrame([{**row, "status": "ok"}]).to_csv(
        tmp_path / "raw_file_db_downloaded.csv",
        index=False,
    )

    fixture = fixture_inventory.load_fixture_inventory(tmp_path).fixtures[0]

    assert fixture.manifest_status == "ok"
    assert fixture.local_state is fixture_inventory.LocalFixtureState.NOT_LOCAL
    assert not fixture.complete
    assert fixture.as_catalog_row()["download_status"] == "missing"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module", "../dia_aif"),
        ("repo_name", "/tmp/outside"),
        ("intermediate_hash", r"..\outside"),
    ],
)
def test_inventory_rejects_unsafe_identity_before_filesystem_lookup(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    row = _catalog_row()
    row[field] = value
    _write_catalog(tmp_path, [row])

    with pytest.raises(ValueError, match="safe path component"):
        fixture_inventory.load_fixture_inventory(tmp_path)


def test_inventory_requires_exactly_one_input_and_parameter(tmp_path: Path) -> None:
    row = _catalog_row()
    _write_catalog(tmp_path, [row])
    directory = tmp_path / "json_dir" / str(row["repo_name"]) / str(row["intermediate_hash"])
    directory.mkdir(parents=True)
    (directory / "input_file.tsv").write_text("Run\n")
    (directory / "input_file.csv").write_text("Run\n")
    (directory / "param_0.txt").write_text("params\n")

    fixture = fixture_inventory.load_fixture_inventory(tmp_path).fixtures[0]

    assert fixture.local_state is fixture_inventory.LocalFixtureState.INCOMPLETE
    assert fixture.input_path is None
    assert fixture.diagnostic is not None
    assert "2 input file(s)" in fixture.diagnostic


def test_settings_updates_one_application_root_without_resetting_other(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config" / "settings.json"
    test_data_root = tmp_path / "fixtures"
    output_root = tmp_path / "outputs"

    first = settings.update_settings(test_data_root=test_data_root, path=path)
    second = settings.update_settings(output_root=output_root, path=path)

    assert first.test_data_root == test_data_root.resolve()
    assert second.test_data_root == test_data_root.resolve()
    assert second.output_root == output_root.resolve()
    assert json.loads(path.read_text())["schema_version"] == 1
    assert not list(path.parent.glob(".settings.json.*"))


def test_settings_reject_relative_root_without_corrupting_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    saved = settings.update_settings(test_data_root=tmp_path / "fixtures", path=path)

    with pytest.raises(ValidationError, match="absolute paths"):
        settings.update_settings(test_data_root=Path("relative"), path=path)

    assert settings.load_settings(path) == saved


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="requires fork to share the synchronized pre-fix loader",
)
def test_settings_read_modify_write_is_locked_between_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two applications updating different fields must not lose either write."""
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    path = tmp_path / "settings.json"
    test_data_root = tmp_path / "fixtures"
    output_root = tmp_path / "outputs"
    original_load = settings.load_settings

    def synchronized_legacy_load(location: Path | None = None):
        current = original_load(location)
        barrier.wait(timeout=5)
        return current

    # Before the lock, update_settings called the public loader and both processes
    # deterministically read the same document before either saved it.
    monkeypatch.setattr(settings, "load_settings", synchronized_legacy_load)
    processes = [
        context.Process(
            target=_update_setting,
            args=(str(path), "test_data_root", str(test_data_root)),
        ),
        context.Process(
            target=_update_setting,
            args=(str(path), "output_root", str(output_root)),
        ),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    stored = original_load(path)
    assert stored.test_data_root == test_data_root.resolve()
    assert stored.output_root == output_root.resolve()
