"""Project recorded scientific diagnostics into one static run summary."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from apb_studio.corpus.models import DatasetReport, Record, RunManifest, write_record

type OddityKind = Literal[
    "unknown_modification",
    "unmatched_peptides",
    "unreadable_numeric",
    "effectively_empty",
    "annotation_only",
    "quantification_only",
    "annotation_corrections",
]

SCIENTIFIC_ROLES = frozenset({"result", "converted", "aggregated", "export", "fasta_verified"})


class Finding(Record):
    """One affected level/category/layer group with source-owned evidence."""

    kind: OddityKind
    level: str
    layer: str = ""
    convention: str = ""
    details: dict[str, JsonValue]


class Coverage(Record):
    """Distinguish unrecorded or unperformed checks from clean results."""

    level: str
    numeric: Literal["recorded", "not_recorded"]
    fasta: Literal["checked", "not_checked"]
    annotation_conventions: list[str]


class DatasetOddities(Record):
    input_file: str
    software_name: str
    module: str
    status: str
    source_step: str = ""
    source_path: str = ""
    source_status: str = ""
    available: bool = False
    findings: list[Finding] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SoftwareOddities(Record):
    software_name: str
    dataset_count: int
    summarized_count: int
    numeric_recorded_count: int
    fasta_checked_count: int
    annotation_checked_count: int
    affected_datasets: dict[str, int]


class RunOddities(Record):
    format: Literal["apb-studio-oddities"] = "apb-studio-oddities"
    format_version: Literal[1] = 1
    run_id: str
    datasets: list[DatasetOddities]
    software: list[SoftwareOddities]


class LevelEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    apb: dict[str, JsonValue] = Field(default_factory=dict)


class RepresentationEvidence(BaseModel):
    """Validate just the sidecar's diagnostic boundary, leaving matrices untouched."""

    model_config = ConfigDict(extra="ignore")
    format: Literal["apb2-result-representation"]
    format_version: Literal["4"]
    levels: list[LevelEvidence]


def _section(record: dict[str, JsonValue], name: str) -> dict[str, JsonValue]:
    value = record.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Diagnostic section {name!r} must be an object")
    return value


def _count(record: dict[str, JsonValue], name: str) -> int:
    value = record.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Diagnostic count {name!r} must be a nonnegative integer")
    return value


def representation_findings(
    representation: RepresentationEvidence,
) -> tuple[list[Finding], list[Coverage]]:
    """Project existing reports once per level without summing unlike units."""
    findings: list[Finding] = []
    coverage: list[Coverage] = []
    for level in representation.levels:
        parse = _section(level.apb, "parse")
        tokens = parse.get("unknown_mod_tokens", [])
        if not isinstance(tokens, list) or not all(isinstance(token, str) for token in tokens):
            raise ValueError("unknown_mod_tokens must be a list of strings")
        if tokens:
            findings.append(
                Finding(
                    kind="unknown_modification",
                    level=level.name,
                    details={
                        "token_count": len(tokens),
                        "examples": tokens,
                    },
                )
            )
        diagnostics = _section(parse, "layer_diagnostics")
        if diagnostics and diagnostics.get("schema_version") != "1":
            raise ValueError("Unsupported layer diagnostics schema")
        kinds: tuple[OddityKind, ...] = ("unreadable_numeric", "effectively_empty")
        for kind in kinds:
            for layer, details in _section(diagnostics, kind).items():
                if not isinstance(details, dict):
                    raise ValueError(f"Layer diagnostic {layer!r} must be an object")
                findings.append(Finding(kind=kind, level=level.name, layer=layer, details=details))
        fasta = _section(level.apb, "fasta")
        verification = _section(fasta, "peptide_verification")
        if _count(verification, "unmatched_feature_count"):
            findings.append(
                Finding(
                    kind="unmatched_peptides",
                    level=level.name,
                    details=verification,
                )
            )
        annotation_findings, conventions = _annotation_findings(level)
        findings.extend(annotation_findings)
        coverage.append(
            Coverage(
                level=level.name,
                numeric="recorded" if diagnostics else "not_recorded",
                fasta="checked" if "peptide_verification" in fasta else "not_checked",
                annotation_conventions=conventions,
            )
        )
    return findings, coverage


