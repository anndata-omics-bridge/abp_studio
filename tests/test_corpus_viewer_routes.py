"""Filesystem-backed corpus viewer routes."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from apb_studio.corpus_viewer.routes import resolve
from apb_studio.fixture_store import Store
from apb_studio.fixture_viewer.server import build_server


def _write_run(root: Path, corpus: str, status: str | None) -> Path:
    directory = root / corpus / "convert" / "hdf5"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(
        json.dumps({"schema_version": 2, "corpus_name": corpus}),
        encoding="utf-8",
    )
    if status is not None:
        (directory / "operation.json").write_text(
            json.dumps({"schema_version": 2, "status": status}),
            encoding="utf-8",
        )
    return directory


def test_catalog_endpoint_tracks_live_run_directories_without_a_static_index(
    tmp_path: Path,
) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    live = _write_run(root, "live", "succeeded")
    cleaned = _write_run(root, "cleaned", "cleaned")
    _write_run(root, "prepared", None)
    legacy = root / "convert-hdf5-deadbeef"
    legacy.mkdir()
    (legacy / "run.json").write_text('{"schema_version": 1}', encoding="utf-8")

    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    server = build_server(Store(root), "127.0.0.1", 0, web_root=web, resolver=resolve)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]

        def catalog() -> dict[str, object]:
            with urlopen(f"http://{host}:{port}/api/catalog") as response:
                return json.loads(response.read())

        first = catalog()
        assert first["store_root"] == str(root.resolve())
        assert first["runs"] == ["live/convert/hdf5/run.json"]
        assert "settings" not in first
        assert "configured_settings" not in first
        (cleaned / "operation.json").write_text(
            json.dumps({"schema_version": 2, "status": "running"}),
            encoding="utf-8",
        )
        (live / "operation.json").write_text(
            json.dumps({"schema_version": 2, "status": "cleaned"}),
            encoding="utf-8",
        )
        assert catalog()["runs"] == ["cleaned/convert/hdf5/run.json"]
    finally:
        server.shutdown()
        server.server_close()


def test_source_endpoint_opens_only_files_in_frozen_input_snapshots(tmp_path: Path) -> None:
    data_root = tmp_path / "inputs"
    input_path = data_root / "submissions" / "sample" / "input.tsv"
    parameter_path = input_path.with_name("parameters.json")
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"vendor table")
    parameter_path.write_bytes(b"parameters")
    (data_root / "secret.txt").write_text("secret", encoding="utf-8")

    root = tmp_path / "corpus"
    root.mkdir()
    run = _write_run(root, "routine", "succeeded")
    (run / "run.json").write_text(json.dumps({"workflow_table": "workflow.csv"}), encoding="utf-8")
    fasta = data_root / "reference.FASTA"
    fasta.write_text(">protein\nPEPTIDE\n", encoding="utf-8")
    (run / "workflow.csv").write_text(
        "module,fasta,description\ntest,reference.FASTA,secret.txt\n",
        encoding="utf-8",
    )
    (run / "execution_settings.json").write_text(
        json.dumps({"data_root": str(data_root)}),
        encoding="utf-8",
    )
    (run / "corpus.csv").write_text(
        "input_file,vendor_parameter_file,module,software_name\n"
        "submissions/sample/input.tsv,submissions/sample/parameters.json,test,Vendor\n",
        encoding="utf-8",
    )
    web = tmp_path / "web"
    web.mkdir()

    context = "routine/convert/hdf5"
    query = urlencode({"context": context, "path": "submissions/sample/input.tsv"})
    response = resolve(f"/api/source?{query}", web, Store(root))
    assert response.status == 200
    assert response.file == input_path
    assert ("Content-Disposition", "inline; filename*=UTF-8''input.tsv") in response.headers
    assert dict(response.headers)["Content-Type"] == "text/plain; charset=utf-8"
    query = urlencode({"context": context, "path": fasta.name})
    resource_response = resolve(f"/api/source?{query}", web, Store(root))
    assert resource_response.file == fasta
    assert dict(resource_response.headers)["Content-Type"] == "text/plain; charset=utf-8"

    parameter_query = urlencode({"context": context, "path": "submissions/sample/parameters.json"})
    assert resolve(f"/api/source?{parameter_query}", web, Store(root)).file == parameter_path

    forbidden = urlencode({"context": context, "path": "secret.txt"})
    assert resolve(f"/api/source?{forbidden}", web, Store(root)).status == 403

    # A snapshot does not grant permission to follow a symlink outside the data root.
    outside = tmp_path / "outside.fasta"
    outside.write_text("private", encoding="utf-8")
    linked = data_root / "linked.fasta"
    linked.symlink_to(outside)
    (run / "workflow.csv").write_text("fasta\nlinked.fasta\n", encoding="utf-8")
    query = urlencode({"context": context, "path": linked.name})
    assert resolve(f"/api/source?{query}", web, Store(root)).status == 403

    # Workflow snapshots themselves must also stay inside the run.
    (run / "run.json").write_text(json.dumps({"workflow_table": str(outside)}), encoding="utf-8")
    assert resolve(f"/api/source?{query}", web, Store(root)).status == 404
