"""Tests for developer lifecycle targets."""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_workflow_variable_reaches_every_corpus_target() -> None:
    for target, expected in (
        ("corpus-run", "run_corpus.py --workflow convert --format duckdb"),
        ("corpus-check", "run_corpus.py --workflow convert --format duckdb"),
    ):
        rendered = subprocess.run(
            ["make", "--dry-run", target, "CORPUS_WORKFLOW=convert", "CORPUS_FORMAT=duckdb"],
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

    assert "--corpus corpuses/routine.csv" in routine
    assert "--corpus corpuses/all.csv" in whole
    # No sample: the default runs everything the pipeline covers.
    assert "--fixtures 0" in whole
    assert (PROJECT_ROOT / "selections" / "routine.txt").is_file()


def test_corpus_viewer_lifecycle_targets_reach_the_cli() -> None:
    for target, command in (
        ("corpus-viewer", "apb-studio-corpus serve"),
        ("corpus-viewer-shutdown", "apb-studio-corpus shutdown"),
        ("corpus-viewer-restart", "apb-studio-corpus restart"),
    ):
        rendered = subprocess.run(
            ["make", "--dry-run", target],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert command in rendered
