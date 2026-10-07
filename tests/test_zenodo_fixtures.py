"""Tests for fixtures acquired from Zenodo records."""

from __future__ import annotations

import gzip
import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from apb_studio import fetch, zenodo_fixtures
from apb_studio import proteobench_fixtures as rawdb
from apb_studio.corpus.config import DEFAULT_CORPUSES
from apb_studio.corpus.tables import read_rows, write_rows
from apb_studio.fixture_store import DOWNLOAD_COLUMNS, Store
from apb_studio.zenodo_fixtures import ZenodoConfig, ZenodoDataset, ZenodoRecord


class _Response:
    def __init__(self, *, content: bytes = b"", payload: object = None) -> None:
        self.content = content
        self.status_code = 200
        self.headers = {"Content-Length": str(len(content))}
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload

    def iter_content(self, _size: int) -> Iterator[bytes]:
        yield self.content

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


TABLES = {"evidence.txt": b"id\tIntensity\n0\t7\n", "peptides.txt": b"id\tSequence\n0\tPEP\n"}
REPORT = b"PG.ProteinGroups\tFG.Quantity\nP\t1\n"


def _record() -> ZenodoRecord:
    return ZenodoRecord(
        name="testrecord",
        record_id=42,
        datasets=(
            ZenodoDataset(
                name="related",
                module="some_module",
                software_name="MaxQuant",
                software_version="2.8.1.0",
                parameters="mqpar.xml",
                files={
                    "evidence.txt": "related__evidence.txt.gz",
                    "peptides.txt": "related__peptides.txt.gz",
                    "mqpar.xml": "related__mqpar.xml.gz",
                },
            ),
            ZenodoDataset(
                name="single",
                module="some_module",
                software_name="Spectronaut",
                input="report.tsv",
                files={"report.tsv": "single__report.tsv"},
            ),
        ),
    )


def _remote() -> dict[str, bytes]:
    """Return the record's published file bytes by key."""
    return {
        "related__evidence.txt.gz": gzip.compress(TABLES["evidence.txt"]),
        "related__peptides.txt.gz": gzip.compress(TABLES["peptides.txt"]),
        "related__mqpar.xml.gz": gzip.compress(b"<MaxQuantParams/>"),
        "single__report.tsv": REPORT,
    }


def _serve(
    monkeypatch: pytest.MonkeyPatch, remote: dict[str, bytes], *, md5s: dict[str, str] | None = None
) -> list[str]:
    """Answer record and file requests from ``remote``; return the URLs asked for."""
    asked: list[str] = []
    checksums = md5s or {key: hashlib.md5(data).hexdigest() for key, data in remote.items()}
    payload = {
        "files": [
            {
                "key": key,
                "checksum": f"md5:{checksums[key]}",
                "links": {"self": f"https://zenodo.test/files/{key}/content"},
            }
            for key in remote
        ]
    }

    def _get(url: str, **_kwargs: Any) -> _Response:
        asked.append(url)
        if url == f"{zenodo_fixtures.RECORDS_API}42":
            return _Response(payload=payload)
        key = url.removeprefix("https://zenodo.test/files/").removesuffix("/content")
        return _Response(content=remote[key])

    monkeypatch.setattr(zenodo_fixtures.requests, "get", _get)
    monkeypatch.setattr(fetch.time, "sleep", lambda _seconds: None)
    return asked


def test_packaged_records_keep_the_multifile_fixture_without_a_standalone_corpus_alias() -> None:
    config = zenodo_fixtures.packaged_config()

    assert "directlfq" in DEFAULT_CORPUSES
    assert "maxquant_entrapment" not in DEFAULT_CORPUSES
    entrapment = config.record("maxquant_entrapment").datasets[0]
    assert entrapment.input is None, "the related tables are read together as one folder"
    assert entrapment.parameters == "mqpar.xml"


def test_a_dataset_names_only_files_it_stores() -> None:
    with pytest.raises(ValidationError, match="not one of its files"):
        ZenodoDataset(
            name="x", module="m", software_name="s", files={"a.txt": "a.txt.gz"}, input="b.txt"
        )
    with pytest.raises(ValidationError, match="plain file name"):
        ZenodoDataset(name="x", module="m", software_name="s", files={"sub/a.txt": "a.txt.gz"})


def test_acquire_stores_verified_decompressed_files_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(root=tmp_path)
    record = _record()
    asked = _serve(monkeypatch, _remote())

    zenodo_fixtures.acquire(store, record)

    related = store.zenodo_dataset_dir("testrecord", "related")
    assert {path.name for path in related.iterdir()} == {
        "evidence.txt",
        "peptides.txt",
        "mqpar.xml",
    }
    assert (related / "evidence.txt").read_bytes() == TABLES["evidence.txt"]
    assert (store.zenodo_dataset_dir("testrecord", "single") / "report.tsv").read_bytes() == REPORT

    asked.clear()
    zenodo_fixtures.acquire(store, record)
    assert asked == [], "a stored dataset is not fetched again"


