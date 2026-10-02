"""The store viewer's pure routes, its listing, and the socket around them."""

from __future__ import annotations

import errno
import json
import threading
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from apb_studio import fixture_index
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer import routes, server


def _body(response: routes.Response) -> bytes:
    return response.file.read_bytes() if response.file else response.body


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

    assert _body(routes.resolve("/", web, store)).startswith(b"<!doctype html>")
    assert routes.resolve("/?x=1#frag", web, store).status == 200
    javascript = routes.resolve("/app.js", web, store)
    assert javascript.headers[0] == ("Content-Type", "text/javascript; charset=utf-8")
    versioned = routes.resolve("/assets/36/app.js", web, store)
    assert versioned.file == web / "app.js"
    assert dict(versioned.headers)["Cache-Control"] == "no-store, max-age=0"
    assert routes.resolve("/assets/36", web, store).status == 404
    assert routes.resolve("/missing.js", web, store).status == 404
    assert routes.resolve("/../secret", web, store).status in {403, 404}

    # The server computes nothing, so an index nobody has written is simply absent.
    assert routes.resolve("/data/index.json", web, store).status == 404
    fixture_index.write(store)
    served = routes.resolve("/data/index.json", web, store)
    assert json.loads(_body(served))["fasta"] == ["ref.fasta"]
    assert json.loads(_body(routes.resolve("/data/", web, store)))["storeVersion"] == 1

    store.index_json.write_text('{"storeVersion": 99}', encoding="utf-8")
    byte_for_byte = json.loads(_body(routes.resolve("/data/index.json", web, store)))
    assert byte_for_byte == {"storeVersion": 99}, "whatever is on disk is what is served"

    table = routes.resolve("/data/catalog.csv", web, store)
    assert table.status == 200 and table.headers[0][1].startswith("text/csv")
    assert routes.resolve("/data/nope.csv", web, store).status == 404
    escaped = routes.resolve("/data/%2E%2E/web/index.html", web, store)
    assert escaped.status in {403, 404}


def test_identity_route_names_the_exact_store_and_viewer(tmp_path: Path) -> None:
    web = _web_root(tmp_path)
    store = _store(tmp_path)
    response = routes.resolve(f"/{routes.VIEWER_IDENTITY_PATH}?probe=1", web, store)

    assert response.status == 200
    assert response.headers[0] == ("Content-Type", "application/json")
    assert response.body == routes.viewer_identity(web, store)
    assert json.loads(response.body)["server"] == "apb-studio-static-viewer"

    other_root = tmp_path / "other-store"
    other_root.mkdir()
    assert response.body != routes.viewer_identity(web, Store(other_root))


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("result_performance.csv", "text/plain; charset=utf-8"),
        ("input.tsv", "text/plain; charset=utf-8"),
        ("module.TOML", "text/plain; charset=utf-8"),
        ("reference.fasta", "text/plain; charset=utf-8"),
        ("workflow.py", "text/plain; charset=utf-8"),
        ("unknown.extension", "text/plain; charset=utf-8"),
        ("multiqc_report.html", "text/html; charset=utf-8"),
        ("plot.png", "image/png"),
    ],
)
def test_file_navigation_is_inline_without_changing_raw_reads(
    tmp_path: Path, name: str, content_type: str
) -> None:
    web, store = _web_root(tmp_path), _store(tmp_path)
    path = store.root / name
    path.write_bytes(b"content")
    raw = routes.resolve(f"/data/{name}", web, store)
    assert raw.headers == routes.headers_for(name)
    response = routes.resolve(f"/data/{name}?view=1", web, store)
    assert response.file == path
    assert dict(response.headers)["Content-Type"] == content_type
    assert dict(response.headers)["Content-Disposition"].startswith("inline;")
    assert routes.resolve("/data/missing.txt?view=1", web, store).status == 404


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("result.h5mu", b"\x89HDF\r\n\x1a\n"),
        ("result.parquet", b"PAR1\0binary"),
        ("result.DUCKDB", b"\0database"),
        ("empty.h5ad", b""),
        ("unknown.extension", b"\xffbinary"),
    ],
)
def test_binary_navigation_streams_downloads_without_html(
    tmp_path: Path, name: str, content: bytes
) -> None:
    web, store = _web_root(tmp_path), _store(tmp_path)
    path = store.root / name
    path.write_bytes(content)
    response = routes.resolve(f"/data/{name}?view=1", web, store)
    assert response.file == path
    assert response.body == b""
    assert _body(response) == content
    assert dict(response.headers)["Content-Type"] == "application/octet-stream"
    assert dict(response.headers)["Content-Disposition"] == f"attachment; filename*=UTF-8''{name}"
    assert routes.resolve(f"/data/{name}", web, store).file == path


@pytest.mark.parametrize("query", ["", "?view=1"])
def test_json_is_served_verbatim_for_native_browser_display(tmp_path: Path, query: str) -> None:
    web, store = _web_root(tmp_path), _store(tmp_path)
    path = store.root / "result.JSON"
    original = b'{ "value": [1, null], "label": "<not HTML>" }\n'
    path.write_bytes(original)
    response = routes.resolve(f"/data/result.JSON{query}", web, store)
    assert response.file == path
    assert response.body == b""
    assert _body(response) == original
    assert dict(response.headers)["Content-Type"] == "application/json"
    assert "Content-Disposition" not in dict(response.headers)


def test_text_detection_allows_a_partial_utf8_character_at_the_probe_boundary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "result.txt"
    path.write_text("a" * 8191 + "\u00e9", encoding="utf-8")
    assert routes.inline_file(path).file == path


def test_directory_links_keep_extensions_encode_names_and_refuse_escapes(tmp_path: Path) -> None:
    web, store = _web_root(tmp_path), _store(tmp_path)
    folder = store.root / "results"
    folder.mkdir()
    (folder / "nested").mkdir()
    (folder / "dataset.parquet").mkdir()
    (folder / "result.h5mu").write_bytes(b"\x89HDF\0")
    name = "report <x> #?%.json"
    (folder / name).write_text("{}", encoding="utf-8")
    (folder / "private").symlink_to(web, target_is_directory=True)
    response = routes.resolve("/data/results?view=1", web, store)
    page = response.body.decode()
    assert "<h1>results/</h1>" in page
    assert 'target="_blank" rel="noopener noreferrer"' in page
    assert "nested/</a>" in page
    assert "report &lt;x&gt; #?%.json</a>" in page
    assert "private" not in page
    url = f"/data/results/{quote(name)}"
    assert url in page
    assert routes.resolve(url, web, store).file == folder / name
    assert '<a href="/data/results/result.h5mu?view=1" download="result.h5mu">' in page
    assert (
        '<a href="/data/results/dataset.parquet" target="_blank" '
        'rel="noopener noreferrer">dataset.parquet/</a>'
    ) in page
    assert routes.resolve("/data/results/private/index.html?view=1", web, store).status == 403
    assert routes.resolve("/data/results/private?view=1", web, store).status == 403


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
        url = f"http://{host}:{port}/data/fasta/ref.fasta?view=1"
        with urlopen(url) as response:
            assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
            assert response.headers["Content-Disposition"].startswith("inline;")
            assert response.read() == b">P\nAA\n"
        with urlopen(Request(url, method="HEAD")) as response:
            assert response.headers["Content-Length"] == "6"
            assert response.read() == b""
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
