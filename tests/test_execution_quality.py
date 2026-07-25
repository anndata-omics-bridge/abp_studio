"""Edge-path coverage for Corpus Runner orchestration."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from apb_studio import (
    capabilities,
    execution,
    fixture_inventory,
    module_resources,
    run_history,
    settings,
)
from apb_studio.jobrunner import Job, JobStatus
from apb_studio.pipeline import (
    RUN_SNAPSHOT_SCHEMA_VERSION,
    ResolvedFixture,
    RunSnapshot,
    Target,
    write_run_snapshot,
)


def _fixture_record(
    tmp_path: Path,
    *,
    with_files: bool = True,
) -> fixture_inventory.FixtureRecord:
    directory = tmp_path / "fixture"
    directory.mkdir(exist_ok=True)
    inputs: tuple[Path, ...] = ()
    parameters: tuple[Path, ...] = ()
    if with_files:
        input_path = directory / "input_file.tsv"
        parameter_path = directory / "param_0.txt"
        input_path.write_text("x\n", encoding="utf-8")
        parameter_path.write_text("params\n", encoding="utf-8")
        inputs = (input_path,)
        parameters = (parameter_path,)
    return fixture_inventory.FixtureRecord(
        module="dda",
        repo_name="repo",
        intermediate_hash="abcdef123456",
        catalog_software_name="DIA-NN",
        dataset_dir=directory,
        input_files=inputs,
        parameter_files=parameters,
        local_state=fixture_inventory.LocalFixtureState.COMPLETE,
    )


def _snapshot(tmp_path: Path, *, run_id: str = "run") -> RunSnapshot:
    fixture = ResolvedFixture(
        module="dda",
        repo_name="repo",
        intermediate_hash="abcdef123456",
        dataset="diann-abcdef12",
        software="DIA-NN",
        vendor="diann",
        input_path=tmp_path / "input.tsv",
        parameter_path=tmp_path / "params.txt",
        branches=("ion",),
        capability_status="supported",
    )
    target = Target(
        module="repo",
        dataset=fixture.dataset,
        stage="convert",
        output=tmp_path / "outputs" / "repo" / fixture.dataset / "ion.h5ad",
        command=["apb", "convert"],
        branch="ion",
    )
    return RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id=run_id,
        created_at="now",
        test_data_root=tmp_path / "fixtures",
        output_root=tmp_path / "outputs",
        registry_digest="digest",
        apb_version=None,
        fixtures=(fixture,),
        targets=(target,),
    )


class _Process:
    pid = 1

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _job(tmp_path: Path) -> Job:
    return Job(("snakemake",), _Process(), tmp_path / "job.log")


def _status(tmp_path: Path, *, running: bool) -> JobStatus:
    return JobStatus(
        command=("snakemake",),
        returncode=None if running else 0,
        running=running,
        log_file=tmp_path / "job.log",
        log_text="",
    )


def test_incomplete_fixture_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inconsistent = _fixture_record(tmp_path, with_files=False)
    monkeypatch.setattr(
        fixture_inventory.FixtureRecord,
        "input_path",
        property(lambda _fixture: None),
    )
    monkeypatch.setattr(
        fixture_inventory.FixtureRecord,
        "parameter_path",
        property(lambda _fixture: None),
    )
    with pytest.raises(ValueError, match="Fixture is not complete"):
        execution._discover_fixture(
            inconsistent,
            lambda *_args: capabilities.CapabilityDiscovery(("ion",)),
        )

    active_settings = settings.StudioSettings(
        test_data_root=tmp_path / "fixtures",
        output_root=tmp_path / "outputs",
    )
    inventory = fixture_inventory.FixtureInventory(
        paths=fixture_inventory.FixtureStorePaths(data_dir=active_settings.test_data_root),
        fixtures=(inconsistent,),
    )
    monkeypatch.setattr(execution, "load_settings", lambda _path=None: active_settings)
    monkeypatch.setattr(execution, "load_fixture_inventory", lambda _root: inventory)
    monkeypatch.setattr(
        execution,
        "load_module_resources",
        lambda _root: module_resources.ModuleResourceInventory(),
    )
    monkeypatch.setattr(
        execution,
        "_discover_fixture",
        lambda *_args: capabilities.CapabilityDiscovery(
            ("ion",),
            software_slug="diann",
        ),
    )
    monkeypatch.setattr(
        execution,
        "resolve_output_aliases",
        lambda *_args, **_kwargs: {inconsistent.identity: "diann-abcdef12"},
    )
    with pytest.raises(ValueError, match="no unique input and parameter"):
        execution.resolve_current_run()


def test_alias_store_validation_and_exhaustion(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid output alias"):
        execution._validate_alias("../escape")

    output_root = tmp_path / "output"
    path = execution.output_alias_path(output_root)
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version": 9}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported output alias map"):
        execution._load_output_aliases(output_root)

    duplicate = {
        "schema_version": 1,
        "aliases": [
            {
                "module": "dda",
                "repo_name": "repo",
                "intermediate_hash": "hash",
                "output_alias": "diann-hash",
            },
            {
                "module": "dda",
                "repo_name": "repo",
                "intermediate_hash": "hash",
                "output_alias": "diann-other",
            },
        ],
    }
    path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate fixture identity"):
        execution._load_output_aliases(output_root)

    identity = ("dda", "repo", "hash")
    digest = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()
    base = "diann-hash"
    used = {
        ("repo", "diann-hash"): ("other", "repo", "hash"),
        **{
            ("repo", f"{base}-{digest[:width]}"): ("other", "repo", str(width))
            for width in range(8, len(digest) + 1, 4)
        },
    }
    with pytest.raises(ValueError, match="Could not allocate"):
        execution._available_output_alias("diann", "hash", "repo", used, identity)


def test_snapshot_log_prepare_and_job_state_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview = _snapshot(tmp_path, run_id="")
    with pytest.raises(ValueError, match="preview"):
        execution.run_snapshot_path(preview)

    snapshot = _snapshot(tmp_path)
    run_path = execution.run_snapshot_path(snapshot)
    monkeypatch.setattr(execution, "_RUNS", {"job": run_path})
    monkeypatch.setattr(execution, "_JOBS", {})
    assert execution.corpus_log_path(job_id="job") == run_path.parent / "snakemake.log"
    assert execution.corpus_log_path(snapshot) == run_path.parent / "snakemake.log"
    assert execution.corpus_log_path(preview) == preview.output_root / ".apb_studio/snakemake.log"
    monkeypatch.setattr(
        execution,
        "load_settings",
        lambda: settings.StudioSettings(
            test_data_root=tmp_path / "fixtures",
            output_root=tmp_path / "fallback",
        ),
    )
    assert execution.corpus_log_path() == tmp_path / "fallback/.apb_studio/snakemake.log"

    monkeypatch.setattr(execution, "resolve_current_run", lambda **_kwargs: snapshot)
    monkeypatch.setattr(execution, "runnable_targets", lambda _targets: [])
    with pytest.raises(ValueError, match="no runnable stages"):
        execution.prepare_run()

    job = _job(tmp_path)
    monkeypatch.setattr(execution, "_JOBS", {"active": job})
    monkeypatch.setattr(execution, "inspect_job", lambda _job: _status(tmp_path, running=True))
    with pytest.raises(RuntimeError, match="already active"):
        execution.launch_corpus()

    monkeypatch.setattr(execution, "_RUNS", {})
    assert execution._running_snapshot("missing") is None
    monkeypatch.setattr(execution, "_RUNS", {"active": run_path})
    monkeypatch.setattr(execution, "_JOBS", {"active": job})
    monkeypatch.setattr(execution, "inspect_job", lambda _job: _status(tmp_path, running=False))
    assert execution._running_snapshot("active") is None

    assert execution.inspect_corpus_job("unknown") is None
    monkeypatch.setattr(execution, "_JOBS", {"active": job})
    monkeypatch.setattr(execution, "active_corpus_job_id", lambda: "active")
    assert execution.inspect_corpus_job(None) is not None


def test_clean_targets_removes_directory_output(tmp_path: Path) -> None:
    output = tmp_path / "outputs" / "directory"
    output.mkdir(parents=True)
    (output / "file").write_text("x", encoding="utf-8")
    target = Target("module", "dataset", "convert", output, [], [])
    deleted = execution.clean_targets([target], input_root=tmp_path / "inputs")
    assert deleted == [output]
    assert not output.exists()


def test_latest_persisted_run_skips_invalid_and_foreign_snapshots(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs"
    invalid = output_root / ".apb_studio/runs/newest/run.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("not JSON", encoding="utf-8")

    foreign = _snapshot(tmp_path / "foreign", run_id="foreign")
    foreign_path = output_root / ".apb_studio/runs/foreign/run.json"
    write_run_snapshot(foreign, foreign_path)

    snapshot = _snapshot(tmp_path, run_id="valid")
    valid_path = execution.run_snapshot_path(snapshot)
    write_run_snapshot(snapshot, valid_path)
    (valid_path.parent / "snakemake.log").write_text("persisted log", encoding="utf-8")
    run_history.start_operation(valid_path, "run", started_at="now")
    run_history.mark_operation(valid_path, "succeeded", finished_at="later")
    orphan = _snapshot(tmp_path, run_id="orphan")
    orphan_path = execution.run_snapshot_path(orphan)
    write_run_snapshot(orphan, orphan_path)
    os.utime(valid_path, (1, 1))
    os.utime(foreign_path, (2, 2))
    os.utime(orphan_path, (3, 3))
    os.utime(invalid, (4, 4))

    persisted = execution.latest_persisted_run(output_root)

    assert persisted is not None
    assert persisted.snapshot == snapshot
    assert persisted.log_path.read_text(encoding="utf-8") == "persisted log"
    assert persisted.operation is not None
    assert persisted.operation.status == "succeeded"
    assert execution.latest_persisted_run(tmp_path / "missing") is None
    empty_runs = tmp_path / "empty/.apb_studio/runs"
    empty_runs.mkdir(parents=True)
    assert execution.latest_persisted_run(tmp_path / "empty") is None


def test_operation_launch_failure_is_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(tmp_path)
    run_path = execution.run_snapshot_path(snapshot)
    write_run_snapshot(snapshot, run_path)
    monkeypatch.setattr(execution, "_JOBS", {})
    monkeypatch.setattr(execution, "_RUNS", {})
    monkeypatch.setattr(
        execution,
        "prepare_run",
        lambda **_kwargs: (snapshot, run_path, list(snapshot.targets)),
    )
    monkeypatch.setattr(
        execution,
        "run_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cannot start")),
    )

    with pytest.raises(OSError, match="cannot start"):
        execution.clear_corpus()

    operation = run_history.load_operation(run_path)
    assert operation is not None
    assert operation.status == "failed"


def test_clean_prepare_and_operation_lookup_edge_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = _snapshot(tmp_path)
    empty = RunSnapshot(
        schema_version=empty.schema_version,
        run_id=empty.run_id,
        created_at=empty.created_at,
        test_data_root=empty.test_data_root,
        output_root=empty.output_root,
        registry_digest=empty.registry_digest,
        apb_version=empty.apb_version,
        fixtures=empty.fixtures,
        targets=(),
    )
    monkeypatch.setattr(execution, "resolve_current_run", lambda **_kwargs: empty)
    with pytest.raises(ValueError, match="no managed stages"):
        execution.prepare_run(operation="clean")

    run_path = tmp_path / "operation/run.json"
    run_history.start_operation(run_path, "clean", started_at="now")
    monkeypatch.setattr(execution, "_RUNS", {"job": run_path})
    monkeypatch.setattr(execution, "active_corpus_job_id", lambda: "job")
    record = execution.corpus_operation(None)
    assert record is not None
    assert record.operation == "clean"
    assert execution.corpus_operation("unknown") is None


def test_clean_targets_accepts_absent_artifact(tmp_path: Path) -> None:
    target = Target(
        "module",
        "dataset",
        "convert",
        tmp_path / "outputs/missing.h5ad",
        [],
        [],
    )

    assert execution.clean_targets([target], input_root=tmp_path / "inputs") == []
