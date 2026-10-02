"""Headless corpus execution and a static JavaScript viewer."""

from __future__ import annotations

import errno
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Literal
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import psutil
from cyclopts import App, Parameter
from loguru import logger

from apb_studio.corpus.clean import archive_results, delete_run, saved_run_roots
from apb_studio.corpus.config import config_path, load_corpuses
from apb_studio.corpus.discovery import (
    SNAKEFILE,
    available_workflows,
    workflow_table_name,
    workflow_tools,
)
from apb_studio.corpus.models import ExecutionSettings, Operation, StorageFormat, write_record
from apb_studio.corpus.runs import (
    dataset_alias,
    prepare_run,
    publish_catalog,
    select_datasets,
)
from apb_studio.corpus.tables import load_corpus
from apb_studio.corpus_viewer.routes import resolve as resolve_corpus_viewer
from apb_studio.disk import atomic_write_text, interprocess_file_lock
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.routes import VIEWER_IDENTITY_PATH, viewer_identity
from apb_studio.fixture_viewer.server import build_server
from apb_studio.settings import load_settings, settings_path

app = App(
    name="corpus",
    help="Run, view, and clean APB corpus workflows",
    help_on_error=True,
)
run_app = App(
    name="run",
    help="Run one workflow over a configured corpus",
    help_on_error=True,
)
view_app = App(
    name="view",
    help="Start or restart the corpus viewer; use `stop` to stop it",
    help_on_error=True,
)
app.command(run_app)
app.command(view_app)

VIEWER_HOST = "127.0.0.1"
VIEWER_PORT = 8766
VIEWER_WEB_ROOT = Path(__file__).parents[1] / "corpus_viewer" / "web"

type ViewerStatus = Literal["matching", "other", "absent"]


def _resolve_executable(executable: Path | None, command: str, option: str) -> Path:
    path = executable or Path(shutil.which(command) or command)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"{command} is not on PATH; pass --{option} /path/to/{command}")
    return path.resolve()


# The workflow decides which tools it needs. These package-internal fields also let tests
# inject exact executable paths without expanding the public command surface.
_EXECUTABLE_OPTIONS = {
    "apb2": ("apb_executable", "apb-executable"),
    "apb-aggregate": ("aggregate_executable", "aggregate-executable"),
    "apb-fasta": ("fasta_executable", "fasta-executable"),
    "apb-proteobench": ("proteobench_executable", "proteobench-executable"),
    "multiqc": ("multiqc_executable", "multiqc-executable"),
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


@dataclass(frozen=True, slots=True)
class RunOptions:
    """Complete package-internal options used to resolve one execution."""

    corpus: Annotated[
        Path | None,
        Parameter(name="--corpus", help="Override the scope's corpus CSV"),
    ] = None
    data_root: Annotated[
        Path | None,
        Parameter(name="--data-root", help="Root for paths recorded in corpus and workflow CSVs"),
    ] = None
    workflow: Annotated[
        str,
        Parameter(name="--workflow", help="Packaged workflow name"),
    ] = "convert"
    storage_format: Annotated[
        StorageFormat,
        Parameter(name="--format", help="One format passed through every APB step"),
    ] = "hdf5"
    workflow_table: Annotated[
        Path | None,
        Parameter(name="--workflow-table", help="Override the selected workflow_NAME.csv"),
    ] = None
    downloads: Annotated[
        Path | None,
        Parameter(name="--downloads", help="Optional downloads.csv for input-size metadata"),
    ] = None
    apb_executable: Annotated[
        Path | None,
        Parameter(name="--apb-executable", help="Override the apb2 executable"),
    ] = None
    aggregate_executable: Annotated[
        Path | None,
        Parameter(name="--aggregate-executable", help="Override the apb-aggregate executable"),
    ] = None
    fasta_executable: Annotated[
        Path | None,
        Parameter(name="--fasta-executable", help="Override the apb-fasta executable"),
    ] = None
    proteobench_executable: Annotated[
        Path | None,
        Parameter(name="--proteobench-executable", help="Override the apb-proteobench executable"),
    ] = None
    multiqc_executable: Annotated[
        Path | None,
        Parameter(name="--multiqc-executable", help="Override the MultiQC executable"),
    ] = None
    output_root: Annotated[
        Path | None,
        Parameter(name="--output-root", help="Override the configured APB Studio output root"),
    ] = None
    datasets: Annotated[
        Path | None,
        Parameter(name="--datasets", help="Optional text file selecting corpus rows"),
    ] = None
    fixtures: Annotated[
        int,
        Parameter(name="--fixtures", help="Sample N software-balanced rows; 0 keeps all"),
    ] = 0
    cores: Annotated[
        int,
        Parameter(name="--cores", help="Maximum parallel Snakemake jobs"),
    ] = 10
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Show scheduled jobs without running them"),
    ] = False
    force: Annotated[
        bool,
        Parameter(name="--force", help="Archive current results and rerun every dataset"),
    ] = False


