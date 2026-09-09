"""Run linear subprocess steps and publish progress independently of Snakemake."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TextIO

import psutil

from apb_studio.corpus.models import DatasetReport, StepResult, utc_now, write_record

SAMPLE_SECONDS = 0.1
PROGRESS_SECONDS = 0.5
LIVE_LOG_CHARACTERS = 16_384


def _sample(pid: int) -> int:
    process = psutil.Process(pid)
    total = 0
    for child in [process, *process.children(recursive=True)]:
        try:
            total += child.memory_info().rss
        except psutil.NoSuchProcess:
            continue
    return total


def _drain(stream: TextIO, destination: TextIO, captured: list[str]) -> None:
    text = stream.read()
    if text:
        captured.append(text)
        destination.write(text)
        destination.flush()


def _observe(
    process: subprocess.Popen[bytes],
    step: StepResult,
    report: DatasetReport,
    progress_path: Path,
    logs: tuple[TextIO, TextIO],
) -> None:
    started = time.monotonic()
    published = 0.0
    stdout: list[str] = []
    stderr: list[str] = []
    previous_runtime = report.runtime_seconds
    while True:
        _drain(logs[0], sys.stdout, stdout)
        _drain(logs[1], sys.stderr, stderr)
        try:
            rss = _sample(process.pid)
            step.peak_memory_bytes = max(step.peak_memory_bytes or 0, rss)
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied as error:
            message = f"Memory measurement unavailable: {error}"
            if message not in step.warnings:
                step.warnings.append(message)
        elapsed = time.monotonic() - started
        if elapsed - published >= PROGRESS_SECONDS:
            step.runtime_seconds = elapsed
            report.runtime_seconds = previous_runtime + elapsed
            step.stdout = "".join(stdout)[-LIVE_LOG_CHARACTERS:]
            step.stderr = "".join(stderr)[-LIVE_LOG_CHARACTERS:]
            write_record(progress_path, report)
            published = elapsed
        if process.poll() is not None:
            break
        time.sleep(SAMPLE_SECONDS)
    _drain(logs[0], sys.stdout, stdout)
    _drain(logs[1], sys.stderr, stderr)
    step.stdout = "".join(stdout)
    step.stderr = "".join(stderr)
    step.exit_code = process.wait()


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Stop the APB process group if the wrapper is interrupted or reporting fails."""
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _check_files(step: StepResult) -> None:
    for artifact in step.inputs:
        if not artifact.path.exists():
            step.errors.append(f"Missing input: {artifact.path}")
        else:
            artifact.size_bytes = _path_size(artifact.path)
    if step.errors:
        return
    for artifact in step.outputs:
        artifact.path.parent.mkdir(parents=True, exist_ok=True)
        if artifact.path.exists():
            step.errors.append(f"Output already exists; refusing stale result: {artifact.path}")


def _execute(step: StepResult, report: DatasetReport, progress_path: Path) -> None:
    _check_files(step)
    if step.errors:
        return
    with tempfile.TemporaryDirectory(prefix="apb-step-") as folder:
        out_path, err_path = Path(folder) / "stdout", Path(folder) / "stderr"
        with out_path.open("wb") as out, err_path.open("wb") as err:
            try:
                process = subprocess.Popen(
                    step.command,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
            except OSError as error:
                step.errors.append(f"Cannot start APB command: {error}")
                return
            try:
                with (
                    out_path.open(encoding="utf-8", errors="replace") as stdout,
                    err_path.open(encoding="utf-8", errors="replace") as stderr,
                ):
                    _observe(process, step, report, progress_path, (stdout, stderr))
            finally:
                _terminate(process)
    if step.exit_code != 0:
        step.errors.append(f"APB command exited with code {step.exit_code}")
    for artifact in step.outputs:
        if artifact.path.exists():
            artifact.size_bytes = _path_size(artifact.path)
        else:
            step.errors.append(f"Declared output was not written: {artifact.path}")


def _path_size(path: Path) -> int:
    """Measure a file or the recursive file contents of a directory artifact."""
    if path.is_file():
        return path.stat().st_size
    return sum(candidate.stat().st_size for candidate in path.rglob("*") if candidate.is_file())


def run_steps(report: DatasetReport, report_path: Path) -> None:
    """Publish APB failures as data; propagate errors of the reporting framework."""
    names = [step.name for step in report.steps]
    if not names or len(names) != len(set(names)):
        raise ValueError("Workflow requires uniquely named steps")
    started = time.monotonic()
    progress_path = report_path.with_suffix(".progress.json")
    report_path.unlink(missing_ok=True)
    write_record(progress_path, report)
    failed = ""
    for step in report.steps:
        if failed:
            step.status = "skipped"
            step.errors = [f"Skipped after failed step: {failed}"]
            continue
        step.status = "running"
        step.started_at = utc_now()
        step_start = time.monotonic()
        write_record(progress_path, report)
        _execute(step, report, progress_path)
        step.runtime_seconds = time.monotonic() - step_start
        step.finished_at = utc_now()
        step.status = "failed" if step.errors else "succeeded"
        if step.errors:
            failed = step.name
        report.runtime_seconds = time.monotonic() - started
        write_record(progress_path, report)
    report.status = "failed" if failed else "succeeded"
    report.finished_at = utc_now()
    report.runtime_seconds = time.monotonic() - started
    write_record(report_path, report)
    write_record(progress_path, report)
