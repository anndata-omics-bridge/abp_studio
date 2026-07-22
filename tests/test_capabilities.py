"""Tests for shared APB conversion-capability discovery."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from apb_studio import capabilities


def test_discovery_reads_version_and_headers_and_puts_mudata_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.tsv"
    input_path.write_text("\ufeffRun\tPrecursor.Id\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("version details\n", encoding="utf-8")
    calls: list[tuple[str, str | None, tuple[str, ...]]] = []

    def fake_parse_params(path: str, *, software: str) -> SimpleNamespace:
        assert path == str(parameter_path)
        assert software == "diann"
        return SimpleNamespace(software_version="2.1")

    def fake_available_targets(
        slug: str,
        version: str | None,
        headers: tuple[str, ...],
    ) -> list[str]:
        calls.append((slug, version, headers))
        return ["ion", "protein", "mudata"]

    monkeypatch.setattr(
        capabilities.parameter_registry,
        "parse_params",
        fake_parse_params,
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "available_targets",
        fake_available_targets,
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

    monkeypatch.setattr(
        capabilities.parameter_registry,
        "parse_params",
        lambda *_args, **_kwargs: SimpleNamespace(software_version="1"),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "available_software",
        lambda: ["software"],
    )

    def fake_available_targets(
        _slug: str,
        _version: str | None,
        headers: tuple[str, ...],
    ) -> list[str]:
        headers_seen.append(headers)
        return ["ion", "mudata"]

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "available_targets",
        fake_available_targets,
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

    monkeypatch.setattr(
        capabilities,
        "_parsing_rule_fingerprint",
        lambda: tuple(fingerprint),
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "recognize_software",
        lambda _headers: "software",
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "available_software",
        lambda: ["software"],
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "parse_params",
        lambda *_args, **_kwargs: SimpleNamespace(software_version="1"),
    )

    def fake_available_targets(*_args: object) -> list[str]:
        nonlocal target_calls
        target_calls += 1
        return [] if target_calls == 1 else ["ion"]

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "available_targets",
        fake_available_targets,
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

    monkeypatch.setattr(
        capabilities.parameter_registry,
        "parse_params",
        lambda *_args, **_kwargs: SimpleNamespace(software_version=None),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "available_software",
        lambda: ["software"],
    )

    def fake_available_targets(
        _slug: str,
        _version: str | None,
        headers: tuple[str, ...],
    ) -> list[str]:
        headers_seen.append(headers)
        return ["protein", "mudata"]

    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "available_targets",
        fake_available_targets,
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
        capabilities.parameter_registry,
        "parse_params",
        fail_parse,
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN",
    )

    assert result.branches == ()
    assert result.status is capabilities.CapabilityStatus.BLOCKED
    assert result.diagnostic == (
        "Capability discovery failed: ValueError: invalid parameter file"
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
    assert result.status is capabilities.CapabilityStatus.BLOCKED
    assert result.diagnostic is not None
    assert "FileNotFoundError" in result.diagnostic
    assert "missing.tsv" in result.diagnostic


def test_discovery_explains_when_no_rule_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input_file.txt"
    input_path.write_text("Mystery\n", encoding="utf-8")
    parameter_path = tmp_path / "param_0.txt"
    parameter_path.write_text("params\n", encoding="utf-8")
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "parse_params",
        lambda *_args, **_kwargs: SimpleNamespace(software_version="3"),
    )
    monkeypatch.setattr(
        capabilities.parameter_registry,
        "available_software",
        lambda: ["unknowntool"],
    )
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "available_targets",
        lambda *_args, **_kwargs: [],
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
        "No APB parsing rule matches software 'unknowntool', version '3', "
        "and the input headers."
    )


def test_discovery_treats_unregistered_software_as_unsupported(
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

    monkeypatch.setattr(
        capabilities.parameter_registry, "parse_params", unexpected_parse
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


def test_discovery_prefers_header_recognition_over_compound_catalog_label(
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
        lambda _headers: "spectronaut",
    )

    def fake_parse(_path: str, *, software: str) -> SimpleNamespace:
        parsed_with.append(software)
        return SimpleNamespace(software_version="19")

    monkeypatch.setattr(capabilities.parameter_registry, "parse_params", fake_parse)
    monkeypatch.setattr(
        capabilities.conversion_pipeline,
        "available_targets",
        lambda *_args: ["ion"],
    )

    result = capabilities.discover_capabilities(
        input_path,
        parameter_path,
        "DIA-NN / Spectronaut",
    )

    assert parsed_with == ["spectronaut"]
    assert result.software_slug == "spectronaut"
    assert result.software_version == "19"
