"""Headless corpus execution and a static JavaScript viewer."""

from __future__ import annotations

import errno
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Literal
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import psutil
from cyclopts import App, Parameter
from loguru import logger

from apb_studio.corpus.clean import archive_results
from apb_studio.corpus.discovery import SNAKEFILE, workflow_table_name, workflow_tools
from apb_studio.corpus.models import ExecutionSettings, Operation, StorageFormat, write_record
from apb_studio.corpus.runs import (
    dataset_alias,
    prepare_run,
    publish_catalog,
    save_execution_settings,
    select_datasets,
)
from apb_studio.corpus.tables import CORPUS_COLUMNS, load_corpus, write_rows
from apb_studio.disk import atomic_write_text, interprocess_file_lock
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.routes import VIEWER_IDENTITY_PATH, viewer_identity
from apb_studio.fixture_viewer.server import build_server
from apb_studio.settings import load_settings

app = App(name="apb-studio-corpus")

VIEWER_HOST = "127.0.0.1"
VIEWER_PORT = 8766
VIEWER_WEB_ROOT = Path(__file__).parents[1] / "corpus_viewer" / "web"

type ViewerStatus = Literal["matching", "other", "absent"]


def _resolve_executable(executable: Path | None, command: str, option: str) -> Path:
    path = executable or Path(shutil.which(command) or command)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"{command} is not on PATH; pass --{option} /path/to/{command}")
    return path.resolve()


# Which CLI override flag feeds which executable. The workflow decides *which* tools it
# needs; this table only says how a user can override each one by hand.
_EXECUTABLE_OPTIONS = {
    "apb2": ("apb_executable", "apb-executable"),
    "apb-aggregate": ("aggregate_executable", "aggregate-executable"),
    "apb-fasta": ("fasta_executable", "fasta-executable"),
    "apb-proteobench": ("proteobench_executable", "proteobench-executable"),
}


def resolve_tools(options: RunOptions) -> dict[str, Path]:
    """Resolve exactly the executables the chosen workflow declares in its TOOLS tuple."""
    resolved: dict[str, Path] = {}
    for tool in workflow_tools(options.workflow):
        if tool not in _EXECUTABLE_OPTIONS:
            raise ValueError(f"No override option is defined for the executable {tool!r}")
        field, option = _EXECUTABLE_OPTIONS[tool]
        resolved[tool] = _resolve_executable(getattr(options, field), tool, option)
    return resolved


def _tool_overrides(tools: Mapping[str, Path]) -> dict[str, Path]:
    """Map already-resolved tool paths back onto the override fields that carry them."""
    return {_EXECUTABLE_OPTIONS[tool][0]: path for tool, path in tools.items()}


@dataclass(frozen=True, slots=True)
class RunOptions:
    """One invocation's settings, shared by both command entry points."""

    corpus: Path | None = None
    data_root: Path | None = None
    workflow: str = "convert"
    storage_format: Annotated[StorageFormat, Parameter(name="--format")] = "hdf5"
    workflow_table: Path | None = None
    downloads: Path | None = None
    apb_executable: Path | None = None
    aggregate_executable: Path | None = None
    fasta_executable: Path | None = None
    proteobench_executable: Path | None = None
    output_root: Path | None = None
    datasets: Path | None = None
    fixtures: int = 0
    cores: int = 10
    dry_run: bool = False
    force: bool = False


DEFAULT_OPTIONS = RunOptions()


def _execution_settings(options: RunOptions) -> ExecutionSettings:
    """Resolve source paths independently of the corpus CSV's own directory."""
    settings = load_settings()
    corpus = (options.corpus or settings.test_data_root.parent / "corpuses" / "all.csv").resolve()
    data_root = (options.data_root or settings.test_data_root).resolve()
    tools = resolve_tools(options)
    table_name = workflow_table_name(options.workflow)
    default_table = Path("workflow_tables") / table_name
    requested_table = options.workflow_table or (default_table if default_table.is_file() else None)
    table = requested_table.resolve() if requested_table is not None else None
    if table is not None and table.name != table_name:
        raise ValueError(f"Expected {table_name}, got {table.name}")
    return ExecutionSettings(
        corpus=corpus,
        data_root=data_root,
        workflow=options.workflow,
        format=options.storage_format,
        workflow_table=table,
        downloads=(
            options.downloads.resolve()
            if options.downloads is not None
            else (data_root / "downloads.csv" if (data_root / "downloads.csv").is_file() else None)
        ),
        tools=tools,
        cores=options.cores,
        datasets=options.datasets.resolve() if options.datasets is not None else None,
        fixtures=options.fixtures,
    )


