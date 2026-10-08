"""Named corpus configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path

from apb_studio.disk import atomic_write_text

DEFAULT_CORPUSES: dict[str, str] = {
    "directlfq": "corpuses/directlfq.csv",
    "proteobench": "corpuses/proteobench.csv",
    "proteobench_entrapment": "corpuses/proteobench_entrapment.csv",
    "proteobench_plasma": "corpuses/proteobench_plasma.csv",
    "routine": "corpuses/routine.csv",
}
CORPUS_NAME_PATTERN = r"^[a-z][a-z0-9_-]*$"


def config_path(test_data_root: Path) -> Path:
    """Return the corpus config beside the fixture and inventory directories."""
    return test_data_root.parent / "corpuses.json"


def load_corpuses(source: Path) -> dict[str, Path]:
    """Load configured corpus names and resolve their CSV paths."""
    document = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not document:
        raise ValueError(f"Corpus config must be a non-empty JSON object: {source}")
    corpuses: dict[str, Path] = {}
    for name, value in sorted(document.items()):
        if (
            not isinstance(name, str)
            or re.fullmatch(CORPUS_NAME_PATTERN, name) is None
            or not isinstance(value, str)
            or not value
        ):
            raise ValueError(f"Corpus names must be path-safe and paths non-empty: {source}")
        target = Path(value).expanduser()
        corpuses[name] = (target if target.is_absolute() else source.parent / target).resolve()
    return corpuses


def ensure_config(source: Path) -> None:
    """Create the default named-corpus config when acquisition has none."""
    if source.exists():
        return
    atomic_write_text(source, f"{json.dumps(DEFAULT_CORPUSES, indent=2, sort_keys=True)}\n")
