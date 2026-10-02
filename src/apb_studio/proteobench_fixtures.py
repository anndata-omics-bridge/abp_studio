"""Manage ProteoBench fixtures.

``corpus`` refreshes the remote submission catalog, downloads the selected vendor tables
and parameter files, downloads every reference FASTA, and writes the
fixture metadata and runner corpus CSV. ``clean`` deletes fixture-store contents.
``view`` serves the fixture-store browser. The store root is Studio's configured
``test_data_root``.
"""

import csv
import io
import json
import math
import shutil
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from contextlib import chdir
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal, TypedDict

import pandas as pd
import pyarrow.parquet as pq
import requests
from bs4 import BeautifulSoup
from cyclopts import App
from loguru import logger
from pydantic import BaseModel, ConfigDict, field_validator

from apb_studio import fixture_index
from apb_studio.corpus.config import config_path, ensure_config
from apb_studio.corpus_export import export_corpus
from apb_studio.disk import atomic_write_text
from apb_studio.fixture_store import INDEX_NAME, TABLE_NAMES, Store
from apb_studio.fixture_viewer.server import run as serve_store
from apb_studio.proteobench_config import packaged_config
from apb_studio.settings import load_settings

# The modules, their results repositories, their settings URLs and the reference FASTAs are
# ProteoBench's facts and live in config/proteobench.toml; see proteobench_config.py.
CONFIG = packaged_config()

# Connect and read timeouts for every request. Without a read timeout a server that
# accepts the connection and then stops sending hangs the download forever: the socket
# stays ESTABLISHED, no bytes arrive, and nothing on screen ever changes. The read
# timeout applies per chunk, so a stalled transfer fails instead of waiting out the night.
REQUEST_TIMEOUT = (10, 120)

# A stalled transfer costs an attempt, not the whole file: the bytes already on disk stay
# in a ``.part`` file and the next attempt asks for the rest with a Range header. The
# datasets server answers 206, so a 36 MB archive that died at 69% resumes there.
DOWNLOAD_ATTEMPTS = 5
FIRST_RETRY_SECONDS = 2.0
MAX_RETRY_SECONDS = 30.0
CHUNK_BYTES = 1 << 20

ModuleKey = Literal[
    "dda_qexactive",
    "dda_astral",
    "dda_peptidoform",
    "dia_astral",
    "dia_diapasef",
    "dia_aif",
    "dia_zenotof",
    "dia_singlecell",
    "dia_plasma",
    "entrapment_dia_astral",
]

# The three corpus strategies, each a boolean column on the catalog: the smallest
# submission by feature count within the named grouping. Ties go to the lexicographically
# smallest hash. Corpus acquisition uses these flags directly.
STRATEGY_COLUMNS: dict[str, list[str]] = {
    "smallest_per_software_version": ["module", "software_name", "software_version"],
    "smallest_per_software": ["module", "software_name"],
    "smallest_per_module": ["module"],
}

_DELIMITER_NAMES = {"\t": "tab", ",": "comma", ";": "semicolon"}


class _SubmissionMetadata(BaseModel):
    """Validated subset of one ProteoBench submission metadata document."""

    model_config = ConfigDict(extra="ignore")

    intermediate_hash: str | None = None
    software_name: str | None = None
    software_version: str | None = None
    nr_feature: int | float | None = None
    nr_prec: int | float | None = None
    is_temporary: bool | None = None
    old_new: str | None = None

    @field_validator(
        "intermediate_hash", "software_name", "software_version", "old_new", mode="before"
    )
    @classmethod
    def nan_is_missing(cls, value: object) -> object:
        """Read a pandas-style ``NaN`` literal in a text field as no value.

        ProteoBench writes some submission documents with ``NaN`` where a string belongs,
        which is not JSON but is what pydantic's parser hands us as a float.
        """
        if isinstance(value, float) and math.isnan(value):
            return None
        return value


class _CatalogRow(TypedDict):
    """One concrete row written to the submission catalog, before the strategy flags."""

    module: str
    repo_name: str
    intermediate_hash: str
    software_name: str | None
    software_version: str | None
    nr_feature: int | float | None
    is_temporary: bool | None
    old_new: str | None


