"""The packaged ProteoBench fetch configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from apb_studio.proteobench_config import PACKAGED, load_config, packaged_config

MINIMAL = """
schema_version = 1
datasets_base_url = "https://example.invalid/datasets/"
settings_revision = "abc123"
settings_root = "https://example.invalid/{revision}/settings"
fasta_urls = ["https://example.invalid/one.zip"]

[[modules]]
name = "dda_qexactive"
repo_url = "https://github.com/Proteobench/Results_quant_ion_DDA/archive/refs/heads/main.zip"
settings_path = "DDA/ion/QExactive/module_settings.toml"
fasta = "mix.fasta"
"""


def test_the_packaged_configuration_covers_every_module() -> None:
    config = packaged_config()
    assert config.schema_version == 1
    assert len(config.modules) == 8
    assert config.module_names[0] == "dda_qexactive"
    assert packaged_config() is config, "read once"
    for name in config.module_names:
        assert config.settings_url(name).startswith("https://raw.githubusercontent.com/")
        assert config.settings_revision in config.settings_url(name)
        assert config.fasta_for_module(name).endswith(".fasta")
    assert config.fasta_for_module("dia_singlecell").endswith("noecoli.fasta")
    assert config.module("dia_aif").repo_name == "Results_quant_ion_DIA_AIF"
    assert len(config.fasta_urls) == 2


def test_a_module_the_configuration_does_not_declare_is_an_error() -> None:
    with pytest.raises(KeyError):
        packaged_config().module("no_such_module")


def test_an_override_file_replaces_the_packaged_one(tmp_path: Path) -> None:
    path = tmp_path / "proteobench.toml"
    path.write_text(MINIMAL, encoding="utf-8")
    config = load_config(path)
    assert config.module_names == ("dda_qexactive",)
    assert config.settings_url("dda_qexactive") == (
        "https://example.invalid/abc123/settings/DDA/ion/QExactive/module_settings.toml"
    )


def test_a_malformed_configuration_is_refused(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.toml"
    block = MINIMAL[MINIMAL.index("[[modules]]") :]
    duplicate.write_text(MINIMAL + block, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate module name"):
        load_config(duplicate)

    empty = tmp_path / "empty.toml"
    empty.write_text(MINIMAL.replace(block, ""), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(empty)

    unknown = tmp_path / "unknown.toml"
    unknown.write_text(MINIMAL + '\nunexpected_key = "x"\n', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(unknown)

    bad_name = tmp_path / "bad_name.toml"
    bad_name.write_text(
        MINIMAL.replace('name = "dda_qexactive"', 'name = "Bad Name"'), encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_config(bad_name)


def test_the_packaged_file_ships_beside_the_code() -> None:
    assert PACKAGED.is_file()
    assert PACKAGED.parent.name == "config"
