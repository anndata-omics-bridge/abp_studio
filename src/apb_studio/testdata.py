"""Backend helpers for the APB Studio ProteoBench test-data application."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import pandas as pd

import apb_studio
from apb_studio import capabilities
from apb_studio import fixture_inventory
from apb_studio.jobrunner import (
    Job,
    JobStatus,
    inspect_job,
    start_job,
    terminate_job,
)
from apb_studio.settings import DEFAULT_TEST_DATA_ROOT
from anndata_proteomics.readers.summary import describe_path

STUDIO_ROOT = Path(apb_studio.__file__).resolve().parents[2]
APB_ROOT = STUDIO_ROOT.parent / "apb"
DEFAULT_TEST_DATA_DIR = DEFAULT_TEST_DATA_ROOT

_JOBS: dict[str, Job | tuple[Job, ...]] = {}
_JOBS_LOCK = threading.RLock()
LEVELS = ("ion", "fragment", "peptidoform", "peptide", "protein")
ALL_LEVELS = "all"


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
            f"PB settings:    {paths.proteobench_settings_dir}",
            f"FASTA cache:    {paths.fasta_dir}",
            f"Resources CSV:  {paths.resource_csv}",
            f"Studio logs:    {paths.log_dir}",
        ]
    )


def read_rows(path: Path) -> list[dict]:
    """Read a generated CSV as JSON-compatible records."""
    if not path.exists():
        return []
    return pd.read_csv(path).fillna("").to_dict(orient="records")


def catalog_rows(paths: TestDataPaths) -> list[dict]:
    """Return all fixtures with live download and conversion status."""
    rows = []
    inventory = fixture_inventory.load_fixture_inventory(paths)
    for fixture in inventory.fixtures:
        row = fixture.as_catalog_row()
        targets = _fixture_conversion_targets(fixture)
        row["conversion_targets"] = list(targets)
        row["conversion_status"] = _conversion_status(
            targets,
            fixture=fixture,
        )
        rows.append(row)
    return rows


def selection_rows(paths: TestDataPaths) -> list[dict]:
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


def conversion_targets(paths: TestDataPaths, row: dict) -> tuple[str, ...]:
    """Return conversion choices supported by one downloaded fixture."""
    return _fixture_conversion_targets(_fixture_for_row(paths, row))


def _fixture_conversion_targets(
    fixture: fixture_inventory.FixtureRecord,
) -> tuple[str, ...]:
    """Resolve UI conversion choices from one complete local fixture."""
    if not fixture.complete:
        return ()
    assert fixture.input_path is not None
    assert fixture.parameter_path is not None
    discovery = capabilities.discover_capabilities(
        fixture.input_path,
        fixture.parameter_path,
        fixture.catalog_software_name,
    )
    levels = tuple(level for level in LEVELS if level in discovery.branches)
    return (ALL_LEVELS, *levels) if levels else ()


def _conversion_status(
    targets: tuple[str, ...],
    *,
    fixture: fixture_inventory.FixtureRecord,
) -> str:
    """Render compact conversion availability for the unified table."""
    if targets:
        return ", ".join(
            "all levels" if target == ALL_LEVELS else target for target in targets
        )
    if fixture.complete:
        assert fixture.input_path is not None
        assert fixture.parameter_path is not None
        discovery = capabilities.discover_capabilities(
            fixture.input_path,
            fixture.parameter_path,
            fixture.catalog_software_name,
        )
        return discovery.diagnostic or discovery.status.value
    if fixture.local_state is fixture_inventory.LocalFixtureState.INCOMPLETE:
        return fixture.diagnostic or "incomplete fixture"
    return "download first"


def dataset_dir(paths: TestDataPaths, row: dict) -> Path:
    """Return the local cache directory for a catalog row."""
    identity = fixture_inventory.fixture_identity(row)
    return fixture_inventory.fixture_directory(paths, identity[1], identity[2])


def converted_dir(paths: TestDataPaths, row: dict) -> Path:
    """Return the directory in which converted artifacts live for one fixture."""
    return dataset_dir(paths, row)


def metadata_path(paths: TestDataPaths, row: dict) -> Path:
    """Return the downloaded ProteoBench submission JSON path."""
    _, repo, fixture_hash = fixture_inventory.fixture_identity(row)
    repository_root = fixture_inventory.fixture_directory(paths, repo, f"{repo}-main")
    return repository_root / f"{fixture_hash}.json"


def row_details(paths: TestDataPaths, row: dict | None) -> tuple[str, str, str]:
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
            parameter_text = json.dumps(
                json.loads(parameter_text), indent=2, sort_keys=True
            )
    info = "\n".join(f"{key}: {value}" for key, value in canonical_row.items())
    return info, json_text, parameter_text


def _fixture_for_row(
    paths: TestDataPaths,
    row: dict,
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


def convert_command(paths: TestDataPaths, row: dict, level: str) -> list[str]:
    """Build an ``apb convert`` command for one downloaded fixture."""
    fixture = _fixture_for_row(paths, row)
    directory = fixture.dataset_dir
    inputs = fixture.input_files
    parameters = fixture.parameter_files
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
    with _JOBS_LOCK:
        _reject_overlapping_job()
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = start_job(
            testdata_command(action, paths, strategy=strategy, module=module),
            paths.log_dir / f"{action}.log",
            cwd=APB_ROOT,
        )
    return job_id


def launch_convert(paths: TestDataPaths, row: dict, levels: Sequence[str]) -> str:
    """Launch the selected APB conversions and return one group identifier."""
    paths.create()
    job_id = uuid.uuid4().hex
    fixture = str(row.get("intermediate_hash", "fixture"))[:12]
    targets = _selected_conversion_targets(levels)
    commands = tuple(
        (
            convert_command(paths, row, level),
            paths.log_dir / f"convert-{fixture}-{level}.log",
        )
        for level in targets
    )
    with _JOBS_LOCK:
        _reject_overlapping_job()
        started: list[Job] = []
        try:
            for command, log_file in commands:
                started.append(start_job(command, log_file, cwd=APB_ROOT))
        except Exception:
            for job in started:
                terminate_job(job)
            raise
        _JOBS[job_id] = tuple(started)
    return job_id


def _reject_overlapping_job() -> None:
    """Reject a new mutation while any registered Fixture Manager job runs."""
    active = next(
        (
            job_id
            for job_id, job in _JOBS.items()
            if _status_for_registered_job(job).running
        ),
        None,
    )
    if active is not None:
        raise JobAlreadyRunningError(
            f"Fixture Manager job {active} is already running."
        )


def _selected_conversion_targets(levels: Sequence[str]) -> tuple[str, ...]:
    """Normalize checkbox values into stable, non-redundant conversion targets."""
    selected = set(levels)
    unknown = selected - {ALL_LEVELS, *LEVELS}
    if unknown:
        raise ValueError(f"Unknown conversion targets: {sorted(unknown)}")
    if ALL_LEVELS in selected:
        return (ALL_LEVELS,)
    targets = tuple(level for level in LEVELS if level in selected)
    if not targets:
        raise ValueError("Select at least one conversion target.")
    return targets


def container_rows(paths: TestDataPaths) -> dict[str, list[dict]]:
    """Route MuData containers and standalone AnnData files to separate tables."""
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
                continue
            level = description["quantification"].get("level")
            if level in tables:
                tables[level].append(_level_row(catalog_row, path, description))
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
) -> dict:
    quantification = description["quantification"]
    return {
        **_base_container_row(catalog_row, path),
        "software_name": quantification.get("software_name") or "",
        "software_version": quantification.get("software_version") or "",
        "n_obs": quantification["n_runs"],
        "n_var": quantification["n_features"],
        "layers": ", ".join(quantification["layers"]),
        "mudata": False,
        "modality": None,
    }


def job_status(job_id: str | None) -> JobStatus | None:
    """Return the current status of a registered background job."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id or "")
    if not job:
        return None
    return _status_for_registered_job(job)


def _status_for_registered_job(job: Job | tuple[Job, ...]) -> JobStatus:
    """Combine one registered job or conversion group into one status."""
    if isinstance(job, Job):
        return inspect_job(job)
    statuses = [inspect_job(part) for part in job]
    running = any(status.running for status in statuses)
    return JobStatus(
        command=statuses[0].command,
        returncode=(
            None
            if running
            else next(
                (status.returncode for status in statuses if not status.success),
                0,
            )
        ),
        running=running,
        log_file=statuses[0].log_file,
        log_text="\n\n".join(status.log_text for status in statuses),
    )


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
