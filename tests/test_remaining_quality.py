"""Focused edge-path tests for Studio's shared backend services."""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import replace
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from dash.exceptions import PreventUpdate
from pydantic import ValidationError

from apb_studio import (
    capabilities,
    config_editor,
    config_panel,
    fixture_inventory,
    module_resources,
    provenance,
    settings,
    testdata,
    testdata_app,
)
from apb_studio.jobrunner import Job, JobStatus
from apb_studio.pipeline import (
    RUN_SNAPSHOT_SCHEMA_VERSION,
    ResolvedFixture,
    RunSnapshot,
    Target,
)


class _Process:
    pid = 7

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _job(tmp_path: Path, *, command: tuple[str, ...] = ("apb", "convert")) -> Job:
    return Job(command, _Process(), tmp_path / "job.log")


def _status(
    tmp_path: Path,
    *,
    returncode: int | None,
    command: tuple[str, ...] = ("apb", "convert"),
    text: str = "",
) -> JobStatus:
    return JobStatus(
        command=command,
        returncode=returncode,
        running=returncode is None,
        log_file=tmp_path / "job.log",
        log_text=text,
    )


def _record(
    tmp_path: Path,
    *,
    state: fixture_inventory.LocalFixtureState,
    manifest_status: str | None = None,
    selected: bool = False,
    input_suffix: str = ".tsv",
    parameter_suffix: str = ".txt",
) -> fixture_inventory.FixtureRecord:
    dataset = tmp_path / "dataset"
    dataset.mkdir(exist_ok=True)
    inputs: tuple[Path, ...] = ()
    parameters: tuple[Path, ...] = ()
    if state is fixture_inventory.LocalFixtureState.COMPLETE:
        input_path = dataset / f"input_file{input_suffix}"
        parameter_path = dataset / f"param_0{parameter_suffix}"
        input_path.write_text("x\n", encoding="utf-8")
        parameter_path.write_text("{}" if parameter_suffix == ".json" else "params\n")
        inputs = (input_path,)
        parameters = (parameter_path,)
    return fixture_inventory.FixtureRecord(
        module="dda",
        repo_name="repo",
        intermediate_hash="abc123",
        catalog_software_name="DIA-NN",
        dataset_dir=dataset,
        input_files=inputs,
        parameter_files=parameters,
        local_state=state,
        diagnostic=(
            "incomplete" if state is fixture_inventory.LocalFixtureState.INCOMPLETE else None
        ),
        manifest_status=manifest_status,
        selected=selected,
    )


def _target(tmp_path: Path, *, stage: str = "convert") -> Target:
    return Target(
        module="repo",
        dataset="dataset",
        stage=stage,
        output=tmp_path / f"{stage}.h5ad",
        command=["apb", stage],
        inputs=[tmp_path / "input.tsv"],
        branch="ion",
    )


def _snapshot(tmp_path: Path, target: Target) -> RunSnapshot:
    fixture = ResolvedFixture(
        module="dda",
        repo_name="repo",
        intermediate_hash="abc123",
        dataset="dataset",
        software="DIA-NN",
        vendor="diann",
        input_path=tmp_path / "input.tsv",
        parameter_path=tmp_path / "params.txt",
        branches=("ion",),
        capability_status="supported",
    )
    return RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id="run",
        created_at="now",
        test_data_root=tmp_path,
        output_root=tmp_path,
        registry_digest="digest",
        apb_version=None,
        fixtures=(fixture,),
        targets=(target,),
    )


def test_small_remaining_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="unsupported extension"):
        capabilities.read_table_columns(tmp_path / "data.xlsx")

    monkeypatch.setattr(
        config_editor,
        "parse_rule_source",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid")),
    )
    monkeypatch.setattr(config_editor, "iter_packaged_documents", lambda: (tmp_path / "x.json",))
    monkeypatch.setattr(config_editor, "document_vendor", lambda _path: "x")
    monkeypatch.setattr(
        config_editor,
        "validate_source",
        lambda *_args, **_kwargs: {"valid": False},
    )
    (tmp_path / "x.json").write_text("{}", encoding="utf-8")
    assert config_editor.catalog_rows()[0]["software_name"] == "x"

    app = testdata_app.create_app(settings_path=tmp_path / "settings.json")
    operate = next(
        entry["callback"].__wrapped__
        for key, entry in app.callback_map.items()
        if "config-section-editor.value" in key
    )
    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="unknown"))
    with pytest.raises(PreventUpdate):
        operate([0], None, None, None, None, None, "base", "{}", {"sections": {}}, "", "rule")
    noted = ValueError("broken")
    noted.add_note("unrelated")
    noted.add_note("in /tmp/rules.json")
    assert config_editor._exception_document(noted) == "/tmp/rules.json"


