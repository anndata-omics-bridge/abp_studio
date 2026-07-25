"""Backend helpers for the APB Studio ProteoBench test-data application."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from apb_studio import fixture_inventory
from apb_studio.jobrunner import (
    Job,
    JobStatus,
    inspect_job,
    start_job,
)
from apb_studio.settings import DEFAULT_TEST_DATA_ROOT

DEFAULT_TEST_DATA_DIR = DEFAULT_TEST_DATA_ROOT

_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.RLock()


class JobAlreadyRunningError(RuntimeError):
    """Raised when a mutating Fixture Manager job is already active."""


class TestDataPaths(fixture_inventory.FixtureStorePaths):
    """Backward-compatible name for the shared Fixture Manager paths."""


def storage_summary(paths: TestDataPaths) -> str:
    """Describe all generated locations shown in the Storage tab."""
    return "\n".join(
        [
            f"Root folder:    {paths.data_dir}",
            f"Catalog CSV:    {paths.catalog_csv}",
            f"Selection CSV:  {paths.selection_csv}",
            f"Manifest CSV:   {paths.manifest_csv}",
            f"Metadata/raw:   {paths.cache_dir}",
            f"Annotations:    {paths.annotation_dir}",
            f"FASTA cache:    {paths.fasta_dir}",
            f"Resources CSV:  {paths.resource_csv}",
            f"Studio logs:    {paths.log_dir}",
        ]
    )


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Read a generated CSV as JSON-compatible records."""
    if not path.exists():
        return []
    records = pd.read_csv(path).fillna("").to_dict(orient="records")
    return [{str(key): value for key, value in record.items()} for record in records]


def catalog_rows(paths: TestDataPaths) -> list[dict[str, Any]]:
    """Return all fixtures with live local download status."""
    inventory = fixture_inventory.load_fixture_inventory(paths)
    return [fixture.as_catalog_row() for fixture in inventory.fixtures]


def selection_rows(paths: TestDataPaths) -> list[dict[str, Any]]:
    """Return selected rows augmented with live local download status."""
    selected_identities = {
        fixture_inventory.fixture_identity(row)
        for row in fixture_inventory.read_csv_rows(paths.selection_csv)
    }
    return [
        row
        for row in catalog_rows(paths)
        if fixture_inventory.fixture_identity(row) in selected_identities
    ]


def dataset_dir(paths: TestDataPaths, row: dict[str, Any]) -> Path:
    """Return the local cache directory for a catalog row."""
    identity = fixture_inventory.fixture_identity(row)
    return fixture_inventory.fixture_directory(paths, identity[1], identity[2])


def metadata_path(paths: TestDataPaths, row: dict[str, Any]) -> Path:
    """Return the downloaded ProteoBench submission JSON path."""
    _, repo, fixture_hash = fixture_inventory.fixture_identity(row)
    repository_root = fixture_inventory.fixture_directory(paths, repo, f"{repo}-main")
    return repository_root / f"{fixture_hash}.json"


def row_details(
    paths: TestDataPaths,
    row: dict[str, Any] | None,
) -> tuple[str, str, str]:
    """Return file information, formatted submission JSON, and parameter content."""
    if not row:
        return "Select a row.", "", ""
    fixture = _fixture_for_row(paths, row)
    canonical_row = fixture.as_catalog_row()
    metadata = metadata_path(paths, canonical_row)
    json_text = "Metadata JSON is not cached yet. Run Catalog."
    if metadata.exists():
        parsed = json.loads(metadata.read_text(encoding="utf-8"))
        json_text = json.dumps(parsed, indent=2, sort_keys=True)
    parameters = fixture.parameter_files
    parameter_text = "Parameter file is not downloaded yet."
    if parameters:
        parameter_text = parameters[0].read_text(encoding="utf-8", errors="replace")
        if parameters[0].suffix.lower() == ".json":
            parameter_text = json.dumps(json.loads(parameter_text), indent=2, sort_keys=True)
    info = "\n".join(f"{key}: {value}" for key, value in canonical_row.items())
    return info, json_text, parameter_text


def _fixture_for_row(
    paths: TestDataPaths,
    row: dict[str, Any],
) -> fixture_inventory.FixtureRecord:
    """Resolve an untrusted client row against the authoritative catalog."""
    identity = fixture_inventory.fixture_identity(row)
    fixture = fixture_inventory.load_fixture_inventory(paths).for_identity(identity)
    if fixture is None:
        raise ValueError(f"Fixture is not present in the catalog: {identity!r}")
    return fixture


def testdata_command(
    action: str,
    paths: TestDataPaths,
    *,
    strategy: str | None = None,
    module: str | None = None,
) -> list[str]:
    """Build an apb-testdata command with explicit shared artifact paths."""
    executable = shutil.which("apb-testdata") or "apb-testdata"
    if action == "catalog":
        return [
            executable,
            "catalog",
            "--catalog-csv",
            str(paths.catalog_csv),
            "--cache-dir",
            str(paths.cache_dir),
        ]
    if action == "select":
        command = [
            executable,
            "select",
            "--catalog-csv",
            str(paths.catalog_csv),
            "--selection-csv",
            str(paths.selection_csv),
            "--strategy",
            strategy or "smallest-per-software-version",
        ]
        if module:
            command.extend(["--module", module])
        return command
    if action == "download":
        return [
            executable,
            "download",
            "--selection-csv",
            str(paths.selection_csv),
            "--cache-dir",
            str(paths.cache_dir),
            "--manifest-csv",
            str(paths.manifest_csv),
        ]
    if action == "fasta":
        return [
            executable,
            "fasta",
            "--fasta-dir",
            str(paths.fasta_dir),
        ]
    if action == "annotations":
        return [
            executable,
            "annotations",
            "--annotation-dir",
            str(paths.annotation_dir),
        ]
    if action == "clean":
        return [executable, "clean", "--data-dir", str(paths.data_dir)]
    raise ValueError(f"Unknown test-data action: {action}")


def launch(
    action: str,
    paths: TestDataPaths,
    *,
    strategy: str | None = None,
    module: str | None = None,
) -> str:
    """Launch an APB test-data command and return its process-registry identifier."""
    paths.create()
    with _JOBS_LOCK:
        _reject_overlapping_job()
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = start_job(
            testdata_command(action, paths, strategy=strategy, module=module),
            paths.log_dir / f"{action}.log",
        )
    return job_id


def _reject_overlapping_job() -> None:
    """Reject a new mutation while any registered Fixture Manager job runs."""
    active = next(
        (job_id for job_id, job in _JOBS.items() if inspect_job(job).running),
        None,
    )
    if active is not None:
        raise JobAlreadyRunningError(f"Fixture Manager job {active} is already running.")


def job_status(job_id: str | None) -> JobStatus | None:
    """Return the current status of a registered background job."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id or "")
    if not job:
        return None
    return inspect_job(job)


def job_presentation(
    status: JobStatus | None,
    *,
    catalog_count: int,
    selection_count: int,
) -> tuple[str, str, str, dict[str, str]]:
    """Build the status line, log content, tab label, and tab style for a job."""
    counts = f"Catalog: {catalog_count} rows · Selected: {selection_count} rows"
    if status is None:
        return counts, "No job has run yet.", "Log", {}
    state = "running…" if status.running else ("done" if status.success else "failed")
    if not status.running and not status.success:
        return (
            f"Job: {state} · {counts}",
            status.log_text or "No log output yet.",
            "Log — ERROR",
            {"color": "#b00020", "fontWeight": "bold"},
        )
    return (
        f"Job: {state} · {counts}",
        status.log_text or "No log output yet.",
        "Log",
        {},
    )
