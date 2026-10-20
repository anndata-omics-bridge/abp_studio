"""The fixture store layout: which file lives where below one root.

Shared by the writer (:mod:`apb_studio.proteobench_fixtures`) and the reader
(:mod:`apb_studio.fixture_viewer.routes`), so neither guesses a path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CATALOG_NAME = "catalog.csv"
DOWNLOADS_NAME = "downloads.csv"
RESOURCES_NAME = "resources.csv"
INDEX_NAME = "index.json"
SUMMARY_NAME = "summary.json"
TABLE_NAMES = (CATALOG_NAME, DOWNLOADS_NAME, RESOURCES_NAME)
# downloads.csv, the fixture manifest: one row per catalogued ProteoBench submission and per
# configured Zenodo dataset. ``dataset`` is ``<repo_name>/<intermediate_hash>``, the key a
# corpus file lists. The paths are the stored files exactly, ``.gz`` included, so a corpus
# never needs to know how the store keeps them; ``dataset_dir`` is where the dataset lives
# whether or not it has been downloaded.
DOWNLOAD_COLUMNS = (
    "dataset",
    "module",
    "repo_name",
    "intermediate_hash",
    "software_name",
    "software_version",
    "dataset_dir",
    "input_file_path",
    "vendor_parameter_file_path",
    "input_file_size_bytes",
    "status",
)
DOWNLOADED = "ok"
"""The manifest status of a dataset whose files are all stored."""


def dataset_key(repo_name: str, intermediate_hash: str) -> str:
    """The key a corpus file names one dataset by."""
    return f"{repo_name}/{intermediate_hash}"


# Where the viewer looks for one submission's summary, given its catalog row. The pattern
# is published in ``index.json`` so the browser composes the URL and asks for the file:
# present means downloaded, absent means not, and nothing has to be aggregated.
SUMMARY_URL_PATTERN = "submissions/{repo_name}/{intermediate_hash}/" + SUMMARY_NAME


@dataclass(frozen=True, slots=True)
class Store:
    """Paths below one fixture-store root."""

    root: Path

    @property
    def catalog_csv(self) -> Path:
        """One row per ProteoBench submission."""
        return self.root / CATALOG_NAME

    @property
    def metadata_dir(self) -> Path:
        """Submission metadata JSONs, one folder per results repository."""
        return self.root / "metadata"

    @property
    def submissions_dir(self) -> Path:
        """Downloaded vendor tables and parameter files, ``<repo>/<hash>/``."""
        return self.root / "submissions"

    @property
    def downloads_csv(self) -> Path:
        """The fixture manifest: what ``download`` found on disk for every known dataset."""
        return self.root / DOWNLOADS_NAME

    @property
    def fasta_dir(self) -> Path:
        """The ProteoBench reference FASTAs."""
        return self.root / "fasta"

    @property
    def sdrf_dir(self) -> Path:
        """Each ProteoBench module's SDRF, as apb-proteobench packages it."""
        return self.root / "sdrf"

    @property
    def resources_csv(self) -> Path:
        """Which FASTA and SDRF each module uses, and whether each is present."""
        return self.root / RESOURCES_NAME

    @property
    def index_json(self) -> Path:
        """The store listing the viewer starts from, written by ``fixture_index``."""
        return self.root / INDEX_NAME

    def metadata_json(self, repo_name: str, intermediate_hash: str) -> Path:
        """Return the metadata document of one submission."""
        return self.metadata_dir / repo_name / f"{intermediate_hash}.json"

    def submission_dir(self, repo_name: str, intermediate_hash: str) -> Path:
        """Return the folder holding one submission's downloaded files."""
        return self.submissions_dir / repo_name / intermediate_hash

    def submission_summary(self, repo_name: str, intermediate_hash: str) -> Path:
        """Return one submission's summary sidecar, written when its files land."""
        return self.submission_dir(repo_name, intermediate_hash) / SUMMARY_NAME

    @property
    def zenodo_dir(self) -> Path:
        """Datasets downloaded from Zenodo records, ``<record>/<dataset>/``."""
        return self.root / "zenodo"

    def zenodo_dataset_dir(self, record: str, dataset: str) -> Path:
        """Return the folder holding one Zenodo dataset's decompressed files."""
        return self.zenodo_dir / record / dataset
