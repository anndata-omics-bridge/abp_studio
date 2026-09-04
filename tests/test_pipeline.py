"""Tests for APB2-only target expansion and progress state."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from apb_studio import pipeline as pipeline_module
from apb_studio.pipeline import (
    AGGREGATE_ARTIFACT_RE,
    CONVERT_ARTIFACT_RE,
    FASTA_ARTIFACT_RE,
    PROTEOBENCH_ARTIFACT_RE,
    RAW_PROTEOBENCH_ARTIFACT_RE,
    RUN_SNAPSHOT_SCHEMA_VERSION,
    Pipeline,
    ResolvedFixture,
    RunSnapshot,
    Target,
    apb2_branch,
    branch_converter,
    branch_level,
    branch_rows,
    command_template,
    convert_artifact,
    coverage,
    expand_resolved_targets,
    load_pipeline,
    load_run_snapshot,
    reject_input_paths,
    render_command,
    runnable_targets,
    stage_order,
    write_run_snapshot,
)
from apb_studio.registry import REGISTRY_PATH, load_registry

_SNAKEFILE = REGISTRY_PATH.parent.parent / "workflow" / "Snakefile"
_REGISTRY = load_registry()
_PIPELINE = load_pipeline()


def _touch(target: Target) -> None:
    target.output.parent.mkdir(parents=True, exist_ok=True)
    target.output.touch()


def _resolved_fixture(
    tmp_path: Path,
    *,
    branches: tuple[str, ...] = ("mudata",),
    capability_status: str = "supported",
    module_settings: Path | None = None,
    fasta: Path | None = None,
    diagnostic: str | None = None,
    parameter_vendor: str = "diann",
) -> ResolvedFixture:
    input_path = tmp_path / "input.tsv"
    parameter_path = tmp_path / "param.txt"
    input_path.write_text("x\n")
    parameter_path.write_text("params\n")
    return ResolvedFixture(
        module="dda_qexactive",
        repo_name="Results_quant_ion_DDA",
        intermediate_hash="abc123456789",
        dataset="diann-abc12345",
        software="DIA-NN",
        vendor="diann",
        parameter_vendor=parameter_vendor,
        input_path=input_path,
        parameter_path=parameter_path,
        branches=branches,
        capability_status=capability_status,
        diagnostic=diagnostic,
        annotation_path=module_settings,
        fasta_path=fasta,
    )


def _resources(tmp_path: Path) -> tuple[Path, Path]:
    module_settings = tmp_path / "module.toml"
    fasta = tmp_path / "proteome.fasta"
    module_settings.write_text("[general]\nlevel = 'ion'\n")
    fasta.write_text(">P1\nPEPTIDE\n")
    return module_settings, fasta


def _run_snapshot(
    tmp_path: Path,
    fixture: ResolvedFixture,
    targets: list[Target],
    *,
    pipeline: Pipeline | None = None,
) -> RunSnapshot:
    return RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id="run-1",
        created_at="2026-07-22T00:00:00+00:00",
        test_data_root=tmp_path,
        output_root=tmp_path / "out",
        registry_digest="digest",
        apb_version="1.0",
        pipeline=pipeline or load_pipeline(),
        fixtures=(fixture,),
        targets=tuple(targets),
    )


def test_convert_artifact_is_branch_driven() -> None:
    assert convert_artifact("mudata") == "mudata.h5mu"
    assert convert_artifact("ion") == "ion.h5ad"
    with pytest.raises(ValueError, match="unknown conversion branch"):
        convert_artifact("protien")


def test_render_command_preserves_values_and_omits_empty_level() -> None:
    command = render_command(
        "apb2 convert {input} {level} --output {output}",
        {"input": "/in/my data.tsv", "level": "", "output": "/out/m"},
    )
    assert command == ["apb2", "convert", "/in/my data.tsv", "--output", "/out/m"]
    with pytest.raises(KeyError, match="params"):
        render_command("apb2 convert {params}", {})


def test_staged_pipeline_fans_out_each_supported_branch(tmp_path: Path) -> None:
    module_settings, fasta = _resources(tmp_path)
    branches = ("mudata", "ion", "fragment", "protein")
    fixture = _resolved_fixture(
        tmp_path,
        branches=branches,
        module_settings=module_settings,
        fasta=fasta,
    )
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    assert len(targets) == 11
    assert {(target.branch, target.stage) for target in targets} == {
        ("mudata", "convert"),
        ("mudata", "fasta"),
        ("mudata", "aggregate-ion"),
        ("mudata", "aggregate-fragment"),
        ("mudata", "proteobench"),
        ("ion", "convert"),
        ("ion", "fasta"),
        ("ion", "proteobench"),
        ("fragment", "convert"),
        ("fragment", "fasta"),
        ("protein", "convert"),
    }
    assert {target.command[0] for target in targets} == {
        "apb2",
        "apb-aggregate",
        "apb-fasta",
        "apb-proteobench",
    }


def test_staged_pipeline_connects_three_cli_calls(tmp_path: Path) -> None:
    module_settings, fasta_path = _resources(tmp_path)
    fixture = _resolved_fixture(
        tmp_path,
        branches=("ion",),
        module_settings=module_settings,
        fasta=fasta_path,
    )
    targets = {
        target.stage: target
        for target in expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    }
    assert list(targets) == ["convert", "fasta", "proteobench"]
    assert targets["convert"].command[:4] == [
        "apb2",
        "convert",
        str(fixture.input_path),
        "ion",
    ]
    assert targets["fasta"].inputs == [targets["convert"].output, fasta_path]
    assert targets["fasta"].command[:3] == [
        "apb-fasta",
        "verify-peptides",
        str(targets["convert"].output),
    ]
    assert targets["proteobench"].inputs == [targets["fasta"].output, module_settings]
    assert targets["proteobench"].command == [
        "apb-proteobench",
        "benchmark",
        str(targets["fasta"].output),
        str(module_settings),
        str(targets["proteobench"].output),
    ]


def test_mudata_pipeline_applies_both_existing_aggregate_commands(tmp_path: Path) -> None:
    module_settings, fasta_path = _resources(tmp_path)
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion", "fragment"),
        module_settings=module_settings,
        fasta=fasta_path,
    )
    targets = {
        target.stage: target
        for target in expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
        if target.branch == "mudata"
    }

    assert list(targets) == [
        "convert",
        "fasta",
        "aggregate-ion",
        "aggregate-fragment",
        "proteobench",
    ]
    assert targets["aggregate-ion"].command[:4] == [
        "apb-aggregate",
        "ion",
        "protein",
        "sum",
    ]
    assert targets["aggregate-ion"].inputs == [targets["fasta"].output]
    assert targets["aggregate-fragment"].command[:4] == [
        "apb-aggregate",
        "fragment",
        "protein",
        "sum",
    ]
    assert targets["aggregate-fragment"].inputs == [targets["aggregate-ion"].output]
    assert targets["proteobench"].inputs == [
        targets["aggregate-fragment"].output,
        module_settings,
    ]


def test_mudata_pipeline_skips_missing_fragment_aggregation(tmp_path: Path) -> None:
    module_settings, fasta_path = _resources(tmp_path)
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion"),
        module_settings=module_settings,
        fasta=fasta_path,
    )
    targets = {
        target.stage: target
        for target in expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
        if target.branch == "mudata"
    }

    assert "aggregate-fragment" not in targets
    assert targets["proteobench"].inputs[0] == targets["aggregate-ion"].output


def test_mudata_pipeline_runs_fragment_without_ion_aggregation(tmp_path: Path) -> None:
    module_settings, fasta_path = _resources(tmp_path)
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "fragment"),
        module_settings=module_settings,
        fasta=fasta_path,
    )
    targets = {
        target.stage: target
        for target in expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
        if target.branch == "mudata"
    }

    assert "aggregate-ion" not in targets
    assert targets["aggregate-fragment"].inputs == [targets["fasta"].output]
    assert targets["proteobench"].inputs[0] == targets["aggregate-fragment"].output


def test_convert_uses_separate_result_and_parameter_software(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("ion",), parameter_vendor="fragpipe")
    target = expand_resolved_targets(load_pipeline("convert"), (fixture,), tmp_path / "out")[0]
    assert target.command[target.command.index("--software") + 1] == "diann"
    assert target.command[target.command.index("--params-software") + 1] == "fragpipe"


def test_direct_pipeline_is_one_raw_to_scored_mudata_call(tmp_path: Path) -> None:
    module_settings, fasta = _resources(tmp_path)
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion", "protein"),
        module_settings=module_settings,
        fasta=fasta,
    )
    targets = expand_resolved_targets(load_pipeline("direct"), (fixture,), tmp_path / "out")
    assert len(targets) == 1
    target = targets[0]
    assert target.branch == "mudata"
    assert target.stage == "raw-proteobench"
    assert target.output.name == "mudata.raw-proteobench.h5mu"
    assert target.command[:4] == [
        "apb-proteobench",
        "run",
        str(fixture.input_path),
        str(fasta),
    ]
    assert target.command[target.command.index("--params") + 1] == str(fixture.parameter_path)
    assert target.command[target.command.index("--module") + 1] == str(module_settings)
    assert target.inputs == [
        fixture.input_path,
        fixture.parameter_path,
        fasta,
        module_settings,
    ]


def test_direct_pipeline_is_blocked_by_missing_resources(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("mudata",))
    target = expand_resolved_targets(load_pipeline("direct"), (fixture,), tmp_path / "out")[0]
    assert target.command == []
    assert target.blocked_reason == "Missing module resource: module_settings"
    assert runnable_targets([target]) == []


def test_registry_order_represents_staged_and_direct_paths() -> None:
    order = stage_order(_REGISTRY)
    assert order.index("convert") < order.index("fasta") < order.index("proteobench")
    assert "raw-proteobench" in order


def test_artifact_regexes_are_disjoint_and_branch_qualified() -> None:
    assert re.fullmatch(CONVERT_ARTIFACT_RE, "ion.h5ad")
    assert re.fullmatch(FASTA_ARTIFACT_RE, "ion.fasta.h5ad")
    assert re.fullmatch(AGGREGATE_ARTIFACT_RE, "mudata.aggregate-ion.h5mu")
    assert re.fullmatch(AGGREGATE_ARTIFACT_RE, "mudata.aggregate-fragment.h5mu")
    assert re.fullmatch(PROTEOBENCH_ARTIFACT_RE, "protein.proteobench.h5ad")
    assert re.fullmatch(RAW_PROTEOBENCH_ARTIFACT_RE, "mudata.raw-proteobench.h5mu")
    assert re.fullmatch(CONVERT_ARTIFACT_RE, "mudata.h5mu")
    assert not re.fullmatch(CONVERT_ARTIFACT_RE, "ion.fasta.h5ad")
    assert not re.fullmatch(RAW_PROTEOBENCH_ARTIFACT_RE, "ion.raw-proteobench.h5ad")


def test_missing_resources_keep_convert_runnable(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    assert [target.stage for target in targets] == ["convert", "fasta", "proteobench"]
    assert [target.stage for target in runnable_targets(targets)] == ["convert"]
    assert targets[1].blocked_reason == "Missing module resource: fasta"
    assert targets[2].blocked_reason == "Missing module resource: module_settings"
    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]
    assert row["convert"] == ""
    assert row["fasta"] == "UNSUPPORTED"
    assert row["proteobench"] == "UNSUPPORTED"


def test_invalid_capability_is_failed_and_downstream_is_unavailable(tmp_path: Path) -> None:
    fixture = _resolved_fixture(
        tmp_path,
        branches=(),
        capability_status="failed",
        diagnostic="invalid parameter file",
    )
    row = branch_rows(_run_snapshot(tmp_path, fixture, []), [])[0]
    assert row["convert"] == "FAILED"
    assert row["fasta"] == ""
    assert row["proteobench"] == ""
    assert row["_stage_details"]["convert"]["error"] == "invalid parameter file"


def test_unresolved_capability_is_retained_as_unsupported_row(tmp_path: Path) -> None:
    fixture = _resolved_fixture(
        tmp_path,
        branches=(),
        capability_status="unsupported",
        diagnostic="No APB2 parsing rule matches this input",
    )
    row = branch_rows(_run_snapshot(tmp_path, fixture, []), [])[0]
    assert row["level"] == "Unresolved"
    assert row["convert"] == "UNSUPPORTED"
    assert row["_stage_details"]["fasta"]["state"] == "unavailable"


def test_rows_update_from_pending_to_completed_and_failed(tmp_path: Path) -> None:
    module_settings, fasta = _resources(tmp_path)
    fixture = _resolved_fixture(tmp_path, module_settings=module_settings, fasta=fasta)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    converted = next(target for target in targets if target.stage == "convert")
    checked = next(target for target in targets if target.stage == "fasta")
    _touch(converted)
    Path(f"{checked.output}.log").write_text("Traceback\nValueError: peptide mismatch\n")
    Path(f"{checked.output}.failed").write_text("exit 1\n")
    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]
    assert row["convert"] == "DONE"
    assert row["fasta"] == "FAILED"
    assert row["proteobench"] == ""
    assert "peptide mismatch" in row["_stage_details"]["fasta"]["error"]
    assert row["_stage_details"]["convert"]["command"].startswith("apb2 convert ")


def test_runnable_targets_keep_existing_outputs_for_snakemake_staleness(tmp_path: Path) -> None:
    module_settings, fasta = _resources(tmp_path)
    fixture = _resolved_fixture(tmp_path, module_settings=module_settings, fasta=fasta)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    for target in targets:
        _touch(target)
    assert runnable_targets(targets) == targets


def test_growing_rule_log_is_pending_until_failure_marker_exists(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    converted = targets[0]
    converted.output.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{converted.output}.log").write_text("Reading input table...\n")
    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]
    assert row["_stage_details"]["convert"]["state"] == "pending"


def test_existing_artifact_wins_over_failure_marker(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    converted = targets[0]
    _touch(converted)
    Path(f"{converted.output}.failed").write_text("exit 1\n")
    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]
    assert row["convert"] == "DONE"


def test_coverage_includes_branch_and_flips_on_artifact(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    _touch(targets[0])
    rows = coverage(targets)
    assert {row["branch"] for row in rows} == {"mudata"}
    assert rows[0]["done"]


def test_run_snapshot_round_trip_is_create_only(tmp_path: Path) -> None:
    module_settings, fasta = _resources(tmp_path)
    fixture = _resolved_fixture(tmp_path, module_settings=module_settings, fasta=fasta)
    targets = expand_resolved_targets(_PIPELINE, (fixture,), tmp_path / "out")
    snapshot = _run_snapshot(tmp_path, fixture, targets)
    path = tmp_path / "runs" / "run-1" / "run.json"
    write_run_snapshot(snapshot, path)
    assert load_run_snapshot(path) == snapshot
    with pytest.raises(FileExistsError):
        write_run_snapshot(snapshot, path)


def test_rows_follow_snapshot_pipeline(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("mudata", "ion"))
    selection = load_pipeline("convert")
    targets = expand_resolved_targets(selection, (fixture,), tmp_path / "out")
    rows = branch_rows(_run_snapshot(tmp_path, fixture, targets, pipeline=selection), targets)
    assert [row["level"] for row in rows] == ["MuData", "ion"]
    assert selection.columns == ("convert",)
    assert "fasta" not in rows[0]


def test_direct_pipeline_rows_have_one_stage(tmp_path: Path) -> None:
    module_settings, fasta = _resources(tmp_path)
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion", "protein"),
        module_settings=module_settings,
        fasta=fasta,
    )
    selection = load_pipeline("direct")
    targets = expand_resolved_targets(selection, (fixture,), tmp_path / "out")
    rows = branch_rows(_run_snapshot(tmp_path, fixture, targets, pipeline=selection), targets)
    assert len(rows) == 1
    assert rows[0]["level"] == "MuData"
    assert selection.columns == ("raw-proteobench",)


def test_completed_stage_records_artifact_size(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("ion",))
    selection = load_pipeline("convert")
    targets = expand_resolved_targets(selection, (fixture,), tmp_path / "out")
    target = targets[0]
    target.output.parent.mkdir(parents=True, exist_ok=True)
    target.output.write_bytes(b"x" * 1234)
    detail = branch_rows(_run_snapshot(tmp_path, fixture, targets, pipeline=selection), targets)[0][
        "_stage_details"
    ]["convert"]
    assert detail["bytes"] == "1234"
    target.output.unlink()
    assert pipeline_module._artifact_bytes(target.output) is None


def test_branch_identity_is_apb2_only() -> None:
    assert apb2_branch("ion") == "ion"
    assert branch_converter("ion") == "apb2"
    assert branch_level("ion") == "ion"
    assert branch_level("mudata") is None
    with pytest.raises(ValueError, match="unknown conversion branch"):
        branch_converter("ion.apb2")


def test_historical_command_maps_still_render_or_report_missing_converter() -> None:
    stage = {"name": "convert", "commands": {"apb2": "apb2 convert {input}"}}
    assert command_template(stage, "apb2") == "apb2 convert {input}"
    with pytest.raises(KeyError, match="convert.*legacy"):
        command_template(stage, "legacy")


def test_expansion_ignores_branches_for_an_unselected_snapshot_converter(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("ion",))
    selection = Pipeline(
        name="historical",
        description="Historical snapshot",
        converters=("legacy",),
        stages=load_pipeline("convert").stages,
    )
    assert expand_resolved_targets(selection, (fixture,), tmp_path / "out") == []


def test_rows_retain_unavailable_cells_for_historical_multi_converter_snapshots(
    tmp_path: Path,
) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("ion",))
    current = load_pipeline("convert")
    targets = expand_resolved_targets(current, (fixture,), tmp_path / "out")
    historical = Pipeline(
        name="historical",
        description="Historical comparison snapshot",
        converters=("apb2", "legacy"),
        stages=current.stages,
    )
    rows = branch_rows(_run_snapshot(tmp_path, fixture, targets, pipeline=historical), targets)
    assert rows[0]["convert2"] == ""
    assert rows[0]["_stage_details"]["convert2"]["state"] == "unavailable"


def test_rows_skip_levels_owned_only_by_an_unselected_snapshot_converter(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path, branches=("ion",))
    historical = Pipeline(
        name="historical",
        description="Historical snapshot",
        converters=("legacy",),
        stages=load_pipeline("convert").stages,
    )
    assert branch_rows(_run_snapshot(tmp_path, fixture, [], pipeline=historical), []) == []


def test_clean_guard_survives_python_optimized_mode() -> None:
    code = (
        "from pathlib import Path\n"
        "from apb_studio.pipeline import reject_input_paths, CleanGuardError\n"
        "try:\n"
        "    reject_input_paths([Path('/in/raw.tsv')], Path('/in')); print('NO_RAISE')\n"
        "except CleanGuardError:\n"
        "    print('RAISED')\n"
    )
    result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)
    assert result.stdout.strip() == "RAISED", result.stdout + result.stderr


def test_reject_input_paths_accepts_outputs_elsewhere() -> None:
    assert reject_input_paths([Path("/out/result.h5ad")], Path("/in")) == [Path("/out/result.h5ad")]


def test_snakefile_executes_all_four_tools_and_direct_rule() -> None:
    snakefile = _SNAKEFILE.read_text()
    assert "load_run_snapshot" in snakefile
    assert '"apb2": _tool_command' in snakefile
    assert '"apb-aggregate": _tool_command' in snakefile
    assert '"apb-fasta": _tool_command' in snakefile
    assert '"apb-proteobench": _tool_command' in snakefile
    assert "rule raw_proteobench:" in snakefile
    assert '"apb": _tool_command' not in snakefile
    assert "--keep-going" not in snakefile
