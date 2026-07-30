"""Tests for the JSON configuration editor backend."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from anndata_proteomics.rules.registry import find_rule

from apb_studio import config_editor
from apb_studio.config_panel import configuration_panel


def _copy_rule_document(tmp_path: Path) -> Path:
    source = find_rule("wombat", "peptidoform").path
    target = tmp_path / "rules.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_catalog_lists_one_row_per_software_version_document() -> None:
    rows = config_editor.catalog_rows()
    assert len(rows) == 9
    assert all(row["valid"] for row in rows)
    assert sum(row["vendor"] == "diann" for row in rows) == 2
    assert next(row for row in rows if row["vendor"] == "spectronaut")["levels"] == [
        "ion",
        "fragment",
        "protein",
    ]


def test_load_document_exposes_base_and_raw_level_sections() -> None:
    path = find_rule("diann", "protein", "1.9.2").path
    loaded = config_editor.load_document(path)
    assert loaded["section_order"] == ["base", "ion", "fragment", "protein"]
    assert json.loads(loaded["sections"]["base"])["input_shape"] == "long"
    protein = json.loads(loaded["sections"]["protein"])
    assert "software_name" not in protein
    assert protein["axis"]["x_layer"] == "PG_MaxLFQ"


def test_invalid_json_reports_syntax_location(tmp_path: Path) -> None:
    path = _copy_rule_document(tmp_path)
    loaded = config_editor.load_document(path)
    report = config_editor.validate_section(
        path,
        "base",
        '{"broken": }',
        document_source=loaded["source"],
    )
    assert report["valid"] is False
    assert report["issues"][0]["type"] == "json_syntax"
    assert "line" in report["issues"][0]["path"]


def test_invalid_level_reports_effective_pydantic_error(tmp_path: Path) -> None:
    path = _copy_rule_document(tmp_path)
    loaded = config_editor.load_document(path)
    level = json.loads(loaded["sections"]["peptidoform"])
    level["axis"]["x_layer"] = "missing"
    report = config_editor.validate_section(
        path,
        "peptidoform",
        json.dumps(level),
        document_source=loaded["source"],
    )
    assert report["valid"] is False
    assert any("x_layer" in issue["message"] for issue in report["issues"])


def test_candidate_base_validates_every_level() -> None:
    path = find_rule("diann", "ion", "1.9.2").path
    loaded = config_editor.load_document(path)
    base = json.loads(loaded["sections"]["base"])
    base.pop("input_shape")
    report = config_editor.validate_section(
        path,
        "base",
        json.dumps(base),
        document_source=loaded["source"],
    )
    assert report["valid"] is False
    assert any(issue["path"] == "$.input_shape" for issue in report["issues"])
    assert report["issues"][0]["document"].endswith("rules.json#ion")


def test_save_section_is_canonical_and_atomic(tmp_path: Path) -> None:
    path = _copy_rule_document(tmp_path)
    path.chmod(0o640)
    loaded = config_editor.load_document(path)
    base = json.loads(loaded["sections"]["base"])
    base["axis"]["duplicates"]["mode"] = "keep_first"
    saved = config_editor.save_section(
        path,
        "base",
        json.dumps(base),
        document_source=loaded["source"],
        expected_hash=loaded["content_hash"],
    )
    document = json.loads(path.read_text())
    assert document["base"]["axis"]["duplicates"]["mode"] == "keep_first"
    assert path.read_text().endswith("\n")
    assert saved["content_hash"] == config_editor.content_hash(path.read_text())
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_save_rejects_invalid_section_without_writing(tmp_path: Path) -> None:
    path = _copy_rule_document(tmp_path)
    loaded = config_editor.load_document(path)
    before = path.read_text()
    with pytest.raises(config_editor.ConfigSaveError, match="invalid"):
        config_editor.save_section(
            path,
            "base",
            "{}",
            document_source=loaded["source"],
            expected_hash=loaded["content_hash"],
        )
    assert path.read_text() == before


def test_save_rejects_stale_browser_copy(tmp_path: Path) -> None:
    path = _copy_rule_document(tmp_path)
    loaded = config_editor.load_document(path)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(config_editor.ConfigSaveError, match="changed on disk"):
        config_editor.save_section(
            path,
            "base",
            loaded["sections"]["base"],
            document_source=loaded["source"],
            expected_hash=loaded["content_hash"],
        )


def test_configuration_panel_has_one_read_only_json_editor_and_no_effective_view() -> None:
    panel = configuration_panel()
    components = _components(panel)
    by_id = {
        component.to_plotly_json()["props"]["id"]: component
        for component in components
        if isinstance(component.to_plotly_json()["props"].get("id"), str)
    }
    editor_props = by_id["config-section-editor"].to_plotly_json()["props"]
    assert editor_props["language"] == "json"
    assert editor_props["readOnly"] is True
    assert "config-effective-editor" not in by_id
    assert by_id["config-edit"].to_plotly_json()["props"]["disabled"] is True
    assert by_id["config-save"].to_plotly_json()["props"]["disabled"] is True


def _components(component: Any) -> Iterator[Any]:
    """Yield a Dash component tree depth-first."""
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    items = children if isinstance(children, list | tuple) else [children]
    for child in items:
        if hasattr(child, "to_plotly_json"):
            yield from _components(child)