@dataclass(frozen=True, slots=True)
class ImmediateRunOptions:
    """Execution controls shared by every named-corpus run."""

    workflow: Annotated[
        str,
        Parameter(name="--workflow", help="Packaged workflow name"),
    ] = "convert"
    storage_format: Annotated[
        StorageFormat,
        Parameter(name="--format", help="Format passed through every APB step"),
    ] = "hdf5"
    cores: Annotated[
        int,
        Parameter(name="--cores", help="Maximum parallel Snakemake jobs"),
    ] = 10
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Show scheduled jobs without running them"),
    ] = False
    force: Annotated[
        bool,
        Parameter(name="--force", help="Archive current results and rerun every dataset"),
    ] = False


DEFAULT_IMMEDIATE_OPTIONS = ImmediateRunOptions()


def _options_for_corpus(name: str, options: RunOptions, /) -> RunOptions:
    """Resolve a configured inventory unless the caller supplied an explicit CSV."""
    if options.corpus is not None:
        return options
    source = config_path(load_settings().test_data_root)
    corpuses = load_corpuses(source)
    if name not in corpuses:
        raise ValueError(
            f"Unknown corpus {name!r}; available: {', '.join(corpuses)}; config: {source}"
        )
    return replace(options, corpus=corpuses[name])


def _run_help() -> str:
    """Describe configured corpuses and packaged workflows for command help."""
    source = config_path(load_settings().test_data_root)
    try:
        corpuses = load_corpuses(source)
    except (OSError, ValueError) as error:
        corpus_section = f"Corpus config: {source}\n\n{error}"
    else:
        entries = "\n".join(f"- {name}: {path}" for name, path in corpuses.items())
        corpus_section = f"Available corpuses from {source}:\n\n{entries}"
    workflow_entries = "\n".join(f"- {name}" for name in available_workflows())
    return f"{corpus_section}\n\nAvailable workflows:\n\n{workflow_entries}"


