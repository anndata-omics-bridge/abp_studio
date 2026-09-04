"""Discover APB2 conversion branches for one vendor input."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from pathlib import Path

from apb2.parserV2.compile import AnnDataOutput, NoCompatibleLevelError, compile_parsers
from apb2.parserV2.detect_document import (
    RuleDetectionError,
    detect_rule_document,
    search_parameter_evidence,
    software_slug,
)
from apb2.parserV2.parse_quant.parameters.source import SingleFile
from apb2.parserV2.vendor_params.parsers.shared.model import ParamsError
from apb2.parserV2.vendor_params.registry import parse_params
from loguru import logger

from apb_studio.pipeline import MUDATA

_RULE_PACKAGE = "apb2.parserV2.vendor_parse_rules.documents"


class CapabilityStatus(StrEnum):
    """Structured result category used by pipeline status rendering."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CapabilityDiscovery:
    """Ordered APB2 branches or a diagnostic explaining why none were found."""

    branches: tuple[str, ...]
    diagnostic: str | None = None
    status: CapabilityStatus = CapabilityStatus.SUPPORTED
    software_slug: str | None = None
    software_version: str | None = None
    parameter_software_slug: str | None = None


def discover_capabilities(
    input_path: Path,
    parameter_path: Path,
    software_name: str,
) -> CapabilityDiscovery:
    """Ask APB2 which MuData and standalone levels the fixture supports."""
    parameter_slug = software_slug(software_name)
    try:
        input_file = input_path.expanduser().resolve()
        parameter_file = parameter_path.expanduser().resolve()
        input_mtime_ns = input_file.stat().st_mtime_ns
        parameter_mtime_ns = parameter_file.stat().st_mtime_ns
        rule_fingerprint = _rule_fingerprint()
    except OSError as error:
        return _discovery_error(
            error,
            action="Required fixture file is unavailable",
            status=CapabilityStatus.UNSUPPORTED,
            parameter_slug=parameter_slug,
        )
    return _cached_capability_discovery(
        str(input_file),
        input_mtime_ns,
        str(parameter_file),
        parameter_mtime_ns,
        parameter_slug,
        rule_fingerprint,
    )


@lru_cache(maxsize=512)
def _cached_capability_discovery(
    input_path: str,
    _input_mtime_ns: int,
    parameter_path: str,
    _parameter_mtime_ns: int,
    parameter_slug: str,
    _rule_fingerprint_value: tuple[tuple[str, int, int], ...],
) -> CapabilityDiscovery:
    try:
        source = SingleFile(path=Path(input_path))
        parameters = parse_params(Path(parameter_path), software=parameter_slug)
        detected = detect_rule_document(parameters, source)
        parsers = compile_parsers(
            document=detected.document,
            levels=detected.document.levels,
            parameter_evidence=search_parameter_evidence(parameters),
            source=source,
            output=AnnDataOutput(),
        )
    except (RuleDetectionError, NoCompatibleLevelError) as error:
        return _discovery_error(
            error,
            action="No APB2 parsing rule matches the fixture",
            status=CapabilityStatus.UNSUPPORTED,
            parameter_slug=parameter_slug,
        )
    except (KeyError, OSError, ParamsError, ValueError) as error:
        return _discovery_error(
            error,
            action="Could not inspect the fixture with APB2",
            status=CapabilityStatus.FAILED,
            parameter_slug=parameter_slug,
        )
    return CapabilityDiscovery(
        branches=(MUDATA, *(parser.level for parser in parsers)),
        software_slug=detected.software,
        software_version=detected.version,
        parameter_software_slug=parameter_slug,
    )


def _rule_fingerprint() -> tuple[tuple[str, int, int], ...]:
    root = Path(str(resources.files(_RULE_PACKAGE)))
    fingerprint = []
    for path in sorted(root.rglob("rules.json")):
        stat_result = path.stat()
        fingerprint.append((str(path), stat_result.st_mtime_ns, stat_result.st_size))
    return tuple(fingerprint)


def _discovery_error(
    error: Exception,
    /,
    *,
    action: str,
    status: CapabilityStatus,
    parameter_slug: str,
) -> CapabilityDiscovery:
    detail = str(error).strip()
    message = type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"
    diagnostic = f"{action}: {message}"
    logger.debug(diagnostic)
    return CapabilityDiscovery(
        branches=(),
        diagnostic=diagnostic,
        status=status,
        parameter_software_slug=parameter_slug,
    )
