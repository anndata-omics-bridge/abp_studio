"""Project the producers' recorded summaries into one static run summary.

Producers compute every summary entry; this module only collects them from the displayed
representation, so Studio never recalculates a metric or reads a log.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from apb_studio.corpus.models import DatasetReport, Record, RunManifest, write_record

SCIENTIFIC_ROLES = frozenset({"result", "converted", "aggregated", "export", "fasta_verified"})
_RECORD_FIELDS = frozenset({"schema_version", "provenance", "result", "summary", "details"})


class Metric(Record):
    """One producer summary entry, with where it was recorded."""

    scope: str
    """``root`` or the level name."""
    record: str
    """The record's path below ``apb``, e.g. ``fasta`` or ``catalog/identification_confidence``."""
    name: str
    label: str
    value: JsonValue
    unit: str
    status: Literal["ok", "attention", "not_checked"]
    layer: str = ""


class DatasetOddities(Record):
    input_file: str
    software_name: str
    module: str
    status: str
    source_step: str = ""
    source_path: str = ""
    source_status: str = ""
    available: bool = False
    metrics: list[Metric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AffectedDatasets(Record):
    """How many datasets of one software have a metric needing attention."""

    record: str
    name: str
    label: str
    datasets: int


class SoftwareOddities(Record):
    software_name: str
    dataset_count: int
    summarized_count: int
    attention_count: int
    affected: list[AffectedDatasets]


class RunOddities(Record):
    format: Literal["apb-studio-oddities"] = "apb-studio-oddities"
    format_version: Literal[2] = 2
    run_id: str
    datasets: list[DatasetOddities]
    software: list[SoftwareOddities]


class PartEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    apb: dict[str, JsonValue] = Field(default_factory=dict)


class LevelEvidence(PartEvidence):
    name: str


class RepresentationEvidence(BaseModel):
    """Validate just the sidecar's metadata boundary, leaving matrices untouched."""

    model_config = ConfigDict(extra="ignore")
    format: Literal["apb2-result-representation"]
    format_version: Literal["5"]
    root: PartEvidence | None = None
    levels: list[LevelEvidence]


def representation_metrics(representation: RepresentationEvidence) -> list[Metric]:
    """Every summary entry of the root and level parts, in recorded order."""
    parts = [("root", representation.root.apb)] if representation.root else []
    parts += [(level.name, level.apb) for level in representation.levels]
    metrics: list[Metric] = []
    for scope, part in parts:
        for producer, record in part.items():
            if not isinstance(record, dict):
                continue
            metrics += _record_metrics(scope, producer, record)
            for name, child in record.items():
                if name not in _RECORD_FIELDS and isinstance(child, dict):
                    metrics += _record_metrics(scope, f"{producer}/{name}", child)
    return metrics


def _record_metrics(scope: str, path: str, record: dict[str, JsonValue]) -> list[Metric]:
    summary = record.get("summary", [])
    if not isinstance(summary, list):
        raise ValueError(f"{scope} {path} summary is not a list")
    return [
        Metric.model_validate({"scope": scope, "record": path, **entry})
        if isinstance(entry, dict)
        else Metric.model_validate(entry)
        for entry in summary
    ]


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
            result.metrics = representation_metrics(representation)
        except (FileNotFoundError, ValidationError, ValueError) as error:
            result.notes.append(f"Cannot read representation {artifact.path}: {error}")
            continue
        result.available = True
        result.source_step = step.name
        result.source_status = step.status
        result.source_path = str(artifact.path)
        break
    if not result.available:
        result.notes.append("No scientific representation is available; oddities are unavailable.")
    return result


def publish_oddities(root: Path, manifest: RunManifest, reports: list[DatasetReport]) -> None:
    """Publish every dataset's metrics and, per software, datasets affected per metric."""
    datasets = [dataset_oddities(report) for report in reports]
    software: list[SoftwareOddities] = []
    for name in sorted({dataset.software_name for dataset in datasets}):
        selected = [dataset for dataset in datasets if dataset.software_name == name]
        labels: dict[tuple[str, str], str] = {}
        counts: Counter[tuple[str, str]] = Counter()
        for dataset in selected:
            attention = {
                (metric.record, metric.name): metric.label
                for metric in dataset.metrics
                if metric.status == "attention"
            }
            labels.update(attention)
            counts.update(attention.keys())
        software.append(
            SoftwareOddities(
                software_name=name,
                dataset_count=len(selected),
                summarized_count=sum(dataset.available for dataset in selected),
                attention_count=sum(
                    any(metric.status == "attention" for metric in dataset.metrics)
                    for dataset in selected
                ),
                affected=[
                    AffectedDatasets(
                        record=record, name=metric, label=labels[record, metric], datasets=count
                    )
                    for (record, metric), count in sorted(counts.items())
                ],
            )
        )
    write_record(
        root / "oddities.json",
        RunOddities(run_id=manifest.run_id, datasets=datasets, software=software),
    )
