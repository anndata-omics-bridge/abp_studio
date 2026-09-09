"""Artifact declarations shared by the concrete corpus workflows."""

from __future__ import annotations

from pathlib import Path

from apb_studio.corpus.models import Artifact

REPRESENTATION_SUFFIX = ".apb.json"


def representation(path: Path, /) -> Artifact:
    """Declare the APB JSON sidecar emitted beside one scientific result."""
    return Artifact(
        role="representation",
        path=path.with_name(f"{path.name}{REPRESENTATION_SUFFIX}"),
    )