@app.command
def configure(options: Annotated[RunOptions, Parameter(name="*")] = DEFAULT_OPTIONS) -> None:
    """Save selectable execution settings and CSV previews without starting a run."""
    settings = _execution_settings(options)
    select_datasets(load_corpus(settings.corpus), settings.datasets, settings.fixtures)
    root = (options.output_root or load_settings().output_root).resolve() / "corpus"
    _, path = save_execution_settings(root, settings)
    publish_catalog(root)
    logger.info("Execution settings: {}", path)


@app.command
def run(options: Annotated[RunOptions, Parameter(name="*")] = DEFAULT_OPTIONS) -> None:
    """Schedule a workflow over existing corpus files and stream the scheduler log."""
    execution = _execution_settings(options)
    rows = select_datasets(load_corpus(execution.corpus), execution.datasets, execution.fixtures)
    root, _ = prepare_run(
        rows,
        output_root=options.output_root or load_settings().output_root,
        settings=execution,
    )
    for row in rows:
        logger.info("{} / {}", row.module, dataset_alias(row))
    logger.info("Run files: {}", root)
    with interprocess_file_lock(root / "run.lock"):
        publish_catalog(root.parent)
        _schedule(root, cores=options.cores, dry_run=options.dry_run, force=options.force)


@app.command
def select(*, corpus: Path, datasets: Path, output: Path) -> None:
    """Write a named corpus CSV from an explicit selection, without running APB."""
    rows = select_datasets(load_corpus(corpus), datasets, 0)
    write_rows(output, CORPUS_COLUMNS, [row.model_dump() for row in rows])
    logger.info("Written {} datasets to {}", len(rows), output.resolve())


