"""Validated JSON configuration services for the APB Studio editor."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Literal

from anndata_proteomics.rules.loader import (
    parse_rule_source,
    validate_rule_source,
)
from anndata_proteomics.rules.registry import (
    document_vendor,
    iter_packaged_documents,
)
from pydantic import ValidationError

ConfigKind = Literal["rule"]


class ConfigSaveError(ValueError):
    """Raised when a configuration cannot safely be written."""

    def __init__(self, message: str, *, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report


def content_hash(text: str) -> str:
    """Return a stable hash used for optimistic write protection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def catalog_rows() -> list[dict[str, Any]]:
    """Describe each packaged software-version rule document once."""
    rows: list[dict[str, Any]] = []
    for path in iter_packaged_documents():
        source = path.read_text(encoding="utf-8")
        report = validate_source(path, source)
        raw = parse_rule_source(source, path=path) if report["valid"] else {}
        rows.append(
            {
                "vendor": document_vendor(path),
                "software_name": raw.get("software_name", document_vendor(path)),
                "software_version": raw.get("software_version", ""),
                "file_version": raw.get("file_version", ""),
                "levels": list(raw.get("levels", {})),
                "valid": report["valid"],
                "path": str(path.resolve()),
            }
        )
    return rows


def load_document(path: Path | str, *, kind: ConfigKind = "rule") -> dict[str, Any]:
    """Load one document as independently viewable raw JSON sections."""
    resolved = _checked_json_path(path)
    source = resolved.read_text(encoding="utf-8")
    report = validate_source(resolved, source, kind=kind)

    raw = parse_rule_source(source, path=resolved)
    sections = {"base": _pretty_json(raw["base"])}
    sections.update((level, _pretty_json(fragment)) for level, fragment in raw["levels"].items())
    labels = {"base": "Base", **{level: level.title() for level in raw["levels"]}}

    return {
        "path": str(resolved),
        "kind": kind,
        "source": source,
        "content_hash": content_hash(source),
        "sections": sections,
        "section_order": list(sections),
        "section_labels": labels,
        **report,
    }


def validate_source(
    path: Path | str,
    source: str,
    *,
    kind: ConfigKind = "rule",
) -> dict[str, Any]:
    """Validate a complete unsaved document through APB's Pydantic models."""
    resolved = Path(path).expanduser().resolve()
    try:
        raw = parse_rule_source(source, path=resolved)
        document = validate_rule_source(raw, path=resolved)
        affected = list(document.levels)
    except ValueError as exc:
        return {"valid": False, "issues": _issues_from_exception(exc), "affected": []}
    return {"valid": True, "issues": [], "affected": affected}


def validate_section(
    path: Path | str,
    section: str,
    section_source: str,
    *,
    document_source: str,
    kind: ConfigKind = "rule",
) -> dict[str, Any]:
    """Validate one edited section in the context of its complete document."""
    resolved = Path(path).expanduser().resolve()
    affected: list[str] = []
    try:
        candidate, affected = _candidate_with_section(
            resolved,
            section,
            section_source,
            document_source=document_source,
            kind=kind,
        )
        raw = parse_rule_source(candidate, path=resolved)
        validate_rule_source(raw, path=resolved)
    except ValueError as exc:
        return {
            "valid": False,
            "issues": _issues_from_exception(exc),
            "affected": affected,
        }
    return {"valid": True, "issues": [], "affected": affected}


def format_json_source(source: str, *, kind: ConfigKind) -> str:
    """Return canonical, two-space-indented complete JSON after validation."""
    data = parse_rule_source(source)
    return _pretty_json(data)


def format_section_source(source: str) -> str:
    """Format a section after requiring it to be a JSON object."""
    data = parse_rule_source(source, path="<editor section>")
    return _pretty_json(data)


def save_section(
    path: Path | str,
    section: str,
    section_source: str,
    *,
    document_source: str,
    expected_hash: str,
    kind: ConfigKind = "rule",
) -> dict[str, Any]:
    """Validate and atomically save one section as part of its full document."""
    resolved = _checked_json_path(path)
    current = resolved.read_text(encoding="utf-8")
    if content_hash(current) != expected_hash:
        raise ConfigSaveError(
            f"{resolved} changed on disk after it was loaded; reload before saving"
        )
    candidate, _ = _candidate_with_section(
        resolved,
        section,
        section_source,
        document_source=document_source,
        kind=kind,
    )
    report = validate_source(resolved, candidate, kind=kind)
    if not report["valid"]:
        raise ConfigSaveError("configuration is invalid", report=report)
    canonical = format_json_source(candidate, kind=kind)
    _atomic_write(resolved, canonical)
    return load_document(resolved, kind=kind)


def save_document(
    path: Path | str,
    source: str,
    *,
    expected_hash: str,
    kind: ConfigKind = "rule",
) -> dict[str, Any]:
    """Validate and atomically save a complete JSON document."""
    resolved = _checked_json_path(path)
    current = resolved.read_text(encoding="utf-8")
    if content_hash(current) != expected_hash:
        raise ConfigSaveError(
            f"{resolved} changed on disk after it was loaded; reload before saving"
        )
    report = validate_source(resolved, source, kind=kind)
    if not report["valid"]:
        raise ConfigSaveError("configuration is invalid", report=report)
    _atomic_write(resolved, format_json_source(source, kind=kind))
    return load_document(resolved, kind=kind)


def _candidate_with_section(
    path: Path,
    section: str,
    section_source: str,
    *,
    document_source: str,
    kind: ConfigKind,
) -> tuple[str, list[str]]:
    """Replace one raw source section and serialize the candidate document."""
    document = parse_rule_source(document_source, path=path)
    fragment = parse_rule_source(section_source, path=f"{path}#{section}")
    levels = document.get("levels")
    if not isinstance(levels, dict):
        raise ValueError("document has no levels object")
    if section == "base":
        document["base"] = fragment
        affected = list(levels)
    elif section in levels:
        levels[section] = fragment
        affected = [section]
    else:
        raise ValueError(f"unknown rule section {section!r}")
    return json.dumps(document), affected


def _checked_json_path(path: Path | str) -> Path:
    """Resolve an existing JSON file path or raise a user-facing error."""
    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.lower() != ".json":
        raise ValueError(f"configuration must be a .json file: {resolved}")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _issues_from_exception(exc: Exception) -> list[dict[str, str]]:
    """Convert syntax and Pydantic exceptions to JSON-path issues."""
    document = _exception_document(exc)
    if isinstance(exc, ValidationError):
        return [
            {
                "document": document,
                "path": _json_path(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
    if isinstance(exc, json.JSONDecodeError):
        return [
            {
                "document": document,
                "path": f"line {exc.lineno}, column {exc.colno}",
                "message": exc.msg,
                "type": "json_syntax",
            }
        ]
    return [
        {
            "document": document,
            "path": "$",
            "message": str(exc),
            "type": type(exc).__name__,
        }
    ]


def _exception_document(exc: Exception) -> str:
    """Extract the source document attached by APB's configuration loaders."""
    for note in getattr(exc, "__notes__", ()):
        if note.startswith("in "):
            context = note.removeprefix("in ")
            if "; level:" in context:
                document, level = context.split("; level:", maxsplit=1)
                return f"{document}#{level.strip()}"
            return context
    return ""


def _json_path(location: tuple[Any, ...]) -> str:
    """Render a Pydantic error location as a compact JSON path."""
    result = "$"
    for part in location:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _pretty_json(data: Any) -> str:
    """Serialize JSON consistently for display and storage."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    """Write text beside the target and atomically replace the target."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode))
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
