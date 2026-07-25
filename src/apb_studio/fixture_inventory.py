"""Typed inventory over the Fixture Manager catalog and live local cache."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from platformdirs import user_cache_path
from pydantic import BaseModel, ConfigDict, Field, field_validator

from apb_studio.jobrunner import make_run_key
from apb_studio.settings import DEFAULT_TEST_DATA_ROOT


class LocalFixtureState(StrEnum):
    """Filesystem completeness of one catalog fixture."""

    NOT_LOCAL = "not_local"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class FixtureStorePaths(BaseModel):
    """Validated paths derived from the active test-data root."""

    model_config = ConfigDict(frozen=True, validate_default=True)

    data_dir: Path = DEFAULT_TEST_DATA_ROOT

    @field_validator("data_dir", mode="before")
    @classmethod
    def validate_data_dir(cls, value: str | Path) -> Path:
        """Resolve an absolute, dedicated Fixture Manager root."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("Test-data folder must be an absolute path.")
        resolved = path.resolve()
        if resolved in {Path(resolved.anchor), Path.home().resolve()}:
            raise ValueError("Choose a dedicated folder, not the filesystem or home root.")
        return resolved

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
        """Return the historical download-report CSV path."""
        return self.data_dir / "raw_file_db_downloaded.csv"

    @property
    def resource_csv(self) -> Path:
        """Return the Fixture Manager-owned module-resource table."""
        return self.data_dir / "module_resources.csv"

    @property
    def cache_dir(self) -> Path:
        """Return the shared metadata and raw-file cache directory."""
        return self.data_dir / "json_dir"

    @property
    def fasta_dir(self) -> Path:
        """Return the APB-managed FASTA cache directory."""
        return self.data_dir / "fasta"

    @property
    def annotation_dir(self) -> Path:
        """Return the APB-managed ProteoBench annotation cache directory."""
        return self.data_dir / "annotations"

    @property
    def log_dir(self) -> Path:
        """Return the OS-cache directory for this root's background logs."""
        root_key = make_run_key(self.data_dir)[:12]
        return user_cache_path("apb-studio") / "fixture-manager" / root_key

    def create(self) -> None:
        """Create the selected root after validation."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.data_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.data_dir}")


class FixtureRecord(BaseModel):
    """Catalog identity plus authoritative live filesystem state."""

    model_config = ConfigDict(frozen=True)

    module: str = Field(min_length=1)
    repo_name: str = Field(min_length=1)
    intermediate_hash: str = Field(min_length=1)
    catalog_software_name: str = ""
    catalog_software_version: str = ""
    dataset_dir: Path
    input_files: tuple[Path, ...] = ()
    parameter_files: tuple[Path, ...] = ()
    local_state: LocalFixtureState
    diagnostic: str | None = None
    selected: bool = False
    manifest_status: str | None = None
    catalog_row: dict[str, Any] = Field(default_factory=dict)

    @field_validator("module", "repo_name", "intermediate_hash", mode="before")
    @classmethod
    def validate_identity_component(cls, value: object) -> str:
        """Reject identity fields that are not safe single path components."""
        return _safe_identity_component(value)

    @property
    def identity(self) -> tuple[str, str, str]:
        """Return the stable, collision-resistant fixture identity."""
        return (self.module, self.repo_name, self.intermediate_hash)

    @property
    def complete(self) -> bool:
        """Return whether exactly one input and one parameter file exist."""
        return self.local_state is LocalFixtureState.COMPLETE

    @property
    def input_path(self) -> Path | None:
        """Return the unique input path for a complete fixture."""
        return self.input_files[0] if self.complete else None

    @property
    def parameter_path(self) -> Path | None:
        """Return the unique parameter path for a complete fixture."""
        return self.parameter_files[0] if self.complete else None

    def as_catalog_row(self) -> dict[str, Any]:
        """Render legacy table fields without replacing raw catalog software."""
        row = dict(self.catalog_row)
        row.update(
            {
                "module": self.module,
                "repo_name": self.repo_name,
                "intermediate_hash": self.intermediate_hash,
                "software_name": self.catalog_software_name,
                "software_version": self.catalog_software_version,
                "download_status": _download_status(self),
                "fixture_status": self.local_state.value.replace("_", " "),
                "local_file": (str(self.input_files[0]) if len(self.input_files) == 1 else ""),
                "fixture_diagnostic": self.diagnostic or "",
            }
        )
        return row


class FixtureInventory(BaseModel):
    """One immutable snapshot of all catalog fixtures and their live state."""

    model_config = ConfigDict(frozen=True)

    paths: FixtureStorePaths
    fixtures: tuple[FixtureRecord, ...] = ()

    @property
    def complete_local(self) -> tuple[FixtureRecord, ...]:
        """Return every locally runnable fixture, including unsupported inputs."""
        return tuple(fixture for fixture in self.fixtures if fixture.complete)

    def for_identity(
        self,
        identity: tuple[str, str, str],
    ) -> FixtureRecord | None:
        """Look up a record by its stable identity."""
        return next(
            (fixture for fixture in self.fixtures if fixture.identity == identity),
            None,
        )


def load_fixture_inventory(
    test_data_root: str | Path | FixtureStorePaths,
) -> FixtureInventory:
    """Combine the full catalog with selections, history, and live local files."""
    paths = (
        test_data_root
        if isinstance(test_data_root, FixtureStorePaths)
        else FixtureStorePaths(data_dir=Path(test_data_root))
    )
    selected = {fixture_identity(row) for row in read_csv_rows(paths.selection_csv)}
    manifest = {fixture_identity(row): row for row in read_csv_rows(paths.manifest_csv)}
    fixtures = []
    seen: set[tuple[str, str, str]] = set()
    for row in read_csv_rows(paths.catalog_csv):
        identity = fixture_identity(row)
        if identity in seen:
            raise ValueError(f"Fixture catalog contains duplicate identity: {identity}")
        seen.add(identity)
        module, repo_name, intermediate_hash = identity
        directory = fixture_directory(paths, repo_name, intermediate_hash)
        inputs = _matching_files(directory, "input_file.*")
        parameters = _matching_files(directory, "param_0.*")
        local_state, diagnostic = _local_state(inputs, parameters)
        history = manifest.get(identity, {})
        fixtures.append(
            FixtureRecord(
                module=module,
                repo_name=repo_name,
                intermediate_hash=intermediate_hash,
                catalog_software_name=str(row.get("software_name", "")),
                catalog_software_version=str(row.get("software_version", "")),
                dataset_dir=directory,
                input_files=inputs,
                parameter_files=parameters,
                local_state=local_state,
                diagnostic=diagnostic,
                selected=identity in selected,
                manifest_status=str(history.get("status", "")) or None,
                catalog_row=row,
            )
        )
    return FixtureInventory(paths=paths, fixtures=tuple(fixtures))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a generated CSV without converting hashes or versions to numbers."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def fixture_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Extract and validate the canonical identity fields from one CSV row."""
    return (
        _safe_identity_component(row.get("module", ""), field="module"),
        _safe_identity_component(row.get("repo_name", ""), field="repo_name"),
        _safe_identity_component(
            row.get("intermediate_hash", ""),
            field="intermediate_hash",
        ),
    )


