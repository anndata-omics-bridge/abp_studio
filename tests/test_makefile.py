"""Tests for developer lifecycle targets."""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_variable_reaches_every_corpus_target() -> None:
    for target, expected in (
        ("corpus-run", "run_corpus.py --pipeline apb2-convert"),
        ("corpus-check", "run_corpus.py --pipeline apb2-convert"),
        ("corpus-clean", "clean_corpus.py --pipeline apb2-convert"),
    ):
        rendered = subprocess.run(
            ["make", "--dry-run", target, "CORPUS_PIPELINE=apb2-convert"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert expected in rendered, target


def test_routine_gate_names_its_fixtures_and_run_defaults_to_the_whole_corpus() -> None:
    routine = subprocess.run(
        ["make", "--dry-run", "corpus-routine"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    whole = subprocess.run(
        ["make", "--dry-run", "corpus-run"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "--datasets selections/routine.txt" in routine
    # No sample: the default runs everything the pipeline covers.
    assert "--fixtures 0" in whole
    assert (PROJECT_ROOT / "selections" / "routine.txt").is_file()