def _execution_settings(corpus_name: str, options: RunOptions) -> ExecutionSettings:
    """Resolve source paths independently of the corpus CSV's own directory."""
    settings = load_settings()
    if options.corpus is None:
        raise ValueError("Corpus name must be resolved before execution")
    corpus = options.corpus.resolve()
    data_root = (options.data_root or settings.test_data_root).resolve()
    tools = resolve_tools(options)
    table_name = workflow_table_name(options.workflow)
    default_table = Path("workflow_tables") / table_name
    requested_table = options.workflow_table or (default_table if default_table.is_file() else None)
    table = requested_table.resolve() if requested_table is not None else None
    if table is not None and table.name != table_name:
        raise ValueError(f"Expected {table_name}, got {table.name}")
    return ExecutionSettings(
        corpus_name=corpus_name,
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
def configure() -> None:
    """Show the main settings file, effective settings, defaults, and data locations."""
    location = settings_path()
    settings = load_settings()
    workspace = settings.test_data_root.parent
    corpuses_source = config_path(settings.test_data_root)
    corpuses = load_corpuses(corpuses_source)
    document = {
        "settings_file": {
            "path": str(location),
            "exists": location.is_file(),
        },
        "settings": settings.model_dump(mode="json"),
        "run_defaults": {
            "workflow": DEFAULT_IMMEDIATE_OPTIONS.workflow,
            "format": DEFAULT_IMMEDIATE_OPTIONS.storage_format,
            "cores": DEFAULT_IMMEDIATE_OPTIONS.cores,
        },
        "configuration_files": {
            "corpuses": str(corpuses_source),
            "downloads": str(settings.test_data_root / "downloads.csv"),
            "workflow_tables": str(workspace / "workflow_tables"),
        },
        "corpuses": {name: str(path) for name, path in corpuses.items()},
    }
    print(json.dumps(document, indent=2, sort_keys=True))  # noqa: T201


@run_app.default
def run(
    corpus: Annotated[str, Parameter(help="Configured corpus name")],
    /,
    *,
    options: Annotated[ImmediateRunOptions, Parameter(name="*")] = DEFAULT_IMMEDIATE_OPTIONS,
) -> None:
    """Run one workflow over a named corpus."""
    try:
        _run_corpus(corpus, _immediate_run_options(options))
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None


def _immediate_run_options(options: ImmediateRunOptions, /) -> RunOptions:
    """Expand the compact immediate-run surface into complete internal options."""
    return RunOptions(
        workflow=options.workflow,
        storage_format=options.storage_format,
        cores=options.cores,
        dry_run=options.dry_run,
        force=options.force,
    )


def _run_corpus(name: str, options: RunOptions, /) -> None:
    """Prepare and schedule one configured corpus."""
    options = _options_for_corpus(name, options)
    execution = _execution_settings(name, options)
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
        store = root.parents[2]
        publish_catalog(store)
        try:
            _schedule(root, cores=options.cores, dry_run=options.dry_run, force=options.force)
        finally:
            publish_catalog(store)


@app.command
def workflows(*, names: bool = False) -> None:
    """List every packaged workflow with the executables and resource table it declares."""
    for name in available_workflows():
        if names:
            print(name)  # noqa: T201 - a machine-readable list for shell loops
            continue
        table = workflow_table_name(name)
        found = "" if (Path("workflow_tables") / table).is_file() else " (absent)"
        tools = ", ".join(workflow_tools(name))
        logger.info("{} | tools: {} | table: {}{}", name, tools, table, found)


@app.command
def clean(
    corpus: Annotated[str | None, Parameter(help="Saved corpus name")] = None,
    workflow: Annotated[str | None, Parameter(help="Saved workflow name")] = None,
    /,
) -> None:
    """Delete all saved runs, or every format for one corpus and workflow."""
    if (corpus is None) != (workflow is None):
        raise SystemExit("Specify both CORPUS and WORKFLOW, or neither")
    store = _viewer_root(None)
    roots = saved_run_roots(store)
    if corpus is not None and workflow is not None:
        roots = [
            root
            for root in roots
            if (parts := root.relative_to(store).parts)[:2] == (corpus, workflow)
            and len(parts) == 3
        ]
    if not roots:
        publish_catalog(store)
        logger.info("No matching runs under {}", store)
        return
    failed: list[str] = []
    for root in roots:
        label = str(root.relative_to(store))
        try:
            deleted = delete_run(root)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failed.append(label)
            logger.error("{}: not deleted: {}", label, error)
        else:
            logger.info("{}: deleted", deleted.relative_to(store))
    publish_catalog(store)
    logger.info("Deleted {}/{} runs under {}", len(roots) - len(failed), len(roots), store)
    if failed:
        raise SystemExit(f"Runs not deleted: {', '.join(failed)}")


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
    is_viewer = any(Path(part).name in {"corpus", "apb-studio-corpus"} for part in command) and any(
        action in command for action in ("view", "serve", "restart")
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


def _serve_viewer(*, output_root: Path | None = None, port: int = VIEWER_PORT) -> None:
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
        server = build_server(
            Store(root),
            VIEWER_HOST,
            port,
            web_root=VIEWER_WEB_ROOT,
            resolver=resolve_corpus_viewer,
        )
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
    logger.info("Press Ctrl-C or run `corpus view stop` to stop")
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


def _stop_viewer(
    *,
    output_root: Path | None = None,
    port: int = VIEWER_PORT,
    quiet_when_absent: bool = False,
) -> None:
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
            if not quiet_when_absent:
                logger.info(
                    "Corpus viewer is not running; the port serves another viewer or service"
                )
        elif not quiet_when_absent:
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


@view_app.default
def view() -> None:
    """Start the managed corpus viewer, restarting it when already active."""
    _stop_viewer(output_root=None, port=VIEWER_PORT, quiet_when_absent=True)
    _serve_viewer(output_root=None, port=VIEWER_PORT)


@view_app.command(name="stop")
def stop_view() -> None:
    """Stop the managed corpus viewer."""
    _stop_viewer(output_root=None, port=VIEWER_PORT)


def main() -> None:
    """Run the corpus command-line application."""
    choices = _run_help()
    run_app.help_epilogue = choices
    app["clean"].help_epilogue = choices
    app()


if __name__ == "__main__":
    main()