def _annotation_findings(level: LevelEvidence) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    conventions: list[str] = []
    for convention, metadata in level.apb.items():
        if not isinstance(metadata, dict) or "annotation" not in metadata:
            continue
        annotation = _section(metadata, "annotation")
        conventions.append(convention)
        kinds: tuple[tuple[OddityKind, str], ...] = (
            ("annotation_only", "annotation_only"),
            ("quantification_only", "quant_only"),
        )
        for kind, field in kinds:
            count = _count(annotation, f"{field}_count")
            if count:
                findings.append(
                    Finding(
                        kind=kind,
                        level=level.name,
                        convention=convention,
                        details={
                            "count": count,
                            "examples": annotation.get(f"{field}_examples", []),
                        },
                    )
                )
        corrections = _section(annotation, "corrections")
        if corrections:
            findings.append(
                Finding(
                    kind="annotation_corrections",
                    level=level.name,
                    convention=convention,
                    details={"count": len(corrections), "corrections": corrections},
                )
            )
    return findings, conventions


def dataset_oddities(report: DatasetReport) -> DatasetOddities:
    """Select the displayed scientific output, falling back to available earlier evidence."""
    result = DatasetOddities(
        **report.dataset.model_dump(exclude={"vendor_parameter_file"}),
        status=report.status,
    )
    outputs = [
        artifact
        for step in report.steps
        if step.status == "succeeded"
        for artifact in step.outputs
        if artifact.role in SCIENTIFIC_ROLES and artifact.size_bytes is not None
    ]
    preferred = f"{outputs[-1].path}.apb.json" if outputs else ""
    candidates = [
        (step, artifact)
        for step in report.steps
        for artifact in step.outputs
        if artifact.role == "representation" and artifact.size_bytes is not None
    ][::-1]
    candidates.sort(key=lambda candidate: str(candidate[1].path) != preferred)
    for step, artifact in candidates:
        try:
            representation = RepresentationEvidence.model_validate_json(artifact.path.read_text())
        except (FileNotFoundError, ValidationError) as error:
            result.notes.append(f"Cannot read representation {artifact.path}: {error}")
            continue
        result.findings, result.coverage = representation_findings(representation)
        result.available = True
        result.source_step = step.name
        result.source_status = step.status
        result.source_path = str(artifact.path)
        break
    if not result.available:
        result.notes.append("No scientific representation is available; oddities are unavailable.")
    return result


def publish_oddities(root: Path, manifest: RunManifest, reports: list[DatasetReport]) -> None:
    """Publish dataset evidence and counts of affected datasets by software/category."""
    datasets = [dataset_oddities(report) for report in reports]
    software: list[SoftwareOddities] = []
    for name in sorted({dataset.software_name for dataset in datasets}):
        selected = [dataset for dataset in datasets if dataset.software_name == name]
        counts = Counter(
            kind for dataset in selected for kind in {f.kind for f in dataset.findings}
        )
        software.append(
            SoftwareOddities(
                software_name=name,
                dataset_count=len(selected),
                summarized_count=sum(dataset.available for dataset in selected),
                numeric_recorded_count=sum(
                    bool(dataset.coverage)
                    and all(c.numeric == "recorded" for c in dataset.coverage)
                    for dataset in selected
                ),
                fasta_checked_count=sum(
                    any(c.fasta == "checked" for c in dataset.coverage) for dataset in selected
                ),
                annotation_checked_count=sum(
                    any(c.annotation_conventions for c in dataset.coverage) for dataset in selected
                ),
                affected_datasets=dict(sorted(counts.items())),
            )
        )
    write_record(
        root / "oddities.json",
        RunOddities(
            run_id=manifest.run_id,
            datasets=datasets,
            software=software,
        ),
    )
