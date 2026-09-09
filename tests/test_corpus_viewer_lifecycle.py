"""Corpus viewer process lifecycle."""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psutil
import pytest

from apb_studio.corpus import cli
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.server import build_server


def test_viewer_status_matches_only_the_exact_output_root(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    httpd = build_server(Store(root), cli.VIEWER_HOST, 0, web_root=cli.VIEWER_WEB_ROOT)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(httpd.server_address[1])
        assert cli._viewer_status(root, port) == "matching"
        assert cli._viewer_status(tmp_path / "another-corpus", port) == "other"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_serve_accepts_an_existing_healthy_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_root = tmp_path / "corpus"
    monkeypatch.setattr(
        cli,
        "_viewer_status",
        lambda root, _port: "matching" if root == expected_root else "other",
    )
    monkeypatch.setattr(
        cli,
        "build_server",
        lambda *_args, **_kwargs: pytest.fail("must not bind a second server"),
    )

    cli.serve(output_root=tmp_path)


def test_serve_refuses_a_viewer_for_another_output_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "other")
    monkeypatch.setattr(
        cli,
        "build_server",
        lambda *_args, **_kwargs: pytest.fail("must not bind over another viewer"),
    )

    with pytest.raises(SystemExit, match="another viewer or store"):
        cli.serve(output_root=tmp_path)


def test_serve_records_its_pid_and_removes_it_on_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    pid_path = tmp_path / "corpus" / "viewer-8766.pid"

    class _Server:
        def serve_forever(self) -> None:
            assert pid_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"
            events.append("serve")
            raise KeyboardInterrupt

        def server_close(self) -> None:
            events.append("close")

    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "absent")
    monkeypatch.setattr(cli, "build_server", lambda *_args, **_kwargs: _Server())

    cli.serve(output_root=tmp_path)

    assert events == ["serve", "close"]
    assert not pid_path.exists()


def test_shutdown_signals_the_recorded_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "corpus" / "viewer-8766.pid"
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("42\n", encoding="utf-8")
    events: list[Any] = []
    process = SimpleNamespace(
        pid=42,
        send_signal=lambda sent: events.append(sent),
        wait=lambda *, timeout: events.append(timeout),
    )
    monkeypatch.setattr(cli, "_viewer_process", lambda _path, _port: process)
    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "matching")

    cli.shutdown(output_root=tmp_path)

    assert events == [signal.SIGINT, 5]
    assert not pid_path.exists()


def test_shutdown_without_a_server_is_successful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_viewer_process", lambda _path, _port: None)
    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "absent")

    cli.shutdown(output_root=tmp_path)


def test_shutdown_never_signals_a_viewer_for_another_output_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "corpus" / "viewer-8766.pid"
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("42\n", encoding="utf-8")
    signals: list[int] = []
    process = SimpleNamespace(
        pid=42,
        send_signal=lambda sent: signals.append(sent),
        wait=lambda *, timeout: pytest.fail(f"must not wait for another viewer: {timeout}"),
    )
    monkeypatch.setattr(cli, "_viewer_process", lambda _path, _port: process)
    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "other")

    with pytest.raises(SystemExit, match="Refusing to stop"):
        cli.shutdown(output_root=tmp_path)

    assert signals == []
    assert pid_path.exists()


def test_restart_stops_then_serves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, Path | None, int]] = []
    monkeypatch.setattr(
        cli,
        "shutdown",
        lambda *, output_root, port: events.append(("shutdown", output_root, port)),
    )
    monkeypatch.setattr(
        cli,
        "serve",
        lambda *, output_root, port: events.append(("serve", output_root, port)),
    )

    cli.restart(output_root=tmp_path, port=9000)

    assert events == [("shutdown", tmp_path, 9000), ("serve", tmp_path, 9000)]


def test_shutdown_never_signals_a_stale_pid_for_another_listener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    httpd = build_server(Store(root), cli.VIEWER_HOST, 0, web_root=cli.VIEWER_WEB_ROOT)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    signals: list[int] = []

    class _OtherViewer:
        def cmdline(self) -> list[str]:
            return ["/venv/bin/apb-studio-corpus", "serve"]

        def net_connections(self, *, kind: str) -> list[SimpleNamespace]:
            assert kind == "tcp"
            return [
                SimpleNamespace(
                    status=psutil.CONN_LISTEN,
                    laddr=SimpleNamespace(ip=cli.VIEWER_HOST, port=9999),
                )
            ]

        def send_signal(self, sent: int) -> None:
            signals.append(sent)

    try:
        port = int(httpd.server_address[1])
        pid_path = root / f"viewer-{port}.pid"
        pid_path.write_text("42\n", encoding="utf-8")
        monkeypatch.setattr(cli.psutil, "Process", lambda _pid: _OtherViewer())

        with pytest.raises(SystemExit, match="PID was not recorded"):
            cli.shutdown(output_root=tmp_path, port=port)

        assert signals == []
        assert not pid_path.exists()
    finally:
        httpd.shutdown()
        httpd.server_close()
