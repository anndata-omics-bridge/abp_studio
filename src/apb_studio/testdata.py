"""Backend helpers for the APB Studio ProteoBench test-data application."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pandas as pd
from platformdirs import user_cache_path
from pydantic import BaseModel, ConfigDict, field_validator

import apb_studio
from apb_studio.jobrunner import Job, JobStatus, inspect_job, make_run_key, start_job

STUDIO_ROOT = Path(apb_studio.__file__).resolve().parents[2]
APB_ROOT = STUDIO_ROOT.parent / "apb"
DEFAULT_TEST_DATA_DIR = (APB_ROOT / "test_data_download").resolve()

_JOBS: dict[str, Job] = {}


class TestDataPaths(BaseModel):
    """Validated paths derived from one dedicated test-data directory."""

    model_config = ConfigDict(frozen=True, validate_default=True)

    data_dir: Path = DEFAULT_TEST_DATA_DIR

    @field_validator("data_dir", mode="before")
    @classmethod
    def validate_data_dir(cls, value: str | Path) -> Path:
        """Resolve an absolute, non-system-root test-data directory."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("Test-data folder must be an absolute path.")
        path = path.resolve()
        if path in {Path(path.anchor), Path.home().resolve()}:
            raise ValueError(
                "Choose a dedicated folder, not the filesystem or home root."
            )
        return path

    @property
    def catalog_csv(self) -> Path:
        """Return the complete catalog CSV path."""
        return self.data_dir / "raw_file_db_full.csv"

    @property
    def selection_csv(self) -> Path:
        """Return the download-selection CSV path."""
        return self.data_dir / "raw_file_db_selected.csv"

    @property
    def manifest_csv(self) -> Path:
        """Return the completed-download manifest CSV path."""
        return self.data_dir / "raw_file_db_downloaded.csv"

    @property
    def cache_dir(self) -> Path:
        """Return the shared metadata and raw-file cache directory."""
        return self.data_dir / "json_dir"

    @property
    def log_dir(self) -> Path:
        """Return the OS-cache directory for this root's Studio job logs."""
        root_key = make_run_key(self.data_dir)[:12]
        return user_cache_path("apb-studio") / "testdata" / root_key

    def create(self) -> None:
        """Create the selected root after validation."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.data_dir}")


def storage_summary(paths: TestDataPaths) -> str:
    """Describe all generated locations shown in the Storage tab."""
    return "\n".join(
        [
            f"Root folder:    {paths.data_dir}",
            f"Catalog CSV:    {paths.catalog_csv}",
            f"Selection CSV:  {paths.selection_csv}",
            f"Manifest CSV:   {paths.manifest_csv}",
            f"Metadata/raw:   {paths.cache_dir}",
            f"Studio logs:    {paths.log_dir}",
        ]
    )


def read_rows(path: Path) -> list[dict]:
    """Read a generated CSV as JSON-compatible records."""
    if not path.exists():
        return []
    return pd.read_csv(path).fillna("").to_dict(orient="records")


def catalog_rows(paths: TestDataPaths) -> list[dict]:
    """Return catalog rows augmented with live local download status."""
    manifest = {row["intermediate_hash"]: row for row in read_rows(paths.manifest_csv)}
    rows = read_rows(paths.catalog_csv)
    for row in rows:
        cached = dataset_dir(paths, row)
        inputs = sorted(cached.glob("input_file.*")) if cached.exists() else []
        recorded = manifest.get(row["intermediate_hash"], {})
        row["download_status"] = (
            "downloaded" if inputs else recorded.get("status", "not selected")
        )
        row["local_file"] = str(inputs[0]) if inputs else ""
    return rows


def selection_rows(paths: TestDataPaths) -> list[dict]:
    """Return selected rows augmented with live local download status."""
    selected_hashes = {
        row["intermediate_hash"] for row in read_rows(paths.selection_csv)
    }
    return [
        row
        for row in catalog_rows(paths)
        if row["intermediate_hash"] in selected_hashes
    ]


def dataset_dir(paths: TestDataPaths, row: dict) -> Path:
    """Return the local cache directory for a catalog row."""
    return paths.cache_dir / str(row["repo_name"]) / str(row["intermediate_hash"])


def metadata_path(paths: TestDataPaths, row: dict) -> Path:
    """Return the downloaded ProteoBench submission JSON path."""
    repo = str(row["repo_name"])
    return paths.cache_dir / repo / f"{repo}-main" / f"{row['intermediate_hash']}.json"


def row_details(paths: TestDataPaths, row: dict | None) -> tuple[str, str, str]:
    """Return file information, formatted submission JSON, and parameter content."""
    if not row:
        return "Select a row.", "", ""
    metadata = metadata_path(paths, row)
    json_text = "Metadata JSON is not cached yet. Run Catalog."
    if metadata.exists():
        parsed = json.loads(metadata.read_text(encoding="utf-8"))
        json_text = json.dumps(parsed, indent=2, sort_keys=True)
    parameters = sorted(dataset_dir(paths, row).glob("param_0.*"))
    parameter_text = "Parameter file is not downloaded yet."
    if parameters:
        parameter_text = parameters[0].read_text(encoding="utf-8", errors="replace")
        if parameters[0].suffix.lower() == ".json":
            parameter_text = json.dumps(
                json.loads(parameter_text), indent=2, sort_keys=True
            )
    info = "\n".join(f"{key}: {value}" for key, value in row.items())
    return info, json_text, parameter_text


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
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = start_job(
        testdata_command(action, paths, strategy=strategy, module=module),
        paths.log_dir / f"{action}.log",
        cwd=APB_ROOT,
    )
    return job_id


def job_status(job_id: str | None) -> JobStatus | None:
    """Return the current status of a registered background job."""
    job = _JOBS.get(job_id or "")
    return inspect_job(job) if job else None


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
