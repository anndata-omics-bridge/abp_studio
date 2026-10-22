"""Recorded search parameters, counted once per dataset and per software."""

import json
from pathlib import Path
from typing import Any

from apb_studio.corpus.models import Artifact, Dataset, DatasetReport, RunManifest, StepResult
from apb_studio.corpus.search_settings import (
    SETTINGS,
    RunSearchSettings,
    dataset_search_settings,
    publish_search_settings,
)

PARAMETERS: dict[str, Any] = {
    "software_name": "Synthetic",
    "software_version": "1.0",
    "acquisition_method": "unknown",
    "enzyme": "Trypsin/P",
    "allowed_miscleavages": 2,
    "precursor_mass_tolerance": {"mode": "automatic"},
    "fragment_mass_tolerance": None,
    "fixed_mods": [],
    "variable_mods": [{"name": "Oxidation", "target": "M"}],
    "ident_fdr_psm": 0.0,
    "ident_fdr_protein": None,
    "max_precursor_charge": "",
    "min_peptide_length": 7,
}


def _sidecar(path: Path, record: dict[str, Any] | None) -> Artifact:
    sidecar = path.with_name(f"{path.name}.apb.json")
    provenance = {"search_parameters": record} if record else {}
    sidecar.write_text(
        json.dumps({
            "format": "apb2-result-representation",
            "format_version": "7",
            "root": {"apb": {"parse": {"provenance": provenance}}},
            "levels": [{"name": "ion", "apb": {}}],
        })
    )
    return Artifact(role="representation", path=sidecar, size_bytes=sidecar.stat().st_size)


def _report(name: str, software: str, steps: list[StepResult]) -> DatasetReport:
    return DatasetReport(
        run_id="test",
        workflow="convert",
        format="hdf5",
        dataset=Dataset(
            dataset=f"Repo/{name}",
            input_file=f"{name}.tsv",
            vendor_parameter_file=f"{name}.params" if software != "Free" else "",
            module="dda",
            software_name=software,
        ),
        steps=steps,
        status="succeeded" if steps and steps[-1].status == "succeeded" else "failed",
    )


def _converted(folder: Path, name: str, record: dict[str, Any] | None) -> list[StepResult]:
    """One conversion writing two split outputs, each with its own sidecar."""
    outputs: list[Artifact] = []
    for part in ("ion", "protein"):
        path = folder / f"{name}_{part}.h5ad"
        outputs += [Artifact(role="converted", path=path, size_bytes=10), _sidecar(path, record)]
    return [StepResult(name="convert", command=["apb2"], status="succeeded", outputs=outputs)]


def _record(**changes: Any) -> dict[str, Any]:
    return {"file_name": "params.txt", "sha256": "0" * 64, "parameters": PARAMETERS | changes}


def test_the_article_rule_decides_what_counts_as_recovered(tmp_path: Path) -> None:
    result = dataset_search_settings(
        _report("a", "Synthetic", _converted(tmp_path, "a", _record()))
    )

    assert result.parameters is not None
    assert result.parameters.file_name == "params.txt"
    assert result.parameters.recovered == [
        "software_version",
        "enzyme",
        "allowed_miscleavages",
        "precursor_mass_tolerance",
        "variable_mods",
        "ident_fdr_psm",
        "min_peptide_length",
    ]
    assert result.source_path.endswith("a_protein.h5ad.apb.json")


def test_a_result_without_a_record_or_a_representation_is_listed_not_counted(
    tmp_path: Path,
) -> None:
    unrecorded = dataset_search_settings(_report("b", "Free", _converted(tmp_path, "b", None)))
    failed = dataset_search_settings(
        _report("c", "Synthetic", [StepResult(name="convert", command=["apb2"], status="failed")])
    )

    assert unrecorded.parameters is None
    assert unrecorded.notes == ["The displayed result records no parameter file."]
    assert failed.parameters is None and failed.source_path == ""
    assert failed.notes == [
        "No scientific representation is available; search settings are unknown."
    ]


def test_software_rows_count_each_recorded_dataset_once(tmp_path: Path) -> None:
    reports = [
        _report("a", "Synthetic", _converted(tmp_path, "a", _record())),
        _report("b", "Synthetic", _converted(tmp_path, "b", _record(acquisition_method="DDA"))),
        _report("c", "Synthetic", [StepResult(name="convert", command=["apb2"], status="failed")]),
        _report("d", "Free", _converted(tmp_path, "d", None)),
    ]
    manifest = RunManifest.model_construct(run_id="test")

    publish_search_settings(tmp_path, manifest, reports)

    summary = RunSearchSettings.model_validate_json((tmp_path / "search_settings.json").read_text())
    assert [setting.name for setting in summary.settings] == list(SETTINGS)
    assert [
        (row.software_name, row.dataset_count, row.recorded_count) for row in summary.software
    ] == [
        ("Free", 1, 0),
        ("Synthetic", 3, 2),
    ]
    synthetic = summary.software[1].recovered
    assert synthetic["enzyme"] == 2
    assert synthetic["acquisition_method"] == 1
    assert synthetic["fixed_mods"] == 0
    assert len(summary.datasets) == 4
