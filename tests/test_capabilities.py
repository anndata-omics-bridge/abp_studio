"""Tests for shared APB conversion-capability discovery."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from anndata_proteomics.params.model import Parameters
from anndata_proteomics.rules.schema import QuantificationLevel

from apb_studio import capabilities


def _resolution(
    parameter_path: Path,
    parameters: Parameters,
) -> capabilities.conversion_pipeline.ParameterResolution:
    """Build the typed APB result returned by a parameter-resolution test double."""
    software_version = parameters.software_version
    version: capabilities.conversion_pipeline.RuleVersion = (
        capabilities.conversion_pipeline.MissingRuleVersion()
        if software_version is None
        else capabilities.conversion_pipeline.PresentRuleVersion(software_version)
    )
    return capabilities.conversion_pipeline.ParameterResolution(
        source_path=parameter_path,
        parameters=parameters,
        version=version,
    )


def _selections(
    *levels: QuantificationLevel,
) -> dict[QuantificationLevel, object]:
    """Return selection-shaped keys; capability discovery only consumes the keys."""
    return {level: object() for level in levels}


def test_discovery_reads_version_and_headers_and_puts_mudata_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("\ufeffRun\tPrecursor.Id\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("version details\n", encoding="utf-8")
    calls: list[tuple[str, str | None, tuple[str, ...]]] = []

    def fake_resolve_parameters(
        path: Path | str,
        slug: str,
    ) -> capabilities.conversion_pipeline.ParameterResolution:
        assert Path(path) == parameter_path
        assert slug == "diann"
        return _resolution(
            parameter_path,
            Parameters(software_name="DIA-NN", software_version="2.1"),
        )

    def fake_select_rules(
        headers: tuple[str, ...],
        slug: str,
        resolution: capabilities.conversion_pipeline.ParameterResolution,
    ) -> dict[QuantificationLevel, object]:
        version = capabilities.conversion_pipeline.resolve_rule_version(resolution, slug)
        assert isinstance(version, capabilities.conversion_pipeline.PresentRuleVersion)
        calls.append((slug, version.value, headers))
        return _selections("ion", "protein")

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        fake_resolve_parameters,
    )
    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        fake_select_rules,
    )

    first = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )
    second = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert first == capabilities.CapabilityDiscovery(
        ("mudata", "ion", "protein"),
        software_slug="diann",
        software_version="2.1",
        parameter_software_slug="diann",
    )
    assert second == first
    assert calls == [("diann", "2.1", ("Run", "Precursor.Id"))]


def test_discovery_cache_invalidates_when_input_mtime_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.csv"
    input_path.write_text("first\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    headers_seen: list[tuple[str, ...]] = []

    monkeypatch.setattr(capabilities, "_has_packaged_rule_document", lambda _name: True)
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        lambda _path, _slug: _resolution(
            parameter_path,
            Parameters(software_name="software", software_version="1"),
        ),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "recognize_parser",
        lambda _name: capabilities.parameter_registry.RecognizedParameterParser("diann"),
    )

    def fake_select_rules(
        headers: tuple[str, ...],
        _slug: str,
        _resolution: capabilities.conversion_pipeline.ParameterResolution,
    ) -> dict[QuantificationLevel, object]:
        headers_seen.append(headers)
        return _selections("ion")

    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        fake_select_rules,
    )

    capabilities.discover_capabilities(input_path, parameter_path, "software")
    old_mtime_ns = input_path.stat().st_mtime_ns
    input_path.write_text("second\n", encoding="utf-8")
    os.utime(input_path, ns=(old_mtime_ns + 1, old_mtime_ns + 1))
    capabilities.discover_capabilities(input_path, parameter_path, "software")

    assert headers_seen == [("first",), ("second",)]


def test_discovery_cache_invalidates_when_packaged_rules_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Run\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    fingerprint = [("rules.json", 1, 10)]
    target_calls = 0

    monkeypatch.setattr(capabilities, "_has_packaged_rule_document", lambda _name: True)
    monkeypatch.setattr(
        capabilities,
        "_parsing_rule_fingerprint",
        lambda: tuple(fingerprint),
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "recognize_software",
        lambda _headers: capabilities.conversion_pipeline.RecognizedSoftware("software"),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "recognize_parser",
        lambda _name: capabilities.parameter_registry.RecognizedParameterParser("diann"),
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        lambda _path, _slug: _resolution(
            parameter_path,
            Parameters(software_name="software", software_version="1"),
        ),
    )

    def fake_select_rules(
        _headers: tuple[str, ...],
        _slug: str,
        _resolution: capabilities.conversion_pipeline.ParameterResolution,
    ) -> dict[QuantificationLevel, object]:
        nonlocal target_calls
        target_calls += 1
        return {} if target_calls == 1 else _selections("ion")

    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        fake_select_rules,
    )

    first = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "software",
    )
    fingerprint[0] = ("rules.json", 2, 10)
    second = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "software",
    )

    assert first.status is capabilities.CapabilityStatus.UNSUPPORTED
    assert second.branches == ("mudata", "ion")
    assert target_calls == 2


def test_discovery_reads_parquet_schema_without_loading_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.parquet"
    pd.DataFrame({"Run": ["run-1"], "Protein.Group": ["P1"]}).to_parquet(
        input_path,
        index=False,
    )
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    headers_seen: list[tuple[str, ...]] = []

    monkeypatch.setattr(capabilities, "_has_packaged_rule_document", lambda _name: True)
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        lambda _path, _slug: _resolution(
            parameter_path,
            Parameters(software_name="software"),
        ),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "recognize_parser",
        lambda _name: capabilities.parameter_registry.RecognizedParameterParser("diann"),
    )

    def fake_select_rules(
        headers: tuple[str, ...],
        _slug: str,
        _resolution: capabilities.conversion_pipeline.ParameterResolution,
    ) -> dict[QuantificationLevel, object]:
        headers_seen.append(headers)
        return _selections("protein")

    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        fake_select_rules,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "software",
    )

    assert result.branches == ("mudata", "protein")
    assert headers_seen == [("Run", "Protein.Group")]


def test_discovery_returns_diagnostic_instead_of_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Run\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("invalid\n", encoding="utf-8")

    def fail_parse(*_args: object, **_kwargs: object) -> None:
        raise ValueError("invalid parameter file")

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        fail_parse,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert result.branches == ()
    assert result.status is capabilities.CapabilityStatus.FAILED
    assert result.diagnostic == (
        "Could not read the parameter file: ValueError: invalid parameter file"
    )


def test_discovery_reports_a_missing_input(tmp_path: Path) -> None:
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")

    result = capabilities.discover_capabilities(
        tmp_path / "missing.tsv",
        parameter_path,
        "DIA-NN",
    )

    assert result.branches == ()
    assert result.status is capabilities.CapabilityStatus.UNSUPPORTED
    assert result.diagnostic is not None
    assert "FileNotFoundError" in result.diagnostic
    assert "missing.tsv" in result.diagnostic


def test_discovery_reports_rule_inspection_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Run\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")

    def fail_fingerprint() -> tuple[tuple[str, int, int], ...]:
        raise RuntimeError("rule registry unavailable")

    monkeypatch.setattr(capabilities, "_parsing_rule_fingerprint", fail_fingerprint)

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert result.status is capabilities.CapabilityStatus.FAILED
    assert result.diagnostic == (
        "Could not inspect packaged parsing rules: RuntimeError: rule registry unavailable"
    )


def test_discovery_reports_software_recognition_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Run\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")

    def fail_recognition(
        _headers: tuple[str, ...],
    ) -> capabilities.conversion_pipeline.SoftwareRecognition:
        raise ValueError("invalid header schema")

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "recognize_software",
        fail_recognition,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert result.status is capabilities.CapabilityStatus.FAILED
    assert result.diagnostic == (
        "Could not recognize the input software: ValueError: invalid header schema"
    )


def test_discovery_reports_rule_matching_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Run\tPrecursor.Id\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        lambda _path, _slug: _resolution(
            parameter_path,
            Parameters(software_name="DIA-NN", software_version="2.1"),
        ),
    )

    def fail_matching(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        raise ValueError("invalid rule document")

    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        fail_matching,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert result.status is capabilities.CapabilityStatus.FAILED
    assert result.software_slug == "diann"
    assert result.software_version == "2.1"
    assert result.diagnostic == (
        "Could not match APB parsing rules: ValueError: invalid rule document"
    )


def test_discovery_explains_when_no_rule_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.txt"
    input_path.write_text("Mystery\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    monkeypatch.setattr(capabilities, "_has_packaged_rule_document", lambda _name: True)
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "recognize_software",
        lambda _headers: capabilities.conversion_pipeline.RecognizedSoftware("unknowntool"),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "recognize_parser",
        lambda _name: capabilities.parameter_registry.RecognizedParameterParser("diann"),
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        lambda _path, _slug: _resolution(
            parameter_path,
            Parameters(software_name="Unknown Tool", software_version="3"),
        ),
    )
    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        lambda *_args, **_kwargs: {},
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "Unknown Tool",
    )

    assert result.branches == ()
    assert result.status is capabilities.CapabilityStatus.UNSUPPORTED
    assert result.software_slug == "unknowntool"
    assert result.software_version == "3"
    assert result.diagnostic == (
        "No APB parsing rule matches software 'unknowntool', version '3', and the input headers."
    )


def test_discovery_marks_software_without_rules_unsupported_before_reading_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "missing-input.xlsx"
    parameter_path = tmp_path / "missing-params.json"
    header_read = False
    parse_called = False

    def unexpected_header_read(_path: Path) -> list[str]:
        nonlocal header_read
        header_read = True
        return []

    def unexpected_parse(*_args: object, **_kwargs: object) -> None:
        nonlocal parse_called
        parse_called = True

    monkeypatch.setattr(capabilities, "read_table_columns", unexpected_header_read)
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        unexpected_parse,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "MSAngel",
    )

    assert not header_read
    assert not parse_called
    assert result.status is capabilities.CapabilityStatus.UNSUPPORTED
    assert result.software_slug == "msangel"
    assert result.software_version is None
    assert result.diagnostic == (
        "APB has no packaged parsing-rule document for software 'msangel'; "
        "this software is unsupported."
    )


def test_comma_delimited_txt_headers_are_detected_not_assumed_tab(tmp_path: Path) -> None:
    """A `.txt` is not necessarily TSV.

    AlphaPept and some PEAKS exports ship comma-delimited `.txt`. Reading them as TSV
    yields one column, so header matching fails and the fixture reports UNSUPPORTED even
    with a correct parsing rule. Delegating to APB's reader content-detects the delimiter,
    so the capability probe and the conversion path agree.
    """
    input_path = tmp_path / "input_file.txt"
    input_path.write_text("sequence,charge,protein\nPEPTIDE,2,P1\n", encoding="utf-8")

    assert tuple(capabilities.read_table_columns(input_path)) == (
        "sequence",
        "charge",
        "protein",
    )


def test_discovery_reports_a_malformed_supported_input_as_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_bytes(b"\xff\xfe")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    parse_called = False

    def unexpected_parse(*_args: object, **_kwargs: object) -> None:
        nonlocal parse_called
        parse_called = True

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        unexpected_parse,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert not parse_called
    assert result.status is capabilities.CapabilityStatus.FAILED
    assert result.software_slug is None
    assert result.software_version is None
    assert result.diagnostic is not None
    assert result.diagnostic.startswith("Could not read input table headers: UnicodeDecodeError:")


def test_discovery_treats_missing_parameter_parser_as_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Unknown.Column\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    parse_called = False

    def unexpected_parse(*_args: object, **_kwargs: object) -> None:
        nonlocal parse_called
        parse_called = True

    monkeypatch.setattr(capabilities, "_has_packaged_rule_document", lambda _name: True)
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "recognize_parser",
        lambda _name: capabilities.parameter_registry.UnrecognizedParameterParser(),
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        unexpected_parse,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "AlphaDIA",
    )

    assert not parse_called
    assert result.status is capabilities.CapabilityStatus.UNSUPPORTED
    assert result.software_slug == "alphadia"
    assert result.software_version is None
    assert result.diagnostic is not None
    assert "no parameter parser" in result.diagnostic


def test_discovery_separates_compound_parameter_and_rule_software(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("Recognized\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    parsed_with: list[str] = []

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "recognize_software",
        lambda _headers: capabilities.conversion_pipeline.RecognizedSoftware("diann"),
    )

    def fake_resolve_parameters(
        path: Path | str,
        slug: str,
    ) -> capabilities.conversion_pipeline.ParameterResolution:
        parsed_with.append(slug)
        return _resolution(
            Path(path),
            Parameters(
                software_name="FragPipe",
                software_version="24.0",
                quantification_software="DIA-NN",
                quantification_software_version="1.8.2 beta 8",
            ),
        )

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "resolve_parameters",
        fake_resolve_parameters,
    )
    monkeypatch.setattr(
        capabilities.conversion_workflow,
        "select_rules_from_parameters",
        lambda *_args, **_kwargs: _selections("ion"),
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "FragPipe (DIA-NN quant)",
    )

    assert parsed_with == ["fragpipe"]
    assert result.software_slug == "diann"
    assert result.software_version == "1.8.2 beta 8"
    assert result.parameter_software_slug == "fragpipe"
