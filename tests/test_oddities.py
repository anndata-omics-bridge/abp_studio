"""Source selection, recorded summaries and affected-dataset counts."""

import json
from pathlib import Path
from typing import Any

from apb_studio.corpus.models import (
    Artifact,
    Dataset,
    DatasetReport,
    RunManifest,
    StepResult,
    StepStatus,
)
from apb_studio.corpus.oddities import (
    RepresentationEvidence,
    RunOddities,
    dataset_oddities,
    publish_oddities,
    representation_metrics,
)


def entry(name: str, value: Any, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "label": name.replace("_", " ").capitalize(),
        "value": value,
        "unit": "items",
        "status": status,
        **extra,
    }


def test_metrics_are_collected_from_root_level_and_named_records() -> None:
    representation = RepresentationEvidence.model_validate({
        "format": "apb2-result-representation",
        "format_version": "5",
        "root": {"apb": {"fasta": {"schema_version": "4", "provenance": {}}}},
        "levels": [
            {
                "name": "ion",
                "apb": {
                    "parse": {
                        "result": {"unknown_mod_tokens": ["Mystery"]},
                        "summary": [entry("unknown_modification_tokens", 1, "attention")],
                    },
                    "fasta": {"summary": [entry("unmatched_features", 3, "attention")]},
                    "catalog": {
                        "identification_confidence": {
                            "summary": [entry("missing_requests", 1, "ok")]
                        }
                    },
                    "proteobench": {
                        "summary": [entry("features", 12, "ok", layer="LFQ/Intensity")]
                    },
                    "roles": {"columns": {"protein_assignment": "Protein"}},
                },
            },
            {
                "name": "protein",
                "apb": {
                    "parse": {"summary": [entry("effectively_empty_layers", None, "not_checked")]}
                },
            },
        ],
    })

    metrics = representation_metrics(representation)

    assert [(metric.scope, metric.record, metric.name, metric.layer) for metric in metrics] == [
        ("ion", "parse", "unknown_modification_tokens", ""),
        ("ion", "fasta", "unmatched_features", ""),
        ("ion", "catalog/identification_confidence", "missing_requests", ""),
        ("ion", "proteobench", "features", "LFQ/Intensity"),
        ("protein", "parse", "effectively_empty_layers", ""),
    ]
    assert metrics[-1].value is None and metrics[-1].status == "not_checked"


def _report(steps: list[StepResult], status: StepStatus = "succeeded") -> DatasetReport:
    return DatasetReport(
        run_id="test",
        workflow="convert",
        format="hdf5",
        dataset=Dataset(
            input_file="input.tsv",
            vendor_parameter_file="",
            module="dda",
            software_name="Synthetic",
        ),
        steps=steps,
        status=status,
    )


def _representation(path: Path, **parse: Any) -> Path:
    sidecar = path.with_name(f"{path.name}.apb.json")
    record = parse or {"summary": [entry("unknown_modification_tokens", 1, "attention")]}
    sidecar.write_text(
        json.dumps({
            "format": "apb2-result-representation",
            "format_version": "5",
            "root": {"apb": {"parse": {}}},
            "levels": [{"name": "ion", "apb": {"parse": record}}],
        })
    )
    return sidecar


def _step(name: str, role: str, path: Path, sidecar: Path) -> StepResult:
    return StepResult(
        name=name,
        command=["tool"],
        status="succeeded",
        outputs=[
            Artifact(role=role, path=path, size_bytes=10),
            Artifact(role="representation", path=sidecar, size_bytes=sidecar.stat().st_size),
        ],
    )


def test_failed_later_steps_keep_the_latest_available_evidence(tmp_path: Path) -> None:
    steps = [
        _step(name, role, tmp_path / f"{name}.h5mu", _representation(tmp_path / f"{name}.h5mu"))
        for name, role in (("convert", "converted"), ("verify", "fasta_verified"))
    ]
    steps.append(StepResult(name="benchmark", command=["tool"], status="failed"))

    result = dataset_oddities(_report(steps, "failed"))

    assert result.available
    assert result.source_step == "verify"
    assert [metric.name for metric in result.metrics] == ["unknown_modification_tokens"]


def test_failed_conversion_has_unavailable_metrics_instead_of_verified_zero() -> None:
    result = dataset_oddities(
        _report([StepResult(name="convert", command=["tool"], status="failed")], "failed")
    )
    assert not result.available
    assert not result.metrics
    assert result.notes


def test_a_malformed_summary_is_a_note_and_earlier_evidence_remains(tmp_path: Path) -> None:
    good = _representation(tmp_path / "converted.h5mu")
    bad = _representation(tmp_path / "scored.h5mu", summary=[{"name": "x", "status": "maybe"}])
    result = dataset_oddities(
        _report([
            _step("convert", "converted", tmp_path / "converted.h5mu", good),
            _step("benchmark", "result", tmp_path / "scored.h5mu", bad),
        ])
    )
    assert result.available
    assert result.source_step == "convert"
    assert len(result.notes) == 1


def test_missing_latest_sidecar_is_explicit_and_earlier_evidence_remains_available(
    tmp_path: Path,
) -> None:
    old = _representation(tmp_path / "converted.h5mu")
    result = dataset_oddities(
        _report([
            StepResult(
                name="convert",
                command=["tool"],
                status="succeeded",
                outputs=[Artifact(role="representation", path=old, size_bytes=10)],
            ),
            StepResult(
                name="benchmark",
                command=["tool"],
                status="succeeded",
                outputs=[
                    Artifact(role="result", path=tmp_path / "scored.h5mu", size_bytes=10),
                    Artifact(
                        role="representation", path=tmp_path / "missing.apb.json", size_bytes=10
                    ),
                ],
            ),
        ])
    )
    assert result.available
    assert result.source_step == "convert"
    assert len(result.notes) == 1


def test_software_summary_counts_affected_datasets_once_across_levels(tmp_path: Path) -> None:
    sidecar = _representation(tmp_path / "converted.h5mu")
    document = json.loads(sidecar.read_text())
    document["levels"].append({
        "name": "protein",
        "apb": {"parse": {"summary": [entry("unknown_modification_tokens", 2, "attention")]}},
    })
    sidecar.write_text(json.dumps(document))
    report = _report([_step("convert", "converted", tmp_path / "converted.h5mu", sidecar)])
    failed = _report([StepResult(name="convert", command=["tool"], status="failed")], "failed")
    failed.dataset.input_file = "failed.tsv"
    manifest = RunManifest(
        run_id="test",
        corpus_name="routine",
        workflow="convert",
        format="hdf5",
        data_root=tmp_path,
        tools={"tool": Path("/usr/bin/tool")},
        tool_versions={"tool": "test"},
        cores=1,
        workflow_source="workflow_convert.py",
        reports=[],
    )

    publish_oddities(tmp_path, manifest, [report, failed])

    summary = RunOddities.model_validate_json((tmp_path / "oddities.json").read_text())
    assert summary.format_version == 2
    assert len(summary.datasets[0].metrics) == 2
    software = summary.software[0]
    assert (software.dataset_count, software.summarized_count, software.attention_count) == (
        2,
        1,
        1,
    )
    assert [(item.record, item.name, item.datasets) for item in software.affected] == [
        ("parse", "unknown_modification_tokens", 1)
    ]
