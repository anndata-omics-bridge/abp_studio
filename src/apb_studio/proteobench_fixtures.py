"""The ProteoBench fixture store: download everything, summarise it, serve it.

``catalog`` collects every submission's metadata and flags the three selection strategies
as columns, ``download`` fetches every submission, and ``resources`` fetches both FASTAs
and all module TOMLs. Each of the three summarises what it fetched and rewrites
``index.json``, so there is no separate summarise or publish step. ``all`` runs the three
in order, ``clean`` empties the store and ``serve`` opens the browser viewer on it.
The store root defaults to Studio's configured test-data root.

The download primitives are ported from ``proteobench.utils.server_io`` so this tool needs
no proteobench install.
"""

import csv
import io
import json
import math
import shutil
import sys
import tempfile
import time
import tomllib
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
]

# The three selection strategies, each a boolean column on the catalog: the smallest
# submission by feature count within the named grouping. Ties go to the lexicographically
# smallest hash. They annotate; nothing filters on them.
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


app = App(name="apb-studio-fixtures", help=__doc__, help_on_error=True)


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


@app.command
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


@app.command
def download(*, store: Path | None = None, module: ModuleKey | None = None) -> None:
    """Download every catalogued submission's vendor table and parameter file.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
        module: Restrict the download to one ProteoBench module.
    """
    target = _store(store)
    _require(target.catalog_csv, "catalog")
    df = pd.read_csv(target.catalog_csv)
    if module is not None:
        df = df[df["module"] == module]

    hash_to_dir: dict[str, Path] = {}
    for repo_name, group in df.groupby("repo_name"):
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
        hash_to_dir.update(present)

    out_rows: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
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
        extract_dir = hash_to_dir.get(row["intermediate_hash"])
        inputs = sorted(extract_dir.glob("input_file.*")) if extract_dir is not None else []
        if extract_dir is None:
            record |= {
                "input_file_path": "",
                "input_file_size_bytes": None,
                "status": "not_on_server",
            }
        elif not inputs:
            record |= {
                "input_file_path": "",
                "input_file_size_bytes": None,
                "status": "input_file_missing",
            }
        else:
            record |= {
                "input_file_path": inputs[0].relative_to(target.root).as_posix(),
                "input_file_size_bytes": inputs[0].stat().st_size,
                "status": "ok",
            }
        out_rows.append(record)

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(target.downloads_csv, index=False)
    logger.info("total rows: {}", len(out_df))
    logger.info("status breakdown:\n{}", out_df["status"].value_counts().to_string())
    logger.info("written to {}", target.downloads_csv)
    fixture_index.write(target)


def _validate_module_settings(path: Path) -> None:
    """Reject a download that is not a complete TOML document."""
    with path.open("rb") as handle:
        tomllib.load(handle)


@app.command
def resources(*, store: Path | None = None) -> None:
    """Download both reference FASTAs and every module's settings TOML.

    Each TOML must parse before it replaces the cached copy, so a truncated response never
    lands in the store. Whether it is a valid ProteoBench module is apb-proteobench's call.

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

    target.modules_dir.mkdir(parents=True, exist_ok=True)
    for module in CONFIG.module_names:
        url = CONFIG.settings_url(module)
        logger.info("downloading {}: {}", module, url)
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        destination = target.modules_dir / f"{module}.toml"
        temporary = target.modules_dir / f".{module}.download.toml"
        temporary.write_bytes(response.content)
        try:
            _validate_module_settings(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    logger.info("downloaded {} module settings to {}", len(CONFIG.modules), target.modules_dir)
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
    """Say which module TOML and FASTA each module has, and whether both are there."""
    resource_rows = []
    for module in CONFIG.module_names:
        toml = target.modules_dir / f"{module}.toml"
        fasta = target.fasta_dir / CONFIG.fasta_for_module(module)
        resource_rows.append({
            "module": module,
            "module_toml": toml.relative_to(target.root).as_posix(),
            "module_toml_present": toml.is_file(),
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
    """Empty the store, so the next run starts from nothing.

    Everything in the store root goes, not only what the current commands write: a store
    is entirely re-downloadable, and leftovers from an older layout would otherwise sit
    there being mistaken for live data.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
        tables_only: Remove only the generated tables and index, keeping the downloads.
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


@app.command(name="all")
def run_all(*, store: Path | None = None, module: ModuleKey | None = None) -> None:
    """Run catalog, download and resources in order.

    Args:
        store: The store root; defaults to Studio's configured test-data root.
        module: Restrict the download to one ProteoBench module.
    """
    catalog(store=store)
    download(store=store, module=module)
    resources(store=store)


@app.command
def serve(*, store: Path | None = None, host: str = "127.0.0.1", port: int = 8765) -> None:
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
