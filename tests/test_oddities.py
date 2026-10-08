"""Source selection, count units and incomplete diagnostic coverage."""

import json
from pathlib import Path

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
    representation_findings,
)


def test_findings_reuse_metadata_and_keep_counts_in_their_own_units() -> None:
    representation = RepresentationEvidence.model_validate({
        "format": "apb2-result-representation",
        "format_version": "4",
        "levels": [
            {
                "name": "ion",
                "apb": {
                    "parse": {
                        "unknown_mod_tokens": ["Mystery"],
                        "layer_diagnostics": {
                            "schema_version": "1",
                            "unreadable_numeric": {
                                "QValue": {
                                    "cell_count": 100,
                                    "distinct_token_count": 1,
                                    "examples": ["NA"],
                                }
                            },
                            "effectively_empty": {"QValue": {"occupancy": 0.0}},
                        },
                    },
                    "fasta": {
                        "peptide_verification": {"feature_count": 12, "unmatched_feature_count": 3}
                    },
                    "prolfquapp": {
                        "annotation": {
                            "quant_only_count": 2,
                            "quant_only_examples": ["run_A"],
                            "annotation_only_count": 1,
                            "annotation_only_examples": ["run_B"],
                            "corrections": {
                                "run_C": {"observed": "run_C", "expected": "run_C.raw", "score": 95}
                            },
                        }
                    },
                },
            },
            {"name": "protein", "apb": {"parse": {}}},
        ],
    })
    findings, coverage = representation_findings(representation)
    assert len(findings) == 7
    assert findings[1].details["cell_count"] == 100
    assert findings[3].details["unmatched_feature_count"] == 3
    assert coverage[0].numeric == "recorded"
    assert coverage[0].fasta == "checked"
    assert coverage[0].annotation_conventions == ["prolfquapp"]
    assert coverage[1].numeric == "not_recorded"
    assert coverage[1].fasta == "not_checked"


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


def _representation(path: Path) -> Path:
    sidecar = path.with_name(f"{path.name}.apb.json")
    sidecar.write_text(
        RepresentationEvidence.model_validate({
            "format": "apb2-result-representation",
            "format_version": "4",
            "levels": [{"name": "ion", "apb": {"parse": {"unknown_mod_tokens": ["Mystery"]}}}],
        }).model_dump_json()
    )
    return sidecar


def test_inherited_findings_count_once_and_failed_later_steps_keep_latest_evidence(
    tmp_path: Path,
) -> None:
    steps: list[StepResult] = []
    for name, role in (("convert", "converted"), ("verify", "fasta_verified")):
        path = tmp_path / f"{name}.h5mu"
        sidecar = _representation(path)
        steps.append(
            StepResult(
                name=name,
                command=["tool"],
                status="succeeded",
                outputs=[
                    Artifact(role=role, path=path, size_bytes=10),
                    Artifact(
                        role="representation", path=sidecar, size_bytes=sidecar.stat().st_size
                    ),
                ],
            )
        )
    steps.append(StepResult(name="benchmark", command=["tool"], status="failed"))
    result = dataset_oddities(_report(steps, "failed"))
    assert result.available
    assert result.source_step == "verify"
    assert len(result.findings) == 1
    assert result.coverage[0].numeric == "not_recorded"


def test_failed_conversion_has_unavailable_diagnostics_instead_of_verified_zero() -> None:
    result = dataset_oddities(
        _report([StepResult(name="convert", command=["tool"], status="failed")], "failed")
    )
    assert not result.available
    assert not result.coverage
    assert result.notes


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
                outputs=[
                    Artifact(role="representation", path=old, size_bytes=10),
                ],
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
        "apb": {"parse": {"unknown_mod_tokens": ["Other"]}},
    })
    sidecar.write_text(json.dumps(document))
    report = _report([
        StepResult(
            name="convert",
            command=["tool"],
            status="succeeded",
            outputs=[
                Artifact(role="representation", path=sidecar, size_bytes=sidecar.stat().st_size),
            ],
        )
    ])
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
    assert len(summary.datasets[0].findings) == 2
    assert summary.software[0].affected_datasets == {"unknown_modification": 1}
    assert summary.software[0].dataset_count == 2
    assert summary.software[0].summarized_count == 1
    assert summary.software[0].numeric_recorded_count == 0
    assert summary.software[0].fasta_checked_count == 0
