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
from apb_studio.corpus.tables import CORPUS_COLUMNS, load_corpus, read_rows, write_rows
from apb_studio.fixture_store import DOWNLOAD_COLUMNS, Store
from apb_studio.table_storage import GzipTables, PlainTables
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
    corpuses = Path(__file__).parents[1] / "corpuses"

    assert (corpuses / "directlfq.csv").is_file()
    assert not (corpuses / "maxquant_entrapment.csv").exists()
    entrapment = config.record("maxquant_entrapment").datasets[0]
    key = zenodo_fixtures.zenodo_key(config.record("maxquant_entrapment"), entrapment)
    assert key in load_corpus(corpuses / "routine.csv"), "its folder is a routine dataset"
    assert entrapment.input is None, "the related tables are read together as one folder"
    assert entrapment.parameters == "mqpar.xml"


def test_full_metamorpheus_example_is_managed_and_selected_for_routine_conversion() -> None:
    record = zenodo_fixtures.packaged_config().record("apb_examples")
    dataset = record.datasets[0]
    corpuses = Path(__file__).parents[1] / "corpuses"
    key = zenodo_fixtures.zenodo_key(record, dataset)

    assert record.record_id == 23737139
    assert key == "zenodo/apb_examples/metamorpheus_ionstar"
    assert key in load_corpus(corpuses / "apb_examples.csv")
    assert key in load_corpus(corpuses / "routine.csv")
    assert len(load_corpus(corpuses / "routine.csv")) == 14
    assert key not in load_corpus(corpuses / "proteobench.csv")
    assert dataset.input == "QuantifiedPeaks.tsv"
    assert dataset.parameters is None, "FlashLFQ settings are not MetaMorpheus search parameters"
    assert dataset.module == "PXD003881", "the experiment is not a ProteoBench benchmark"
    assert dataset.files[dataset.input] == "metamorpheus_ionstar__QuantifiedPeaks.tsv.gz"
    assert {
        "FlashLfqSettings.toml",
        "PXD003881_community_annotated.sdrf.tsv",
        "sdrf.tsv",
        "provenance.json",
    } <= dataset.files.keys()


def test_fgcz_maxquant_examples_read_all_levels_from_one_folder() -> None:
    record = zenodo_fixtures.packaged_config().record("apb_examples")
    corpuses = Path(__file__).parents[1] / "corpuses"

    for name, module in (
        ("maxquant_dda_qexactive", "dda_qexactive"),
        ("maxquant_dda_astral", "dda_astral"),
    ):
        dataset = next(d for d in record.datasets if d.name == name)
        assert zenodo_fixtures.zenodo_key(record, dataset) in load_corpus(
            corpuses / "apb_examples.csv"
        )
        assert dataset.module == module
        assert dataset.input is None, "the related tables are read together as one folder"
        assert dataset.parameters == "mqpar.xml"
        assert {
            "evidence.txt",
            "modificationSpecificPeptides.txt",
            "peptides.txt",
            "proteinGroups.txt",
        } <= dataset.files.keys()


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

    zenodo_fixtures.acquire(store, record, PlainTables())

    related = store.zenodo_dataset_dir("testrecord", "related")
    assert {path.name for path in related.iterdir()} == {
        "evidence.txt",
        "peptides.txt",
        "mqpar.xml",
    }
    assert (related / "evidence.txt").read_bytes() == TABLES["evidence.txt"]
    assert (store.zenodo_dataset_dir("testrecord", "single") / "report.tsv").read_bytes() == REPORT

    asked.clear()
    zenodo_fixtures.acquire(store, record, PlainTables())
    assert asked == [], "a stored dataset is not fetched again"


def test_gzip_acquisition_keeps_tables_gzipped_and_parameters_plain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(root=tmp_path)
    record = _record()
    asked = _serve(monkeypatch, _remote())

    zenodo_fixtures.acquire(store, record, GzipTables())

    related = store.zenodo_dataset_dir("testrecord", "related")
    single = store.zenodo_dataset_dir("testrecord", "single")
    assert {path.name for path in related.iterdir()} == {
        "evidence.txt.gz",
        "peptides.txt.gz",
        "mqpar.xml",
    }
    assert gzip.decompress((related / "evidence.txt.gz").read_bytes()) == TABLES["evidence.txt"]
    assert (related / "mqpar.xml").read_bytes() == b"<MaxQuantParams/>"
    assert gzip.decompress((single / "report.tsv.gz").read_bytes()) == REPORT
    assert all(zenodo_fixtures.is_present(store, record, dataset) for dataset in record.datasets)
    config = ZenodoConfig(schema_version=1, records=(record,))
    rows = zenodo_fixtures.download_rows(store, config)
    assert [row["input_file_path"] for row in rows] == [
        "zenodo/testrecord/related",
        "zenodo/testrecord/single/report.tsv.gz",
    ], "the manifest names the stored file"
    assert rows[0]["vendor_parameter_file_path"] == "zenodo/testrecord/related/mqpar.xml"
    asked.clear()
    zenodo_fixtures.acquire(store, record, GzipTables())
    assert asked == [], "a stored gzipped dataset is not fetched again"


