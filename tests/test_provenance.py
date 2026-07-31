"""Tests for the provenance sidecar (decision 17)."""

import json
from pathlib import Path

from loguru import logger

from apb_studio.pipeline import (
    RUN_SNAPSHOT_SCHEMA_VERSION,
    ResolvedFixture,
    RunSnapshot,
    Target,
    write_run_snapshot,
)
from apb_studio.provenance import (
    apb_version,
    app,
    main,
    prune_for_target,
    record,
    sidecar_path,
    write_for_target,
)


def _t(
    out_dir: Path | str,
    stage: str = "convert",
    name: str = "mudata.h5mu",
) -> Target:
    return Target("m", "d", stage, Path(out_dir) / name, ["apb", stage, "x"], [Path("/in/x")])


def _run(tmp_path: Path, *targets: Target) -> tuple[RunSnapshot, Path]:
    fixture = ResolvedFixture(
        module="dda",
        repo_name="m",
        intermediate_hash="abcdef123456",
        dataset="d",
        software="DIA-NN",
        vendor="diann",
        input_path=tmp_path / "input.tsv",
        parameter_path=tmp_path / "params.txt",
        branches=("mudata",),
        capability_status="supported",
    )
    snapshot = RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id="run-1",
        created_at="2026-07-22T00:00:00+00:00",
        test_data_root=tmp_path,
        output_root=tmp_path / "out",
        registry_digest="registry-hash",
        apb_version="0.1.0",
        fixtures=(fixture,),
        targets=tuple(targets),
    )
    path = tmp_path / "run.json"
    write_run_snapshot(snapshot, path)
    return snapshot, path


def test_record_shape():
    rec = record(_t("/out"), timestamp="2026-06-29T00:00:00+00:00", version="0.1.0")
    assert rec == {
        "stage": "convert",
        "artifact": "mudata.h5mu",
        "command": ["apb", "convert", "x"],
        "inputs": ["/in/x"],
        "apb_version": "0.1.0",
        "timestamp": "2026-06-29T00:00:00+00:00",
    }


def test_write_for_target_keeps_same_stage_branches_separate(tmp_path: Path) -> None:
    mudata = _t(tmp_path, stage="convert", name="mudata.h5mu")
    ion = _t(tmp_path, stage="convert", name="ion.h5ad")

    mudata_path = write_for_target(mudata, timestamp="t1", version="0.1.0")
    ion_path = write_for_target(ion, timestamp="t2", version="0.1.0")

    assert mudata_path == tmp_path / "mudata.h5mu.provenance.json"
    assert ion_path == tmp_path / "ion.h5ad.provenance.json"
    assert json.loads(mudata_path.read_text())["artifact"] == "mudata.h5mu"
    ion_data = json.loads(ion_path.read_text())
    assert ion_data["artifact"] == "ion.h5ad"
    assert ion_data["stage"] == "convert"
    assert ion_data["timestamp"] == "t2"


def test_prune_for_target_removes_only_its_artifact_sidecar(tmp_path: Path) -> None:
    mudata = _t(tmp_path, stage="convert", name="mudata.h5mu")
    ion = _t(tmp_path, stage="convert", name="ion.h5ad")
    mudata_path = write_for_target(mudata, timestamp="t1")
    ion_path = write_for_target(ion, timestamp="t2")

    prune_for_target(mudata)

    assert not mudata_path.exists()
    assert ion_path.exists()


def test_corrupt_sidecar_is_backed_up_not_lost(tmp_path: Path) -> None:
    target = _t(tmp_path, stage="convert")
    path = sidecar_path(target.output)
    path.write_text("}{ not json")
    write_for_target(target, timestamp="t")
    assert Path(f"{path}.bak").exists()  # corrupt file preserved
    assert json.loads(path.read_text())["stage"] == "convert"  # fresh, valid


def test_main_writes_sidecar_for_an_output(tmp_path: Path) -> None:
    convert = Target(
        module="m",
        dataset="d",
        stage="convert",
        output=tmp_path / "out/m/d/mudata.h5mu",
        command=["apb", "convert"],
        branch="mudata",
    )
    _snapshot, run_path = _run(tmp_path, convert)
    convert.output.parent.mkdir(parents=True)
    convert.output.touch()
    assert main(["--run", str(run_path), "--output", str(convert.output)]) == 0
    data = json.loads(sidecar_path(convert.output).read_text())
    assert data["stage"] == "convert"
    assert data["artifact"] == "mudata.h5mu"
    assert data["run_id"] == "run-1"
    assert data["fixture_identity"] == ["dda", "m", "abcdef123456"]


def test_cli_preserves_run_and_output_options(tmp_path: Path) -> None:
    _snapshot, run_path = _run(tmp_path)

    command, bound, ignored = app.parse_args(
        ["--run", str(run_path), "--output", "/out/mudata.h5mu"],
        exit_on_error=False,
    )

    assert command.__name__ == "write_provenance"
    assert bound.arguments == {
        "run": run_path,
        "output": Path("/out/mudata.h5mu"),
    }
    assert ignored == {}


def test_main_rejects_unknown_output_with_loguru_diagnostic(tmp_path: Path) -> None:
    _snapshot, run_path = _run(tmp_path)
    messages: list[str] = []
    sink = logger.add(messages.append, format="{message}")
    try:
        assert main(["--run", str(run_path), "--output", "/out/nope/mudata.h5mu"]) == 2
    finally:
        logger.remove(sink)

    assert any("Refusing provenance for output outside this run" in message for message in messages)


def test_main_rejects_a_known_output_that_was_not_created(tmp_path: Path) -> None:
    convert = Target(
        module="m",
        dataset="d",
        stage="convert",
        output=tmp_path / "out/m/d/mudata.h5mu",
        command=["apb", "convert"],
        branch="mudata",
    )
    _snapshot, run_path = _run(tmp_path, convert)

    assert main(["--run", str(run_path), "--output", str(convert.output)]) == 1
    assert not sidecar_path(convert.output).exists()


def test_apb_version_returns_str_or_none():
    assert apb_version() is None or isinstance(apb_version(), str)
