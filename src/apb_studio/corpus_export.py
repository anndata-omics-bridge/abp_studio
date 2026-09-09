"""Acquisition-side export of existing files for independent corpus execution."""

from pathlib import Path

from apb_studio.corpus.tables import CORPUS_COLUMNS, read_rows, write_rows
from apb_studio.fixture_store import Store


def export_corpus(store: Store, target: Path | None = None) -> Path:
    """Export exactly located input/parameter pairs without download-state columns."""
    rows: list[dict[str, str]] = []
    for entry in read_rows(store.catalog_csv):
        folder = store.submission_dir(entry["repo_name"], entry["intermediate_hash"])
        inputs = [path for path in folder.glob("input_file.*") if path.is_file()]
        parameters = [path for path in folder.glob("param_0.*") if path.is_file()]
        if len(inputs) != 1 or len(parameters) != 1:
            continue
        rows.append({
            "input_file": inputs[0].relative_to(store.root).as_posix(),
            "vendor_parameter_file": parameters[0].relative_to(store.root).as_posix(),
            "module": entry["module"],
            "software_name": entry["software_name"],
        })
    destination = target or store.root.parent / "corpuses" / "all.csv"
    write_rows(destination, CORPUS_COLUMNS, rows)
    return destination


def export_proteobench_table(store: Store, directory: Path) -> Path:
    """Copy only the workflow resource mapping into a separately owned table."""
    columns = ("module", "module_toml", "fasta")
    rows = [{key: row[key] for key in columns} for row in read_rows(store.resources_csv)]
    target = directory / "workflow_proteobench.csv"
    write_rows(target, columns, rows)
    return target
