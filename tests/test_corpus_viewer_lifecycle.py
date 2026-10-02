"""Corpus viewer process lifecycle."""

from __future__ import annotations

import json
import os
import signal
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psutil
import pytest
from loguru import logger

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


def test_viewer_requests_do_not_emit_debug_logs(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    httpd = build_server(Store(root), cli.VIEWER_HOST, 0, web_root=cli.VIEWER_WEB_ROOT)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    messages: list[str] = []
    sink = logger.add(messages.append, level="DEBUG", format="{level}:{message}")
    thread.start()
    try:
        port = int(httpd.server_address[1])
        assert cli._viewer_status(root, port) == "matching"
    finally:
        httpd.shutdown()
        httpd.server_close()
        logger.remove(sink)

    assert messages == []


@pytest.mark.parametrize("action", ["view", "serve", "restart"])
def test_viewer_process_recognizes_current_and_prior_managed_commands(
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_path = tmp_path / "viewer.pid"
    pid_path.write_text("42\n", encoding="utf-8")
    process = SimpleNamespace(
        cmdline=lambda: ["/venv/bin/corpus", action],
        net_connections=lambda *, kind: [
            SimpleNamespace(
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(ip=cli.VIEWER_HOST, port=9000),
            )
        ],
    )
    monkeypatch.setattr(cli.psutil, "Process", lambda _pid: process)

    assert cli._viewer_process(pid_path, 9000) is process


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

    cli._serve_viewer(output_root=tmp_path)


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
        cli._serve_viewer(output_root=tmp_path)


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

    cli._serve_viewer(output_root=tmp_path)

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

    cli._stop_viewer(output_root=tmp_path)

    assert events == [signal.SIGINT, 5]
    assert not pid_path.exists()


def test_shutdown_without_a_server_is_successful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_viewer_process", lambda _path, _port: None)
    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "absent")

    cli._stop_viewer(output_root=tmp_path)


def test_shutdown_reports_a_port_owned_by_another_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[str] = []
    sink = logger.add(messages.append, format="{message}")
    monkeypatch.setattr(cli, "_viewer_process", lambda _path, _port: None)
    monkeypatch.setattr(cli, "_viewer_status", lambda _root, _port: "other")
    try:
        cli._stop_viewer(output_root=tmp_path)
    finally:
        logger.remove(sink)

    assert "port serves another viewer or service" in "".join(messages)


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
        cli._stop_viewer(output_root=tmp_path)

    assert signals == []
    assert pid_path.exists()


def test_view_stops_then_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, Path | None, int, bool | None]] = []
    monkeypatch.setattr(
        cli,
        "_stop_viewer",
        lambda *, output_root, port, quiet_when_absent: events.append((
            "stop",
            output_root,
            port,
            quiet_when_absent,
        )),
    )
    monkeypatch.setattr(
        cli,
        "_serve_viewer",
        lambda *, output_root, port: events.append(("serve", output_root, port, None)),
    )

    cli.view()

    assert events == [
        ("stop", None, cli.VIEWER_PORT, True),
        ("serve", None, cli.VIEWER_PORT, None),
    ]


def test_view_stop_only_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[Path | None, int, bool]] = []
    monkeypatch.setattr(
        cli,
        "_stop_viewer",
        lambda *, output_root, port, quiet_when_absent=False: events.append((
            output_root,
            port,
            quiet_when_absent,
        )),
    )

    cli.stop_view()

    assert events == [(None, cli.VIEWER_PORT, False)]


def test_cli_uses_nested_view_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(cli, "_stop_viewer", lambda **_kwargs: events.append("stop"))
    monkeypatch.setattr(cli, "_serve_viewer", lambda **_kwargs: events.append("serve"))

    cli.app(["view"], exit_on_error=False, result_action="return_value")
    cli.app(["view", "stop"], exit_on_error=False, result_action="return_value")

    assert events == ["stop", "serve", "stop"]


