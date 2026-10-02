"""``index.json``, written by the command that changed the store."""

from __future__ import annotations

import json
from pathlib import Path

from apb_studio import fixture_index
from apb_studio.fixture_store import Store


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "store")
    store.submission_dir("Repo", "a").mkdir(parents=True)
    (store.submission_dir("Repo", "a") / "input_file.tsv").write_text("x\n1\n", encoding="utf-8")
    store.fasta_dir.mkdir()
    (store.fasta_dir / "ref.fasta").write_text(">P\nAA\n", encoding="utf-8")
    store.catalog_csv.write_text("module\ndda\n", encoding="utf-8")
    return store


def test_the_index_names_the_stores_files(tmp_path: Path) -> None:
    document = fixture_index.build(_store(tmp_path))
    assert document["fasta"] == ["ref.fasta"]
    assert "modules" not in document and "modules" not in document["bytes"]
    assert [table["name"] for table in document["tables"]] == ["catalog.csv"]
    assert document["bytes"]["fasta"] == 6


def test_the_index_publishes_the_summary_url_pattern(tmp_path: Path) -> None:
    """The viewer composes a summary URL and asks for it; presence is the download status."""
    store = _store(tmp_path)
    pattern = fixture_index.build(store)["submissionSummary"]
    filled = pattern.format(repo_name="Repo", intermediate_hash="a")
    assert store.root / filled == store.submission_summary("Repo", "a")
    assert "submissions" not in fixture_index.build(store), "no listing to go stale"


def test_write_puts_the_index_in_the_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    written = fixture_index.write(store)
    assert written == store.index_json
    assert json.loads(written.read_text(encoding="utf-8"))["root"] == str(store.root)

    fresh = Store(tmp_path / "fresh")
    assert json.loads(fixture_index.write(fresh).read_text(encoding="utf-8"))["tables"] == []
