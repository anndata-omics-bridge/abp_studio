"""Load the stage catalogue and the pipeline selections that draw from it."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

_CONFIG = Path(__file__).resolve().parent / "config"
REGISTRY_PATH = _CONFIG / "registry.yaml"
PIPELINES_PATH = _CONFIG / "pipelines"

DEFAULT_PIPELINE = "full"
"""The default APB2 → FASTA-check → aggregate → ProteoBench workflow."""


def load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    """Return the ordered list of stage definitions from the registry YAML."""
    return yaml.safe_load(path.read_text())["stages"]


class PipelineDocument(BaseModel):
    """One pipeline YAML: which converters a run exercises, and which catalogue stages.

    A selection, never a definition: stage commands, dependencies, and resources stay in the
    catalogue so the two cannot drift.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    converters: tuple[str, ...]
    stages: tuple[str, ...]


def available_pipelines(directory: Path = PIPELINES_PATH) -> tuple[str, ...]:
    """Return every loadable pipeline name, sorted."""
    return tuple(sorted(path.stem for path in directory.glob("*.yaml")))


def load_pipeline_document(name: str, directory: Path = PIPELINES_PATH) -> PipelineDocument:
    """Return one pipeline document by name, validating its shape."""
    path = directory / f"{name}.yaml"
    if not path.is_file():
        known = ", ".join(available_pipelines(directory))
        raise ValueError(f"Unknown pipeline {name!r}; available pipelines are: {known}")
    document = PipelineDocument.model_validate(yaml.safe_load(path.read_text()))
    if document.name != name:
        raise ValueError(f"Pipeline {path} declares name {document.name!r}, expected {name!r}")
    return document
