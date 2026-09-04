"""Tests for APB2 capability discovery."""

from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apb_studio import capabilities
from apb_studio.capabilities import CapabilityStatus, discover_capabilities


@pytest.fixture(autouse=True)
def _clear_cache() -> Generator[None]:
    capabilities._cached_capability_discovery.cache_clear()
    yield
    capabilities._cached_capability_discovery.cache_clear()


def _files(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "report.tsv"
    params = tmp_path / "parameters.txt"
    data.write_text("Precursor.Id\nPEPTIDE\n")
    params.write_text("DIA-NN 1.9\n")
    return data, params


def _successful_apb2(
    monkeypatch: pytest.MonkeyPatch,
    *,
    levels: tuple[str, ...] = ("ion", "protein"),
) -> None:
    parameters = object()
    document = SimpleNamespace(levels=levels)
    detected = SimpleNamespace(document=document, software="diann", version="1.9")
    monkeypatch.setattr(capabilities, "parse_params", lambda *_args, **_kwargs: parameters)
    monkeypatch.setattr(capabilities, "detect_rule_document", lambda *_args: detected)
    monkeypatch.setattr(capabilities, "search_parameter_evidence", lambda value: value)
    monkeypatch.setattr(
        capabilities,
        "compile_parsers",
        lambda **_kwargs: tuple(SimpleNamespace(level=level) for level in levels),
    )
    monkeypatch.setattr(capabilities, "_rule_fingerprint", lambda: (("rules.json", 1, 1),))


def test_discovery_returns_mudata_then_apb2_levels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    _successful_apb2(monkeypatch)

    discovered = discover_capabilities(data, params, "DIA-NN")

    assert discovered.branches == ("mudata", "ion", "protein")
    assert discovered.status is CapabilityStatus.SUPPORTED
    assert discovered.software_slug == "diann"
    assert discovered.software_version == "1.9"
    assert discovered.parameter_software_slug == "diann"


def test_compound_software_uses_parameter_parser_slug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    seen: dict[str, object] = {}
    _successful_apb2(monkeypatch, levels=("ion",))

    def parse(path: Path, *, software: str) -> object:
        seen.update(path=path, software=software)
        return object()

    monkeypatch.setattr(capabilities, "parse_params", parse)
    discovered = discover_capabilities(data, params, "FragPipe")
    assert seen == {"path": params.resolve(), "software": "fragpipe"}
    assert discovered.parameter_software_slug == "fragpipe"


def test_missing_fixture_file_is_unsupported(tmp_path: Path) -> None:
    discovered = discover_capabilities(
        tmp_path / "missing.tsv",
        tmp_path / "missing.params",
        "DIA-NN",
    )
    assert discovered.branches == ()
    assert discovered.status is CapabilityStatus.UNSUPPORTED
    assert "Required fixture file is unavailable" in (discovered.diagnostic or "")


def test_rule_detection_failure_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    monkeypatch.setattr(capabilities, "_rule_fingerprint", lambda: ())
    monkeypatch.setattr(capabilities, "parse_params", lambda *_args, **_kwargs: object())

    def fail(*_args: object) -> None:
        raise capabilities.RuleDetectionError("no matching rules")

    monkeypatch.setattr(capabilities, "detect_rule_document", fail)
    discovered = discover_capabilities(data, params, "DIA-NN")
    assert discovered.status is CapabilityStatus.UNSUPPORTED
    assert "No APB2 parsing rule matches" in (discovered.diagnostic or "")


def test_parameter_parser_failure_is_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    monkeypatch.setattr(capabilities, "_rule_fingerprint", lambda: ())

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError("malformed parameters")

    monkeypatch.setattr(capabilities, "parse_params", fail)
    discovered = discover_capabilities(data, params, "DIA-NN")
    assert discovered.status is CapabilityStatus.FAILED
    assert "Could not inspect the fixture with APB2" in (discovered.diagnostic or "")


def test_cache_reuses_unchanged_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    _successful_apb2(monkeypatch, levels=("ion",))
    calls = 0
    original = capabilities.compile_parsers

    def counted(**kwargs: Any):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(capabilities, "compile_parsers", counted)
    assert discover_capabilities(data, params, "DIA-NN").branches == ("mudata", "ion")
    assert discover_capabilities(data, params, "DIA-NN").branches == ("mudata", "ion")
    assert calls == 1


def test_cache_invalidates_when_input_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    _successful_apb2(monkeypatch, levels=("ion",))
    calls = 0
    original = capabilities.compile_parsers

    def counted(**kwargs: Any):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(capabilities, "compile_parsers", counted)
    discover_capabilities(data, params, "DIA-NN")
    data.write_text("Precursor.Id\nPEPTIDE\nOTHER\n")
    discover_capabilities(data, params, "DIA-NN")
    assert calls == 2


def test_cache_invalidates_when_rules_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data, params = _files(tmp_path)
    _successful_apb2(monkeypatch, levels=("ion",))
    fingerprint = iter([(("rules.json", 1, 1),), (("rules.json", 2, 1),)])
    monkeypatch.setattr(capabilities, "_rule_fingerprint", lambda: next(fingerprint))
    calls = 0
    original = capabilities.compile_parsers

    def counted(**kwargs: Any):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(capabilities, "compile_parsers", counted)
    discover_capabilities(data, params, "DIA-NN")
    discover_capabilities(data, params, "DIA-NN")
    assert calls == 2
