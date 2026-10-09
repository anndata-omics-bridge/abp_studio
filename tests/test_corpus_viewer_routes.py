"""Corpus viewer reads files only: runs, the viewer bundle, and the fixture store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apb_studio.corpus.models import Dataset
from apb_studio.corpus.publish import publish_site
from apb_studio.corpus.viewer_inputs import (
    INPUT_KINDS_NAME,
    REFERENCES_NAME,
    write_viewer_inputs,
)
from apb_studio.corpus_viewer.routes import corpus_resolver
from apb_studio.fixture_store import Store


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


def _dataset(input_file: str) -> Dataset:
    return Dataset(
        input_file=input_file, vendor_parameter_file="", module="test", software_name="Vendor"
    )


def test_fixture_store_is_served_as_files_beside_runs_and_no_route_computes(
    tmp_path: Path,
) -> None:
    fixtures = tmp_path / "fixtures"
    table = fixtures / "submissions" / "repo" / "hash" / "input file.tsv"
    table.parent.mkdir(parents=True)
    table.write_text("a\tb\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    (fixtures / "linked.txt").symlink_to(tmp_path / "secret.txt")
    runs = tmp_path / "corpus"
    run = _write_run(runs, "routine", "succeeded")
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    resolve = corpus_resolver(fixtures)

    viewed = resolve("/fixtures/submissions/repo/hash/input%20file.tsv?view=1", web, Store(runs))
    assert viewed.status == 200
    assert viewed.file == table
    assert ("Content-Disposition", "inline; filename*=UTF-8''input%20file.tsv") in viewed.headers

    listing = resolve("/fixtures/submissions/repo/hash?view=1", web, Store(runs))
    assert listing.status == 200
    assert b'href="/fixtures/submissions/repo/hash/input%20file.tsv?view=1"' in listing.body

    assert resolve("/fixtures/../secret.txt", web, Store(runs)).status in {403, 404}
    assert resolve("/fixtures/linked.txt?view=1", web, Store(runs)).status == 403
    assert resolve("/data/routine/convert/hdf5/run.json", web, Store(runs)).file == run / "run.json"
    assert resolve("/api/catalog", web, Store(runs)).status == 404


def test_run_records_input_kinds_and_strict_proteobench_references(tmp_path: Path) -> None:
    data_root = tmp_path / "inputs"
    store = Store(data_root)
    submission = "submissions/repo-a/hash/input.tsv"
    mismatched = "submissions/repo-b/hash/input.tsv"
    absent = "submissions/repo-c/hash/input.tsv"
    folder = "zenodo/record/folder.with.dots"
    for path in (submission, mismatched, absent):
        (data_root / path).parent.mkdir(parents=True)
        (data_root / path).write_text("vendor table", encoding="utf-8")
    (data_root / folder).mkdir(parents=True)
    for repo, identity in (("repo-a", "hash"), ("repo-b", "other")):
        metadata = store.metadata_json(repo, "hash")
        metadata.parent.mkdir(parents=True)
        metadata.write_text(
            json.dumps({
                "intermediate_hash": identity,
                "results": {"1": {"error": 0.1, "missing": float("nan")}},
                "note": "NaN stays text",
            }),
            encoding="utf-8",
        )
    run = tmp_path / "run"
    run.mkdir()
    rows = [_dataset(path) for path in (submission, mismatched, absent, folder, "missing.tsv")]

    write_viewer_inputs(run, rows, data_root)

    kinds = json.loads((run / INPUT_KINDS_NAME).read_text(encoding="utf-8"))
    assert kinds == {
        "schema_version": 2,
        "input_kinds": {submission: "file", mismatched: "file", absent: "file", folder: "folder"},
    }
    references = json.loads((run / REFERENCES_NAME).read_text(encoding="utf-8"))
    assert list(references["references"]) == [submission]
    reference = references["references"][submission]
    assert reference["path"] == "metadata/repo-a/hash.json"
    assert reference["document"]["results"]["1"] == {"error": 0.1, "missing": None}
    assert reference["document"]["note"] == "NaN stays text"

    escaping = tmp_path / "escaping"
    escaping.mkdir()
    (data_root / "linked.tsv").symlink_to(tmp_path / "run" / INPUT_KINDS_NAME)
    with pytest.raises(ValueError, match="escapes data root"):
        write_viewer_inputs(escaping, [_dataset("linked.tsv")], data_root)


def test_publish_copies_viewer_and_visible_runs_without_scheduler_state(tmp_path: Path) -> None:
    store = tmp_path / "corpus"
    live = _write_run(store, "live", "succeeded")
    (live / "reports").mkdir()
    (live / "reports" / "key.json").write_text("{}", encoding="utf-8")
    (live / ".snakemake").mkdir()
    (live / ".snakemake" / "metadata").write_text("scheduler", encoding="utf-8")
    (live / "run.lock").write_text("", encoding="utf-8")
    _write_run(store, "cleaned", "cleaned")
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (web / "assets" / "corpus.js").write_text("", encoding="utf-8")
    site = tmp_path / "site"

    copied = publish_site(store, web, site)

    assert copied == [site / "data" / "live" / "convert" / "hdf5"]
    assert (site / "index.html").is_file()
    assert (site / "assets" / "corpus.js").is_file()
    published = site / "data" / "live" / "convert" / "hdf5"
    assert (published / "reports" / "key.json").is_file()
    assert not (published / ".snakemake").exists()
    assert not (published / "run.lock").exists()
    assert not (site / "data" / "cleaned").exists()
    catalog = json.loads((site / "data" / "index.json").read_text(encoding="utf-8"))
    assert catalog["runs"] == ["live/convert/hdf5/run.json"]

    with pytest.raises(ValueError, match="empty folder"):
        publish_site(store, web, site)
