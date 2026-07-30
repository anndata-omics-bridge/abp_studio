"""Tests for developer lifecycle targets."""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_corpus_runner_make_targets_restart_and_stop_by_port() -> None:
    restart = subprocess.run(
        ["make", "--dry-run", "corpus-runner", "APP_PORT=49151"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    stop = subprocess.run(
        ["make", "--dry-run", "corpus-runner-stop", "APP_PORT=49151"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "lsof -tiTCP:49151" in restart
    assert "Refusing to stop PID" in restart
    assert "VIRTUAL_ENV= APB_STUDIO_PORT=49151" in restart
    assert "exec apb-studio-corpus-runner" in restart
    assert "kill -INT" in stop
    assert ".apb-studio-corpus-runner-49151.pid" in stop
