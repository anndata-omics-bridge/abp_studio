"""Background-job runner: launch a command as a detached subprocess, stream its combined output to
a log file, poll status without side effects, and terminate the whole process tree.

Framework-independent: driven by the Dash applications and covered as ordinary Python code.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TextIO


class Process(Protocol):
    """Subprocess surface used by Studio and its deterministic test doubles."""

    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class PopenFactory(Protocol):
    """Typed constructor surface injected by process-runner tests."""

    def __call__(  # noqa: PLR0913 - mirrors subprocess construction
        self,
        command: list[str],
        *,
        stdout: TextIO,
        stderr: int,
        text: Literal[True],
        cwd: str | None,
        env: Mapping[str, str],
        creationflags: int = 0,
        start_new_session: bool = False,
    ) -> Process: ...


def _popen(  # noqa: PLR0913 - mirrors subprocess construction
    command: list[str],
    *,
    stdout: TextIO,
    stderr: int,
    text: Literal[True],
    cwd: str | None,
    env: Mapping[str, str],
    creationflags: int = 0,
    start_new_session: bool = False,
) -> Process:
    """Call the standard-library subprocess constructor through the typed surface."""
    return subprocess.Popen(
        command,
        stdout=stdout,
        stderr=stderr,
        text=text,
        cwd=cwd,
        env=env,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )


@dataclass
class Job:
    """A running (or finished) background subprocess job."""

    command: tuple[str, ...]
    process: Process
    log_file: Path


@dataclass(frozen=True)
class JobStatus:
    """Immutable snapshot of a job, built by inspect_job (safe to render every refresh)."""

    command: tuple[str, ...]
    returncode: int | None
    running: bool
    log_file: Path
    log_text: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


def make_run_key(*parts: object) -> str:
    """sha256 fingerprint of the inputs that define a run (detects selection changes)."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def start_job(
    command: Sequence[str],
    log_file: Path | str,
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    popen: PopenFactory = _popen,
) -> Job:
    """Launch `command` in the background, streaming stdout+stderr to `log_file`."""
    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Own process group/session so terminate_job can kill the whole tree (wrapper + children).
    command = tuple(str(part) for part in command)
    process_env = dict(env) if env is not None else os.environ.copy()
    # Python fully buffers stdout when it targets a file. Studio tails that file,
    # so force child Python CLIs to publish each line as it is produced.
    process_env.setdefault("PYTHONUNBUFFERED", "1")
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("$ " + shlex.join(command) + "\n\n")  # faithful, copy-pasteable header
        handle.flush()
        if os.name == "nt":
            process = popen(
                list(command),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(cwd) if cwd is not None else None,
                env=process_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            process = popen(
                list(command),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(cwd) if cwd is not None else None,
                env=process_env,
                start_new_session=True,
            )
    return Job(command=command, process=process, log_file=log_path)


def read_text_tail(path: Path | str, max_log_chars: int = 40000) -> str:
    """Return the tail of a UTF-8 text file (with a truncation marker if clipped)."""
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return ""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_log_chars:
        return text
    return "... log truncated ...\n" + text[-max_log_chars:]


def inspect_job(job: Job, *, max_log_chars: int = 40000) -> JobStatus:
    """Poll the job and read its log tail. Pure: no state mutation, safe to call every refresh."""
    returncode = job.process.poll()
    return JobStatus(
        command=job.command,
        returncode=returncode,
        running=returncode is None,
        log_file=job.log_file,
        log_text=read_text_tail(job.log_file, max_log_chars=max_log_chars),
    )


def _signal_group(  # noqa: PLR0911 - platform-specific signal fallbacks
    process: Process,
    *,
    force: bool,
) -> bool:
    pid = getattr(process, "pid", None)
    if not isinstance(pid, int):
        return False
    if os.name == "nt":
        args = (
            ["taskkill", "/F", "/T", "/PID", str(pid)]
            if force
            else ["taskkill", "/T", "/PID", str(pid)]
        )
        try:
            subprocess.run(args, capture_output=True, check=False)
            return True
        except OSError:
            return False
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return False
    if pgid != pid:  # child is not its own group leader → caller falls back
        return False
    try:
        os.killpg(pgid, signal.SIGKILL if force else signal.SIGTERM)
        return True
    except OSError:
        return False


def terminate_job(job: Job | None, timeout: float = 5.0) -> bool:
    """Terminate a still-running job and its child tree. No-op (False) if already done/None."""
    if job is None or job.process.poll() is not None:
        return False
    proc = job.process
    if not _signal_group(proc, force=False):
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if not _signal_group(proc, force=True):
            proc.kill()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    return True
