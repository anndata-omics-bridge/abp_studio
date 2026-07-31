"""Discover conversion branches supported by APB for one vendor input."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from anndata_proteomics.converters import pipeline as conversion_pipeline
from anndata_proteomics.params import registry as parameter_registry
from anndata_proteomics.params.model import Parameters, ParamsError
from anndata_proteomics.readers.dispatch import read_table_columns
from anndata_proteomics.rules import registry as rule_registry


class CapabilityStatus(StrEnum):
    """Structured result category used by pipeline status rendering."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CapabilityDiscovery:
    """Ordered APB branches or a diagnostic explaining why none were found."""

    branches: tuple[str, ...]
    diagnostic: str | None = None
    status: CapabilityStatus = CapabilityStatus.SUPPORTED
    software_slug: str | None = None
    software_version: str | None = None
    parameter_software_slug: str | None = None


class _CapabilityStepError(Exception):
    """Expected external-input failure annotated with its discovery stage."""

    def __init__(
        self,
        cause: Exception,
        *,
        action: str,
        software_slug: str | None = None,
        software_version: str | None = None,
        parameter_software_slug: str | None = None,
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.action = action
        self.software_slug = software_slug
        self.software_version = software_version
        self.parameter_software_slug = parameter_software_slug

    def as_discovery(self) -> CapabilityDiscovery:
        """Render this stage failure as the public structured result."""
        return _failed_discovery(
            self.cause,
            action=self.action,
            software_slug=self.software_slug,
            software_version=self.software_version,
            parameter_software_slug=self.parameter_software_slug,
        )


def discover_capabilities(
    input_path: str | Path,
    parameter_path: str | Path,
    software_name: str,
) -> CapabilityDiscovery:
    """Discover APB branches without loading a quantitative matrix.

    Results are cached by both resolved paths and their modification times. MuData
    is returned first, followed by APB's stable standalone-level order.

    Args:
        input_path: Vendor table whose schema determines matching parsing rules.
        parameter_path: Vendor parameter file used to resolve the software version.
        software_name: Catalog software name, such as ``DIA-NN``.

    Returns:
        The ordered branches, or an empty tuple and a diagnostic on failure.
    """
    catalog_slug = conversion_pipeline.software_slug(software_name)
    if not _has_packaged_rule_document(software_name):
        return CapabilityDiscovery(
            branches=(),
            diagnostic=(
                "APB has no packaged parsing-rule document for "
                f"software {catalog_slug!r}; this software is unsupported."
            ),
            status=CapabilityStatus.UNSUPPORTED,
            software_slug=catalog_slug,
        )
    try:
        input_file = Path(input_path).expanduser().resolve()
        parameter_file = Path(parameter_path).expanduser().resolve()
        input_mtime_ns = input_file.stat().st_mtime_ns
        parameter_mtime_ns = parameter_file.stat().st_mtime_ns
        parsing_rule_fingerprint = _parsing_rule_fingerprint()
    except OSError as error:
        return _unsupported_discovery(
            error,
            action="Required fixture file is unavailable",
            software_slug=catalog_slug,
        )
    except RuntimeError as error:
        return _failed_discovery(error, action="Could not inspect packaged parsing rules")
    return _cached_capability_discovery(
        str(input_file),
        input_mtime_ns,
        str(parameter_file),
        parameter_mtime_ns,
        software_name,
        parsing_rule_fingerprint,
    )


def _has_packaged_rule_document(software_name: str) -> bool:
    """Return whether the catalog label names at least one packaged rule vendor."""
    catalog_slug = conversion_pipeline.software_slug(software_name)
    vendors = {
        rule_registry.document_vendor(path) for path in rule_registry.iter_packaged_documents()
    }
    return any(vendor in catalog_slug for vendor in vendors)


@lru_cache(maxsize=512)
def _cached_capability_discovery(
    input_path: str,
    _input_mtime_ns: int,
    parameter_path: str,
    _parameter_mtime_ns: int,
    software_name: str,
    _parsing_rules: tuple[tuple[str, int, int], ...],
) -> CapabilityDiscovery:
    """Resolve one modification-time-qualified capability lookup."""
    try:
        headers = _read_input_headers(Path(input_path))
        slug, parameter_slug = _recognize_software(headers, software_name)
        if parameter_slug is None:
            return CapabilityDiscovery(
                branches=(),
                diagnostic=(
                    "APB has no parameter parser for "
                    f"software {software_name!r}; this fixture is not supported."
                ),
                status=CapabilityStatus.UNSUPPORTED,
                software_slug=slug,
            )
        parameters, version, version_status = _resolve_parameters(
            Path(parameter_path),
            parameter_slug,
            slug,
        )
        targets = _match_targets(
            slug,
            version,
            version_status,
            headers,
            parameters,
            parameter_slug,
        )
    except _CapabilityStepError as error:
        return error.as_discovery()

    if not targets:
        return CapabilityDiscovery(
            branches=(),
            diagnostic=(
                "No APB parsing rule matches "
                f"software {slug!r}, version {version!r}, and the input headers."
            ),
            status=CapabilityStatus.UNSUPPORTED,
            software_slug=slug,
            software_version=version,
            parameter_software_slug=parameter_slug,
        )
    standalone = tuple(target for target in targets if target != conversion_pipeline.MUDATA)
    return CapabilityDiscovery(
        branches=(conversion_pipeline.MUDATA, *standalone),
        software_slug=slug,
        software_version=version,
        parameter_software_slug=parameter_slug,
    )


def _read_input_headers(input_path: Path) -> tuple[str, ...]:
    """Read headers while translating malformed external input at one boundary."""
    try:
        # APB's reader content-detects delimiters exactly as conversion does.
        return tuple(read_table_columns(input_path))
    except (OSError, ValueError) as error:
        raise _CapabilityStepError(
            error,
            action="Could not read input table headers",
        ) from error


def _recognize_software(
    headers: tuple[str, ...],
    software_name: str,
) -> tuple[str, str | None]:
    """Resolve input and parameter parser slugs."""
    try:
        slug = conversion_pipeline.recognize_software(headers) or conversion_pipeline.software_slug(
            software_name
        )
        parameter_slug = parameter_registry.parser_slug(software_name)
    except ValueError as error:
        raise _CapabilityStepError(
            error,
            action="Could not recognize the input software",
        ) from error
    return slug, parameter_slug


def _resolve_parameters(
    parameter_path: Path,
    parameter_slug: str,
    software_slug: str,
) -> tuple[Parameters, str | None, conversion_pipeline.ParameterVersionStatus]:
    """Parse search parameters and select the rule-version status."""
    try:
        parameters = parameter_registry.parse_params(
            str(parameter_path),
            software=parameter_slug,
        )
        resolution = conversion_pipeline.ParameterResolution(
            source_path=parameter_path,
            parameters=parameters,
            version=parameters.software_version,
            version_status=("present" if parameters.software_version is not None else "missing"),
        )
        version, version_status = conversion_pipeline.resolve_rule_version(
            resolution,
            software_slug,
        )
    except (KeyError, OSError, ParamsError, ValueError) as error:
        raise _CapabilityStepError(
            error,
            action="Could not read the parameter file",
            software_slug=software_slug,
            parameter_software_slug=parameter_slug,
        ) from error
    return parameters, version, version_status


def _match_targets(
    software_slug: str,
    version: str | None,
    version_status: conversion_pipeline.ParameterVersionStatus,
    headers: tuple[str, ...],
    parameters: Parameters,
    parameter_slug: str,
) -> tuple[str, ...]:
    """Match resolved input metadata against APB's packaged rules."""
    try:
        return tuple(
            conversion_pipeline.available_targets(
                software_slug,
                version,
                headers,
                version_status=version_status,
                search_parameters=parameters,
            )
        )
    except (KeyError, OSError, ValueError) as error:
        raise _CapabilityStepError(
            error,
            action="Could not match APB parsing rules",
            software_slug=software_slug,
            software_version=version,
            parameter_software_slug=parameter_slug,
        ) from error


def _parsing_rule_fingerprint() -> tuple[tuple[str, int, int], ...]:
    """Return a stable cache key for APB's packaged parsing-rule JSON files."""
    fingerprint = []
    for path in rule_registry.iter_packaged_documents():
        resolved = path.resolve()
        stat_result = resolved.stat()
        fingerprint.append((str(resolved), stat_result.st_mtime_ns, stat_result.st_size))
    return tuple(fingerprint)


def _unsupported_discovery(
    error: Exception,
    *,
    action: str,
    software_slug: str | None = None,
) -> CapabilityDiscovery:
    """Convert an unavailable fixture prerequisite into an unsupported result."""
    detail = str(error).strip()
    message = type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"
    return CapabilityDiscovery(
        branches=(),
        diagnostic=f"{action}: {message}",
        status=CapabilityStatus.UNSUPPORTED,
        software_slug=software_slug,
    )


def _failed_discovery(
    error: Exception,
    *,
    action: str,
    software_slug: str | None = None,
    software_version: str | None = None,
    parameter_software_slug: str | None = None,
) -> CapabilityDiscovery:
    """Convert malformed input or an inspection failure into a failed result."""
    detail = str(error).strip()
    message = type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"
    return CapabilityDiscovery(
        branches=(),
        diagnostic=f"{action}: {message}",
        status=CapabilityStatus.FAILED,
        software_slug=software_slug,
        software_version=software_version,
        parameter_software_slug=parameter_software_slug,
    )
