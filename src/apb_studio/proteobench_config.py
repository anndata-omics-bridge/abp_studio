"""What the fixture store fetches from ProteoBench, read from a packaged TOML.

The module list, the results-repository URLs and the reference FASTAs are ProteoBench's
facts, not this package's behaviour, so they live in
``config/proteobench.toml`` and are validated here. An override path lets a caller point at
a different ProteoBench snapshot without editing the package.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

PACKAGED = Path(__file__).parent / "config" / "proteobench.toml"


class ModuleConfig(BaseModel):
    """One ProteoBench module: where its submissions and FASTA come from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    repo_url: str = Field(min_length=1)
    fasta: str = Field(min_length=1)
    corpus: str = Field(default="all", pattern=r"^[a-z][a-z0-9_-]*$")

    @property
    def repo_name(self) -> str:
        """Return the results-repository name the submission paths are keyed by."""
        return self.repo_url.split("/")[-5]


class ProteoBenchConfig(BaseModel):
    """The complete fetch configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    datasets_base_url: str = Field(min_length=1)
    fasta_urls: tuple[str, ...] = Field(min_length=1)
    modules: tuple[ModuleConfig, ...] = Field(min_length=1)

    @property
    def module_names(self) -> tuple[str, ...]:
        """Return every configured module name, in file order."""
        return tuple(module.name for module in self.modules)

    def module(self, name: str) -> ModuleConfig:
        """Return one module's configuration.

        Raises:
            KeyError: No module is configured under that name.
        """
        for module in self.modules:
            if module.name == name:
                return module
        raise KeyError(name)

    def fasta_for_module(self, name: str) -> str:
        """Return the extracted FASTA file name one module uses."""
        return self.module(name).fasta

    @property
    def corpus_names(self) -> tuple[str, ...]:
        """Return every corpus the modules are exported into, in file order."""
        return tuple(dict.fromkeys(module.corpus for module in self.modules))

    def modules_in(self, corpus: str) -> frozenset[str]:
        """Return the names of the modules exported into one corpus."""
        return frozenset(module.name for module in self.modules if module.corpus == corpus)


def load_config(path: Path | None = None) -> ProteoBenchConfig:
    """Load and validate the fetch configuration.

    Args:
        path: A TOML file to read instead of the packaged one.

    Returns:
        The validated configuration.

    Raises:
        ValueError: A module name is declared twice.
    """
    source = path if path is not None else PACKAGED
    with source.open("rb") as handle:
        config = ProteoBenchConfig.model_validate(tomllib.load(handle))
    names = config.module_names
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate module name in {source}")
    return config


@lru_cache(maxsize=1)
def packaged_config() -> ProteoBenchConfig:
    """Return the packaged configuration, read once."""
    return load_config()
