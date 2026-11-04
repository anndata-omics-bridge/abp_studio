"""The rules viewer's commands: the bundle served at /data/, the published site, its default."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

import pytest

from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer import server
from apb_studio.rules_viewer import cli
from apb_studio.rules_viewer.publish import publish_site, require_bundle

MANIFEST = '{"bundle_format": 1, "files": ["rules.json"]}'


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    (bundle / "documents" / "sage").mkdir(parents=True)
    (bundle / "manifest.json").write_text(MANIFEST, encoding="utf-8")
    (bundle / "rules.json").write_text('{"rules": []}', encoding="utf-8")
    (bundle / "documents" / "sage" / "rules.json").write_text("{}", encoding="utf-8")
    return bundle


def _web_root(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><rules-app></rules-app>", encoding="utf-8")
    (web / "assets" / "rules-a1.js").write_text("export {}", encoding="utf-8")
    return web


def test_the_server_serves_the_viewer_at_root_and_the_bundle_under_data(tmp_path: Path) -> None:
    httpd = server.build_server(
        Store(_bundle(tmp_path)), "127.0.0.1", 0, web_root=_web_root(tmp_path)
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with urlopen(f"{base}/") as response:
            assert b"<rules-app>" in response.read()
        with urlopen(f"{base}/data/manifest.json") as response:
            assert response.read().decode() == MANIFEST
        with urlopen(f"{base}/data/documents/sage/rules.json") as response:
            assert response.read() == b"{}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_publish_copies_the_viewer_and_the_bundle_into_data(tmp_path: Path) -> None:
    site = tmp_path / "site"

    publish_site(_bundle(tmp_path), _web_root(tmp_path), site)

    assert (site / "index.html").is_file()
    assert (site / "assets" / "rules-a1.js").is_file()
    assert (site / "data" / "manifest.json").read_text(encoding="utf-8") == MANIFEST
    assert (site / "data" / "documents" / "sage" / "rules.json").is_file()
    with pytest.raises(ValueError, match="empty folder"):
        publish_site(_bundle(tmp_path / "again"), _web_root(tmp_path / "again"), site)


def test_a_folder_without_a_manifest_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    empty = tmp_path / "build"
    empty.mkdir()
    site = tmp_path / "site"

    with pytest.raises(ValueError, match="make rules-bundle"):
        require_bundle(empty)
    with pytest.raises(ValueError, match="make rules-bundle"):
        publish_site(empty, _web_root(tmp_path), site)
    assert not site.exists()


def test_the_default_bundle_is_apb2s_build_beside_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_data = tmp_path / "apb_studio" / "test_data_download"
    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace(test_data_root=test_data))

    assert cli.default_bundle() == tmp_path / "apb2" / "build" / "apb2-rules-bundle"
    with pytest.raises(SystemExit, match="make rules-bundle"):
        cli.publish(tmp_path / "site")
