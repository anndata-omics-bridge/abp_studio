"""The fixture store keeps vendor tables plain or gzipped, and reads either the same way."""

from __future__ import annotations

import gzip
from pathlib import Path

from apb_studio import proteobench_fixtures as rawdb
from apb_studio.corpus.tables import resolve_secondary_inputs
from apb_studio.table_storage import (
    GzipTable,
    GzipTables,
    PlainTable,
    PlainTables,
    find_stored_table,
    stored_table,
)

SUBMISSION = {
    "input_file.tsv": "Run\tIntensity\nA\t1\n",
    "input_file_secondary.tsv": "Run\tScore\nA\t0.5\n",
    "param_0..txt": "fasta = human\n",
    "comment.txt": "submitted\n",
    "result_performance.csv": "metric,value\n",
}


def _submission(folder: Path) -> Path:
    folder.mkdir(parents=True)
    for name, text in SUBMISSION.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_gzip_storage_compresses_only_a_submissions_input_tables(tmp_path: Path) -> None:
    packed = _submission(tmp_path / "packed")
    plain = _submission(tmp_path / "plain")

    GzipTables().keep_extracted(packed)
    PlainTables().keep_extracted(plain)

    assert {path.name for path in packed.iterdir()} == {
        "input_file.tsv.gz",
        "input_file_secondary.tsv.gz",
        "param_0..txt",
        "comment.txt",
        "result_performance.csv",
    }
    assert (
        gzip.decompress((packed / "input_file.tsv.gz").read_bytes()).decode()
        == (SUBMISSION["input_file.tsv"])
    )
    assert {path.name for path in plain.iterdir()} == set(SUBMISSION)


def test_a_parquet_submission_table_stays_as_written(tmp_path: Path) -> None:
    (tmp_path / "input_file.parquet").write_bytes(b"PAR1")

    GzipTables().keep_extracted(tmp_path)

    assert [path.name for path in tmp_path.iterdir()] == ["input_file.parquet"]


def test_a_parquet_record_file_stays_as_written(tmp_path: Path) -> None:
    """apb2 refuses gzipped Parquet, so a downloaded Parquet table is stored as it came."""
    download = tmp_path / "single__report.parquet"
    download.write_bytes(b"PAR1")

    GzipTables().keep_download(download, tmp_path / "report.parquet", table=True)

    assert [path.name for path in tmp_path.iterdir()] == ["report.parquet"]


def test_a_workbook_named_like_a_text_table_stays_as_written(tmp_path: Path) -> None:
    """ProlineStudio and MSAngel submit .xlsx workbooks as input_file.txt."""
    workbook = tmp_path / "input_file.txt"
    workbook.write_bytes(b"PK\x03\x04 rest of an xlsx archive")

    GzipTables().keep_extracted(tmp_path)

    assert [path.name for path in tmp_path.iterdir()] == ["input_file.txt"]


def test_a_stored_table_reads_the_same_plain_or_gzipped(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "peptides.txt.gz").write_bytes(gzip.compress(b"id\n2\n"))

    assert find_stored_table(tmp_path, "evidence.txt") == PlainTable(tmp_path / "evidence.txt")
    assert find_stored_table(tmp_path, "peptides.txt") == GzipTable(tmp_path / "peptides.txt.gz")
    assert find_stored_table(tmp_path, "proteinGroups.txt") is None
    packed = stored_table(tmp_path / "peptides.txt.gz")
    assert packed.name == "peptides.txt"
    with packed.open_text() as handle:
        assert handle.read() == "id\n2\n"


def test_a_gzipped_table_is_summarized_like_its_plain_table(tmp_path: Path) -> None:
    plain = tmp_path / "input_file.tsv"
    plain.write_text(SUBMISSION["input_file.tsv"], encoding="utf-8")
    packed = tmp_path / "input_file.tsv.gz"
    packed.write_bytes(gzip.compress(plain.read_bytes()))

    expected = rawdb.summarize_table(plain)
    produced = rawdb.summarize_table(packed)

    assert produced["size_bytes"] == packed.stat().st_size
    assert {**produced, "size_bytes": None} == {**expected, "size_bytes": None}


def test_companions_of_a_gzipped_primary_table_are_found(tmp_path: Path) -> None:
    packed = _submission(tmp_path / "submissions" / "packed")
    GzipTables().keep_extracted(packed)

    found = resolve_secondary_inputs(tmp_path, "submissions/packed/input_file.tsv.gz")

    assert found == ((packed / "input_file_secondary.tsv.gz").resolve(),)
