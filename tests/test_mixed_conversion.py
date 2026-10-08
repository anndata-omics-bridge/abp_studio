"""Mixed parameter inputs keep full conversion and aggregation dependency contracts."""

import sys
from pathlib import Path

import pytest

from apb_studio.corpus import runs
from apb_studio.corpus.discovery import workflow_parameter_inputs
from apb_studio.corpus.models import Dataset, ExecutionSettings, StorageFormat
from apb_studio.corpus.runs import dataset_dependencies, prepare_run
from apb_studio.corpus.tables import CORPUS_COLUMNS, write_rows
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.workflows.workflow_aggregate import steps as aggregate_steps
from apb_studio.workflows.workflow_aggregate_medpolish import steps as medpolish_steps
from apb_studio.workflows.workflow_convert import steps as convert_steps


def _dataset(input_file: str, parameters: str = "", software: str = "MaxQuant") -> Dataset:
    return Dataset(
        input_file=input_file,
        vendor_parameter_file=parameters,
        module="directlfq",
        software_name=software,
    )


def _context(tmp_path: Path, dataset: Dataset, storage_format: StorageFormat) -> WorkflowContext:
    table = tmp_path / "workflow_aggregate.csv"
    write_rows(
        table,
        ["software_name", "method"],
        [{"software_name": dataset.software_name, "method": "all"}],
    )
    return WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset,
        workflow_table=table,
        format=storage_format,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb2": tmp_path / "apb2", "apb-aggregate": tmp_path / "apb-aggregate"},
    )


@pytest.mark.parametrize("has_parameters", [False, True])
@pytest.mark.parametrize(
    ("storage_format", "suffix"),
    [("hdf5", ".h5mu"), ("parquet", ".parquet"), ("duckdb", ".duckdb")],
)
def test_full_conversion_preserves_all_compatible_levels_with_optional_parameters(
    tmp_path: Path, has_parameters: bool, storage_format: StorageFormat, suffix: str
) -> None:
    source = tmp_path / "MaxQuant"
    source.mkdir()
    (source / "evidence.txt").write_text("ion", encoding="utf-8")
    (source / "peptides.txt").write_text("peptide", encoding="utf-8")
    row = _dataset("MaxQuant", "params.xml" if has_parameters else "")
    context = _context(tmp_path, row, storage_format)

    step = convert_steps(context)[0]

    assert step.command[2] == str(source)
    assert "--level" not in step.command
    assert step.outputs[0].path.name == f"converted{suffix}"
    assert step.outputs[1].path.name == f"converted{suffix}.apb.json"
    assert step.command[step.command.index("--format") + 1] == storage_format
    assert step.command[step.command.index("--software") + 1] == "maxquant"
    assert ("--params" in step.command) == has_parameters
    if has_parameters:
        assert step.command[step.command.index("--params") + 1] == str(tmp_path / "params.xml")
        assert [artifact.role for artifact in step.inputs] == [
            "vendor_table",
            "vendor_parameter_file",
        ]
    else:
        assert [artifact.role for artifact in step.inputs] == ["vendor_table"]
        assert str(tmp_path) not in step.command


def test_parameter_free_compound_software_uses_the_result_producer(tmp_path: Path) -> None:
    row = _dataset("report.tsv", software="FragPipe (DIA-NN quant)")
    without_parameters = convert_steps(_context(tmp_path, row, "hdf5"))[0]
    with_parameters = convert_steps(
        _context(
            tmp_path, row.model_copy(update={"vendor_parameter_file": "fragpipe.params"}), "hdf5"
        )
    )[0]

    assert without_parameters.command[without_parameters.command.index("--software") + 1] == "diann"
    assert with_parameters.command[with_parameters.command.index("--software") + 1] == "fragpipe"


@pytest.mark.parametrize("storage_format", ["hdf5", "parquet", "duckdb"])
def test_parameter_free_aggregation_keeps_general_layers_and_primary_medpolish_distinct(
    tmp_path: Path, storage_format: StorageFormat
) -> None:
    context = _context(tmp_path, _dataset("evidence.txt"), storage_format)
    general = aggregate_steps(context)
    medpolish = medpolish_steps(context.model_copy(update={"workflow_table": None}))

    for conversion, aggregation in (general, medpolish):
        assert "--params" not in conversion.command
        assert "--level" not in conversion.command
        assert aggregation.inputs == [conversion.outputs[0]]
        assert conversion.outputs[0].format == aggregation.outputs[0].format == storage_format
    assert general[1].command[3] == "all"
    assert general[1].command[general[1].command.index("--layers") + 1] == "all"
    assert medpolish[1].command[3] == "medpolish"
    assert medpolish[1].command[medpolish[1].command.index("--layers") + 1] == "primary"


@pytest.mark.parametrize("workflow", ["convert", "aggregate", "aggregate_medpolish"])
def test_mixed_corpus_dependencies_track_provided_parameters_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workflow: str
) -> None:
    parameterized = _dataset("parameterized.txt", "params.xml")
    parameter_free = _dataset("parameter_free.txt")
    for row in (parameterized, parameter_free):
        (tmp_path / row.input_file).write_text("data", encoding="utf-8")
    parameters = tmp_path / "params.xml"
    parameters.write_text("parameters", encoding="utf-8")
    corpus = tmp_path / "corpus.csv"
    write_rows(corpus, CORPUS_COLUMNS, [parameterized.model_dump(), parameter_free.model_dump()])
    monkeypatch.setattr(runs, "_tool_version", lambda _executable: "test 1.0")
    settings = ExecutionSettings(
        corpus_name="all",
        corpus=corpus,
        data_root=tmp_path,
        workflow=workflow,
        format="hdf5",
        workflow_table=None,
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )
    root, manifest = prepare_run(
        [parameterized, parameter_free], output_root=tmp_path / "runs", settings=settings
    )
    supplied = dataset_dependencies(root, manifest, parameterized, manifest.reports[0])
    omitted = dataset_dependencies(root, manifest, parameter_free, manifest.reports[1])

    assert parameters in supplied
    assert parameters not in omitted
    assert tmp_path not in omitted
    assert tmp_path / parameter_free.input_file in omitted
    assert Path(runs.__file__).parent / "parameters.py" in supplied


def test_parameter_contract_preserves_ignored_and_required_workflows(tmp_path: Path) -> None:
    parameterized = _dataset("evidence.txt", "params.xml")
    parameter_free = _dataset("evidence.txt")

    assert workflow_parameter_inputs("convert_no_param", tmp_path, parameterized) == ()
    assert workflow_parameter_inputs("convert_no_param", tmp_path, parameter_free) == ()
    assert workflow_parameter_inputs("convert_ion", tmp_path, parameterized) == (
        tmp_path / "params.xml",
    )
    assert workflow_parameter_inputs("convert_ion", tmp_path, parameter_free) == ()
