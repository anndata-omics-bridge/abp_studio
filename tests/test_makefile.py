"""The Makefile owns development gates, not the corpus application lifecycle."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_application_lifecycle_is_owned_by_python_entry_points() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "corpus-run:",
        "corpus-run-all:",
        "corpus-routine:",
        "corpus-clean:",
        "corpus-clean-all:",
        "corpus-viewer:",
        "corpus-export:",
        "fixture-manager:",
    ):
        assert target not in makefile
    assert "apb-studio-fixtures" not in makefile
    assert "corpus select" not in makefile
