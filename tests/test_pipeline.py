"""Tests for resolved-fixture target expansion and progress state."""

import subprocess
import sys
from pathlib import Path

import pytest

from apb_studio.pipeline import (
    ANNOTATE_ARTIFACT_RE,
    CONVERT_ARTIFACT_RE,
    FASTA_ARTIFACT_RE,
    PROTEOBENCH_ARTIFACT_RE,
    RUN_SNAPSHOT_SCHEMA_VERSION,
    ResolvedFixture,
    RunSnapshot,
    Target,
    branch_rows,
    convert_artifact,
    coverage,
    expand_resolved_targets,
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


def _touch(target: Target) -> None:
    target.output.parent.mkdir(parents=True, exist_ok=True)
    target.output.touch()


def _resolved_fixture(
    tmp_path: Path,
    *,
    branches: tuple[str, ...] = ("mudata",),
    capability_status: str = "supported",
    annotation: Path | None = None,
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
        annotation_path=annotation,
        fasta_path=fasta,
    )


def _run_snapshot(
    tmp_path: Path,
    fixture: ResolvedFixture,
    targets: list[Target],
) -> RunSnapshot:
    return RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id="run-1",
        created_at="2026-07-22T00:00:00+00:00",
        test_data_root=tmp_path,
        output_root=tmp_path / "out",
        registry_digest="digest",
        apb_version="1.0",
        fixtures=(fixture,),
        targets=tuple(targets),
    )


def test_convert_artifact_is_branch_driven() -> None:
    assert convert_artifact("mudata") == "mudata.h5mu"
    assert convert_artifact("ion") == "ion.h5ad"
    with pytest.raises(ValueError, match="unknown conversion branch"):
        convert_artifact("protien")


def test_render_command_substitutes_without_splitting_values() -> None:
    command = render_command(
        "apb convert {input} --software {vendor} --output {output}",
        {"input": "/in/my data.tsv", "vendor": "diann", "output": "/out/m"},
    )
    assert command == [
        "apb",
        "convert",
        "/in/my data.tsv",
        "--software",
        "diann",
        "--output",
        "/out/m",
    ]
    with pytest.raises(KeyError, match="params"):
        render_command("apb {params}", {})


def test_resolved_expansion_fans_out_every_supported_branch_through_all_stages(
    tmp_path: Path,
) -> None:
    annotation = tmp_path / "annotation.toml"
    fasta = tmp_path / "proteome.fasta"
    annotation.touch()
    fasta.touch()
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion", "fragment", "protein"),
        annotation=annotation,
        fasta=fasta,
    )
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    assert len(targets) == 16
    assert {(target.branch, target.stage) for target in targets} == {
        (branch, stage)
        for branch in ("mudata", "ion", "fragment", "protein")
        for stage in ("convert", "annotate", "fasta", "proteobench")
    }

    names = {target.output.name for target in targets}
    assert {
        "mudata.h5mu",
        "mudata.annotated.h5mu",
        "mudata.fasta.h5mu",
        "ion.h5ad",
        "ion.annotated.h5ad",
        "ion.fasta.h5ad",
        "fragment.h5ad",
        "fragment.annotated.h5ad",
        "fragment.fasta.h5ad",
    } <= names

    mudata = next(
        target for target in targets if target.branch == "mudata" and target.stage == "convert"
    )
    ion = next(target for target in targets if target.branch == "ion" and target.stage == "convert")
    assert "--level" not in mudata.command
    assert ion.command[-2:] == ["--level", "ion"]
    assert mudata.command[mudata.command.index("--output") + 1].endswith("/mudata")
    assert ion.command[ion.command.index("--output") + 1].endswith("/ion")


def test_resolved_compound_fixture_uses_separate_parameter_parser(
    tmp_path: Path,
) -> None:
    fixture = _resolved_fixture(
        tmp_path,
        branches=("ion",),
        parameter_vendor="fragpipe",
    )
    target = next(
        target
        for target in expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
        if target.stage == "convert"
    )

    assert target.command[target.command.index("--software") + 1] == "diann"
    assert target.command[target.command.index("--params-software") + 1] == "fragpipe"


def test_stage_edges_and_branch_suffixes_are_isolated(tmp_path: Path) -> None:
    annotation = tmp_path / "annotation.toml"
    fasta = tmp_path / "proteome.fasta"
    annotation.touch()
    fasta.touch()
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion"),
        annotation=annotation,
        fasta=fasta,
    )
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    for branch in ("mudata", "ion"):
        converted = next(
            target for target in targets if target.branch == branch and target.stage == "convert"
        )
        annotated = next(
            target for target in targets if target.branch == branch and target.stage == "annotate"
        )
        fasta = next(
            target for target in targets if target.branch == branch and target.stage == "fasta"
        )
        assert annotated.inputs[0] == converted.output
        assert fasta.inputs[0] == converted.output
        assert annotated.output.suffix == converted.output.suffix
        assert fasta.output.suffix == converted.output.suffix


