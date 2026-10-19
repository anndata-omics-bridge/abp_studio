"""Named corpora: the hand-curated files in ``corpuses/``, named by their file stem."""

from __future__ import annotations

import re
from pathlib import Path

CORPUS_NAME_PATTERN = r"^[a-z][a-z0-9_-]*$"
ALL = "all"
"""The reserved corpus name meaning every downloaded dataset; no file defines it."""


def corpus_dir(test_data_root: Path) -> Path:
    """Return the directory of corpus files beside the fixture store."""
    return test_data_root.parent / "corpuses"


def corpus_files(directory: Path) -> dict[str, Path]:
    """Map each corpus name to its file in ``directory``, sorted by name.

    Raises:
        ValueError: A file is named ``all.csv`` or its stem is not a path-safe corpus name.
    """
    files: dict[str, Path] = {}
    for path in sorted(directory.glob("*.csv")):
        if path.stem == ALL or re.fullmatch(CORPUS_NAME_PATTERN, path.stem) is None:
            raise ValueError(f"Corpus file names must be path-safe and not {ALL!r}: {path}")
        files[path.stem] = path.resolve()
    return files
