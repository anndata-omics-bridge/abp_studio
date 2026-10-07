"""Acquired source files, rather than earlier inventories, define the all corpus."""

from pathlib import Path

from apb_studio.corpus.tables import CORPUS_COLUMNS, load_corpus, read_rows, write_rows
from apb_studio.corpus_export import export_all_corpus, export_corpus
from apb_studio.fixture_store import Store
from apb_studio.zenodo_fixtures import ZenodoDataset, ZenodoRecord


def _proteobench(store: Store) -> list[dict[str, str]]:
    entries = [
        {
            "repo_name": "Repo",
            "intermediate_hash": name,
            "module": module,
            "software_name": "DIA-NN",
        }
        for name, module in (
            ("regular", "dia_astral"),
            ("plasma", "dia_plasma"),
            ("entrapment", "entrapment_dia_astral"),
            ("no-parameters", "dia_astral"),
            ("ambiguous-input", "dia_astral"),
            ("ambiguous-parameters", "dia_astral"),
            ("absent", "dia_astral"),
        )
    ]
    for entry in entries[:-1]:
        folder = store.submission_dir(entry["repo_name"], entry["intermediate_hash"])
        folder.mkdir(parents=True)
        (folder / "input_file.tsv").write_text("intensity\n1\n")
        if entry["intermediate_hash"] != "no-parameters":
            (folder / "param_0..txt").write_text("parameters")
    (store.submission_dir("Repo", "ambiguous-input") / "input_file.csv").write_text("x\n")
    (store.submission_dir("Repo", "ambiguous-parameters") / "param_0..xml").write_text("x")
    write_rows(store.catalog_csv, tuple(entries[0]), [*entries, entries[0]])
    return entries


def _zenodo(store: Store) -> ZenodoRecord:
    record = ZenodoRecord(
        name="fixture",
        record_id=42,
        datasets=(
            ZenodoDataset(
                name="multifile",
                module="entrapment_dia_astral",
                software_name="MaxQuant",
                parameters="mqpar.xml",
                files={"evidence.txt": "evidence.gz", "mqpar.xml": "mqpar.gz"},
            ),
            ZenodoDataset(
                name="single",
                module="directlfq",
                software_name="DIA-NN",
                input="report.tsv",
                files={"report.tsv": "report.gz"},
            ),
            ZenodoDataset(
                name="incomplete",
                module="directlfq",
                software_name="MaxQuant",
                files={"evidence.txt": "other.gz", "peptides.txt": "peptides.gz"},
            ),
        ),
    )
    for dataset in record.datasets:
        folder = store.zenodo_dataset_dir(record.name, dataset.name)
        folder.mkdir(parents=True)
        (folder / next(iter(dataset.files))).write_text("value\n1\n")
    (store.zenodo_dataset_dir(record.name, "multifile") / "mqpar.xml").write_text("params")
    return record


def test_all_unions_every_acquired_source_without_download_status_or_recursive_rows(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "store")
    _proteobench(store)
    record = _zenodo(store)
    store.downloads_csv.write_text("stale,download,metadata\n")
    inventory = tmp_path / "corpuses" / "all.csv"
    write_rows(
        inventory,
        CORPUS_COLUMNS,
        [
            {
                "input_file": "stale/table.tsv",
                "vendor_parameter_file": "",
                "module": "retired",
                "software_name": "gone",
            }
        ],
    )

    assert export_all_corpus(store, inventory, [record]) == inventory

    rows = read_rows(inventory)
    assert list(rows[0]) == list(CORPUS_COLUMNS)
    inputs = [row["input_file"] for row in rows]
    assert inputs == sorted({
        "submissions/Repo/regular/input_file.tsv",
        "submissions/Repo/plasma/input_file.tsv",
        "submissions/Repo/entrapment/input_file.tsv",
        "submissions/Repo/no-parameters/input_file.tsv",
        "zenodo/fixture/multifile",
        "zenodo/fixture/single/report.tsv",
    })
    assert len(load_corpus(inventory)) == 6, "duplicate catalog inputs are published once"
    by_input = {row["input_file"]: row for row in rows}
    assert by_input["submissions/Repo/no-parameters/input_file.tsv"]["vendor_parameter_file"] == ""
    assert by_input["zenodo/fixture/single/report.tsv"]["vendor_parameter_file"] == ""
    assert by_input["zenodo/fixture/multifile"]["vendor_parameter_file"] == (
        "zenodo/fixture/multifile/mqpar.xml"
    )
    scoring = export_corpus(store, tmp_path / "scoring.csv", modules={"dia_astral"})
    assert [row["input_file"] for row in read_rows(scoring)] == [
        "submissions/Repo/regular/input_file.tsv",
        "submissions/Repo/regular/input_file.tsv",
    ], "explicit source exports continue to require parameter pairs"


def test_republication_drops_retired_metadata_and_incomplete_sources_without_deleting_files(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "store")
    entries = _proteobench(store)
    record = _zenodo(store)
    inventory = tmp_path / "all.csv"
    export_all_corpus(store, inventory, [record])
    first = inventory.read_bytes()
    export_all_corpus(store, inventory, [record])
    assert inventory.read_bytes() == first, "rebuilding produces a stable sorted inventory"

    write_rows(store.catalog_csv, tuple(entries[0]), entries[1:])
    export_all_corpus(store, inventory, [])

    assert [row.input_file for row in load_corpus(inventory)] == [
        "submissions/Repo/entrapment/input_file.tsv",
        "submissions/Repo/no-parameters/input_file.tsv",
        "submissions/Repo/plasma/input_file.tsv",
    ]
    assert (store.submission_dir("Repo", "regular") / "input_file.tsv").is_file()
    assert (store.zenodo_dataset_dir("fixture", "single") / "report.tsv").is_file()


def test_all_can_publish_zenodo_acquisition_before_a_proteobench_catalog_exists(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "store")
    record = _zenodo(store)

    inventory = export_all_corpus(store, tmp_path / "all.csv", [record])

    assert [row.input_file for row in load_corpus(inventory)] == [
        "zenodo/fixture/multifile",
        "zenodo/fixture/single/report.tsv",
    ]