def test_settings_validation_and_direct_save(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="schema version"):
        settings.StudioSettings(schema_version=2)
    with pytest.raises(ValidationError, match="dedicated folder"):
        settings.StudioSettings(test_data_root=Path("/"))
    path = tmp_path / "settings.json"
    value = settings.StudioSettings(
        test_data_root=tmp_path / "fixtures",
        output_root=tmp_path / "outputs",
    )
    assert settings.save_settings(value, path) == value
    assert settings.settings_path(path) == path.resolve()


def test_default_settings_use_user_owned_data_paths() -> None:
    package_root = Path(settings.__file__).resolve().parent

    assert settings.DEFAULT_TEST_DATA_ROOT.is_absolute()
    assert settings.DEFAULT_OUTPUT_ROOT.is_absolute()
    assert package_root not in settings.DEFAULT_TEST_DATA_ROOT.parents
    assert package_root not in settings.DEFAULT_OUTPUT_ROOT.parents


def test_fixture_inventory_defensive_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError, match="dedicated folder"):
        fixture_inventory.FixtureStorePaths(data_dir=Path("/"))
    paths = fixture_inventory.FixtureStorePaths(data_dir=tmp_path / "fixtures")
    monkeypatch.setattr(Path, "is_dir", lambda _path: False)
    with pytest.raises(NotADirectoryError):
        paths.create()

    monkeypatch.undo()
    paths.data_dir.mkdir(exist_ok=True)
    with paths.catalog_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["module", "repo_name", "intermediate_hash"],
        )
        writer.writeheader()
        writer.writerow({"module": "dda", "repo_name": "repo", "intermediate_hash": "abc"})
        writer.writerow({"module": "dda", "repo_name": "repo", "intermediate_hash": "abc"})
    with pytest.raises(ValueError, match="duplicate identity"):
        fixture_inventory.load_fixture_inventory(paths)

    record = _record(
        tmp_path,
        state=fixture_inventory.LocalFixtureState.NOT_LOCAL,
        manifest_status="queued",
    )
    assert record.as_catalog_row()["download_status"] == "queued"
    selected = record.model_copy(update={"manifest_status": None, "selected": True})
    assert selected.as_catalog_row()["download_status"] == "selected"

    original_resolve = Path.resolve

    def escape_fixture(path: Path, strict: bool = False) -> Path:
        if path.name == "abc":
            return tmp_path / "outside"
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", escape_fixture)
    with pytest.raises(ValueError, match="escapes the cache root"):
        fixture_inventory.fixture_directory(paths, "repo", "abc")