@app.command
def execute(
    execution_settings: Path,
    *,
    output_root: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Execute an explicitly saved settings JSON without reconstructing its CLI flags."""
    settings = ExecutionSettings.model_validate_json(execution_settings.read_text())
    run(
        replace(
            RunOptions(
                corpus=settings.corpus,
                data_root=settings.data_root,
                workflow=settings.workflow,
                storage_format=settings.format,
                workflow_table=settings.workflow_table,
                downloads=settings.downloads,
                cores=settings.cores,
                datasets=settings.datasets,
                fixtures=settings.fixtures,
                output_root=output_root,
                dry_run=dry_run,
                force=force,
            ),
            **_tool_overrides(settings.tools),
        )
    )


def _schedule(root: Path, *, cores: int, dry_run: bool, force: bool) -> None:
    command = [
        sys.executable,
        "-m",
        "snakemake",
        "--snakefile",
        str(SNAKEFILE),
        "--configfile",
        str(root / "run.json"),
        "--cores",
        str(cores),
        "--directory",
        str(root),
        "--rerun-incomplete",
    ]
    if dry_run:
        command.append("--dry-run")
    if force:
        command.append("--forceall")
    if not dry_run:
        if force:
            archived = archive_results(root)
            logger.info("Previous results preserved in {}", archived)
        write_record(root / "operation.json", Operation(status="running"))
    try:
        log_name = "dry-run.log" if dry_run else "snakemake.log"
        code = _stream_scheduler(command, root / log_name)
    except BaseException:
        if not dry_run:
            write_record(root / "operation.json", Operation(status="interrupted"))
        raise
    if not dry_run:
        write_record(
            root / "operation.json",
            Operation(
                status="succeeded" if code == 0 else "failed",
                exit_code=code,
            ),
        )
    if code:
        raise SystemExit(code)


def _stream_scheduler(command: list[str], log_path: Path) -> int:
    """Stream scheduler output and stop its process group on interruption."""
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                log.write(line)
                log.flush()
            return process.wait()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


def _viewer_root(output_root: Path | None) -> Path:
    return (output_root or load_settings().output_root).resolve() / "corpus"


def _viewer_url(port: int) -> str:
    return f"http://{VIEWER_HOST}:{port}/"


def _viewer_pid_path(root: Path, port: int) -> Path:
    return root / f"viewer-{port}.pid"


def _viewer_status(root: Path, port: int) -> ViewerStatus:
    """Identify whether the port serves this exact corpus store and viewer."""
    expected = viewer_identity(VIEWER_WEB_ROOT, Store(root))
    try:
        identity_url = f"{_viewer_url(port)}{VIEWER_IDENTITY_PATH}"
        with urlopen(identity_url, timeout=0.5) as response:
            if response.status != 200:
                return "other"
            return "matching" if response.read(len(expected) + 1) == expected else "other"
    except HTTPError:
        return "other"
    except (OSError, URLError):
        return "absent"


def _viewer_process(pid_path: Path, port: int) -> psutil.Process | None:
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        process = psutil.Process(pid)
        command = process.cmdline()
        connections = process.net_connections(kind="tcp")
    except (OSError, ValueError, psutil.Error):
        pid_path.unlink(missing_ok=True)
        return None
    is_viewer = any(Path(part).name == "apb-studio-corpus" for part in command) and any(
        action in command for action in ("serve", "restart")
    )
    owns_listener = any(
        connection.status == psutil.CONN_LISTEN
        and connection.laddr.ip == VIEWER_HOST
        and connection.laddr.port == port
        for connection in connections
    )
    if not is_viewer or not owns_listener:
        pid_path.unlink(missing_ok=True)
        return None
    return process


@app.command
def serve(*, output_root: Path | None = None, port: int = VIEWER_PORT) -> None:
    """Serve persisted runs and the JavaScript corpus viewer on localhost."""
    root = _viewer_root(output_root)
    root.mkdir(parents=True, exist_ok=True)
    url = _viewer_url(port)
    status = _viewer_status(root, port)
    if status == "matching":
        logger.info("Corpus viewer already running: {}", url)
        return
    if status == "other":
        raise SystemExit(f"Cannot start corpus viewer: {url} serves another viewer or store")
    try:
        server = build_server(Store(root), VIEWER_HOST, port, web_root=VIEWER_WEB_ROOT)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        if _viewer_status(root, port) == "matching":
            logger.info("Corpus viewer already running: {}", url)
            return
        raise SystemExit(
            f"Cannot start corpus viewer: {url} serves another service or store"
        ) from None
    pid_path = _viewer_pid_path(root, port)
    atomic_write_text(pid_path, f"{os.getpid()}\n")
    logger.info("Corpus viewer: {}", url)
    logger.info("Press Ctrl-C or run `make corpus-viewer-shutdown` to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Corpus viewer stopped")
    finally:
        server.server_close()
        try:
            owns_pid_file = pid_path.read_text(encoding="utf-8").strip() == str(os.getpid())
        except OSError:
            owns_pid_file = False
        if owns_pid_file:
            pid_path.unlink(missing_ok=True)


@app.command
def shutdown(*, output_root: Path | None = None, port: int = VIEWER_PORT) -> None:
    """Stop the corpus viewer recorded for this output root."""
    root = _viewer_root(output_root)
    pid_path = _viewer_pid_path(root, port)
    status = _viewer_status(root, port)
    process = _viewer_process(pid_path, port)
    if status != "matching":
        if process is not None:
            raise SystemExit(
                f"Refusing to stop corpus viewer PID {process.pid}: "
                f"{_viewer_url(port)} does not serve the requested output root"
            )
        if status == "other":
            logger.info("Corpus viewer is not running; the port serves another viewer or service")
        else:
            logger.info("Corpus viewer is not running")
        return
    if process is None:
        raise SystemExit(
            f"Corpus viewer is running at {_viewer_url(port)}, but its PID was not recorded"
        )
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
    except psutil.TimeoutExpired as error:
        raise SystemExit(f"Corpus viewer PID {process.pid} did not stop") from error
    pid_path.unlink(missing_ok=True)
    logger.info("Corpus viewer stopped")


@app.command
def restart(*, output_root: Path | None = None, port: int = VIEWER_PORT) -> None:
    """Stop the managed corpus viewer, then serve it again."""
    shutdown(output_root=output_root, port=port)
    serve(output_root=output_root, port=port)


def main() -> None:
    """Run the corpus command-line application."""
    app()


if __name__ == "__main__":
    main()