def test_a_checksum_mismatch_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(root=tmp_path)
    remote = _remote()
    md5s = {key: hashlib.md5(data).hexdigest() for key, data in remote.items()}
    md5s["single__report.tsv"] = "0" * 32
    _serve(monkeypatch, remote, md5s=md5s)

    with pytest.raises(OSError, match="MD5 mismatch"):
        zenodo_fixtures.acquire(store, _record(), PlainTables())
    single = store.zenodo_dataset_dir("testrecord", "single")
    assert not (single / "report.tsv").exists(), "no unverified file looks finished"
    assert not (single / "single__report.tsv.part").exists()


def test_manifest_rows_name_a_folder_or_a_table_once_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(root=tmp_path)
    record = _record()
    config = ZenodoConfig(schema_version=1, records=(record,))
    before = zenodo_fixtures.download_rows(store, config)
    assert [(row["dataset"], row["status"], row["input_file_path"]) for row in before] == [
        ("zenodo/testrecord/related", "not_selected", ""),
        ("zenodo/testrecord/single", "not_selected", ""),
    ]
    assert before[0]["dataset_dir"] == "zenodo/testrecord/related", "known before download"
    _serve(monkeypatch, _remote())
    zenodo_fixtures.acquire(store, record, PlainTables())

    rows = zenodo_fixtures.download_rows(store, config)

    assert [tuple(row) for row in rows] == [DOWNLOAD_COLUMNS] * 2
    assert [
        (row["input_file_path"], row["vendor_parameter_file_path"], row["software_name"])
        for row in rows
    ] == [
        ("zenodo/testrecord/related", "zenodo/testrecord/related/mqpar.xml", "MaxQuant"),
        ("zenodo/testrecord/single/report.tsv", "", "Spectronaut"),
    ]
    related = store.zenodo_dataset_dir("testrecord", "related")
    assert int(rows[0]["input_file_size_bytes"]) == sum(
        path.stat().st_size for path in related.iterdir()
    )


def test_download_fetches_exactly_what_a_corpus_lists_and_writes_no_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "test_data_download")
    record = _record()
    folder = store.submission_dir("Repo", "regular")
    folder.mkdir(parents=True)
    (folder / "input_file.tsv.gz").write_bytes(gzip.compress(b"value\n1\n"))
    (folder / "param_0..txt").write_text("params")
    write_rows(
        store.catalog_csv,
        ["repo_name", "intermediate_hash", "module", "software_name", "software_version"],
        [
            {
                "repo_name": "Repo",
                "intermediate_hash": hash_,
                "module": "dia_astral",
                "software_name": "DIA-NN",
                "software_version": "2.3",
            }
            for hash_ in ("regular", "other")
        ],
    )
    corpuses = tmp_path / "corpuses"
    pair = corpuses / "pair.csv"
    write_rows(
        pair,
        CORPUS_COLUMNS,
        [
            {"dataset": "Repo/regular", "note": "stored gzipped"},
            {"dataset": "zenodo/testrecord/single", "note": ""},
        ],
    )
    monkeypatch.setattr(rawdb, "ZENODO", ZenodoConfig(schema_version=1, records=(record,)))
    monkeypatch.setattr(rawdb, "_store", lambda _root: store)
    monkeypatch.setattr(rawdb, "catalog", lambda *, store: None)
    monkeypatch.setattr(rawdb, "resources", lambda *, store: None)
    monkeypatch.setattr(rawdb.fixture_index, "write", lambda _store: None)
    _serve(monkeypatch, _remote())

    rawdb.acquire("pair", PlainTables())

    assert (store.zenodo_dataset_dir("testrecord", "single") / "report.tsv").is_file()
    assert not store.zenodo_dataset_dir("testrecord", "related").exists(), "not listed"
    rows = {row["dataset"]: row for row in read_rows(store.downloads_csv)}
    assert {key: row["status"] for key, row in rows.items()} == {
        "Repo/regular": "ok",
        "Repo/other": "not_selected",
        "zenodo/testrecord/related": "not_selected",
        "zenodo/testrecord/single": "ok",
    }
    assert rows["Repo/regular"]["input_file_path"] == ("submissions/Repo/regular/input_file.tsv.gz")
    assert rows["Repo/regular"]["vendor_parameter_file_path"] == (
        "submissions/Repo/regular/param_0..txt"
    )
    assert sorted(path.name for path in corpuses.iterdir()) == ["pair.csv"]

    write_rows(pair, CORPUS_COLUMNS, [{"dataset": "Repo/typo", "note": ""}])
    with pytest.raises(ValueError, match=r"nothing provides: \['Repo/typo'\]"):
        rawdb.acquire("pair", PlainTables())
    with pytest.raises(ValueError, match="Unknown corpus 'absent'; available: all, pair"):
        rawdb.acquire("absent", PlainTables())
