"""The store viewer's pure routes, its listing, and the socket around them."""

from __future__ import annotations

import errno
import json
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from apb_studio import fixture_index
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer import routes, server


def _web_root(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (web / "app.js").write_text("export {}", encoding="utf-8")
    return web


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "store")
    store.submission_dir("Repo", "a").mkdir(parents=True)
    (store.submission_dir("Repo", "a") / "input_file.tsv").write_text("x\n1\n", encoding="utf-8")
    store.fasta_dir.mkdir()
    (store.fasta_dir / "ref.fasta").write_text(">P\nAA\n", encoding="utf-8")
    store.modules_dir.mkdir()
    (store.modules_dir / "dda.toml").write_text("[g]\n", encoding="utf-8")
    store.catalog_csv.write_text("module\ndda\n", encoding="utf-8")
    return store


def test_headers_follow_the_suffix() -> None:
    assert routes.headers_for("catalog.csv")[0] == ("Content-Type", "text/csv; charset=utf-8")
    assert routes.headers_for("x.parquet")[0] == ("Content-Type", "application/octet-stream")
    assert routes.headers_for("x.png")[0] == ("Content-Type", "image/png")
    assert routes.headers_for("x.unknownsuffix")[0] == ("Content-Type", "application/octet-stream")


def test_resolve_serves_files_and_nothing_else(tmp_path: Path) -> None:
    web = _web_root(tmp_path)
    store = _store(tmp_path)

    assert routes.resolve("/", web, store).body.startswith(b"<!doctype html>")
    assert routes.resolve("/?x=1#frag", web, store).status == 200
    javascript = routes.resolve("/app.js", web, store)
    assert javascript.headers[0] == ("Content-Type", "text/javascript; charset=utf-8")
    assert routes.resolve("/missing.js", web, store).status == 404
    assert routes.resolve("/../secret", web, store).status in {403, 404}

    # The server computes nothing, so an index nobody has written is simply absent.
    assert routes.resolve("/data/index.json", web, store).status == 404
    fixture_index.write(store)
    served = routes.resolve("/data/index.json", web, store)
    assert json.loads(served.body)["modules"] == ["dda"]
    assert json.loads(routes.resolve("/data/", web, store).body)["storeVersion"] == 1

    store.index_json.write_text('{"storeVersion": 99}', encoding="utf-8")
    byte_for_byte = json.loads(routes.resolve("/data/index.json", web, store).body)
    assert byte_for_byte == {"storeVersion": 99}, "whatever is on disk is what is served"

    table = routes.resolve("/data/catalog.csv", web, store)
    assert table.status == 200 and table.headers[0][1].startswith("text/csv")
    assert routes.resolve("/data/nope.csv", web, store).status == 404
    escaped = routes.resolve("/data/%2E%2E/web/index.html", web, store)
    assert escaped.status in {403, 404}


def test_server_binds_and_answers(tmp_path: Path) -> None:
    web = _web_root(tmp_path)
    store = _store(tmp_path)
    with pytest.raises(NotADirectoryError):
        server.build_server(Store(tmp_path / "absent"), "127.0.0.1", 0, web_root=web)
    fixture_index.write(store)
    httpd = server.build_server(store, "127.0.0.1", 0, web_root=web)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address[:2]
        summary = store.submission_summary("Repo", "a")
        summary.write_text('{"rows": 1}', encoding="utf-8")
        with urlopen(f"http://{host}:{port}/data/submissions/Repo/a/summary.json") as response:
            assert response.status == 200
            assert json.loads(response.read())["rows"] == 1
        with urlopen(f"http://{host}:{port}/") as response:
            assert response.headers["Content-Type"].startswith("text/html")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_port_in_use_is_a_message_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    taken = OSError(errno.EADDRINUSE, "Address already in use")

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise taken

    monkeypatch.setattr(server, "build_server", _refuse)
    with pytest.raises(SystemExit, match="Another viewer is probably already serving"):
        server.run(store, "127.0.0.1", 8765)

    def _break(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(server, "build_server", _break)
    with pytest.raises(OSError, match="Broken pipe"):
        server.run(store)


def test_run_serves_until_interrupted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    events: list[str] = []

    class _Server:
        server_address = ("127.0.0.1", 1)

        def serve_forever(self) -> None:
            events.append("serve")
            raise KeyboardInterrupt

        def server_close(self) -> None:
            events.append("close")

    monkeypatch.setattr(server, "build_server", lambda *_a, **_k: _Server())
    server.run(store)
    assert events == ["serve", "close"]