def test_run_help_lists_configured_corpuses_and_workflows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "corpuses.json"
    source.write_text('{"all": "all.csv", "routine": "routine.csv"}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "config_path", lambda _root: source)
    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace(test_data_root=tmp_path))
    monkeypatch.setattr(cli.run_app, "help_epilogue", cli._run_help())

    with pytest.raises(SystemExit) as stopped:
        cli.app(["run", "--help"], exit_on_error=False)

    assert stopped.value.code == 0
    rendered = capsys.readouterr().out
    assert "Available corpuses" in rendered
    assert "all:" in rendered
    assert "routine:" in rendered
    assert "Available workflows" in rendered
    for workflow in cli.available_workflows():
        assert workflow in rendered
    for option in ("--workflow", "--format", "--cores", "--dry-run", "--force"):
        assert option in rendered
    for option in (
        "--corpus",
        "--data-root",
        "--workflow-table",
        "--downloads",
        "--apb-executable",
        "--output-root",
        "--datasets",
        "--fixtures",
        "--scope",
    ):
        assert option not in rendered


def test_clean_help_lists_configured_corpuses_and_workflows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "corpuses.json"
    source.write_text('{"proteobench": "proteobench.csv"}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "config_path", lambda _root: source)
    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace(test_data_root=tmp_path))
    monkeypatch.setattr(cli.app["clean"], "help_epilogue", cli._run_help())

    with pytest.raises(SystemExit) as stopped:
        cli.app(["clean", "--help"], exit_on_error=False)

    assert stopped.value.code == 0
    rendered = capsys.readouterr().out
    assert "Available corpuses" in rendered
    assert "proteobench:" in rendered
    assert "Available workflows" in rendered
    for workflow in cli.available_workflows():
        assert workflow in rendered


def test_run_help_reports_missing_corpus_config_and_workflows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "missing.json"
    monkeypatch.setattr(cli, "config_path", lambda _root: source)
    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace(test_data_root=tmp_path))

    rendered = cli._run_help()
    assert rendered.startswith(f"Corpus config: {source}")
    assert "Available workflows" in rendered
    assert "convert" in rendered


