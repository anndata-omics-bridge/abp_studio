"""Fixture Manager-owned annotation and FASTA resources keyed by module."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from anndata_proteomics.annotation.loader import ANNOTATION_SUFFIXES, load_annotation
from anndata_proteomics.fasta.parser import iter_fasta
from anndata_proteomics.test_data import find_annotation, find_fasta
from pydantic import BaseModel, ConfigDict, Field, field_validator

from apb_studio.disk import atomic_write_text
from apb_studio.fixture_inventory import (
    FixtureStorePaths,
    fixture_identity,
    read_csv_rows,
)

RESOURCE_COLUMNS = ("module", "annotation_path", "fasta_path")


class ModuleResource(BaseModel):
    """Assigned resource paths for one canonical ProteoBench module."""

    model_config = ConfigDict(frozen=True)

    module: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    annotation_path: Path | None = None
    fasta_path: Path | None = None
    annotation_error: str | None = None
    fasta_error: str | None = None
    annotation_managed: bool = False
    fasta_managed: bool = False

    @field_validator("annotation_path", "fasta_path", mode="before")
    @classmethod
    def resolve_optional_path(cls, value: str | Path | None) -> Path | None:
        """Normalize assigned paths while allowing an empty CSV cell."""
        if value is None or not str(value).strip():
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("Module resource paths must be absolute.")
        return path.resolve()

    @property
    def annotation_available(self) -> bool:
        """Return whether the assigned annotation still exists as a file."""
        return (
            self.annotation_path is not None
            and self.annotation_error is None
            and self.annotation_path.is_file()
        )

    @property
    def fasta_available(self) -> bool:
        """Return whether the assigned FASTA still exists as a file."""
        return (
            self.fasta_path is not None and self.fasta_error is None and self.fasta_path.is_file()
        )


class ModuleResourceInventory(BaseModel):
    """Validated immutable module-resource assignments."""

    model_config = ConfigDict(frozen=True)

    resources: tuple[ModuleResource, ...] = ()

    def for_module(self, module: str) -> ModuleResource | None:
        """Return the assignment for one canonical module, if present."""
        return next(
            (resource for resource in self.resources if resource.module == module),
            None,
        )


def load_module_resources(
    test_data_root: str | Path | FixtureStorePaths,
) -> ModuleResourceInventory:
    """Load overrides and discover APB-managed annotations and FASTAs."""
    paths = _paths(test_data_root)
    rows: list[dict[str, str]] = []
    if paths.resource_csv.exists():
        with paths.resource_csv.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    resources = tuple(_assess_resource(ModuleResource.model_validate(row)) for row in rows)
    modules = [resource.module for resource in resources]
    if len(set(modules)) != len(modules):
        raise ValueError("module_resources.csv contains duplicate module rows.")
    by_module = {resource.module: resource for resource in resources}
    catalog_modules = {fixture_identity(row)[0] for row in read_csv_rows(paths.catalog_csv)}
    for module in sorted(catalog_modules):
        existing = by_module.get(module)
        managed_annotation = find_annotation(
            module=module,
            test_data_dir=paths.data_dir,
        )
        managed_fasta = find_fasta(module=module, test_data_dir=paths.data_dir)
        annotation_path = managed_annotation or (
            existing.annotation_path if existing is not None else None
        )
        fasta_path = (
            existing.fasta_path
            if existing is not None and existing.fasta_path is not None
            else managed_fasta
        )
        if annotation_path is None and fasta_path is None:
            continue
        by_module[module] = _assess_resource(
            ModuleResource(
                module=module,
                annotation_path=annotation_path,
                fasta_path=fasta_path,
                annotation_managed=managed_annotation is not None,
                fasta_managed=(
                    managed_fasta is not None and (existing is None or existing.fasta_path is None)
                ),
            )
        )
    return ModuleResourceInventory(
        resources=tuple(by_module[module] for module in sorted(by_module))
    )


def save_module_resources(
    test_data_root: str | Path | FixtureStorePaths,
    inventory: ModuleResourceInventory,
) -> ModuleResourceInventory:
    """Atomically persist canonical, module-sorted resource assignments."""
    paths = _paths(test_data_root)
    paths.create()
    validated = ModuleResourceInventory(
        resources=tuple(_assess_resource(resource) for resource in inventory.resources)
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RESOURCE_COLUMNS)
    writer.writeheader()
    for resource in sorted(validated.resources, key=lambda item: item.module):
        persisted_annotation = None if resource.annotation_managed else resource.annotation_path
        persisted_fasta = None if resource.fasta_managed else resource.fasta_path
        if persisted_annotation is None and persisted_fasta is None:
            continue
        writer.writerow(
            {
                "module": resource.module,
                "annotation_path": persisted_annotation or "",
                "fasta_path": persisted_fasta or "",
            }
        )
    atomic_write_text(paths.resource_csv, stream.getvalue())
    return validated


def set_module_resource(
    test_data_root: str | Path | FixtureStorePaths,
    module: str,
    *,
    annotation_path: str | Path | None,
    fasta_path: str | Path | None,
) -> ModuleResourceInventory:
    """Validate and replace the complete assignment for one module."""
    annotation = _validate_annotation(annotation_path)
    fasta = _validate_fasta(fasta_path)
    current = load_module_resources(test_data_root)
    resources = [item for item in current.resources if item.module != module]
    if annotation is not None or fasta is not None:
        resources.append(
            ModuleResource(
                module=module,
                annotation_path=annotation,
                fasta_path=fasta,
            )
        )
    return save_module_resources(
        test_data_root,
        ModuleResourceInventory(resources=tuple(resources)),
    )


def sync_fasta_resources(
    test_data_root: str | Path | FixtureStorePaths,
    modules: Iterable[str],
) -> ModuleResourceInventory:
    """Assign APB's downloaded module FASTAs without copying its module map."""
    paths = _paths(test_data_root)
    current = load_module_resources(paths)
    by_module = {resource.module: resource for resource in current.resources}
    for module in sorted(set(modules)):
        existing = by_module.get(module)
        annotation = existing.annotation_path if existing is not None else None
        assigned_fasta = (
            existing.fasta_path
            if existing is not None and existing.fasta_path is not None
            else find_fasta(module=module, test_data_dir=paths.data_dir)
        )
        if annotation is not None or assigned_fasta is not None:
            by_module[module] = ModuleResource(
                module=module,
                annotation_path=annotation,
                fasta_path=assigned_fasta,
                annotation_managed=(existing.annotation_managed if existing is not None else False),
                fasta_managed=False,
            )
    return save_module_resources(
        paths,
        ModuleResourceInventory(resources=tuple(by_module.values())),
    )