def test_registry_has_no_optional_stage_and_order_is_topological() -> None:
    assert not {stage["name"] for stage in _REGISTRY if stage.get("optional")}
    order = stage_order(_REGISTRY)
    assert order.index("convert") < order.index("annotate") < order.index("fasta")
    assert order.index("convert") < order.index("annotate") < order.index("proteobench")


def test_artifact_regexes_are_disjoint_and_branch_qualified() -> None:
    import re

    assert re.fullmatch(CONVERT_ARTIFACT_RE, "ion.h5ad")
    assert re.fullmatch(ANNOTATE_ARTIFACT_RE, "ion.annotated.h5ad")
    assert re.fullmatch(FASTA_ARTIFACT_RE, "ion.fasta.h5ad")
    assert re.fullmatch(PROTEOBENCH_ARTIFACT_RE, "ion.proteobench.h5ad")
    # Scoring routes every level, not only the one a module TOML declares.
    assert re.fullmatch(PROTEOBENCH_ARTIFACT_RE, "protein.proteobench.h5ad")
    assert not re.fullmatch(PROTEOBENCH_ARTIFACT_RE, "proteobench.h5ad")
    assert not re.fullmatch(ANNOTATE_ARTIFACT_RE, "annotated.h5ad")


def test_resolved_expansion_keeps_blocked_descendants_without_suppressing_convert(
    tmp_path: Path,
) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")

    assert [target.stage for target in targets] == [
        "convert",
        "annotate",
        "fasta",
        "proteobench",
    ]
    assert [target.stage for target in runnable_targets(targets)] == ["convert"]
    assert targets[1].blocked_reason == "Missing module resource: annotation"
    assert targets[2].blocked_reason == "Missing module resource: fasta"
    assert targets[3].blocked_reason == "Missing module resource: module_settings"

    rows = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)
    assert rows[0]["convert"] == ""
    assert rows[0]["annotate"] == "UNSUPPORTED"
    assert rows[0]["fasta"] == "UNSUPPORTED"
    assert rows[0]["proteobench"] == "UNSUPPORTED"
    assert "annotation" in rows[0]["_stage_details"]["annotate"]["error"]


def test_invalid_capability_is_failed_and_leaves_downstream_blank(
    tmp_path: Path,
) -> None:
    fixture = _resolved_fixture(
        tmp_path,
        branches=(),
        capability_status="failed",
        diagnostic="Could not read the parameter file: invalid parameter file",
    )
    run = _run_snapshot(tmp_path, fixture, [])

    row = branch_rows(run, [])[0]

    assert row["convert"] == "FAILED"
    assert row["annotate"] == ""
    assert row["fasta"] == ""
    assert row["_stage_details"]["convert"]["state"] == "failed"
    assert row["_stage_details"]["annotate"]["state"] == "unavailable"


def test_runnable_targets_keep_existing_outputs_for_snakemake_staleness(
    tmp_path: Path,
) -> None:
    annotation = tmp_path / "annotation.toml"
    fasta = tmp_path / "proteome.fasta"
    annotation.touch()
    fasta.touch()
    fixture = _resolved_fixture(tmp_path, annotation=annotation, fasta=fasta)
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    for target in targets:
        _touch(target)

    assert runnable_targets(targets) == targets


def test_unresolved_capability_is_retained_as_unsupported_row(tmp_path: Path) -> None:
    diagnostic = "No APB parsing rule matches this input"
    fixture = _resolved_fixture(
        tmp_path,
        branches=(),
        capability_status="unsupported",
        diagnostic=diagnostic,
    )
    rows = branch_rows(_run_snapshot(tmp_path, fixture, []), [])
    assert len(rows) == 1
    assert rows[0]["level"] == "Unresolved"
    assert rows[0]["convert"] == "UNSUPPORTED"
    assert rows[0]["_stage_details"]["convert"]["state"] == "unsupported"
    assert rows[0]["_stage_details"]["convert"]["error"] == diagnostic
    assert rows[0]["annotate"] == ""
    assert rows[0]["_stage_details"]["annotate"]["state"] == "unavailable"


def test_rows_update_from_pending_to_completed_and_failed(tmp_path: Path) -> None:
    annotation = tmp_path / "annotation.toml"
    fasta = tmp_path / "proteome.fasta"
    annotation.touch()
    fasta.touch()
    fixture = _resolved_fixture(tmp_path, annotation=annotation, fasta=fasta)
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    converted = next(target for target in targets if target.stage == "convert")
    annotated = next(target for target in targets if target.stage == "annotate")
    _touch(converted)
    annotated.output.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{annotated.output}.log").write_text("Traceback\nValueError: annotation group mismatch\n")
    Path(f"{annotated.output}.failed").write_text("exit 1\n")

    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]
    assert row["convert"] == "DONE"
    assert row["annotate"] == "FAILED"
    assert row["fasta"] == ""
    assert "group mismatch" in row["_stage_details"]["annotate"]["error"]
    assert row["_stage_details"]["convert"]["command"].startswith("apb convert ")
    assert row["_stage_details"]["annotate"]["command"].startswith("apb annotate ")


