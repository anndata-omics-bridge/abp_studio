"""``index.json``: where the store's files are, written by the script that changed it.

It names the tables, the FASTAs, and the URL pattern of a submission's
own ``summary.json``. It does not list which submissions are downloaded: the viewer asks
for each summary by name, and its presence is the answer. So a submission that lands
mid-run needs no listing to be refreshed, and the server needs no directory walk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apb_studio.fixture_store import SUMMARY_URL_PATTERN, TABLE_NAMES, Store

STORE_VERSION = 1


def _tree_bytes(directory: Path) -> int:
    """Sum the size of every file below a directory, 0 when it does not exist."""
    if not directory.is_dir():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def build(store: Store) -> dict[str, Any]:
    """Describe what the store holds, as the viewer's starting document."""
    tables = [
        {
            "name": name,
            "url": name,
            "sizeBytes": (store.root / name).stat().st_size,
            "modifiedNs": (store.root / name).stat().st_mtime_ns,
        }
        for name in TABLE_NAMES
        if (store.root / name).is_file()
    ]
    fasta = (
        sorted(p.name for p in store.fasta_dir.glob("*.fasta")) if store.fasta_dir.is_dir() else []
    )
    return {
        "storeVersion": STORE_VERSION,
        "root": str(store.root),
        "tables": tables,
        "submissionSummary": SUMMARY_URL_PATTERN,
        "fasta": fasta,
        "bytes": {
            "metadata": _tree_bytes(store.metadata_dir),
            "fasta": _tree_bytes(store.fasta_dir),
        },
    }


def write(store: Store) -> Path:
    """Write ``index.json`` into the store, returning the path written."""
    store.root.mkdir(parents=True, exist_ok=True)
    store.index_json.write_text(json.dumps(build(store), indent=1), encoding="utf-8")
    return store.index_json
