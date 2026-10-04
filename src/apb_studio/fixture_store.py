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
        """One row per ProteoBench submission, with the selection-strategy flags."""
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
        """What ``download`` found on disk for every catalogued submission."""
        return self.root / DOWNLOADS_NAME

    @property
    def fasta_dir(self) -> Path:
        """The ProteoBench reference FASTAs."""
        return self.root / "fasta"

    @property
    def resources_csv(self) -> Path:
        """Which FASTA each module uses, and whether it is present."""
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