def test_a_checksum_mismatch_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(root=tmp_path)
    remote = _remote()
    md5s = {key: hashlib.md5(data).hexdigest() for key, data in remote.items()}
    md5s["single__report.tsv"] = "0" * 32
    _serve(monkeypatch, remote, md5s=md5s)

    with pytest.raises(OSError, match="MD5 mismatch"):
        zenodo_fixtures.acquire(store, _record())
    single = store.zenodo_dataset_dir("testrecord", "single")
    assert not (single / "report.tsv").exists(), "no unverified file looks finished"
    assert not (single / "single__report.tsv.part").exists()


def test_corpus_rows_name_a_folder_or_a_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(root=tmp_path)
    record = _record()
    assert zenodo_fixtures.corpus_rows(store, record) == [], "nothing stored, nothing exported"
    _serve(monkeypatch, _remote())
    zenodo_fixtures.acquire(store, record)

    assert zenodo_fixtures.corpus_rows(store, record) == [
        {
            "input_file": "zenodo/testrecord/related",
            "vendor_parameter_file": "zenodo/testrecord/related/mqpar.xml",
            "module": "some_module",
            "software_name": "MaxQuant",
        },
        {
            "input_file": "zenodo/testrecord/single/report.tsv",
            "vendor_parameter_file": "",
            "module": "some_module",
            "software_name": "Spectronaut",
        },
    ]


def test_downloads_keep_proteobench_rows_and_refresh_zenodo_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(root=tmp_path)
    record = _record()
    config = ZenodoConfig(schema_version=1, records=(record,))
    monkeypatch.setattr(rawdb, "ZENODO", config)
    proteobench = dict.fromkeys(DOWNLOAD_COLUMNS, "") | {
        "module": "dia_aif",
        "repo_name": "Results_quant_ion_DIA_AIF",
        "intermediate_hash": "abc",
        "status": "not_on_server",
    }
    stale = dict.fromkeys(DOWNLOAD_COLUMNS, "") | {
        "repo_name": "zenodo/retired",
        "intermediate_hash": "gone",
    }
    write_rows(store.downloads_csv, DOWNLOAD_COLUMNS, [proteobench, stale])
    _serve(monkeypatch, _remote())
    zenodo_fixtures.acquire(store, record)

    rawdb._write_zenodo_downloads(store)

    rows = read_rows(store.downloads_csv)
    assert rows[0] == proteobench, "a ProteoBench status survives a Zenodo acquisition"
    assert [(row["repo_name"], row["intermediate_hash"], row["status"]) for row in rows[1:]] == [
        ("zenodo/testrecord", "related", "ok"),
        ("zenodo/testrecord", "single", "ok"),
    ]
    related = store.zenodo_dataset_dir("testrecord", "related")
    assert rows[1]["input_file_path"] == "zenodo/testrecord/related"
    assert int(rows[1]["input_file_size_bytes"]) == sum(
        path.stat().st_size for path in related.iterdir()
    )


def test_acquiring_a_zenodo_record_refreshes_all_without_losing_proteobench_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "test_data_download")
    record = _record()
    folder = store.submission_dir("Repo", "regular")
    folder.mkdir(parents=True)
    (folder / "input_file.tsv").write_text("value\n1\n")
    (folder / "param_0..txt").write_text("params")
    write_rows(
        store.catalog_csv,
        ["repo_name", "intermediate_hash", "module", "software_name"],
        [
            {
                "repo_name": "Repo",
                "intermediate_hash": "regular",
                "module": "dia_astral",
                "software_name": "DIA-NN",
            }
        ],
    )
    monkeypatch.setattr(rawdb, "ZENODO", ZenodoConfig(schema_version=1, records=(record,)))
    monkeypatch.setattr(rawdb, "_store", lambda _root: store)
    monkeypatch.setattr(rawdb.fixture_index, "write", lambda _store: None)
    _serve(monkeypatch, _remote())

    rawdb._acquire_zenodo_corpus(record.name)

    inventories = tmp_path / "corpuses"
    assert len(read_rows(inventories / "testrecord.csv")) == 2
    assert [row["input_file"] for row in read_rows(inventories / "all.csv")] == [
        "submissions/Repo/regular/input_file.tsv",
        "zenodo/testrecord/related",
        "zenodo/testrecord/single/report.tsv",
    ]
