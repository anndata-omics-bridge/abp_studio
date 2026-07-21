"""Backend helpers for the APB Studio ProteoBench test-data application."""

from __future__ import annotations

import json
import shutil
import uuid
from functools import lru_cache
from pathlib import Path

import pandas as pd
from platformdirs import user_cache_path
from pydantic import BaseModel, ConfigDict, field_validator

import apb_studio
from apb_studio.jobrunner import Job, JobStatus, inspect_job, make_run_key, start_job
from anndata_proteomics.readers.summary import describe_path

STUDIO_ROOT = Path(apb_studio.__file__).resolve().parents[2]
APB_ROOT = STUDIO_ROOT.parent / "apb"
DEFAULT_TEST_DATA_DIR = (APB_ROOT / "test_data_download").resolve()

_JOBS: dict[str, Job] = {}
LEVELS = ("ion", "fragment", "peptidoform", "peptide", "protein")
ALL_LEVELS = "all"


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


def converted_dir(paths: TestDataPaths, row: dict) -> Path:
    """Return the directory in which converted artifacts live for one fixture."""
    return dataset_dir(paths, row)


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


def convert_command(paths: TestDataPaths, row: dict, level: str) -> list[str]:
    """Build an ``apb convert`` command for one downloaded fixture."""
    directory = converted_dir(paths, row)
    inputs = sorted(directory.glob("input_file.*"))
    parameters = sorted(directory.glob("param_0.*"))
    if len(inputs) != 1:
        raise ValueError(
            f"Expected exactly one downloaded input_file.* for the selected fixture, got {len(inputs)}"
        )
    if len(parameters) != 1:
        raise ValueError(
            f"Expected exactly one param_0.* for the selected fixture, got {len(parameters)}"
        )
    if level not in {ALL_LEVELS, *LEVELS}:
        raise ValueError(f"Unknown conversion target: {level}")

    executable = shutil.which("apb") or "apb"
    command = [executable, "convert", str(inputs[0])]
    output_name = "mudata" if level == ALL_LEVELS else level
    if level != ALL_LEVELS:
        command.append(level)
    command.extend(
        [
            "--params",
            str(parameters[0]),
            "--output",
            str(directory / output_name),
        ]
    )
    return command


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


def launch_convert(paths: TestDataPaths, row: dict, level: str) -> str:
    """Launch one APB conversion and return its process-registry identifier."""
    paths.create()
    job_id = uuid.uuid4().hex
    fixture = str(row.get("intermediate_hash", "fixture"))[:12]
    _JOBS[job_id] = start_job(
        convert_command(paths, row, level),
        paths.log_dir / f"convert-{fixture}-{level}.log",
        cwd=APB_ROOT,
    )
    return job_id


def container_rows(paths: TestDataPaths) -> dict[str, list[dict]]:
    """Return MuData and per-level table rows for all converted fixtures."""
    tables = {"mudata": [], **{level: [] for level in LEVELS}}
    for catalog_row in catalog_rows(paths):
        directory = converted_dir(paths, catalog_row)
        if not directory.exists():
            continue
        containers = sorted(directory.glob("*.h5ad")) + sorted(directory.glob("*.h5mu"))
        for path in containers:
            description = _description_for(path)
            if description["container_type"] == "mudata":
                tables["mudata"].append(_mudata_row(catalog_row, path, description))
                for modality, modality_description in description["modalities"].items():
                    level = modality_description["quantification"].get("level")
                    if level in tables:
                        tables[level].append(
                            _level_row(
                                catalog_row,
                                path,
                                modality_description,
                                mudata=True,
                                modality=modality,
                            )
                        )
                continue
            level = description["quantification"].get("level")
            if level in tables:
                tables[level].append(
                    _level_row(
                        catalog_row,
                        path,
                        description,
                        mudata=False,
                        modality=None,
                    )
                )
    return tables


def container_summary(path: Path | str, modality: str | None = None) -> str:
    """Format one cached APB descriptive summary for the detail pane."""
    container = Path(path)
    description = _description_for(container, modality=modality)
    return json.dumps(description, indent=2, sort_keys=True)


def _description_for(path: Path, modality: str | None = None) -> dict:
    resolved = path.expanduser().resolve()
    return _cached_description(str(resolved), resolved.stat().st_mtime_ns, modality)


@lru_cache(maxsize=512)
def _cached_description(
    path: str,
    _mtime_ns: int,
    modality: str | None,
) -> dict:
    return describe_path(path, modality=modality)


def _base_container_row(catalog_row: dict, path: Path) -> dict:
    return {
        "dataset": catalog_row.get("intermediate_hash", path.parent.name),
        "module": catalog_row.get("module", ""),
        "path": str(path),
    }


def _mudata_row(catalog_row: dict, path: Path, description: dict) -> dict:
    quantification = description["quantification"]
    modality_quantification = [
        value["quantification"] for value in description["modalities"].values()
    ]
    software_names = sorted(
        {
            value["software_name"]
            for value in modality_quantification
            if value.get("software_name")
        }
    )
    software_versions = sorted(
        {
            value["software_version"]
            for value in modality_quantification
            if value.get("software_version")
        }
    )
    return {
        **_base_container_row(catalog_row, path),
        "software_name": ", ".join(software_names),
        "software_version": ", ".join(software_versions),
        "n_obs": quantification["n_runs"],
        "n_var": quantification["n_features"],
        "modalities": ", ".join(quantification["modalities"]),
        "modality": None,
    }


def _level_row(
    catalog_row: dict,
    path: Path,
    description: dict,
    *,
    mudata: bool,
    modality: str | None,
) -> dict:
    quantification = description["quantification"]
    return {
        **_base_container_row(catalog_row, path),
        "software_name": quantification.get("software_name") or "",
        "software_version": quantification.get("software_version") or "",
        "n_obs": quantification["n_runs"],
        "n_var": quantification["n_features"],
        "layers": ", ".join(quantification["layers"]),
        "mudata": mudata,
        "modality": modality,
    }


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
