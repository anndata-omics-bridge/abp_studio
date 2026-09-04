"""Error-path and callback tests for the blocking quality contract."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from apb_studio import disk, jobrunner


class _Process:
    def __init__(
        self,
        *,
        pid: int = 42,
        returncode: int | None = None,
        timeouts: int = 0,
    ) -> None:
        self.pid = pid
        self.returncode = returncode
        self.timeouts = timeouts
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        if self.timeouts:
            self.timeouts -= 1
            raise subprocess.TimeoutExpired("test", timeout or 0.0)
        self.returncode = 0
        return 0


def _job(tmp_path: Path, process: _Process) -> jobrunner.Job:
    log = tmp_path / "job.log"
    log.write_text("abcdef", encoding="utf-8")
    return jobrunner.Job(("command",), process, log)


def test_jobrunner_tail_and_termination_fallbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert jobrunner.read_text_tail(tmp_path / "missing") == ""
    log = tmp_path / "tail.log"
    log.write_text("abcdef", encoding="utf-8")
    assert jobrunner.read_text_tail(log) == "abcdef"
    assert jobrunner.read_text_tail(log, 3) == "... log truncated ...\ndef"

    bad_pid = cast(jobrunner.Process, SimpleNamespace(pid="bad"))
    assert jobrunner._signal_group(bad_pid, force=False) is False
    monkeypatch.setattr(jobrunner.os, "getpgid", lambda _pid: 99)
    assert jobrunner._signal_group(_Process(), force=False) is False
    monkeypatch.setattr(
        jobrunner.os,
        "getpgid",
        lambda _pid: (_ for _ in ()).throw(OSError("gone")),
    )
    assert jobrunner._signal_group(_Process(), force=False) is False

    monkeypatch.setattr(jobrunner, "_signal_group", lambda _process, *, force: False)
    confirmed = _Process()
    assert jobrunner.terminate_job(_job(tmp_path, confirmed), timeout=0.01) is True
    assert confirmed.terminated is True
    assert confirmed.killed is False

    process = _Process(timeouts=2)
    assert jobrunner.terminate_job(_job(tmp_path, process), timeout=0.01) is False
    assert process.terminated is True
    assert process.killed is True
    assert jobrunner.terminate_job(None) is False
    assert jobrunner.terminate_job(_job(tmp_path, _Process(returncode=0))) is False


def test_jobrunner_platform_signal_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(jobrunner.os, "name", "nt")
    monkeypatch.setattr(
        jobrunner.subprocess,
        "run",
        lambda args, **_kwargs: calls.append(args),
    )
    assert jobrunner._signal_group(_Process(), force=False) is True
    assert jobrunner._signal_group(_Process(), force=True) is True
    assert calls[0][1:3] == ["/T", "/PID"]
    assert "/F" in calls[1]
    monkeypatch.setattr(
        jobrunner.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    assert jobrunner._signal_group(_Process(), force=False) is False


def test_jobrunner_posix_group_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobrunner.os, "name", "posix")
    monkeypatch.setattr(jobrunner.os, "getpgid", lambda pid: pid)
    signals: list[int] = []
    monkeypatch.setattr(jobrunner.os, "killpg", lambda _pid, sig: signals.append(sig))
    assert jobrunner._signal_group(_Process(), force=False) is True
    assert jobrunner._signal_group(_Process(), force=True) is True
    assert signals == [jobrunner.signal.SIGTERM, jobrunner.signal.SIGKILL]
    monkeypatch.setattr(
        jobrunner.os,
        "killpg",
        lambda *_args: (_ for _ in ()).throw(OSError("gone")),
    )
    assert jobrunner._signal_group(_Process(), force=False) is False


def test_atomic_write_preserves_mode_and_cleans_failed_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o640)
    disk.atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert target.stat().st_mode & 0o777 == 0o640

    monkeypatch.setattr(
        disk.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError, match="replace failed"):
        disk.atomic_write_text(target, "broken")
    assert not list(tmp_path.glob(".state.json.*"))


def test_windows_lock_branch_uses_one_byte_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    fake = SimpleNamespace(
        LK_LOCK=1,
        LK_UNLCK=2,
        locking=lambda _fd, mode, _size: calls.append(mode),
    )
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(disk.os, "name", "nt")
    with disk.interprocess_file_lock(tmp_path / "state.lock"):
        assert (tmp_path / "state.lock").read_bytes() == b"\0"
    assert calls == [1, 2]
    with disk.interprocess_file_lock(tmp_path / "state.lock"):
        pass
    assert calls == [1, 2, 1, 2]


def test_windows_job_launch_and_successful_group_termination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def popen(request: jobrunner.PopenRequest) -> _Process:
        captured["command"] = request.command
        captured["creationflags"] = request.creationflags
        return _Process()

    monkeypatch.setattr(jobrunner, "Path", type(tmp_path))
    monkeypatch.setattr(jobrunner.os, "name", "nt")
    monkeypatch.setattr(
        jobrunner.subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        512,
        raising=False,
    )
    jobrunner.start_job(
        ["apb", "convert"],
        tmp_path / "job.log",
        popen=popen,
    )
    assert captured["creationflags"] == 512

    signals = iter((True, True))
    monkeypatch.setattr(
        jobrunner,
        "_signal_group",
        lambda _process, *, force: next(signals),
    )
    process = _Process(timeouts=1)
    assert jobrunner.terminate_job(_job(tmp_path, process), timeout=0.01) is True
    assert process.terminated is False
    assert process.killed is False
