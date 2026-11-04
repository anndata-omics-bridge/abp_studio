"""Copy the rules viewer and one apb2 rules bundle into a folder a plain file server serves."""

from __future__ import annotations

import shutil
from pathlib import Path

MANIFEST_NAME = "manifest.json"
"""The file that makes a folder an apb2 rules bundle; the viewer loads it first."""


def require_bundle(bundle: Path) -> Path:
    """Return ``bundle`` when it holds an apb2 rules bundle.

    Raises:
        ValueError: The folder holds no ``manifest.json``.
    """
    if not (bundle / MANIFEST_NAME).is_file():
        raise ValueError(f"No rules bundle in {bundle}: run `make rules-bundle` in apb2")
    return bundle


def publish_site(bundle: Path, web_root: Path, site: Path) -> None:
    """Copy the viewer into ``site`` and the bundle into ``site/data``, where the viewer reads it.

    Raises:
        ValueError: ``site`` is not empty, or ``bundle`` holds no bundle.
    """
    if site.exists() and any(site.iterdir()):
        raise ValueError(f"Publish into an empty folder: {site}")
    require_bundle(bundle)
    shutil.copytree(web_root, site, dirs_exist_ok=True)
    shutil.copytree(bundle, site / "data")
