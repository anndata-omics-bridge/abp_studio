"""Edge-state coverage for pipeline persistence and progress diagnostics."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from apb_studio import capabilities, pipeline


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


def test_registry_helpers_and_nearest_upstream(tmp_path: Path) -> None:
    registry: list[dict[str, Any]] = [
        {"name": "convert", "basket": "converted", "depends_on": []},
        {"name": "optional", "depends_on": ["convert"], "optional": True},
        {"name": "finish", "depends_on": ["optional"]},
    ]
    assert pipeline.basket_names(registry) == [
        "inputs",
        "converted",
        "optional",
        "finish",
    ]
    assert pipeline.stage_by_basket(registry)["converted"] == "convert"
    assert pipeline.descendants(registry, "convert") == {"optional", "finish"}

    emitted = {"convert": tmp_path / "converted.h5ad"}
    by_name: dict[str, dict[str, Any]] = {cast(str, item["name"]): item for item in registry}
    assert pipeline._nearest_upstream(["optional"], emitted, by_name) == emitted["convert"]
    assert pipeline._nearest_upstream(["missing"], emitted, by_name) is None

    diamond: list[dict[str, Any]] = [
        {"name": "root"},
        {"name": "left", "depends_on": ["root"]},
        {"name": "right", "depends_on": ["root"]},
        {"name": "finish", "depends_on": ["left", "right"]},
    ]
    assert pipeline.descendants(diamond, "root") == {"left", "right", "finish"}


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


def test_log_failure_and_provenance_parsers(
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

    sidecar = Path(f"{output}.provenance.json")
    assert pipeline._provenance_warnings(sidecar) == []
    sidecar.write_text("not json", encoding="utf-8")
    assert pipeline._provenance_warnings(sidecar) == []
    sidecar.write_text("[]", encoding="utf-8")
    assert pipeline._provenance_warnings(sidecar) == []
    sidecar.write_text("{}", encoding="utf-8")
    assert pipeline._provenance_warnings(sidecar) == []
    sidecar.write_text('{"warning": "degraded"}', encoding="utf-8")
    assert pipeline._provenance_warnings(sidecar) == ["artifact: degraded"]


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


def test_problem_aggregation_and_terminal_blockers(tmp_path: Path) -> None:
    target = _target(tmp_path, "artifact.h5ad")
    Path(f"{target.output}.failed").write_text("2", encoding="utf-8")
    corpus = {
        "input_root": str(tmp_path),
        "modules": {
            "module": {
                "annotation": "missing.toml",
                "fasta": "missing.fasta",
                "datasets": [
                    {
                        "name": "dataset",
                        "input": "missing.tsv",
                        "params": "missing.txt",
                    }
                ],
            }
        },
    }
    messages = pipeline.problems(corpus, [target])[("module", "dataset")]
    assert len(messages) == 5
    assert any("convert failed" in message for message in messages)

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


def test_baskets_capability_fallback_and_dataset_selection(tmp_path: Path) -> None:
    registry = [
        {"name": "convert", "basket": "converted", "depends_on": []},
        {"name": "annotate", "basket": "annotated", "depends_on": ["convert"]},
    ]
    convert = _target(tmp_path, "convert.h5ad")
    annotate = _target(
        tmp_path,
        "annotate.h5ad",
        stage="annotate",
        inputs=[convert.output],
    )
    baskets = pipeline.baskets([convert, annotate], registry)
    assert baskets["inputs"][0]["next_stage"] == "convert"
    convert.output.touch()
    baskets = pipeline.baskets(
        [convert, annotate],
        registry,
        {("module", "dataset"): ["warning"]},
    )
    assert baskets["converted"][0]["next_stage"] == "annotate"
    assert baskets["converted"][0]["problem"] == "warning"
    annotate.output.touch()
    assert pipeline.baskets([convert, annotate], registry)["annotated"][0]["runnable"] is False

    without_status = cast(
        capabilities.CapabilityDiscovery,
        SimpleNamespace(branches=("ion",)),
    )
    assert pipeline._capability_status(without_status) == "supported"
    without_branches = cast(
        capabilities.CapabilityDiscovery,
        SimpleNamespace(branches=()),
    )
    assert pipeline._capability_status(without_branches) == "unsupported"


@pytest.mark.parametrize("optional", [False, True])
def test_legacy_expansion_skips_unavailable_root_dependency(
    tmp_path: Path,
    optional: bool,
) -> None:
    registry: list[dict[str, Any]] = [
        {
            "name": "root",
            "command": "apb convert {input} --output {output}",
            "branch_policy": "module_level",
            "optional": optional,
        },
        {
            "name": "finish",
            "depends_on": ["root"],
            "artifact": "finished",
            "command": "apb finish {input} --output {output}",
        },
    ]
    corpus = {
        "input_root": str(tmp_path),
        "output_root": str(tmp_path / "out"),
        "modules": {
            "module": {
                "proteobench_level": "protein",
                "datasets": [
                    {
                        "name": "dataset",
                        "vendor": "diann",
                        "input": "input.tsv",
                        "params": "params.txt",
                    }
                ],
            }
        },
    }

    def discover(*_args: object) -> capabilities.CapabilityDiscovery:
        return capabilities.CapabilityDiscovery(("ion",))

    assert pipeline.expand_targets(registry, corpus, discover=discover) == []

    fixture = replace(_fixture(tmp_path), proteobench_level="protein")
    resolved = pipeline.expand_resolved_targets(registry, (fixture,), tmp_path / "out")
    assert len(resolved) == 1
    assert resolved[0].blocked_reason == "Blocked by unavailable stage: root"