def fixture_directory(
    paths: FixtureStorePaths,
    repo_name: object,
    intermediate_hash: object,
) -> Path:
    """Return a contained fixture directory from validated identity fields."""
    repo = _safe_identity_component(repo_name, field="repo_name")
    fixture_hash = _safe_identity_component(
        intermediate_hash,
        field="intermediate_hash",
    )
    cache_root = paths.cache_dir.resolve()
    directory = (cache_root / repo / fixture_hash).resolve()
    if cache_root not in directory.parents:
        raise ValueError(f"Fixture directory escapes the cache root: {directory}")
    return directory


def _safe_identity_component(value: object, *, field: str = "identity") -> str:
    """Validate one catalog identity as a portable, single path component."""
    text = str(value).strip()
    posix = PurePosixPath(text)
    windows = PureWindowsPath(text)
    unsafe = (
        not text
        or text in {".", ".."}
        or posix.name != text
        or posix.is_absolute()
        or windows.name != text
        or windows.is_absolute()
        or bool(windows.drive)
        or any(ord(character) < 32 for character in text)
    )
    if unsafe:
        raise ValueError(f"Fixture {field} must be a non-empty, safe path component; got {text!r}.")
    return text


def _matching_files(directory: Path, pattern: str) -> tuple[Path, ...]:
    """Return sorted regular files matching one cache naming contract."""
    if not directory.is_dir():
        return ()
    return tuple(path.resolve() for path in sorted(directory.glob(pattern)) if path.is_file())


def _local_state(
    inputs: tuple[Path, ...],
    parameters: tuple[Path, ...],
) -> tuple[LocalFixtureState, str | None]:
    """Classify local completeness solely from live files."""
    if len(inputs) == 1 and len(parameters) == 1:
        return LocalFixtureState.COMPLETE, None
    if not inputs and not parameters:
        return LocalFixtureState.NOT_LOCAL, None
    return (
        LocalFixtureState.INCOMPLETE,
        "Expected exactly one input_file.* and one param_0.*; "
        f"found {len(inputs)} input file(s) and {len(parameters)} parameter file(s).",
    )


def _download_status(fixture: FixtureRecord) -> str:
    """Render selection/download history while allowing live files to win."""
    if fixture.complete:
        return "downloaded"
    if fixture.local_state is LocalFixtureState.INCOMPLETE:
        return "incomplete"
    if fixture.manifest_status and fixture.manifest_status.casefold() in {
        "complete",
        "downloaded",
        "ok",
        "success",
    }:
        return "missing"
    if fixture.manifest_status:
        return fixture.manifest_status
    return "selected" if fixture.selected else "not selected"
