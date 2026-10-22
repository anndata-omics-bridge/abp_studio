"""Project the search parameters APB recorded into one static run summary.

apb2 records the parameter file it read in the root part's parse provenance. This module only
reads that record from the displayed representation and counts, per software, the datasets
where each setting was recovered; Studio never parses a parameter file.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from apb_studio.corpus.models import DatasetReport, Record, RunManifest, write_record
from apb_studio.corpus.oddities import representation_candidates

SETTINGS = {
    "software_version": "Version",
    "acquisition_method": "Acquisition",
    "enzyme": "Enzyme",
    "allowed_miscleavages": "Missed cleavages",
    "precursor_mass_tolerance": "Precursor tol.",
    "fragment_mass_tolerance": "Fragment tol.",
    "fixed_mods": "Fixed mods",
    "variable_mods": "Variable mods",
    "ident_fdr_psm": "PSM FDR",
    "ident_fdr_protein": "Protein FDR",
    "max_precursor_charge": "Max. charge",
    "min_peptide_length": "Min. length",
}
"""The settings of the article's Figure S1, in its column order, with its labels."""


class SearchSetting(Record):
    name: str
    label: str


class RecordedParameters(Record):
    """The parameter file one result records, and which settings it recovered."""

    file_name: str
    sha256: str
    recovered: list[str]
    """Recovered setting names, in ``SETTINGS`` order."""


class DatasetSearchSettings(Record):
    dataset: str
    input_file: str
    vendor_parameter_file: str
    software_name: str
    module: str
    status: str
    source_path: str = ""
    parameters: RecordedParameters | None = None
    notes: list[str] = Field(default_factory=list)


class SoftwareSearchSettings(Record):
    software_name: str
    dataset_count: int
    recorded_count: int
    """Datasets whose result records a parameter file; every count in ``recovered`` is of these."""
    recovered: dict[str, int]


class RunSearchSettings(Record):
    format: Literal["apb-studio-search-settings"] = "apb-studio-search-settings"
    format_version: Literal[1] = 1
    run_id: str
    settings: list[SearchSetting]
    datasets: list[DatasetSearchSettings]
    software: list[SoftwareSearchSettings]


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SearchParametersRecord(_Evidence):
    file_name: str
    sha256: str
    parameters: dict[str, JsonValue]


class ParseProvenance(_Evidence):
    search_parameters: SearchParametersRecord | None = None


class ParseRecord(_Evidence):
    provenance: ParseProvenance = Field(default_factory=ParseProvenance)


class RootApb(_Evidence):
    parse: ParseRecord = Field(default_factory=ParseRecord)


class RootPart(_Evidence):
    apb: RootApb = Field(default_factory=RootApb)


class SearchParameterEvidence(_Evidence):
    """Validate just the path to the root parse record, leaving the rest of the sidecar."""

    format: Literal["apb2-result-representation"]
    format_version: Literal["6"]
    root: RootPart = Field(default_factory=RootPart)


def recovered(name: str, value: JsonValue) -> bool:
    """The article's rule: an automatic tolerance counts, modifications when one is listed."""
    if name == "acquisition_method":
        return value != "unknown"
    return value not in (None, "", [])


def dataset_search_settings(report: DatasetReport) -> DatasetSearchSettings:
    """Read the record from the first readable representation, the displayed output's first."""
    result = DatasetSearchSettings(**report.dataset.model_dump(), status=report.status)
    for _step, artifact in representation_candidates(report):
        try:
            evidence = SearchParameterEvidence.model_validate_json(artifact.path.read_text())
        except (FileNotFoundError, ValidationError) as error:
            result.notes.append(f"Cannot read representation {artifact.path}: {error}")
            continue
        result.source_path = str(artifact.path)
        record = evidence.root.apb.parse.provenance.search_parameters
        if record is None:
            result.notes.append("The displayed result records no parameter file.")
        else:
            result.parameters = RecordedParameters(
                file_name=record.file_name,
                sha256=record.sha256,
                recovered=[
                    name for name in SETTINGS if recovered(name, record.parameters.get(name))
                ],
            )
        return result
    result.notes.append("No scientific representation is available; search settings are unknown.")
    return result


def publish_search_settings(
    root: Path, manifest: RunManifest, reports: list[DatasetReport]
) -> None:
    """Publish every dataset's record and, per software, datasets recovering each setting."""
    datasets = [dataset_search_settings(report) for report in reports]
    software: list[SoftwareSearchSettings] = []
    for name in sorted({dataset.software_name for dataset in datasets}):
        selected = [dataset for dataset in datasets if dataset.software_name == name]
        recorded = [dataset.parameters for dataset in selected if dataset.parameters]
        counts = Counter(setting for parameters in recorded for setting in parameters.recovered)
        software.append(
            SoftwareSearchSettings(
                software_name=name,
                dataset_count=len(selected),
                recorded_count=len(recorded),
                recovered={setting: counts[setting] for setting in SETTINGS},
            )
        )
    write_record(
        root / "search_settings.json",
        RunSearchSettings(
            run_id=manifest.run_id,
            settings=[SearchSetting(name=name, label=label) for name, label in SETTINGS.items()],
            datasets=datasets,
            software=software,
        ),
    )
