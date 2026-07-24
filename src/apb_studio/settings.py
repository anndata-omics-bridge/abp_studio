"""Validated, disk-backed settings shared by both APB Studio applications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Self

from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel, ConfigDict, field_validator

from apb_studio.disk import atomic_write_text, interprocess_file_lock

_DEFAULT_DATA_ROOT = user_data_path("apb-studio").resolve()
DEFAULT_TEST_DATA_ROOT = _DEFAULT_DATA_ROOT / "test_data_download"
DEFAULT_OUTPUT_ROOT = _DEFAULT_DATA_ROOT / "outputs"
DEFAULT_SETTINGS_PATH = user_config_path("apb-studio") / "settings.json"


class StudioSettings(BaseModel):
    """The small set of roots intentionally shared across Studio processes."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    schema_version: int = 1
    test_data_root: Path = DEFAULT_TEST_DATA_ROOT
    output_root: Path = DEFAULT_OUTPUT_ROOT

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        """Reject settings written by an unknown schema."""
        if value != 1:
            raise ValueError(f"Unsupported settings schema version: {value}")
        return value

    @field_validator("test_data_root", "output_root", mode="before")
    @classmethod
    def validate_dedicated_root(cls, value: str | Path) -> Path:
        """Resolve an absolute path while rejecting broad system roots."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("Studio roots must be absolute paths.")
        resolved = path.resolve()
        if resolved in {Path(resolved.anchor), Path.home().resolve()}:
            raise ValueError("Choose a dedicated folder, not the filesystem or home root.")
        return resolved

    @classmethod
    def from_json(cls, source: str) -> Self:
        """Validate settings loaded from a JSON document."""
        return cls.model_validate(json.loads(source))


def settings_path(path: Path | None = None) -> Path:
    """Return the explicit or platform-native settings location."""
    return (path or DEFAULT_SETTINGS_PATH).expanduser().resolve()


def load_settings(path: Path | None = None) -> StudioSettings:
    """Load shared settings, returning typed defaults before the first save."""
    location = settings_path(path)
    return _load_settings_unlocked(location)


def _load_settings_unlocked(location: Path) -> StudioSettings:
    """Load one atomic settings document while an optional caller lock is held."""
    if not location.exists():
        return StudioSettings()
    return StudioSettings.from_json(location.read_text(encoding="utf-8"))


def save_settings(
    value: StudioSettings,
    path: Path | None = None,
) -> StudioSettings:
    """Validate and atomically persist a complete settings document."""
    location = settings_path(path)
    with interprocess_file_lock(_settings_lock_path(location)):
        return _save_settings_unlocked(value, location)


def _save_settings_unlocked(
    value: StudioSettings,
    location: Path,
) -> StudioSettings:
    """Persist one settings document while the caller holds its lock."""
    validated = StudioSettings.model_validate(value.model_dump())
    source = json.dumps(
        validated.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(location, f"{source}\n")
    return validated


def update_settings(
    *,
    test_data_root: str | Path | None = None,
    output_root: str | Path | None = None,
    path: Path | None = None,
) -> StudioSettings:
    """Atomically save selected fields without resetting the other application."""
    location = settings_path(path)
    with interprocess_file_lock(_settings_lock_path(location)):
        current = _load_settings_unlocked(location)
        changes: dict[str, Any] = {}
        if test_data_root is not None:
            changes["test_data_root"] = test_data_root
        if output_root is not None:
            changes["output_root"] = output_root
        candidate = {**current.model_dump(), **changes}
        return _save_settings_unlocked(
            StudioSettings.model_validate(candidate),
            location,
        )


def _settings_lock_path(location: Path) -> Path:
    """Return the stable lock-file path shared by both Studio applications."""
    return location.with_name(f"{location.name}.lock")