app = App(name="fixture", help=__doc__, help_on_error=True)
corpus_app = App(
    name="corpus",
    help=(
        "Refresh the catalog; download selected vendor tables, parameter files, and FASTAs; "
        "write catalog.csv, downloads.csv, resources.csv, index.json, "
        "and the selected corpus CSV"
    ),
    help_on_error=True,
)
app.command(corpus_app)


def _store(root: Path | None) -> Store:
    """Return the store at ``root``, or at Studio's configured test-data root."""
    return Store(root=(root if root is not None else load_settings().test_data_root).resolve())


def _feature_count(metadata: _SubmissionMetadata) -> int | float | None:
    """Return the current feature count, falling back to the named legacy field."""
    return metadata.nr_feature if metadata.nr_feature is not None else metadata.nr_prec


def _require(path: Path, previous: str) -> None:
    """Stop with the command to run when a prerequisite file is absent."""
    if not path.is_file():
        raise SystemExit(f"{path.name} not found in {path.parent}. Run '{previous}' first.")


# --- ProteoBench download primitives -----------------------------------------


def _extract_zip(zip_file: zipfile.ZipFile, output_directory: Path) -> None:
    """Extract an archive after rejecting members outside the destination."""
    destination = output_directory.resolve()
    for member in zip_file.infolist():
        target = (destination / member.filename).resolve()
        if target != destination and destination not in target.parents:
            raise RuntimeError(f"Unsafe ZIP member outside destination: {member.filename}")
    zip_file.extractall(destination)


