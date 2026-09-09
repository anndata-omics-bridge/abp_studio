"""Versioned execution records shared with the JavaScript corpus viewer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apb_studio.disk import atomic_write_text

type StorageFormat = Literal["hdf5", "duckdb", "parquet"]
type StepStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]


def utc_now() -> str:
    """Return an ISO timestamp understood by JavaScript Date."""
    return datetime.now(UTC).isoformat()


class Record(BaseModel):
    """Strict JSON boundary; unknown fields and nonfinite numbers are errors."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Dataset(Record):
    """Exactly the four corpus CSV columns; paths are relative to the data root."""

    input_file: str = Field(min_length=1)
    vendor_parameter_file: str = Field(min_length=1)
    module: str = Field(min_length=1)
    software_name: str = Field(min_length=1)


class InputMetadata(Record):
    """Acquisition evidence joined to one selected corpus input."""

    input_file: str = Field(min_length=1)
    input_file_size_bytes: int = Field(ge=0)


class Artifact(Record):
    """A declared input or output path and its role."""

    role: str
    path: Path
    format: StorageFormat | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class StepSpec(Record):
    """One command, without shell interpretation, and its file contract."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    command: list[str] = Field(min_length=1)
    inputs: list[Artifact] = Field(default_factory=list)
    outputs: list[Artifact] = Field(default_factory=list)


class StepResult(StepSpec):
    """Observed step state; null telemetry means unavailable or unattempted."""

    status: StepStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    runtime_seconds: float | None = Field(default=None, ge=0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)
    memory_measurement: str = "sampled_sum_rss_process_tree"
    memory_sample_interval_seconds: float = 0.1
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DatasetReport(Record):
    """Final report and live progress use the same browser-readable shape."""

    schema_version: Literal[1] = 1
    run_id: str
    workflow: str
    format: StorageFormat
    dataset: Dataset
    status: StepStatus = "running"
    started_at: str = Field(default_factory=utc_now)
    finished_at: str | None = None
    runtime_seconds: float = 0
    steps: list[StepResult] = Field(default_factory=list)


class ReportLink(Record):
    """Run-relative paths, available before any job starts."""

    input_file: str
    path: str
    progress: str
    output_dir: str


class RunManifest(Record):
    """Frozen settings, table links and expected reports for a corpus invocation.

    ``tools`` and ``tool_versions`` are keyed by the executable names the selected workflow
    declared in its ``TOOLS`` tuple; this record never names a particular tool.
    """

    schema_version: Literal[1] = 1
    run_id: str
    created_at: str = Field(default_factory=utc_now)
    workflow: str
    format: StorageFormat
    data_root: Path
    tools: dict[str, Path] = Field(min_length=1)
    tool_versions: dict[str, str] = Field(min_length=1)
    cores: int = Field(ge=1)
    corpus: str = "corpus.csv"
    workflow_table: str | None = None
    workflow_source: str
    reports: list[ReportLink]
    settings_id: str | None = None
    execution_settings: str | None = None
    source_corpus: str | None = None
    input_metadata: str | None = None


class ExecutionSettings(Record):
    """Reusable execution inputs, independent of run IDs, versions and timestamps.

    ``tools`` maps every executable name the selected workflow declared to a resolved path.
    """

    schema_version: Literal[1] = 1
    workflow: str
    format: StorageFormat
    corpus: Path
    data_root: Path
    workflow_table: Path | None
    downloads: Path | None = None
    tools: dict[str, Path] = Field(min_length=1)
    cores: int = Field(ge=1)
    datasets: Path | None = None
    fixtures: int = Field(default=0, ge=0)


class CorpusIndex(Record):
    """Final index, published only when every valid final report exists."""

    schema_version: Literal[1] = 1
    run_id: str
    workflow: str
    format: StorageFormat
    reports: list[ReportLink]


class Operation(Record):
    """Scheduler state; dataset failures are separately recorded results."""

    schema_version: Literal[1] = 1
    status: Literal["running", "succeeded", "failed", "interrupted", "cleaned"]
    updated_at: str = Field(default_factory=utc_now)
    exit_code: int | None = None


def write_record(path: Path, record: Record) -> None:
    """Publish a complete UTF-8 JSON document with an atomic rename."""
    atomic_write_text(path, record.model_dump_json(indent=2) + "\n")
