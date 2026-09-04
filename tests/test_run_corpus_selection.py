"""Selection reading for the headless runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _script() -> ModuleType:
    """Import scripts/run_corpus.py, which is a script rather than a package module."""
    spec = importlib.util.spec_from_file_location(
        "run_corpus_script", PROJECT_ROOT / "scripts" / "run_corpus.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dataset_file_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    selection = tmp_path / "sel.txt"
    selection.write_text(
        "# a comment\n"
        "\n"
        "diann-300beac4   # trailing note\n"
        "  Results_quant_ion_DDA/sage-05906d50  \n"
        "   \n",
        encoding="utf-8",
    )

    assert _script().read_dataset_names(selection) == [
        "diann-300beac4",
        "Results_quant_ion_DDA/sage-05906d50",
    ]


def test_the_packaged_routine_selection_is_readable() -> None:
    names = _script().read_dataset_names(PROJECT_ROOT / "selections" / "routine.txt")

    assert len(names) >= 8
    assert all("/" in name for name in names)