def get_merged_json(repo_url: str) -> Path:
    """Download a results-repo ZIP from GitHub and extract it into the cwd.

    Returns the archive's actual extracted root. GitHub can redirect a historical repository
    URL to a renamed repository, so the ZIP root is discovered from its members instead of
    being derived from the request URL.
    """
    response = requests.get(repo_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    output_directory = Path(repo_url.split("/")[-5])
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
        archive_roots = {
            Path(member.filename).parts[0]
            for member in zip_ref.infolist()
            if member.filename and Path(member.filename).parts
        }
        if len(archive_roots) != 1:
            raise RuntimeError(
                f"Expected one root folder in {repo_url}, found {sorted(archive_roots)}"
            )
        _extract_zip(zip_ref, output_directory)
    return output_directory / archive_roots.pop()


def _hrefs_ending_with(soup: BeautifulSoup, suffix: str) -> list[str]:
    """Return string href targets from one directory listing by suffix."""
    hrefs: list[str] = []
    for link in soup.find_all("a"):
        href = link.get("href")
        if isinstance(href, str) and href.endswith(suffix):
            hrefs.append(href)
    return hrefs


def _accept(part: Path, destination: Path) -> Path:
    """Move a finished download into place, refusing bytes that are not a ZIP."""
    if not part.is_file():
        raise OSError(f"nothing downloaded: {part.name}")
    if not zipfile.is_zipfile(part):
        part.unlink()
        raise OSError(f"not a ZIP archive: {part.name}")
    return part.replace(destination)


def _expected_total(response: Any, resumed_from: int) -> int | None:
    """Read the archive's full length from a response, ``None`` when it says nothing."""
    content_range = response.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[1].strip()
        return int(total) if total.isdigit() else None
    length = response.headers.get("Content-Length", "")
    return resumed_from + int(length) if length.isdigit() else None


def _is_permanent(error: Exception) -> bool:
    """Say whether retrying an HTTP failure could ever help."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500 and status not in {408, 429}


def fetch_zip(url: str, destination: Path, attempts: int = DOWNLOAD_ATTEMPTS) -> Path:
    """Download one archive, resuming a partial file and retrying a stalled transfer.

    Bytes accumulate in ``<destination>.part`` so an interrupted transfer is never mistaken
    for a complete archive. Each attempt asks for the remainder with a ``Range`` header; a
    server that ignores it answers 200 and the file restarts. The archive moves into place
    only once its length matches what the server reports and it reads as a ZIP: a remote
    file replaced between two attempts would otherwise leave two halves spliced together.

    A 4xx other than 408 or 429 is raised at once — no amount of waiting fixes a URL that
    is not there.
    """
    part = destination.with_name(destination.name + ".part")
    destination.unlink(missing_ok=True)
    delay = FIRST_RETRY_SECONDS
    for attempt in range(1, attempts + 1):
        resumed_from = part.stat().st_size if part.is_file() else 0
        headers = {"Range": f"bytes={resumed_from}-"} if resumed_from else {}
        logger.info(
            "downloading: {}{}",
            url,
            f" (resuming at {resumed_from} bytes)" if resumed_from else "",
        )
        try:
            with requests.get(
                url, stream=True, timeout=REQUEST_TIMEOUT, headers=headers
            ) as response:
                if response.status_code == 416:
                    # Nothing left to send — but only believe that if what is on disk is
                    # the length the server names. A shrunken remote file lands here too.
                    total = _expected_total(response, 0)
                    if resumed_from and total in {None, resumed_from}:
                        logger.info("server reports nothing left to send: {}", part.name)
                        return _accept(part, destination)
                    logger.warning("range refused for {} bytes; restarting", resumed_from)
                    part.unlink(missing_ok=True)
                    raise OSError(f"range refused: {resumed_from} bytes on disk, {total} remote")
                if resumed_from and response.status_code != 206:
                    logger.warning("server ignored the range request; restarting {}", part.name)
                    resumed_from = 0
                response.raise_for_status()
                total = _expected_total(response, resumed_from)
                with part.open("ab" if resumed_from else "wb") as handle:
                    for data in response.iter_content(CHUNK_BYTES):
                        handle.write(data)
            size = part.stat().st_size
            if total is not None and size != total:
                raise OSError(f"incomplete download: {size} of {total} bytes")
            return _accept(part, destination)
        except (requests.RequestException, OSError) as error:
            if _is_permanent(error):
                raise
            if attempt == attempts:
                raise
            logger.warning(
                "attempt {}/{} failed ({}); retrying in {:.0f}s", attempt, attempts, error, delay
            )
            time.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_SECONDS)
    raise OSError(f"could not download {url}")  # pragma: no cover - the loop returns or raises


def get_raw_data(
    df: pd.DataFrame,
    base_url: str | None = None,
    output_directory: Path = Path("extracted_files"),
    on_extracted: Callable[[str], object] | None = None,
) -> dict[str, Path]:
    """Download raw quantification files for the submissions listed in `df`.

    Scrapes the datasets-server directory listing, matches folder names to
    `df["intermediate_hash"]`, downloads each matching folder's ZIP(s), and extracts them to
    `output_directory/<hash>/`. Returns `{intermediate_hash: extract_dir}` for the folders
    found. Folders already present and non-empty are skipped (idempotent re-runs).

    `on_extracted` is called with each submission's hash as it lands, so a long run can
    describe each one on the spot instead of only when the whole run ends.
    """
    found: dict[str, Path] = {}
    hash_list = set(df["intermediate_hash"].tolist())
    base_url = base_url if base_url is not None else CONFIG.datasets_base_url

    response = requests.get(base_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    folder_links = [href.strip("/") for href in _hrefs_ending_with(soup, "/")]
    matching_folders = [folder for folder in folder_links if folder in hash_list]

    output_directory.mkdir(parents=True, exist_ok=True)
    for folder in matching_folders:
        extract_dir = output_directory / folder
        # The same rule as `get_datasets_to_download`: a vendor table, not merely a
        # non-empty folder. A folder left half-extracted by an interrupted run must be
        # fetched again, and the two gates disagreeing would strand it for good.
        if extract_dir.is_dir() and any(extract_dir.glob("input_file.*")):
            logger.info("already present, skipping: {}", extract_dir)
            found[folder] = extract_dir
            continue

        folder_url = f"{base_url}{folder}/"
        logger.info("processing folder: {}", folder_url)
        folder_response = requests.get(folder_url, timeout=REQUEST_TIMEOUT)
        folder_response.raise_for_status()
        folder_soup = BeautifulSoup(folder_response.text, "html.parser")

        for zip_file in _hrefs_ending_with(folder_soup, ".zip"):
            zip_url = f"{folder_url}{zip_file}"
            zip_path = fetch_zip(zip_url, output_directory / Path(zip_file).name)
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                _extract_zip(zip_ref, extract_dir)
                logger.info("extracted contents to: {}", extract_dir)
            zip_path.unlink()
            found[folder] = extract_dir
        if folder in found and on_extracted is not None:
            on_extracted(folder)

    return found


def _download_module_jsons(repo_url: str, metadata_dir: Path) -> Path:
    """Replace ``metadata/<repo>/`` with the repository's current submission JSONs.

    Only the metadata snapshot is replaced; a failed replacement restores the previous one.
    Returns the folder containing the ``*.json`` files.
    """
    repo_name = repo_url.split("/")[-5]
    metadata_dir = metadata_dir.resolve()
    target = metadata_dir / repo_name

    metadata_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{repo_name}-", dir=metadata_dir) as temporary:
        staging_root = Path(temporary)
        with chdir(staging_root):
            extracted_dir = staging_root / get_merged_json(repo_url=repo_url)
        if not extracted_dir.is_dir():
            raise RuntimeError(f"Expected extracted folder not found: {extracted_dir}")

        previous = staging_root / "previous"
        if target.exists():
            target.replace(previous)
        try:
            extracted_dir.replace(target)
        finally:
            if previous.exists() and not target.exists():
                previous.replace(target)

    if not target.is_dir():
        raise RuntimeError(f"Expected extracted folder not found: {target}")
    return target


# --- commands ------------------------------------------------------------------


def _strategy_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add one boolean column per selection strategy."""
    ranked = df.dropna(subset=["nr_feature"]).sort_values(
        ["nr_feature", "intermediate_hash"], kind="stable"
    )
    flags: dict[str, Any] = {}
    for column, group_columns in STRATEGY_COLUMNS.items():
        chosen = set(
            ranked
            .groupby(group_columns, dropna=False, as_index=False)
            .head(1)["intermediate_hash"]
            .tolist()
        )
        flags[column] = df["intermediate_hash"].isin(chosen)
    return df.assign(**flags)


def catalog(*, store: Path | None = None) -> None:
    """Refresh the submission catalog for every ProteoBench module.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
    """
    target = _store(store)
    rows: list[_CatalogRow] = []
    for module in CONFIG.modules:
        module_key, repo_url, repo_name = module.name, module.repo_url, module.repo_name
        logger.info("[{}] downloading {}", module_key, repo_url)
        metadata_dir = _download_module_jsons(repo_url, target.metadata_dir)
        json_files = sorted(metadata_dir.glob("*.json"))
        logger.info("[{}] read {} JSON file(s)", module_key, len(json_files))
        for jf in json_files:
            metadata = _SubmissionMetadata.model_validate_json(jf.read_text(encoding="utf-8"))
            rows.append({
                "module": module_key,
                "repo_name": repo_name,
                "intermediate_hash": (
                    metadata.intermediate_hash
                    if metadata.intermediate_hash is not None
                    else jf.stem
                ),
                "software_name": metadata.software_name,
                "software_version": metadata.software_version,
                "nr_feature": _feature_count(metadata),
                "is_temporary": metadata.is_temporary,
                "old_new": metadata.old_new,
            })

    df = _strategy_flags(pd.DataFrame(rows))
    target.root.mkdir(parents=True, exist_ok=True)
    df.to_csv(target.catalog_csv, index=False)
    logger.info("total rows: {}", len(df))
    logger.info("rows per module:\n{}", df["module"].value_counts().to_string())
    for column in STRATEGY_COLUMNS:
        logger.info("{}: {} flagged", column, int(df[column].sum()))
    logger.info("written to {}", target.catalog_csv)
    fixture_index.write(target)


def get_datasets_to_download(
    df: pd.DataFrame,
    output_directory: Path,
) -> tuple[pd.DataFrame, dict[str, Path]]:
    """Split catalog rows into those still to fetch and those already on disk.

    A folder holding no ``input_file.*`` is not a download: a run interrupted while
    extracting leaves one behind, and counting it as present would strand it forever.
    """
    hash_list = set(df["intermediate_hash"].tolist())
    present: dict[str, Path] = {}
    if output_directory.exists():
        for folder in output_directory.iterdir():
            if folder.name in hash_list and folder.is_dir() and any(folder.glob("input_file.*")):
                present[folder.name] = folder
    if not present:
        return df, present
    return df[~df["intermediate_hash"].isin(set(present))], present


def _selected_catalog(df: pd.DataFrame, column: str | None) -> pd.DataFrame:
    """Return rows selected by one validated catalog strategy column."""
    if column is None:
        return df
    if column not in STRATEGY_COLUMNS:
        raise ValueError(f"Unknown corpus selection strategy: {column}")
    values = df[column].astype(str).str.casefold()
    invalid = sorted(set(values) - {"true", "false"})
    if invalid:
        raise ValueError(f"Catalog selection {column!r} has invalid values: {invalid}")
    return df[values == "true"]


def _write_downloads(target: Store, catalog_df: pd.DataFrame, requested: pd.DataFrame) -> None:
    """Describe every catalog row while distinguishing unrequested missing fixtures."""
    requested_keys = {
        (row["repo_name"], row["intermediate_hash"]) for row in requested.to_dict(orient="records")
    }
    out_rows: list[dict[str, Any]] = []
    for row in catalog_df.to_dict(orient="records"):
        repo_name = row["repo_name"]
        intermediate_hash = row["intermediate_hash"]
        if not isinstance(repo_name, str) or not isinstance(intermediate_hash, str):
            raise TypeError("repo_name and intermediate_hash values must be strings")
        record: dict[str, Any] = {
            key: row[key]
            for key in (
                "module",
                "repo_name",
                "intermediate_hash",
                "software_name",
                "software_version",
            )
        }
        extract_dir = target.submission_dir(repo_name, intermediate_hash)
        inputs = sorted(extract_dir.glob("input_file.*")) if extract_dir.is_dir() else []
        if inputs:
            record |= {
                "input_file_path": inputs[0].relative_to(target.root).as_posix(),
                "input_file_size_bytes": inputs[0].stat().st_size,
                "status": "ok",
            }
        elif extract_dir.is_dir():
            record |= {
                "input_file_path": "",
                "input_file_size_bytes": None,
                "status": "input_file_missing",
            }
        else:
            record |= {
                "input_file_path": "",
                "input_file_size_bytes": None,
                "status": (
                    "not_on_server"
                    if (repo_name, intermediate_hash) in requested_keys
                    else "not_selected"
                ),
            }
        out_rows.append(record)

    out_df = pd.DataFrame(out_rows)
    atomic_write_text(target.downloads_csv, out_df.to_csv(index=False))
    logger.info("total rows: {}", len(out_df))
    logger.info("status breakdown:\n{}", out_df["status"].value_counts().to_string())
    logger.info("written to {}", target.downloads_csv)


def _download(target: Store, selected: pd.DataFrame, catalog_df: pd.DataFrame) -> None:
    """Fetch selected catalog rows and refresh the complete on-disk status table."""
    for repo_name, group in selected.groupby("repo_name"):
        if not isinstance(repo_name, str):
            raise TypeError("repo_name values must be strings")
        repo_dir = target.submissions_dir / repo_name
        to_download, present = get_datasets_to_download(group, repo_dir)
        if len(to_download) > 0:
            logger.info(
                "[{}] downloading {} dataset(s) (already present: {})",
                repo_name,
                len(to_download),
                len(present),
            )
            present |= get_raw_data(
                to_download,
                output_directory=repo_dir,
                on_extracted=partial(write_submission_summary, target, repo_name),
            )
        else:
            logger.info("[{}] all {} dataset(s) already present", repo_name, len(group))
        # A summary already written is left alone; one missing because the run that fetched
        # it predates summaries, or was interrupted, is written now.
        for intermediate_hash in sorted(present):
            if not target.submission_summary(repo_name, intermediate_hash).is_file():
                write_submission_summary(target, repo_name, intermediate_hash)
    _write_downloads(target, catalog_df, selected)
    for corpus in CONFIG.corpus_names:
        export_corpus(
            target, _corpus_dir(target) / f"{corpus}.csv", modules=CONFIG.modules_in(corpus)
        )
    fixture_index.write(target)


def _corpus_dir(target: Store) -> Path:
    """Return the directory of the named corpus inventories beside the store."""
    return target.root.parent / "corpuses"


def download(*, store: Path | None = None, module: ModuleKey | None = None) -> None:
    """Download every catalogued submission's vendor table and parameter file.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
        module: Restrict the download to one ProteoBench module.
    """
    target = _store(store)
    _require(target.catalog_csv, "catalog")
    catalog_df = pd.read_csv(target.catalog_csv)
    selected = catalog_df if module is None else catalog_df[catalog_df["module"] == module]
    _download(target, selected, catalog_df)


def resources(*, store: Path | None = None) -> None:
    """Download every reference FASTA and the module data files.

    Module definitions are not fixtures: workflows name apb-proteobench's packaged modules.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
    """
    target = _store(store)
    target.fasta_dir.mkdir(parents=True, exist_ok=True)
    for url in CONFIG.fasta_urls:
        logger.info("downloading {}", url)
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            _extract_zip(zip_file, target.fasta_dir)
    macos_metadata = target.fasta_dir / "__MACOSX"
    if macos_metadata.exists():
        shutil.rmtree(macos_metadata)
    logger.info("extracted FASTAs to {}", target.fasta_dir)

    target.module_data_dir.mkdir(parents=True, exist_ok=True)
    for url in CONFIG.module_data_urls:
        logger.info("downloading {}", url)
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        (target.module_data_dir / url.rsplit("/", 1)[-1]).write_bytes(response.content)
    logger.info("wrote module data to {}", target.module_data_dir)

    _write_resource_summary(target)
    fixture_index.write(target)


def _delimiter(header: str) -> str:
    """Sniff the delimiter of one header line, defaulting to tab."""
    try:
        return csv.Sniffer().sniff(header, delimiters="\t,;").delimiter
    except csv.Error:
        return "\t"


def summarize_table(path: Path) -> dict[str, Any]:
    """Describe one vendor table: format, size, rows, and column names.

    Delimited row counts are line counts after the header, so a quoted field containing a
    newline counts twice; this is a summary, not a parse.
    """
    size = path.stat().st_size
    if path.suffix.lower() == ".parquet":
        parquet = pq.ParquetFile(path)
        names = list(parquet.schema_arrow.names)
        return {
            "format": "parquet",
            "delimiter": "",
            "size_bytes": size,
            "rows": parquet.metadata.num_rows,
            "columns": len(names),
            "column_names": "|".join(names),
        }
    with path.open(encoding="utf-8", errors="replace", newline="") as stream:
        header = stream.readline().rstrip("\r\n")
        rows = sum(1 for _ in stream)
    delimiter = _delimiter(header)
    names = next(csv.reader([header], delimiter=delimiter)) if header else []
    return {
        "format": "delimited",
        "delimiter": _DELIMITER_NAMES.get(delimiter, delimiter),
        "size_bytes": size,
        "rows": rows,
        "columns": len(names),
        "column_names": "|".join(names),
    }


def write_submission_summary(target: Store, repo_name: str, intermediate_hash: str) -> Path | None:
    """Describe one downloaded submission beside its files, returning the path written.

    The viewer asks for this file by name: present means downloaded, absent means not. So
    it is written the moment a submission lands, and nothing has to be aggregated, refreshed
    or recomputed for a page reload to show the truth. ``None`` when the folder holds no
    vendor table.
    """
    folder = target.submission_dir(repo_name, intermediate_hash)
    tables = sorted(folder.glob("input_file.*"))
    if not tables:
        return None
    parameters = sorted(folder.glob("param_0.*"))
    document: dict[str, Any] = {
        "repo_name": repo_name,
        "intermediate_hash": intermediate_hash,
        "input_file": tables[0].relative_to(target.root).as_posix(),
        # The vendor table's own mtime, set when the archive was extracted, rather than
        # the clock now: a summary rewritten later must not claim a later download.
        "downloaded_at": datetime.fromtimestamp(tables[0].stat().st_mtime, UTC).isoformat(
            timespec="seconds"
        ),
        **summarize_table(tables[0]),
        "parameter_file": (parameters[0].relative_to(target.root).as_posix() if parameters else ""),
        "parameter_size_bytes": parameters[0].stat().st_size if parameters else None,
    }
    summary = target.submission_summary(repo_name, intermediate_hash)
    summary.write_text(json.dumps(document, indent=1), encoding="utf-8")
    return summary


def _write_resource_summary(target: Store) -> None:
    """Say which FASTA each module uses, and whether it is there."""
    resource_rows = []
    for module in CONFIG.module_names:
        fasta = target.fasta_dir / CONFIG.fasta_for_module(module)
        resource_rows.append({
            "module": module,
            "fasta": fasta.relative_to(target.root).as_posix(),
            "fasta_present": fasta.is_file(),
        })
    pd.DataFrame(resource_rows).to_csv(target.resources_csv, index=False)
    logger.info("written to {}", target.resources_csv)


@app.command
def clean(
    *,
    store: Path | None = None,
    tables_only: bool = False,
) -> None:
    """Delete downloaded fixtures and generated metadata from the fixture store.

    By default, delete every file and directory inside the store root. With
    ``--tables-only``, delete only ``catalog.csv``, ``downloads.csv``, ``resources.csv``,
    and ``index.json`` while preserving downloaded submission files, FASTAs, and any other
    store contents.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
        tables_only: Delete only catalog.csv, downloads.csv, resources.csv, and index.json.
    """
    target = _store(store)
    if target.root in {Path(target.root.anchor), Path.home().resolve()}:
        raise ValueError("Refusing to clean the filesystem or home root.")
    if not target.root.is_dir():
        raise SystemExit(f"No store to clean: {target.root}")
    entries = (
        [target.root / name for name in (*TABLE_NAMES, INDEX_NAME)]
        if tables_only
        else sorted(target.root.iterdir())
    )
    removed: list[Path] = []
    for path in entries:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
        else:
            continue
        removed.append(path)
    logger.info("removed {} path(s)", len(removed))
    for path in removed:
        logger.info("removed {}", path)


def _acquire_corpus(selection: str | None, destination_name: str, corpus: str = "all") -> None:
    """Acquire one corpus selection and publish its runner-facing CSVs."""
    target = _store(None)
    catalog(store=target.root)
    catalog_df = pd.read_csv(target.catalog_csv)
    modules = CONFIG.modules_in(corpus)
    selected = _selected_catalog(catalog_df[catalog_df["module"].isin(modules)], selection)
    _download(target, selected, catalog_df)
    resources(store=target.root)
    corpus_path = export_corpus(
        target,
        _corpus_dir(target) / destination_name,
        modules=modules,
        selection_column=selection,
    )
    ensure_config(config_path(target.root))
    logger.info("written to {}", corpus_path)
    fixture_index.write(target)


@corpus_app.command(name="all")
def corpus_all() -> None:
    """Download every quant fixture and write corpuses/all.csv."""
    _acquire_corpus(None, "all.csv")


@corpus_app.command(name="entrapment")
def corpus_entrapment() -> None:
    """Download every entrapment fixture and write corpuses/entrapment.csv."""
    _acquire_corpus(None, "entrapment.csv", "entrapment")


@corpus_app.command(name="plasma")
def corpus_plasma() -> None:
    """Download every plasma fixture and write corpuses/plasma.csv."""
    _acquire_corpus(None, "plasma.csv", "plasma")


@corpus_app.command(name="smallest-per-module")
def corpus_smallest_per_module() -> None:
    """Download the smallest fixture per module and write corpuses/routine.csv."""
    _acquire_corpus("smallest_per_module", "routine.csv")


@corpus_app.command(name="smallest-per-software")
def corpus_smallest_per_software() -> None:
    """Download the smallest fixture per module/software and write corpuses/routine.csv."""
    _acquire_corpus("smallest_per_software", "routine.csv")


@corpus_app.command(name="smallest-per-software-version")
def corpus_smallest_per_software_version() -> None:
    """Download the smallest fixture per module/software/version into corpuses/routine.csv."""
    _acquire_corpus("smallest_per_software_version", "routine.csv")


@app.command
def view(*, store: Path | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the browser viewer on the store until interrupted.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
        host: The interface to bind.
        port: The port to bind.
    """
    serve_store(_store(store), host=host, port=port)


def _configure_logging(level: str = "INFO") -> None:
    """Reset loguru and install one stderr sink with a plain format."""
    logger.remove()
    logger.add(sys.stderr, format="<level>{level: <7}</level> | {message}", level=level)


def main() -> None:
    """Run the fixture-store command-line application."""
    _configure_logging()
    app()


if __name__ == "__main__":
    main()