def test_main_refreshes_run_and_clean_help(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_app = cli.app["clean"]
    calls: list[str] = []

    class _AppProxy:
        def __getitem__(self, name: str) -> Any:
            assert name == "clean"
            return clean_app

        def __call__(self) -> None:
            calls.append("app")

    monkeypatch.setattr(cli, "_run_help", lambda: "named corpuses and workflows")
    monkeypatch.setattr(cli.run_app, "help_epilogue", None)
    monkeypatch.setattr(clean_app, "help_epilogue", None)
    monkeypatch.setattr(cli, "app", _AppProxy())

    cli.main()

    assert cli.run_app.help_epilogue == "named corpuses and workflows"
    assert clean_app.help_epilogue == "named corpuses and workflows"
    assert calls == ["app"]


def test_top_level_cli_exposes_only_intent_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.app(["--help"], exit_on_error=False)

    assert stopped.value.code == 0
    rendered = capsys.readouterr().out
    for command in ("clean", "configure", "run", "view", "workflows"):
        assert f"│ {command}" in rendered
    for command in ("execute", "select", "restart", "serve", "shutdown"):
        assert f"│ {command}" not in rendered


@pytest.mark.parametrize("arguments", [["clean", "--help"], ["view", "--help"]])
def test_clean_and_view_help_have_no_configuration_flags(
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.app(arguments, exit_on_error=False)

    assert stopped.value.code == 0
    rendered = capsys.readouterr().out
    assert "--output-root" not in rendered
    assert "--port" not in rendered


def test_run_selects_named_corpus_and_one_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs: list[tuple[str, cli.RunOptions]] = []
    monkeypatch.setattr(cli, "_run_corpus", lambda name, options: runs.append((name, options)))

    arguments = ["--workflow", "aggregate", "--format", "parquet", "--cores", "3"]
    cli.app(["run", "routine", *arguments], exit_on_error=False, result_action="return_value")
    cli.app(
        ["run", "all", "--workflow", "convert", "--format", "parquet", "--cores", "3"],
        exit_on_error=False,
        result_action="return_value",
    )

    assert [name for name, _options in runs] == ["routine", "all"]
    assert [options.workflow for _name, options in runs] == ["aggregate", "convert"]
    assert all(run_options.storage_format == "parquet" for _name, run_options in runs)
    assert all(run_options.cores == 3 for _name, run_options in runs)


def test_run_reports_unknown_corpus_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "corpuses.json"
    source.write_text('{"routine": "routine.csv"}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "config_path", lambda _root: source)
    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace(test_data_root=tmp_path))

    with pytest.raises(SystemExit, match="Unknown corpus 'missing'; available: routine"):
        cli.app(["run", "missing"], exit_on_error=False, result_action="return_value")


def test_clean_without_a_run_deletes_every_saved_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    runs = [
        corpus / "all" / "convert" / "hdf5",
        corpus / "routine" / "convert" / "hdf5",
    ]
    for root in runs:
        root.mkdir(parents=True)
        (root / "run.json").write_text("{}", encoding="utf-8")
    deleted: list[Path] = []
    published: list[Path] = []
    monkeypatch.setattr(cli, "_viewer_root", lambda _output_root: corpus)
    monkeypatch.setattr(cli, "delete_run", lambda root: deleted.append(root) or root)
    monkeypatch.setattr(cli, "publish_catalog", published.append)

    cli.clean()

    assert deleted == runs
    assert published == [corpus]


def test_clean_selects_only_one_corpus_workflow_across_formats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = tmp_path / "corpus"
    selected = [
        store / "proteobench" / "proteobench_pmultiqc" / "hdf5",
        store / "proteobench" / "proteobench_pmultiqc" / "parquet",
    ]
    retained = [
        store / "proteobench" / "convert" / "hdf5",
        store / "routine" / "proteobench_pmultiqc" / "hdf5",
        store / "proteobench-pmultiqc-legacyhash",
    ]
    data_root = tmp_path / "fixtures"
    for root in selected + retained:
        root.mkdir(parents=True)
        (root / "run.json").write_text(json.dumps({"data_root": str(data_root)}), encoding="utf-8")
    published: list[Path] = []
    monkeypatch.setattr(cli, "_viewer_root", lambda _output_root: store)
    monkeypatch.setattr(cli, "publish_catalog", published.append)

    cli.app(
        ["clean", "proteobench", "proteobench_pmultiqc"],
        exit_on_error=False,
        result_action="return_value",
    )

    assert all(not root.exists() for root in selected)
    assert all(root.exists() for root in retained)
    assert published == [store]


def test_clean_requires_a_complete_pair() -> None:
    with pytest.raises(SystemExit, match="Specify both CORPUS and WORKFLOW"):
        cli.app(["clean", "proteobench"], exit_on_error=False, result_action="return_value")


def test_clean_help_shows_positional_names(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.app(["clean", "--help"], exit_on_error=False)
    assert stopped.value.code == 0
    rendered = capsys.readouterr().out
    assert "CORPUS" in rendered
    assert "WORKFLOW" in rendered
    assert "--corpus" not in rendered
    assert "--workflow" not in rendered


def test_clean_with_no_saved_runs_refreshes_the_empty_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    published: list[Path] = []
    monkeypatch.setattr(cli, "_viewer_root", lambda _output_root: corpus)
    monkeypatch.setattr(cli, "publish_catalog", published.append)

    cli.clean()

    assert published == [corpus]


def test_clean_all_reports_runs_that_could_not_be_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = tmp_path / "corpus"
    failed = corpus / "failed" / "convert" / "hdf5"
    succeeded = corpus / "succeeded" / "convert" / "hdf5"
    for root in (failed, succeeded):
        root.mkdir(parents=True)
        (root / "run.json").write_text("{}", encoding="utf-8")
    deleted: list[Path] = []

    def delete(root: Path) -> Path:
        if root == failed:
            raise ValueError("unsafe")
        deleted.append(root)
        return root

    monkeypatch.setattr(cli, "_viewer_root", lambda _output_root: corpus)
    monkeypatch.setattr(cli, "delete_run", delete)
    monkeypatch.setattr(cli, "publish_catalog", lambda _root: None)

    with pytest.raises(SystemExit, match="Runs not deleted: failed/convert/hdf5"):
        cli.clean()

    assert deleted == [succeeded]


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
            return ["/venv/bin/corpus", "view"]

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
            cli._stop_viewer(output_root=tmp_path, port=port)

        assert signals == []
        assert not pid_path.exists()
    finally:
        httpd.shutdown()
        httpd.server_close()
