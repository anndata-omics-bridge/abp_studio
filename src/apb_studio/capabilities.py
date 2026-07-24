"""Discover conversion branches supported by APB for one vendor input."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from anndata_proteomics.converters import pipeline as conversion_pipeline
from anndata_proteomics.params import registry as parameter_registry
from anndata_proteomics.rules import registry as rule_registry


class CapabilityStatus(StrEnum):
    """Structured result category used by pipeline status rendering."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CapabilityDiscovery:
    """Ordered APB branches or a diagnostic explaining why none were found."""

    branches: tuple[str, ...]
    diagnostic: str | None = None
    status: CapabilityStatus = CapabilityStatus.SUPPORTED
    software_slug: str | None = None
    software_version: str | None = None


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
    try:
        input_file = Path(input_path).expanduser().resolve()
        parameter_file = Path(parameter_path).expanduser().resolve()
        input_mtime_ns = input_file.stat().st_mtime_ns
        parameter_mtime_ns = parameter_file.stat().st_mtime_ns
        parsing_rule_fingerprint = _parsing_rule_fingerprint()
    except (OSError, RuntimeError) as error:
        return _failed_discovery(error)
    return _cached_capability_discovery(
        str(input_file),
        input_mtime_ns,
        str(parameter_file),
        parameter_mtime_ns,
        software_name,
        parsing_rule_fingerprint,
    )


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
    slug: str | None = None
    version: str | None = None
    try:
        headers = read_table_headers(Path(input_path))
        slug = conversion_pipeline.recognize_software(headers)
        if slug is None:
            slug = conversion_pipeline.software_slug(software_name)
        if slug not in parameter_registry.available_software():
            return CapabilityDiscovery(
                branches=(),
                diagnostic=(
                    "APB has no parameter parser for "
                    f"software {slug!r}; this fixture is not supported."
                ),
                status=CapabilityStatus.UNSUPPORTED,
                software_slug=slug,
            )
        version = parameter_registry.parse_params(
            parameter_path,
            software=slug,
        ).software_version
        targets = tuple(conversion_pipeline.available_targets(slug, version, headers))
    except Exception as error:  # noqa: BLE001 - callers need a visible diagnostic
        return _failed_discovery(
            error,
            software_slug=slug,
            software_version=version,
        )

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
        )
    standalone = tuple(target for target in targets if target != conversion_pipeline.MUDATA)
    return CapabilityDiscovery(
        branches=(conversion_pipeline.MUDATA, *standalone),
        software_slug=slug,
        software_version=version,
    )


def _parsing_rule_fingerprint() -> tuple[tuple[str, int, int], ...]:
    """Return a stable cache key for APB's packaged parsing-rule JSON files."""
    fingerprint = []
    for path in rule_registry.iter_packaged_documents():
        resolved = path.resolve()
        stat_result = resolved.stat()
        fingerprint.append((str(resolved), stat_result.st_mtime_ns, stat_result.st_size))
    return tuple(fingerprint)


def read_table_headers(path: Path) -> tuple[str, ...]:
    """Read a table schema from Parquet metadata or a zero-row text read."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return tuple(pq.read_schema(path).names)
    separators = {".csv": ",", ".tsv": "\t", ".txt": "\t"}
    separator = separators.get(suffix)
    if separator is None:
        raise ValueError(f"unsupported table extension {suffix!r}")
    return tuple(
        pd.read_csv(
            path,
            sep=separator,
            encoding="utf-8-sig",
            nrows=0,
        ).columns
    )


def _failed_discovery(
    error: Exception,
    *,
    software_slug: str | None = None,
    software_version: str | None = None,
) -> CapabilityDiscovery:
    """Convert an exception into a stable UI-facing capability diagnostic."""
    detail = str(error).strip()
    message = type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"
    return CapabilityDiscovery(
        branches=(),
        diagnostic=f"Capability discovery failed: {message}",
        status=CapabilityStatus.BLOCKED,
        software_slug=software_slug,
        software_version=software_version,
    )