def test_proteobench_uses_annotation_on_every_annotated_branch(tmp_path: Path) -> None:
    annotation = tmp_path / "module.toml"
    annotation.write_text("[general]\nlevel = 'ion'\n")
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion", "fragment", "protein"),
        annotation=annotation,
    )

    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    scoring = [target for target in targets if target.stage == "proteobench"]

    # The module TOML's declared level no longer restricts scoring to a matching branch.
    assert {target.branch for target in scoring} == {"mudata", "ion", "fragment", "protein"}
    for target in scoring:
        annotated = next(
            item for item in targets if item.branch == target.branch and item.stage == "annotate"
        )
        assert target.inputs == [annotated.output, annotation]
        assert target.command[:3] == ["apb", "proteobench", str(annotated.output)]
        assert target.command[3] == str(annotation)
        assert target.command[4] == "--output"


def test_growing_rule_log_is_pending_until_failure_marker_exists(
    tmp_path: Path,
) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    converted = next(target for target in targets if target.stage == "convert")
    converted.output.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{converted.output}.log").write_text("Reading input table...\n")

    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]

    assert row["convert"] == ""
    assert row["_stage_details"]["convert"]["state"] == "pending"


def test_existing_artifact_wins_over_failure_marker(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    converted = next(target for target in targets if target.stage == "convert")
    _touch(converted)
    Path(f"{converted.output}.log").write_text("ValueError: old failure\n")
    Path(f"{converted.output}.failed").write_text("exit 1\n")

    row = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)[0]

    assert row["convert"] == "DONE"
    assert row["_stage_details"]["convert"]["state"] == "completed"


def test_coverage_includes_branch_and_flips_on_artifact(tmp_path: Path) -> None:
    fixture = _resolved_fixture(tmp_path)
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    converted = next(target for target in targets if target.stage == "convert")
    _touch(converted)
    rows = coverage(targets)
    assert {row["branch"] for row in rows} == {"mudata"}
    assert next(row for row in rows if row["stage"] == "convert")["done"]


def test_run_snapshot_round_trip_is_create_only(tmp_path: Path) -> None:
    annotation = tmp_path / "annotation.toml"
    fasta = tmp_path / "proteome.fasta"
    annotation.write_text('[[samples]]\nraw_file = "run1"\ncondition = "A"\n')
    fasta.write_text(">P1\nPEPTIDE\n")
    fixture = _resolved_fixture(
        tmp_path,
        annotation=annotation,
        fasta=fasta,
    )
    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    snapshot = _run_snapshot(tmp_path, fixture, targets)
    path = tmp_path / "runs" / "run-1" / "run.json"

    write_run_snapshot(snapshot, path)
    loaded = load_run_snapshot(path)

    assert loaded == snapshot
    assert loaded.targets[0].command == targets[0].command
    with pytest.raises(FileExistsError):
        write_run_snapshot(snapshot, path)


def test_clean_guard_survives_python_optimized_mode() -> None:
    code = (
        "from pathlib import Path\n"
        "from apb_studio.pipeline import reject_input_paths, CleanGuardError\n"
        "try:\n"
        "    reject_input_paths([Path('/in/raw.tsv')], '/in'); print('NO_RAISE')\n"
        "except CleanGuardError:\n"
        "    print('RAISED')\n"
    )
    result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)
    assert result.stdout.strip() == "RAISED", result.stdout + result.stderr


def test_reject_input_paths_accepts_outputs_elsewhere() -> None:
    assert reject_input_paths([Path("/out/result.h5ad")], "/in") == [Path("/out/result.h5ad")]


def test_snakefile_lets_snakemake_assess_expanded_runnable_targets() -> None:
    snakefile = _SNAKEFILE.read_text()
    assert "load_run_snapshot" in snakefile
    assert "runnable_targets" in snakefile
    assert "corpus.yaml" not in snakefile
    assert "find_spec" in snakefile
    assert "sys.path.append" in snakefile
    assert "sys.path.insert(0" not in snakefile
    assert "command_text = environment + command_text" in snakefile
    assert "provenance_command = environment + provenance_command" in snakefile
    assert "os.environ[_RUN_PATH_ENV] = _RUN_PATH" in snakefile
    assert '"${_RUN_PATH_ENV}"' in snakefile
    assert "--keep-going" not in snakefile  # execution owns the invocation flag