def resource_rows(
    inventory: ModuleResourceInventory,
    modules: Iterable[str],
) -> list[dict[str, Any]]:
    """Render every catalog module, including currently unassigned resources."""
    rows = []
    for module in sorted(set(modules)):
        resource = inventory.for_module(module)
        rows.append(
            {
                "module": module,
                "annotation_path": str(resource.annotation_path)
                if resource and resource.annotation_path
                else "",
                "annotation_status": "available"
                if resource and resource.annotation_available
                else _unavailable_status(
                    resource.annotation_path if resource else None,
                    resource.annotation_error if resource else None,
                ),
                "fasta_path": str(resource.fasta_path) if resource and resource.fasta_path else "",
                "fasta_status": "available"
                if resource and resource.fasta_available
                else _unavailable_status(
                    resource.fasta_path if resource else None,
                    resource.fasta_error if resource else None,
                ),
            }
        )
    return rows


def _paths(
    value: str | Path | FixtureStorePaths,
) -> FixtureStorePaths:
    return (
        value if isinstance(value, FixtureStorePaths) else FixtureStorePaths(data_dir=Path(value))
    )


def _validate_annotation(value: str | Path | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Module resource paths must be absolute.")
    path = path.resolve()
    if path.suffix.lower() not in ANNOTATION_SUFFIXES or not path.is_file():
        formats = ", ".join(sorted(ANNOTATION_SUFFIXES))
        raise ValueError(f"Annotation must be an existing supported table ({formats}): {path}")
    try:
        _cached_load_annotation(*_file_signature(path))
    except Exception as error:
        raise ValueError(
            f"Annotation must be a readable sample table: {path}: {type(error).__name__}: {error}"
        ) from error
    return path


def _validate_fasta(value: str | Path | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Module resource paths must be absolute.")
    path = path.resolve()
    if path.suffix.lower() not in {".fa", ".fas", ".fasta"} or not path.is_file():
        raise ValueError(f"FASTA must be an existing .fa/.fas/.fasta file: {path}")
    try:
        _cached_validate_fasta(*_file_signature(path))
    except Exception as error:
        raise ValueError(
            f"FASTA must be a valid FASTA file: {path}: {type(error).__name__}: {error}"
        ) from error
    return path


def _assess_resource(resource: ModuleResource) -> ModuleResource:
    """Attach live parser diagnostics without rejecting persisted assignments."""
    return resource.model_copy(
        update={
            "annotation_error": _resource_error(
                "annotation",
                resource.annotation_path,
            ),
            "fasta_error": _resource_error("FASTA", resource.fasta_path),
        }
    )


def _resource_error(kind: str, path: Path | None) -> str | None:
    """Return a concise missing/invalid diagnostic for one assigned resource."""
    if path is None:
        return None
    if not path.is_file():
        return f"Missing {kind} resource: {path}"
    if kind == "annotation" and path.suffix.lower() not in ANNOTATION_SUFFIXES:
        return f"Invalid annotation resource extension: {path}"
    if kind == "FASTA" and path.suffix.lower() not in {".fa", ".fas", ".fasta"}:
        return f"Invalid FASTA resource extension: {path}"
    try:
        signature = _file_signature(path)
        if kind == "annotation":
            _cached_load_annotation(*signature)
        else:
            _cached_validate_fasta(*signature)
    except Exception as error:
        return f"Invalid {kind} resource {path}: {type(error).__name__}: {error}"
    return None


def _file_signature(path: Path) -> tuple[str, int, int]:
    """Return a cache key that changes when a resource file changes."""
    stat_result = path.stat()
    return str(path), stat_result.st_mtime_ns, stat_result.st_size


@lru_cache(maxsize=256)
def _cached_load_annotation(
    path: str,
    _mtime_ns: int,
    _size: int,
) -> None:
    """Parse one external sample-annotation table."""
    load_annotation(path)


@lru_cache(maxsize=64)
def _cached_validate_fasta(
    path: str,
    _mtime_ns: int,
    _size: int,
) -> None:
    """Validate the first record with APB's streaming FASTA parser."""
    first = next(iter_fasta(Path(path)), None)
    if first is None or not first.header.strip() or not first.sequence.strip():
        raise ValueError("expected at least one non-empty FASTA record")


def _unavailable_status(path: Path | None, error: str | None) -> str:
    """Distinguish a malformed assigned file from a missing resource."""
    if path is not None and path.is_file() and error is not None:
        return "invalid"
    return "missing"