def test_module_resource_edge_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_file = tmp_path / "module_resources.csv"
    resource_file.write_text(
        "module,annotation_path,fasta_path\ndda,,\ndda,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate module"):
        module_resources.load_module_resources(tmp_path)
    with pytest.raises(ValidationError, match="absolute"):
        module_resources.ModuleResource(module="dda", fasta_path=Path("relative.fasta"))

    resource_file.unlink()
    catalog = tmp_path / "raw_file_db_full.csv"
    catalog.write_text(
        "module,repo_name,intermediate_hash\ndda,repo,abc\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module_resources,
        "find_annotation",
        lambda **_kwargs: module_resources.AnnotationUnavailable("dda"),
    )
    monkeypatch.setattr(
        module_resources,
        "find_fasta_for_module",
        lambda *_args, **_kwargs: module_resources.FastaUnavailable("dda"),
    )
    assert module_resources.load_module_resources(tmp_path).resources == ()

    managed = module_resources.ModuleResource(
        module="dda",
        annotation_managed=True,
        fasta_managed=True,
    )
    module_resources.save_module_resources(
        tmp_path,
        module_resources.ModuleResourceInventory(resources=(managed,)),
    )
    assert resource_file.read_text(encoding="utf-8").splitlines() == [
        "module,annotation_path,fasta_path"
    ]
    assert (
        module_resources.set_module_resource(
            tmp_path,
            "dda",
            annotation_path=None,
            fasta_path=None,
        ).resources
        == ()
    )

    assert module_resources.sync_fasta_resources(tmp_path, ["dda"]).resources == ()
    missing = tmp_path / "missing.fasta"
    inventory = module_resources.ModuleResourceInventory(
        resources=(module_resources.ModuleResource(module="dda", fasta_path=missing),)
    )
    rows = module_resources.resource_rows(inventory, ["dda", "new"])
    assert rows[0]["fasta_status"] == "missing"
    assert rows[1]["annotation_path"] == ""

    bad_annotation = tmp_path / "annotation.bad"
    bad_annotation.write_text("bad", encoding="utf-8")
    assert "extension" in cast(str, module_resources._resource_error("annotation", bad_annotation))
    bad_fasta = tmp_path / "proteome.txt"
    bad_fasta.write_text("bad", encoding="utf-8")
    assert "extension" in cast(str, module_resources._resource_error("FASTA", bad_fasta))
    empty = tmp_path / "empty.fasta"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty FASTA"):
        module_resources._cached_validate_fasta(
            str(empty),
            empty.stat().st_mtime_ns,
            empty.stat().st_size,
        )
    assert module_resources._unavailable_status(bad_fasta, "bad") == "invalid"

    with pytest.raises(ValueError, match="supported table"):
        module_resources._validate_annotation(bad_annotation)
    with pytest.raises(ValueError, match="absolute"):
        module_resources._validate_annotation(Path("relative.tsv"))
    invalid_annotation = tmp_path / "invalid.toml"
    invalid_annotation.write_text("[general]\nlevel = 'ion'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="readable sample table"):
        module_resources._validate_annotation(invalid_annotation)
    valid_annotation = tmp_path / "valid.tsv"
    valid_annotation.write_text(
        "raw_file\tsample_name\tcondition\nrun\tsample\tA\n",
        encoding="utf-8",
    )
    assert module_resources._validate_annotation(valid_annotation) == valid_annotation
    assert module_resources._validate_annotation(None) is None


def test_testdata_rows_commands_and_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = testdata.TestDataPaths(data_dir=tmp_path / "fixtures")
    paths.data_dir.mkdir()
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("name,value\nx,\n", encoding="utf-8")
    assert testdata.read_rows(csv_path) == [{"name": "x", "value": ""}]
    assert testdata.read_rows(tmp_path / "missing.csv") == []
    assert testdata.row_details(paths, None) == ("Select a row.", "", "")

    row = {
        "module": "dda",
        "repo_name": "repo",
        "intermediate_hash": "abc123",
    }
    selected = paths.selection_csv
    selected.write_text(
        "module,repo_name,intermediate_hash\ndda,repo,abc123\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(testdata, "catalog_rows", lambda _paths: [row])
    assert testdata.selection_rows(paths) == [row]

    select_command = testdata.testdata_command("select", paths, module="dda")
    assert select_command[-2:] == ["--module", "dda"]
    assert "--module" not in testdata.testdata_command("select", paths)
    with pytest.raises(ValueError, match="Unknown test-data action"):
        testdata.testdata_command("unknown", paths)

    monkeypatch.setattr(testdata, "_JOBS", {})
    assert testdata.job_status("missing") is None
    single = _job(tmp_path)
    monkeypatch.setattr(
        testdata,
        "inspect_job",
        lambda _job: _status(tmp_path, returncode=0),
    )
    testdata._JOBS["single"] = single
    assert cast(JobStatus, testdata.job_status("single")).success is True
    failed = testdata.job_presentation(
        _status(tmp_path, returncode=2, text="failed"),
        catalog_count=1,
        selection_count=2,
    )
    assert failed[2] == "Log — ERROR"
    assert testdata.job_presentation(None, catalog_count=0, selection_count=0)[2] == "Log"
    running = testdata.job_presentation(
        _status(tmp_path, returncode=None),
        catalog_count=0,
        selection_count=0,
    )
    assert "running" in running[0]


def test_testdata_details_and_missing_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = testdata.TestDataPaths(data_dir=tmp_path / "fixtures")
    record = _record(
        tmp_path,
        state=fixture_inventory.LocalFixtureState.COMPLETE,
        parameter_suffix=".json",
    )
    inventory = fixture_inventory.FixtureInventory(paths=paths, fixtures=(record,))
    monkeypatch.setattr(
        testdata.fixture_inventory,
        "load_fixture_inventory",
        lambda _paths: inventory,
    )
    row = {
        "module": "dda",
        "repo_name": "repo",
        "intermediate_hash": "abc123",
    }
    metadata = testdata.metadata_path(paths, row)
    metadata.parent.mkdir(parents=True)
    metadata.write_text('{"b": 2, "a": 1}', encoding="utf-8")
    details = testdata.row_details(paths, row)
    assert details[1].startswith("{\n")
    assert json.loads(details[2]) == {}

    with pytest.raises(ValueError, match="not present"):
        testdata._fixture_for_row(
            paths,
            {**row, "intermediate_hash": "missing"},
        )


def test_testdata_unpopulated_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = testdata.TestDataPaths(data_dir=tmp_path / "fixtures")
    row = {
        "module": "dda",
        "repo_name": "repo",
        "intermediate_hash": "abc123",
    }
    empty_inventory = fixture_inventory.FixtureInventory(
        paths=paths,
        fixtures=(
            _record(
                tmp_path,
                state=fixture_inventory.LocalFixtureState.NOT_LOCAL,
            ),
        ),
    )
    monkeypatch.setattr(
        testdata.fixture_inventory,
        "load_fixture_inventory",
        lambda _paths: empty_inventory,
    )
    assert testdata.row_details(paths, row)[1:] == (
        "Metadata JSON is not cached yet. Run Catalog.",
        "Parameter file is not downloaded yet.",
    )

    text_record = _record(
        tmp_path,
        state=fixture_inventory.LocalFixtureState.COMPLETE,
        parameter_suffix=".txt",
    )
    monkeypatch.setattr(
        testdata.fixture_inventory,
        "load_fixture_inventory",
        lambda _paths: fixture_inventory.FixtureInventory(
            paths=paths,
            fixtures=(text_record,),
        ),
    )
    assert testdata.row_details(paths, row)[2] == "params\n"


def test_provenance_fallbacks_and_sidecar_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provenance,
        "version",
        lambda _name: (_ for _ in ()).throw(PackageNotFoundError),
    )
    monkeypatch.setattr(provenance.shutil, "which", lambda _name: None)
    assert provenance.apb_version() is None
    monkeypatch.setattr(provenance.shutil, "which", lambda _name: "/bin/apb")
    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "1.2.3\n", ""),
    )
    assert provenance.apb_version() == "1.2.3"
    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "failed"),
    )
    assert provenance.apb_version() is None
    monkeypatch.setattr(provenance.shutil, "which", lambda _name: None)
    assert provenance.apb_version() is None

    target = _target(tmp_path)
    snapshot = _snapshot(tmp_path, target)
    record = provenance.record(target, timestamp="now", run=snapshot)
    assert record["fixture_identity"] == ["dda", "repo", "abc123"]
    other = replace(snapshot, fixtures=())
    assert "fixture_identity" not in provenance.record(target, timestamp="now", run=other)

    sidecar = provenance.sidecar_path(target.output)
    provenance._preserve_corrupt_sidecar(sidecar)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(Path, "replace", lambda *_args: (_ for _ in ()).throw(OSError("locked")))
    provenance._preserve_corrupt_sidecar(sidecar)
    monkeypatch.undo()
    sidecar.write_text("{}", encoding="utf-8")
    provenance._preserve_corrupt_sidecar(sidecar)
    provenance.prune_for_target(target)
    assert provenance._now()
