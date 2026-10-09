"""Copy the corpus viewer and its saved runs into one folder a plain file server serves."""

from __future__ import annotations

import shutil
from pathlib import Path

from apb_studio.corpus.catalog import build_catalog
from apb_studio.corpus.runs import publish_catalog

_LOCAL_ONLY = shutil.ignore_patterns(".snakemake", "run.lock")
"""Scheduler state and locks, which only the machine that ran the corpus needs."""


def publish_site(store: Path, web_root: Path, site: Path) -> list[Path]:
    """Copy the viewer into ``site`` and every visible run of ``store`` into ``site/data``.

    The fixture store is not copied: the server serves it beside them as ``site/fixtures``.
    Returns the copied run folders.
    """
    if site.exists() and any(site.iterdir()):
        raise ValueError(f"Publish into an empty folder: {site}")
    shutil.copytree(web_root, site, dirs_exist_ok=True)
    data = site / "data"
    data.mkdir()
    runs: list[str] = build_catalog(store)["runs"]
    copied: list[Path] = []
    for manifest in runs:
        relative = Path(manifest).parent
        shutil.copytree(store / relative, data / relative, ignore=_LOCAL_ONLY)
        copied.append(data / relative)
    publish_catalog(data)
    return copied
