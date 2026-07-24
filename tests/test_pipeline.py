"""Tests for branch-aware corpus target expansion and progress state."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from apb_studio.capabilities import CapabilityDiscovery, CapabilityStatus
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
    descendants,
    expand_resolved_targets,
    expand_targets,
    load_run_snapshot,
    problems,
    reject_input_paths,
    render_command,
    runnable_targets,
    stage_order,
    target_blocker,
    validate_dataset,
    write_run_snapshot,
)
from apb_studio.registry import REGISTRY_PATH, load_registry

_SNAKEFILE = REGISTRY_PATH.parent.parent / "workflow" / "Snakefile"
_REGISTRY = load_registry()


def _discovery(
    *branches: str,
    diagnostic: str | None = None,
    status: CapabilityStatus | None = None,
):
    def discover(_input: Path, _params: Path, _software: str) -> CapabilityDiscovery:
        resolved_status = status or (
            CapabilityStatus.SUPPORTED if branches else CapabilityStatus.UNSUPPORTED
        )
        return CapabilityDiscovery(tuple(branches), diagnostic, resolved_status)

    return discover


def _corpus(
    tmp_path: Path,
    *,
    annotation: bool = True,
    fasta: bool = True,
    touch_resources: bool = True,
    level: str | None = None,
) -> dict[str, Any]:
    input_root = tmp_path / "in"
    input_root.mkdir()
    (input_root / "report.tsv").write_text("x\n")
    (input_root / "params.txt").write_text("params\n")
    module: dict[str, Any] = {
        "datasets": [
            {
                "name": "diann-d",
                "vendor": "diann",
                "input": "report.tsv",
                "params": "params.txt",
            }
        ]
    }
    if level is not None:
        module["datasets"][0]["level"] = level
    if annotation:
        module["annotation"] = "annotation.toml"
        if touch_resources:
            (input_root / "annotation.toml").write_text(
                '[[samples]]\nraw_file = "run1"\ncondition = "A"\n'
            )
    if fasta:
        module["fasta"] = "proteome.fasta"
        if touch_resources:
            (input_root / "proteome.fasta").write_text(">P1\nPEPTIDE\n")
    return {
        "input_root": str(input_root),
        "output_root": str(tmp_path / "out"),
        "modules": {"m": module},
    }


def _expand(
    corpus: dict[str, Any],
    *branches: str,
    registry: list[dict[str, Any]] | None = None,
) -> list[Target]:
    return expand_targets(
        registry or _REGISTRY,
        corpus,
        discover=_discovery(*branches),
    )


def _touch(target: Target) -> None:
    target.output.parent.mkdir(parents=True, exist_ok=True)
    target.output.touch()


def _resolved_fixture(  # noqa: PLR0913 - explicit fixture factory fields
    tmp_path: Path,
    *,
    branches: tuple[str, ...] = ("mudata",),
    capability_status: str = "supported",
    annotation: Path | None = None,
    fasta: Path | None = None,
    tool_settings: Path | None = None,
    proteobench_level: str | None = None,
    diagnostic: str | None = None,
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
        input_path=input_path,
        parameter_path=parameter_path,
        branches=branches,
        capability_status=capability_status,
        diagnostic=diagnostic,
        annotation_path=annotation,
        fasta_path=fasta,
        tool_settings_path=tool_settings,
        proteobench_level=proteobench_level,
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


def test_dataset_level_is_ignored_but_manifest_fields_are_required() -> None:
    validate_dataset(
        "m",
        {
            "name": "d",
            "vendor": "maxquant",
            "input": "evidence.txt",
            "params": "mqpar.xml",
            "level": "wrong-and-ignored",
        },
    )
    with pytest.raises(ValueError, match="vendor"):
        validate_dataset("m", {"name": "d", "input": "x", "params": "params"})


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


def test_expand_fans_out_every_json_supported_branch_through_all_stages(
    tmp_path: Path,
) -> None:
    targets = _expand(_corpus(tmp_path), "mudata", "ion", "fragment", "protein")
    assert len(targets) == 4 * 3
    assert {(target.branch, target.stage) for target in targets} == {
        (branch, stage)
        for branch in ("mudata", "ion", "fragment", "protein")
        for stage in ("convert", "annotate", "fasta")
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


def test_yaml_level_never_constrains_json_branches(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path, level="protein")
    targets = _expand(corpus, "mudata", "ion", "fragment")
    assert {target.branch for target in targets} == {"mudata", "ion", "fragment"}


def test_stage_edges_and_branch_suffixes_are_isolated(tmp_path: Path) -> None:
    targets = _expand(_corpus(tmp_path), "mudata", "ion")
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
    assert order.index("convert") < order.index("proteobench")
    assert descendants(_REGISTRY, "convert") == {
        "annotate",
        "fasta",
        "proteobench",
    }


def test_artifact_regexes_are_disjoint_and_branch_qualified() -> None:
    import re

    assert re.fullmatch(CONVERT_ARTIFACT_RE, "ion.h5ad")
    assert re.fullmatch(ANNOTATE_ARTIFACT_RE, "ion.annotated.h5ad")
    assert re.fullmatch(FASTA_ARTIFACT_RE, "ion.fasta.h5ad")
    assert re.fullmatch(PROTEOBENCH_ARTIFACT_RE, "ion.proteobench.h5ad")
    assert not re.fullmatch(PROTEOBENCH_ARTIFACT_RE, "protein.proteobench.h5ad")
    assert not re.fullmatch(ANNOTATE_ARTIFACT_RE, "annotated.h5ad")


def test_missing_module_resources_leave_converts_and_failed_stage_cells(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path, annotation=False, fasta=False)
    targets = _expand(corpus, "mudata", "ion")
    assert {target.stage for target in targets} == {"convert"}

    rows = branch_rows(
        corpus,
        targets,
        registry=_REGISTRY,
        discover=_discovery("mudata", "ion"),
    )
    assert len(rows) == 2
    assert {row["convert"] for row in rows} == {""}
    assert {row["annotate"] for row in rows} == {"BLOCKED"}
    assert {row["fasta"] for row in rows} == {"BLOCKED"}
    assert "unavailable" in rows[0]["_stage_details"]["annotate"]["error"]


def test_missing_declared_resource_blocks_only_affected_targets(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path, touch_resources=False)
    targets = _expand(corpus, "mudata", "ion")
    runnable = runnable_targets(targets)
    assert {(target.branch, target.stage) for target in runnable} == {
        ("mudata", "convert"),
        ("ion", "convert"),
    }
    annotated = next(target for target in targets if target.stage == "annotate")
    assert "annotation.toml" in (target_blocker(annotated, targets) or "")

    rows = branch_rows(
        corpus,
        targets,
        registry=_REGISTRY,
        discover=_discovery("mudata", "ion"),
    )
    assert {row["annotate"] for row in rows} == {"BLOCKED"}
    assert {row["fasta"] for row in rows} == {"BLOCKED"}

    for target in targets:
        _touch(target)
    assert {target.stage for target in runnable_targets(targets)} == {"convert"}


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
    assert targets[3].blocked_reason == "Missing module resource: tool_settings"

    rows = branch_rows(_run_snapshot(tmp_path, fixture, targets), targets)
    assert rows[0]["convert"] == ""
    assert rows[0]["annotate"] == "BLOCKED"
    assert rows[0]["fasta"] == "BLOCKED"
    assert rows[0]["proteobench"] == "BLOCKED"
    assert "annotation" in rows[0]["_stage_details"]["annotate"]["error"]


def test_invalid_capability_is_blocked_without_repeating_downstream_status(
    tmp_path: Path,
) -> None:
    fixture = _resolved_fixture(
        tmp_path,
        branches=(),
        capability_status="blocked",
        diagnostic="Capability discovery failed: invalid parameter file",
    )
    run = _run_snapshot(tmp_path, fixture, [])

    row = branch_rows(run, [])[0]

    assert row["convert"] == "BLOCKED"
    assert row["annotate"] == ""
    assert row["fasta"] == ""
    assert row["_stage_details"]["convert"]["state"] == "blocked"


def test_runnable_targets_keep_existing_outputs_for_snakemake_staleness(
    tmp_path: Path,
) -> None:
    targets = _expand(_corpus(tmp_path), "mudata")
    for target in targets:
        _touch(target)

    assert runnable_targets(targets) == targets


def test_unresolved_capability_is_retained_as_unsupported_row(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    diagnostic = "No APB parsing rule matches this input"
    rows = branch_rows(
        corpus,
        [],
        registry=_REGISTRY,
        discover=_discovery(diagnostic=diagnostic),
    )
    assert len(rows) == 1
    assert rows[0]["level"] == "Unresolved"
    assert rows[0]["convert"] == "UNSUPPORTED"
    assert rows[0]["_stage_details"]["convert"]["state"] == "unsupported"
    assert rows[0]["_stage_details"]["convert"]["error"] == diagnostic


def test_rows_update_from_pending_to_completed_and_failed(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    discover = _discovery("mudata")
    targets = expand_targets(_REGISTRY, corpus, discover=discover)
    converted = next(target for target in targets if target.stage == "convert")
    annotated = next(target for target in targets if target.stage == "annotate")
    _touch(converted)
    annotated.output.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{annotated.output}.log").write_text("Traceback\nValueError: annotation group mismatch\n")
    Path(f"{annotated.output}.failed").write_text("exit 1\n")

    row = branch_rows(
        corpus,
        targets,
        registry=_REGISTRY,
        discover=discover,
    )[0]
    assert row["convert"] == "DONE"
    assert row["annotate"] == "FAILED"
    assert row["fasta"] == ""
    assert "group mismatch" in row["_stage_details"]["annotate"]["error"]


def test_proteobench_uses_convert_and_only_module_level_branches(tmp_path: Path) -> None:
    annotation = tmp_path / "module.toml"
    annotation.write_text("[general]\nlevel = 'ion'\n")
    tool = tmp_path / "tool.toml"
    tool.write_text("[mapper]\nProtein = 'Proteins'\n")
    fixture = _resolved_fixture(
        tmp_path,
        branches=("mudata", "ion", "fragment", "protein"),
        annotation=annotation,
        tool_settings=tool,
        proteobench_level="ion",
    )

    targets = expand_resolved_targets(_REGISTRY, (fixture,), tmp_path / "out")
    scoring = [target for target in targets if target.stage == "proteobench"]

    assert {target.branch for target in scoring} == {"mudata", "ion"}
    for target in scoring:
        converted = next(
            item for item in targets if item.branch == target.branch and item.stage == "convert"
        )
        assert target.inputs == [converted.output, annotation, tool]
        assert target.command[:3] == ["apb", "proteobench", str(converted.output)]
        assert target.command[3:5] == [str(annotation), str(tool)]


def test_growing_rule_log_is_pending_until_failure_marker_exists(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path)
    discover = _discovery("mudata")
    targets = expand_targets(_REGISTRY, corpus, discover=discover)
    converted = next(target for target in targets if target.stage == "convert")
    converted.output.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{converted.output}.log").write_text("Reading input table...\n")

    row = branch_rows(corpus, targets, registry=_REGISTRY, discover=discover)[0]

    assert row["convert"] == ""
    assert row["_stage_details"]["convert"]["state"] == "pending"


def test_existing_artifact_wins_over_failure_marker(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    discover = _discovery("mudata")
    targets = expand_targets(_REGISTRY, corpus, discover=discover)
    converted = next(target for target in targets if target.stage == "convert")
    _touch(converted)
    Path(f"{converted.output}.log").write_text("ValueError: old failure\n")
    Path(f"{converted.output}.failed").write_text("exit 1\n")

    row = branch_rows(corpus, targets, registry=_REGISTRY, discover=discover)[0]

    assert row["convert"] == "DONE"
    assert row["_stage_details"]["convert"]["state"] == "completed"


def test_coverage_includes_branch_and_flips_on_artifact(tmp_path: Path) -> None:
    targets = _expand(_corpus(tmp_path), "mudata")
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


def test_problems_read_artifact_provenance_warning(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    targets = _expand(corpus, "mudata")
    converted = next(target for target in targets if target.stage == "convert")
    _touch(converted)
    Path(f"{converted.output}.provenance.json").write_text(
        json.dumps(
            {
                "stage": "convert",
                "artifact": converted.output.name,
                "warning": "parameter metadata incomplete",
            }
        )
    )
    found = problems(corpus, targets)
    assert "parameter metadata incomplete" in "; ".join(found[("m", "diann-d")])


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
    assert "--keep-going" not in snakefile  # execution owns the invocation flag
