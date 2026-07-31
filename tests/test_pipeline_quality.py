"""Edge-state coverage for pipeline persistence and progress diagnostics."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from apb_studio import pipeline


def _target(
    tmp_path: Path,
    name: str,
    *,
    stage: str = "convert",
    inputs: list[Path] | None = None,
    blocked: str | None = None,
    module: str = "module",
    dataset: str = "dataset",
) -> pipeline.Target:
    return pipeline.Target(
        module=module,
        dataset=dataset,
        stage=stage,
        output=tmp_path / name,
        command=["apb", stage],
        inputs=inputs or [],
        vendor="diann",
        branch="ion",
        blocked_reason=blocked,
    )


def _fixture(tmp_path: Path) -> pipeline.ResolvedFixture:
    return pipeline.ResolvedFixture(
        module="dda",
        repo_name="module",
        intermediate_hash="abc123",
        dataset="dataset",
        software="DIA-NN",
        vendor="diann",
        input_path=tmp_path / "input.tsv",
        parameter_path=tmp_path / "params.txt",
        branches=("ion",),
        capability_status="supported",
    )


def _snapshot(
    tmp_path: Path,
    targets: tuple[pipeline.Target, ...] = (),
) -> pipeline.RunSnapshot:
    return pipeline.RunSnapshot(
        schema_version=pipeline.RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id="run",
        created_at="now",
        test_data_root=tmp_path / "inputs",
        output_root=tmp_path / "outputs",
        registry_digest="digest",
        apb_version=None,
        fixtures=(_fixture(tmp_path),),
        targets=targets,
    )


def test_snapshot_validation_rejects_bad_shapes_and_paths(tmp_path: Path) -> None:
    data = pipeline.run_snapshot_data(_snapshot(tmp_path))
    with pytest.raises(ValueError, match="schema version"):
        pipeline.run_snapshot_from_data({**data, "schema_version": 9})

    escaped = _target(tmp_path, "outside.h5ad")
    with pytest.raises(ValueError, match="outside output root"):
        pipeline.run_snapshot_from_data(pipeline.run_snapshot_data(_snapshot(tmp_path, (escaped,))))

    path = tmp_path / "run.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="one JSON object"):
        pipeline.load_run_snapshot(path)


def test_nearest_upstream_follows_registry_dependencies(tmp_path: Path) -> None:
    registry: list[dict[str, Any]] = [
        {"name": "convert", "basket": "converted", "depends_on": []},
        {"name": "optional", "depends_on": ["convert"], "optional": True},
        {"name": "finish", "depends_on": ["optional"]},
    ]
    emitted = {"convert": tmp_path / "converted.h5ad"}
    by_name: dict[str, dict[str, Any]] = {cast(str, item["name"]): item for item in registry}
    assert pipeline._nearest_upstream(["optional"], emitted, by_name) == emitted["convert"]
    # A chain with no emitted stage means a malformed registry: every real chain reaches the root.
    with pytest.raises(ValueError, match="No emitted upstream stage"):
        pipeline._nearest_upstream(["missing"], emitted, by_name)


def test_target_blocker_covers_existing_cycles_and_nested_failures(tmp_path: Path) -> None:
    external = tmp_path / "missing.tsv"
    root = _target(tmp_path, "root.h5ad", inputs=[external])
    child = _target(tmp_path, "child.h5ad", stage="annotate", inputs=[root.output])
    assert "Missing prerequisite" in cast(str, pipeline.target_blocker(child, [root, child]))

    root.output.touch()
    assert pipeline.target_blocker(child, [root, child]) is None
    root.output.unlink()
    blocked = replace(root, blocked_reason="not supported")
    assert pipeline.target_blocker(child, [blocked, child]) == "not supported"

    first = _target(tmp_path, "first.h5ad")
    second = _target(tmp_path, "second.h5ad")
    first.inputs.append(second.output)
    second.inputs.append(first.output)
    assert pipeline.target_blocker(first, [first, second]) is None


def test_log_and_failure_marker_parsers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert pipeline._log_error(tmp_path / "missing.log") is None
    log = tmp_path / "rule.log"
    log.write_text("\n\n", encoding="utf-8")
    assert pipeline._log_error(log) is None
    log.write_text("start\nValueError: broken\nlast line\n", encoding="utf-8")
    assert pipeline._log_error(log) == "ValueError: broken"
    log.write_text("start\nlast line\n", encoding="utf-8")
    assert pipeline._log_error(log) == "last line"

    output = tmp_path / "artifact.h5ad"
    marker = pipeline.failure_marker_path(output)
    assert pipeline._failed_rule_error(output) is None
    marker.write_text("exit 3", encoding="utf-8")
    assert pipeline._failed_rule_error(output) == "Rule failed (exit 3)"
    marker.write_text("", encoding="utf-8")
    assert pipeline._failed_rule_error(output) == "Rule failed"
    original_read = Path.read_text

    def fail_marker(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        if path == marker:
            raise OSError("locked")
        return original_read(path, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "read_text", fail_marker)
    assert pipeline._failed_rule_error(output) == "Rule failed"
    monkeypatch.setattr(Path, "read_text", original_read)


def test_stage_timing_parses_and_formats_snakemake_benchmarks(tmp_path: Path) -> None:
    output = tmp_path / "artifact.h5ad"
    assert pipeline._benchmark_seconds(output) is None

    benchmark = pipeline.benchmark_path(output)
    benchmark.write_text("s\th:m:s\n134.25\t0:02:14\n", encoding="utf-8")
    assert pipeline._benchmark_seconds(output) == 134.25
    assert pipeline.format_duration(0.25) == "0.2s"
    assert pipeline.format_duration(12.4) == "12s"
    assert pipeline.format_duration(134.25) == "2m 14s"
    assert pipeline.format_duration(3_725) == "1h 02m"

    benchmark.write_text("", encoding="utf-8")
    assert pipeline._benchmark_seconds(output) is None
    benchmark.write_text("wrong\n1\n", encoding="utf-8")
    assert pipeline._benchmark_seconds(output) is None
    benchmark.write_text("s\ninvalid\n", encoding="utf-8")
    assert pipeline._benchmark_seconds(output) is None
    benchmark.write_text("s\n-1\n", encoding="utf-8")
    assert pipeline._benchmark_seconds(output) is None
    benchmark.write_text("s\ninf\n", encoding="utf-8")
    assert pipeline._benchmark_seconds(output) is None


def test_stage_detail_includes_persisted_runtime(tmp_path: Path) -> None:
    assert pipeline._stage_detail(None, targets=[], missing_reason="not emitted") == {
        "state": "unsupported",
        "display": "UNSUPPORTED",
        "error": "not emitted",
    }
    assert pipeline._stage_detail(None, targets=[])["error"] == "Stage target unavailable"

    missing_input = tmp_path / "missing.tsv"
    missing = _target(tmp_path, "missing-input.h5ad", inputs=[missing_input])
    assert pipeline._stage_detail(missing, targets=[missing])["error"] == (
        f"Missing prerequisite: {missing_input}"
    )

    target = _target(tmp_path, "artifact.h5ad")
    target.output.touch()
    pipeline.benchmark_path(target.output).write_text(
        "s\th:m:s\n61.2\t0:01:01\n",
        encoding="utf-8",
    )

    completed = pipeline._stage_detail(target, targets=[target])

    assert completed["display"] == "DONE · 1m 01s"
    assert completed["duration"] == "1m 01s"
    assert completed["command"] == "apb convert"
    target.output.unlink()
    pipeline.failure_marker_path(target.output).write_text("exit 1", encoding="utf-8")
    failed = pipeline._stage_detail(target, targets=[target])
    assert failed["display"] == "FAILED"


def test_terminal_blockers_follow_upstream_state(tmp_path: Path) -> None:
    existing_input = tmp_path / "input.tsv"
    existing_input.touch()
    upstream = _target(tmp_path, "upstream.h5ad", inputs=[existing_input])
    downstream = _target(
        tmp_path,
        "downstream.h5ad",
        stage="annotate",
        inputs=[upstream.output],
    )
    assert pipeline._terminal_blocker(downstream, [upstream, downstream]) is None
    Path(f"{upstream.output}.failed").write_text("1", encoding="utf-8")
    assert "failed upstream" in cast(
        str, pipeline._terminal_blocker(downstream, [upstream, downstream])
    )
    assert pipeline._stage_detail(downstream, targets=[upstream, downstream])["state"] == (
        "unavailable"
    )
    Path(f"{upstream.output}.failed").unlink()
    blocked = replace(upstream, blocked_reason="resource absent")
    assert "upstream stage" in cast(
        str, pipeline._terminal_blocker(downstream, [blocked, downstream])
    )
    upstream.output.touch()
    assert pipeline._terminal_blocker(downstream, [upstream, downstream]) is None
    downstream.output.touch()
    assert pipeline._terminal_blocker(downstream, [upstream, downstream]) is None

    first = _target(tmp_path, "first.h5ad")
    second = _target(tmp_path, "second.h5ad")
    first.inputs.append(second.output)
    second.inputs.append(first.output)
    assert pipeline._terminal_blocker(first, [first, second]) is None


def test_resolved_expansion_keeps_full_topology_for_a_missing_resource(
    tmp_path: Path,
) -> None:
    registry: list[dict[str, Any]] = [
        {
            "name": "root",
            "command": "apb convert {input} --output {output}",
        },
        {
            "name": "middle",
            "depends_on": ["root"],
            "artifact": "middled",
            "resource": "annotation",
            "command": "apb annotate {input} {annotation} --output {output}",
        },
        {
            "name": "finish",
            "depends_on": ["middle"],
            "artifact": "finished",
            "command": "apb finish {input} --output {output}",
        },
    ]
    resolved = pipeline.expand_resolved_targets(registry, (_fixture(tmp_path),), tmp_path / "out")
    blocked = {target.stage: target.blocked_reason for target in resolved}
    assert blocked == {
        "root": None,
        "middle": "Missing module resource: annotation",
        "finish": None,
    }
    finish = next(target for target in resolved if target.stage == "finish")
    assert pipeline.target_blocker(finish, resolved) == "Missing module resource: annotation"
