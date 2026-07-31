"""Error-path and callback tests for the blocking quality contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anndata_proteomics.rules.registry import find_rule
from dash.exceptions import PreventUpdate

from apb_studio import config_editor, config_panel, disk, jobrunner
from apb_studio.testdata_app import create_app


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


def _copy_rule(tmp_path: Path) -> Path:
    source = find_rule("wombat", "peptidoform").path
    target = tmp_path / "rules.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_config_editor_complete_document_and_path_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_rule(tmp_path)
    loaded = config_editor.load_document(path)
    saved = config_editor.save_document(
        path,
        loaded["source"],
        expected_hash=loaded["content_hash"],
    )
    assert saved["valid"] is True

    with pytest.raises(config_editor.ConfigSaveError, match="changed on disk"):
        config_editor.save_document(
            path,
            loaded["source"],
            expected_hash="stale",
        )
    with pytest.raises(config_editor.ConfigSaveError, match="invalid"):
        config_editor.save_document(
            path,
            "{}",
            expected_hash=saved["content_hash"],
        )
    with pytest.raises(ValueError, match=r"\.json"):
        config_editor.load_document(tmp_path / "rules.toml")
    with pytest.raises(FileNotFoundError):
        config_editor.load_document(tmp_path / "missing.json")

    document = json.loads(path.read_text(encoding="utf-8"))
    document["levels"] = []
    with pytest.raises(ValueError, match="levels object"):
        config_editor._candidate_with_section(
            path,
            "base",
            "{}",
            document_source=json.dumps(document),
            kind="rule",
        )
    with pytest.raises(ValueError, match="unknown rule section"):
        config_editor._candidate_with_section(
            path,
            "missing",
            "{}",
            document_source=loaded["source"],
            kind="rule",
        )

    original_replace = config_editor.os.replace
    monkeypatch.setattr(
        config_editor.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError, match="replace failed"):
        config_editor._atomic_write(path, loaded["source"])
    monkeypatch.setattr(config_editor.os, "replace", original_replace)
    assert not list(tmp_path.glob(".rules.json.*"))


def test_config_editor_issue_context_helpers() -> None:
    error = ValueError("broken")
    error.add_note("in /tmp/rules.json; level: ion")
    assert config_editor._exception_document(error) == "/tmp/rules.json#ion"
    plain = ValueError("broken")
    plain.add_note("in /tmp/rules.json")
    assert config_editor._exception_document(plain) == "/tmp/rules.json"
    assert config_editor._exception_document(ValueError("broken")) == ""
    assert config_editor._json_path(("levels", 2, "axis")) == "$.levels[2].axis"
    issue = config_editor._issues_from_exception(ValueError("broken"))[0]
    assert issue["type"] == "ValueError"


def _configuration_callbacks() -> tuple[Any, Any]:
    app = create_app()
    operate = next(
        entry["callback"].__wrapped__
        for key, entry in app.callback_map.items()
        if "config-section-editor.value" in key
    )
    validate = next(
        entry["callback"].__wrapped__
        for key, entry in app.callback_map.items()
        if "config-status.children" in key
    )
    return operate, validate


def _operate_args(
    *,
    active: str | None,
    editor_source: str,
    state: dict[str, Any] | None,
    path: str | None,
) -> list[Any]:
    return [[0], None, None, None, None, None, active, editor_source, state, path, "rule"]


def test_configuration_callbacks_cover_edit_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_rule(tmp_path)
    loaded = config_editor.load_document(path)
    operate, validate = _configuration_callbacks()

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-load"))
    result = operate(*_operate_args(active=None, editor_source="", state=None, path=str(path)))
    state = result[2]
    active = result[7]
    source = result[0]
    assert result[3] == "Loaded configuration."

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-edit"))
    editing = operate(
        *_operate_args(active=active, editor_source=source, state=state, path=str(path))
    )
    assert editing[1] is False
    edit_state = editing[2]

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-format"))
    formatted = operate(
        *_operate_args(
            active=active,
            editor_source='{"z":1, "a":2}',
            state=edit_state,
            path=str(path),
        )
    )
    assert formatted[0].startswith("{\n")

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-cancel"))
    cancelled = operate(
        *_operate_args(active=active, editor_source=source, state=edit_state, path=str(path))
    )
    assert cancelled[3] == "Discarded in-memory changes."

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-section-tabs"))
    viewed = operate(
        *_operate_args(active=active, editor_source=source, state=state, path=str(path))
    )
    assert viewed[3] == "Viewing raw section."
    with pytest.raises(PreventUpdate):
        operate(
            *_operate_args(
                active=active,
                editor_source=source,
                state=edit_state,
                path=str(path),
            )
        )

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-save"))
    saved = operate(
        *_operate_args(active=active, editor_source=source, state=edit_state, path=str(path))
    )
    assert saved[3] == "Saved complete document atomically."

    assert validate("", None, None)[0] == "No document loaded"
    assert "read-only" in validate(source, state, active)[0]
    valid_dirty = validate(source + "\n", edit_state, active)
    assert "dirty" in valid_dirty[0]
    invalid = validate("{", edit_state, active)
    assert invalid[0].startswith("invalid")

    assert loaded["valid"] is True


def test_configuration_callbacks_load_and_error_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_rule(tmp_path)
    operate, _validate = _configuration_callbacks()
    trigger = {"type": "config-document", "path": str(path)}
    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id=trigger))
    args = _operate_args(active=None, editor_source="", state=None, path=None)
    args[0] = [1]
    result = operate(*args)
    assert result[3] == "Loaded packaged rule document."
    with pytest.raises(PreventUpdate):
        operate(
            *[
                [],
                None,
                None,
                None,
                None,
                None,
                None,
                "",
                None,
                None,
                "rule",
            ]
        )

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="config-load"))
    error = operate(*_operate_args(active=None, editor_source="", state=None, path=None))
    assert str(error[3]).startswith("Error:")

    monkeypatch.setattr(config_panel, "ctx", SimpleNamespace(triggered_id="unknown"))
    with pytest.raises(PreventUpdate):
        operate(*_operate_args(active=None, editor_source="", state=None, path=str(path)))
