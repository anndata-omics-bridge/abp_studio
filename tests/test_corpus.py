"""Execution failures remain reports; input joins and final publication stay strict."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Collection
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apb_studio.corpus import cli, discovery, runner, runs
from apb_studio.corpus.clean import clear_results, delete_run
from apb_studio.corpus.config import corpus_files
from apb_studio.corpus.discovery import (
    available_workflows,
    workflow_path,
    workflow_table_name,
    workflow_tools,
)
from apb_studio.corpus.models import (
    Artifact,
    Dataset,
    DatasetReport,
    ExecutionSettings,
    InputMetadata,
    Operation,
    Record,
    StepResult,
    StorageFormat,
    write_record,
)
from apb_studio.corpus.runner import run_steps
from apb_studio.corpus.runs import (
    dataset_dependencies,
    prepare_run,
    publish_catalog,
    publish_index,
    select_datasets,
)
from apb_studio.corpus.selection import resolve_corpus
from apb_studio.corpus.tables import (
    CORPUS_COLUMNS,
    DATASET_COLUMNS,
    INPUT_METADATA_COLUMNS,
    join_input_metadata,
    join_workflow,
    load_corpus,
    load_datasets,
    read_rows,
    resolve_file,
    resolve_secondary_inputs,
    write_rows,
)
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.fixture_store import DOWNLOAD_COLUMNS
from apb_studio.proteobench_config import packaged_config
from apb_studio.settings import StudioSettings
from apb_studio.workflows.workflow_aggregate import steps as aggregate_steps
from apb_studio.workflows.workflow_aggregate_medpolish import steps as aggregate_medpolish_steps
from apb_studio.workflows.workflow_convert import steps as convert_steps
from apb_studio.workflows.workflow_convert_ion import steps as convert_ion_steps
from apb_studio.workflows.workflow_convert_no_param import steps as convert_no_param_steps
from apb_studio.workflows.workflow_export_msmu import steps as export_msmu_steps
from apb_studio.workflows.workflow_proteobench import WORKFLOW_COLUMNS as PROTEOBENCH_COLUMNS
from apb_studio.workflows.workflow_proteobench import steps as proteobench_steps
from apb_studio.workflows.workflow_proteobench_entrapment import (
    WORKFLOW_COLUMNS as PROTEOBENCH_ENTRAPMENT_COLUMNS,
)
from apb_studio.workflows.workflow_proteobench_entrapment import (
    steps as proteobench_entrapment_steps,
)
from apb_studio.workflows.workflow_proteobench_plasma import (
    WORKFLOW_COLUMNS as PROTEOBENCH_PLASMA_COLUMNS,
)
from apb_studio.workflows.workflow_proteobench_plasma import steps as proteobench_plasma_steps
from apb_studio.workflows.workflow_proteobench_plasma_run import (
    steps as proteobench_plasma_run_steps,
)
from apb_studio.workflows.workflow_proteobench_pmultiqc import (
    WORKFLOW_COLUMNS as PROTEOBENCH_PMULTIQC_COLUMNS,
)
from apb_studio.workflows.workflow_proteobench_pmultiqc import (
    steps as proteobench_pmultiqc_steps,
)
from apb_studio.workflows.workflow_proteobench_run import (
    WORKFLOW_COLUMNS as PROTEOBENCH_RUN_COLUMNS,
)
from apb_studio.workflows.workflow_proteobench_run import steps as proteobench_run_steps
from apb_studio.workflows.workflow_proteobench_run_vendor import (
    steps as proteobench_run_vendor_steps,
)


def dataset() -> Dataset:
    return Dataset(
        dataset="Repo/vendor",
        input_file="vendor.txt",
        vendor_parameter_file="params.txt",
        module="dia_aif",
        software_name="DIA-NN",
    )


REPOSITORY = Path(__file__).parents[1]
SEPARATELY_SCORED = frozenset({"dia_plasma", "entrapment_dia_astral"})
"""Modules with their own scoring workflows rather than workflow_proteobench.csv."""


def committed_corpus(name: str | None) -> list[Dataset]:
    """A committed corpus, or ``all``, resolved through the local fixture manifest.

    Committed corpus files list only keys, so checking a workflow table against their
    modules and software needs the downloaded store; without it the check is skipped.
    """
    manifest = REPOSITORY / "test_data_download" / "downloads.csv"
    if not manifest.is_file():
        pytest.skip("needs the fixture manifest; run `fixture download all`")
    keys = None if name is None else load_corpus(REPOSITORY / "corpuses" / f"{name}.csv")
    return resolve_corpus(keys, manifest).datasets


def write_corpus(path: Path, rows: Collection[Dataset]) -> Path:
    """A hand-curated corpus file listing ``rows`` by key."""
    write_rows(path, CORPUS_COLUMNS, [{"dataset": row.dataset, "note": ""} for row in rows])
    return path


def _size(manifest: Path, row: Dataset) -> str:
    stored = manifest.parent / row.input_file
    return str(stored.stat().st_size) if stored.is_file() else "1"


def write_manifest(path: Path, rows: Collection[Dataset], missing: Collection[str] = ()) -> Path:
    """A fixture manifest storing ``rows``; keys in ``missing`` are known but not downloaded."""
    write_rows(
        path,
        DOWNLOAD_COLUMNS,
        [
            {
                "dataset": row.dataset,
                "module": row.module,
                "repo_name": str(Path(row.dataset).parent),
                "intermediate_hash": Path(row.dataset).name,
                "software_name": row.software_name,
                "software_version": "",
                "dataset_dir": f"store/{row.dataset}",
                "input_file_path": "" if row.dataset in missing else row.input_file,
                "vendor_parameter_file_path": (
                    "" if row.dataset in missing else row.vendor_parameter_file
                ),
                "input_file_size_bytes": "" if row.dataset in missing else _size(path, row),
                "status": "not_selected" if row.dataset in missing else "ok",
            }
            for row in rows
        ],
    )
    return path


def test_csv_minimal_schema_and_explicit_joins(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path / "corpus.csv", [dataset()])
    assert load_corpus(corpus) == ["Repo/vendor"]
    resolved = tmp_path / "datasets.csv"
    row = dataset().model_dump()
    write_rows(resolved, DATASET_COLUMNS, [row])
    assert load_datasets(resolved) == [dataset()]
    table = tmp_path / "workflow_proteobench.csv"
    write_rows(table, ["module", "fasta"], [{"module": "dia_aif", "fasta": "ref.fasta"}])
    assert join_workflow(row, table, on=["module"])["fasta"] == "ref.fasta"
    with pytest.raises(ValueError, match="No workflow row"):
        join_workflow({**row, "module": "other"}, table, on=["module"])
    with pytest.raises(ValueError, match="Invalid explicit"):
        join_workflow(row, table, on=[])
    write_rows(table, ["module", "fasta"], [{"module": "dia_aif", "fasta": "x"}] * 2)
    with pytest.raises(ValueError, match="Duplicate workflow"):
        join_workflow(row, table, on=["module"])
    write_corpus(corpus, [dataset(), dataset()])
    with pytest.raises(ValueError, match="Duplicate dataset"):
        load_corpus(corpus)
    write_rows(resolved, DATASET_COLUMNS, [row, {**row, "dataset": "Repo/other"}])
    with pytest.raises(ValueError, match="Duplicate input_file"):
        load_datasets(resolved)
    corpus.write_text("input_file,status\nx,ok\n")
    with pytest.raises(ValueError, match="exactly"):
        load_corpus(corpus)
    with pytest.raises(ValueError, match="escapes"):
        resolve_file(tmp_path, "../outside")


def test_secondary_inputs_are_fixture_owned_siblings(tmp_path: Path) -> None:
    folder = tmp_path / "submission"
    folder.mkdir()
    primary = folder / "input_file.tsv"
    secondary = folder / "input_file_secondary.tsv"
    primary.write_text("primary", encoding="utf-8")
    secondary.write_text("secondary", encoding="utf-8")
    (folder / "param_0.txt").write_text("parameters", encoding="utf-8")

    assert resolve_secondary_inputs(tmp_path, "submission/input_file.tsv") == (secondary.resolve(),)


def test_a_folder_input_has_no_secondary_inputs(tmp_path: Path) -> None:
    """APB reads the related tables inside a folder by their own names."""
    folder = tmp_path / "dataset"
    folder.mkdir()
    (folder / "evidence.txt").write_text("ion", encoding="utf-8")
    (tmp_path / "dataset_peptides.txt").write_text("not a companion", encoding="utf-8")

    assert resolve_secondary_inputs(tmp_path, "dataset") == ()


def test_a_dataset_without_parameters_refuses_parameter_workflows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = Dataset.model_validate({**dataset().model_dump(), "vendor_parameter_file": ""})
    (tmp_path / row.input_file).write_text("data")
    corpus = write_corpus(tmp_path / "corpus.csv", [row])
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "__init__.py").write_text("")
    (workflows / "workflow_proteobench_run.py").write_text("TOOLS = ('apb2',)\n")
    monkeypatch.setattr(discovery, "WORKFLOWS", workflows)
    monkeypatch.setattr(runs, "_tool_version", lambda _executable: "apb2 1.0")
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path,
        workflow="proteobench_run",
        format="hdf5",
        workflow_table=None,
        downloads=write_manifest(tmp_path / "downloads.csv", [row]),
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )
    root, manifest = prepare_run([row], output_root=tmp_path / "output", settings=settings)

    with pytest.raises(ValueError, match="has no vendor parameter file"):
        runs.dataset_dependencies(root, manifest, row, manifest.reports[0])
    with pytest.raises(ValueError, match="Empty file path"):
        resolve_file(tmp_path, row.vendor_parameter_file)


def test_download_sizes_join_only_selected_inputs_with_explicit_columns(tmp_path: Path) -> None:
    first = dataset()
    second = first.model_copy(update={"input_file": "other.txt"})
    downloads = tmp_path / "downloads.csv"
    write_rows(
        downloads,
        ["input_file_path", "input_file_size_bytes", "status"],
        [
            {
                "input_file_path": first.input_file,
                "input_file_size_bytes": "123",
                "status": "ok",
            },
            {
                "input_file_path": second.input_file,
                "input_file_size_bytes": "456",
                "status": "historical-value-ignored-by-execution",
            },
            {
                "input_file_path": "input_file_path",
                "input_file_size_bytes": "input_file_size_bytes",
                "status": "status",
            },
        ],
    )

    assert join_input_metadata([second], downloads) == [
        InputMetadata(input_file="other.txt", input_file_size_bytes=456)
    ]
    with pytest.raises(ValueError, match="No download row"):
        join_input_metadata([first.model_copy(update={"input_file": "missing.txt"})], downloads)
    write_rows(
        downloads,
        ["input_file_path", "input_file_size_bytes"],
        [
            {"input_file_path": first.input_file, "input_file_size_bytes": "123"},
            {"input_file_path": first.input_file, "input_file_size_bytes": "123"},
        ],
    )
    with pytest.raises(ValueError, match="Duplicate download join key"):
        join_input_metadata([first], downloads)


def test_runner_streams_and_records_failure_then_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshots: list[DatasetReport] = []

    def observe(path: Path, record: Record) -> None:
        snapshots.append(DatasetReport.model_validate_json(record.model_dump_json()))
        write_record(path, record)
        if snapshots[-1].status == "running":
            assert not (tmp_path / "report.json").exists()

    monkeypatch.setattr(runner, "write_record", observe)
    source = tmp_path / "input.txt"
    source.write_text("source")
    output = tmp_path / "output.txt"
    first = StepResult(
        name="first",
        command=[
            sys.executable,
            "-c",
            f"from pathlib import Path; import sys,time; print('hello',flush=True); "
            f"print('warning',file=sys.stderr,flush=True); time.sleep(.6); "
            f"Path({str(output)!r}).write_text('written')",
        ],
        inputs=[Artifact(role="input", path=source)],
        outputs=[Artifact(role="result", path=output)],
    )
    second = StepResult(name="second", command=[sys.executable, "-c", "raise SystemExit(3)"])
    third = StepResult(name="third", command=[sys.executable, "-c", "raise RuntimeError('never')"])
    report = DatasetReport(
        run_id="test",
        workflow="convert",
        format="hdf5",
        dataset=dataset(),
        steps=[first, second, third],
    )
    path = tmp_path / "report.json"
    run_steps(report, path)
    result = DatasetReport.model_validate_json(path.read_text())
    assert result.status == "failed"
    assert [step.status for step in result.steps] == ["succeeded", "failed", "skipped"]
    assert result.steps[0].stdout == "hello\n"
    assert result.steps[0].stderr == "warning\n"
    assert result.steps[0].peak_memory_bytes is not None
    assert result.steps[0].inputs[0].size_bytes == len("source")
    assert result.steps[0].outputs[0].size_bytes == len("written")
    assert result.steps[1].exit_code == 3
    assert result.steps[2].exit_code is None
    assert result.steps[2].runtime_seconds is None
    assert json.loads(path.with_suffix(".progress.json").read_text())["status"] == "failed"
    assert any(
        snapshot.steps[0].status == "running"
        and snapshot.steps[0].stdout == "hello\n"
        and snapshot.runtime_seconds > 0
        for snapshot in snapshots
    )
    console = capsys.readouterr()
    assert console.out == "hello\n"
    assert console.err == "warning\n"


@pytest.mark.parametrize("failure", ["executable", "input", "output"])
def test_expected_tool_failure_still_publishes_report(tmp_path: Path, failure: str) -> None:
    step = StepResult(name="convert", command=[sys.executable, "-c", "pass"])
    if failure == "executable":
        step.command = [str(tmp_path / "missing-tool")]
    if failure == "input":
        step.inputs = [Artifact(role="input", path=tmp_path / "missing-input")]
    if failure == "output":
        step.outputs = [Artifact(role="result", path=tmp_path / "missing-output")]
    report = DatasetReport(
        run_id="test", workflow="convert", format="hdf5", dataset=dataset(), steps=[step]
    )
    path = tmp_path / "report.json"
    run_steps(report, path)
    assert json.loads(path.read_text())["status"] == "failed"
    assert step.errors


def test_reporting_failure_is_not_hidden(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("block")
    report = DatasetReport(
        run_id="test",
        workflow="convert",
        format="hdf5",
        dataset=dataset(),
        steps=[StepResult(name="convert", command=[sys.executable, "-c", "pass"])],
    )
    with pytest.raises(OSError):
        run_steps(report, blocker / "report.json")


def test_runner_records_recursive_directory_artifact_size(tmp_path: Path) -> None:
    output = tmp_path / "result.parquet"
    code = (
        "from pathlib import Path; "
        f"root=Path({str(output)!r}); root.mkdir(); "
        "(root/'a').write_bytes(b'123'); (root/'b').write_bytes(b'4567')"
    )
    report = DatasetReport(
        run_id="test",
        workflow="convert",
        format="parquet",
        dataset=dataset(),
        steps=[
            StepResult(
                name="convert",
                command=[sys.executable, "-c", code],
                outputs=[Artifact(role="result", path=output, format="parquet")],
            )
        ],
    )

    run_steps(report, tmp_path / "report.json")

    assert report.steps[0].outputs[0].size_bytes == 7


def test_runner_records_present_output_when_later_publication_fails(tmp_path: Path) -> None:
    artifact = tmp_path / "result.h5ad"
    representation = tmp_path / "result.h5ad.apb.json"
    code = (
        "from pathlib import Path; import sys; "
        f"Path({str(artifact)!r}).write_bytes(b'artifact'); sys.exit(1)"
    )
    report = DatasetReport(
        run_id="test",
        workflow="convert",
        format="hdf5",
        dataset=dataset(),
        steps=[
            StepResult(
                name="convert",
                command=[sys.executable, "-c", code],
                outputs=[
                    Artifact(role="converted", path=artifact, format="hdf5"),
                    Artifact(role="representation", path=representation),
                ],
            )
        ],
    )

    run_steps(report, tmp_path / "report.json")

    step = report.steps[0]
    assert step.status == "failed"
    assert step.outputs[0].size_bytes == len("artifact")
    assert step.outputs[1].size_bytes is None
    assert any("exited with code 1" in error for error in step.errors)
    assert any(str(representation) in error for error in step.errors)


def test_run_snapshots_selected_download_sizes_without_changing_corpus(tmp_path: Path) -> None:
    first = dataset()
    second = first.model_copy(update={"dataset": "Repo/other", "input_file": "other.txt"})
    for row, content in ((first, "data"), (second, "another")):
        (tmp_path / row.input_file).write_text(content)
    (tmp_path / first.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpuses" / "routine.csv"
    write_corpus(corpus, [first, second])
    downloads = write_manifest(tmp_path / "downloads.csv", [first, second])
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        downloads=downloads,
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )

    root, manifest = prepare_run([second], output_root=tmp_path / "output", settings=settings)

    assert manifest.input_metadata == "input_metadata.csv"
    assert load_datasets(root / manifest.corpus) == [second]
    settings_json = json.loads((root / "execution_settings.json").read_text())
    assert settings_json["downloads"] == str(downloads)
    assert (root / manifest.input_metadata).read_text().splitlines() == [
        ",".join(INPUT_METADATA_COLUMNS),
        "other.txt,7",
    ]
    assert not (root.parents[2] / "settings").exists()


def test_run_snapshots_and_index_validation(tmp_path: Path) -> None:
    row = dataset()
    (tmp_path / row.input_file).write_text("data")
    (tmp_path / row.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpuses" / "routine.csv"
    write_corpus(corpus, [row])
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        downloads=write_manifest(tmp_path / "downloads.csv", [row]),
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )
    root, manifest = prepare_run(
        [row],
        output_root=tmp_path / "output",
        settings=settings,
    )
    snapshots = [
        root / "selected_corpus.csv",
        root / "corpus.csv",
        root / "execution_settings.json",
        root / "workflow_convert.py",
        root / "run.json",
    ]
    modified = {path: path.stat().st_mtime_ns for path in snapshots}
    again, _ = prepare_run(
        [row],
        output_root=tmp_path / "output",
        settings=settings,
    )
    assert again == root
    assert root == tmp_path / "output" / "corpus" / "routine" / "convert" / "hdf5"
    assert manifest.run_id == "routine-convert-hdf5"
    assert manifest.corpus_name == "routine"
    assert {path: path.stat().st_mtime_ns for path in snapshots} == modified
    assert manifest.workflow_table is None
    assert manifest.source_corpus == "corpus.csv"
    assert manifest.corpus == "selected_corpus.csv"
    saved = ExecutionSettings.model_validate_json((root / "execution_settings.json").read_text())
    assert saved.corpus == corpus
    assert saved.workflow_table is None
    assert load_corpus(root / "corpus.csv") == [row.dataset]
    with pytest.raises(FileNotFoundError):
        publish_index(root, manifest)
    report = DatasetReport(
        run_id=manifest.run_id,
        workflow="convert",
        format="hdf5",
        dataset=row,
        steps=[
            StepResult(name="convert", command=["missing"], status="failed", errors=["missing"])
        ],
        status="failed",
    )
    write_record(root / manifest.reports[0].path, report)
    publish_index(root, manifest)
    write_record(root / "operation.json", Operation(status="succeeded"))
    legacy = root.parents[2] / "convert-hdf5-legacy"
    legacy.mkdir()
    (legacy / "run.json").write_text('{"schema_version": 1}\n')
    publish_catalog(root.parents[2])
    assert (root / "corpus_index.json").exists()
    assert json.loads((root.parents[2] / "index.json").read_text())["runs"] == [
        "routine/convert/hdf5/run.json"
    ]
    with pytest.raises(ValueError, match="overlaps"):
        clear_results(root)
    for invalid in ({"schema_version": 1}, {"unknown": True}, {"runtime_seconds": float("nan")}):
        with pytest.raises(ValidationError):
            DatasetReport.model_validate({**report.model_dump(), **invalid})


def test_dependencies_track_shared_workflow_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = dataset()
    (tmp_path / row.input_file).write_text("data")
    secondary = tmp_path / "vendor_secondary.txt"
    secondary.write_text("secondary")
    (tmp_path / row.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpus.csv"
    write_corpus(corpus, [row])
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "__init__.py").write_text("")
    selected = workflows / "workflow_convert.py"
    selected.write_text("TOOLS = ('apb2',)\n")
    helper = workflows / "artifacts.py"
    helper.write_text("REPRESENTATION_SUFFIX = '.apb.json'\n")
    monkeypatch.setattr(discovery, "WORKFLOWS", workflows)
    monkeypatch.setattr(runs, "_tool_version", lambda _executable: "apb2 1.0")
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        downloads=write_manifest(tmp_path / "downloads.csv", [row]),
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )

    first, manifest = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    helper.write_text("REPRESENTATION_SUFFIX = '.changed.json'\n")
    second, _ = prepare_run([row], output_root=tmp_path / "output", settings=settings)

    assert helper in discovery.workflow_implementation_paths("convert")
    assert helper.resolve() in runs.dataset_dependencies(first, manifest, row, manifest.reports[0])
    assert secondary.resolve() in runs.dataset_dependencies(
        first, manifest, row, manifest.reports[0]
    )
    assert first == second


def test_dependencies_track_editable_apb_source_without_importing_apb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = dataset()
    (tmp_path / row.input_file).write_text("data")
    (tmp_path / row.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpus.csv"
    write_corpus(corpus, [row])
    project = tmp_path / "editable-apb"
    package = project / "src" / "apb2"
    package.mkdir(parents=True)
    source = package / "conversion.py"
    source.write_text("VALUE = 1\n")
    dist_info = tmp_path / "apb2-1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "direct_url.json").write_text(
        json.dumps({"url": project.as_uri(), "dir_info": {"editable": True}})
    )
    monkeypatch.setattr(
        runs,
        "_distribution_info_path",
        lambda _executable, distribution: dist_info if distribution == "apb2" else None,
    )
    monkeypatch.setattr(runs, "_tool_version", lambda _executable: "apb2 1.0")
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        downloads=write_manifest(tmp_path / "downloads.csv", [row]),
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )
    first, manifest = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    source.write_text("VALUE = 2\n")
    second, _ = prepare_run([row], output_root=tmp_path / "output", settings=settings)

    assert source.resolve() in runs.dataset_dependencies(first, manifest, row, manifest.reports[0])
    assert first == second


def test_every_workflow_declares_the_executables_it_needs() -> None:
    """The workflow owns which tools it needs; generic code must not name them."""
    assert workflow_tools("convert") == ("apb2",)
    assert workflow_tools("aggregate") == ("apb2", "apb-aggregate")
    assert workflow_tools("aggregate_medpolish") == ("apb2", "apb-aggregate")
    assert workflow_tools("proteobench") == ("apb2", "apb-fasta", "apb-proteobench")
    assert workflow_tools("proteobench_pmultiqc") == ("apb-proteobench", "multiqc")
    assert workflow_tools("proteobench_run") == ("apb-proteobench",)
    assert workflow_tools("proteobench_entrapment") == ("apb-proteobench",)
    for name in ("../convert", "unknown", "convert.py"):
        with pytest.raises(ValueError):
            workflow_tools(name)


def test_only_declared_executables_are_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A convert run must not require apb-aggregate on PATH; an aggregate run must."""
    from apb_studio.corpus.cli import RunOptions, resolve_tools

    # Empty PATH, so the dev venv's own apb-aggregate cannot satisfy the lookup.
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    apb2 = tmp_path / "apb2"
    apb2.write_text("#!/bin/sh\n")
    apb2.chmod(0o755)

    convert = resolve_tools(RunOptions(workflow="convert", apb_executable=apb2))
    assert set(convert) == {"apb2"}
    assert convert["apb2"] == apb2.resolve()

    with pytest.raises(ValueError, match="apb-aggregate is not on PATH"):
        resolve_tools(RunOptions(workflow="aggregate", apb_executable=apb2))

    aggregate_bin = tmp_path / "apb-aggregate"
    aggregate_bin.write_text("#!/bin/sh\n")
    aggregate_bin.chmod(0o755)
    both = resolve_tools(
        RunOptions(workflow="aggregate", apb_executable=apb2, aggregate_executable=aggregate_bin)
    )
    assert set(both) == {"apb2", "apb-aggregate"}


def test_a_workflow_must_declare_tools_as_a_tuple_of_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workflow with a missing or malformed TOOLS declaration is refused, not guessed at."""
    import types

    from apb_studio.corpus import discovery

    for bad in (None, "apb2", ("apb2", 2)):
        module = types.SimpleNamespace() if bad is None else types.SimpleNamespace(TOOLS=bad)
        monkeypatch.setattr(discovery.importlib, "import_module", lambda _n, m=module: m)
        with pytest.raises(ValueError, match="must declare TOOLS"):
            discovery.workflow_tools("convert")


def test_a_declared_tool_needs_a_matching_override_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declaring an executable with no --*-executable flag is a packaging error, not a run."""
    from apb_studio.corpus import cli
    from apb_studio.corpus.cli import RunOptions, resolve_tools

    monkeypatch.setattr(cli, "workflow_tools", lambda _name: ("apb2", "apb-unknown"))
    with pytest.raises(ValueError, match="No override option is defined"):
        resolve_tools(RunOptions(workflow="convert", apb_executable=Path(sys.executable)))


def test_discovery_and_named_selection(tmp_path: Path) -> None:
    assert available_workflows() == [
        "aggregate",
        "aggregate_medpolish",
        "convert",
        "convert_ion",
        "convert_no_param",
        "export_alphapepttools",
        "export_msmu",
        "export_prolfqua",
        "export_proteopy",
        "proteobench",
        "proteobench_entrapment",
        "proteobench_plasma",
        "proteobench_plasma_run",
        "proteobench_pmultiqc",
        "proteobench_run",
        "proteobench_run_vendor",
    ]
    assert workflow_path("convert").name == "workflow_convert.py"
    assert workflow_path("convert_ion").name == "workflow_convert_ion.py"
    assert workflow_tools("convert_ion") == ("apb2",)
    for name in ("../convert", "unknown", "convert.py"):
        with pytest.raises(ValueError):
            workflow_path(name)
    row = dataset()
    selection = tmp_path / "selection.txt"
    selection.write_text("vendor.txt # input path\n")
    assert select_datasets([row], selection, 0) == [row]
    selection.write_text("unknown\n")
    with pytest.raises(ValueError, match="Unknown"):
        select_datasets([row], selection, 0)


def test_named_corpuses_are_the_files_in_corpuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apb_studio.corpus import cli

    test_data_root = tmp_path / "test_data_download"
    routine = write_corpus(tmp_path / "corpuses" / "routine.csv", [dataset()]).resolve()
    monkeypatch.setattr(
        cli,
        "load_settings",
        lambda: SimpleNamespace(test_data_root=test_data_root),
    )

    assert cli._options_for_corpus("routine", cli.RunOptions()).corpus == routine
    assert cli._options_for_corpus("all", cli.RunOptions()).corpus is None
    with pytest.raises(ValueError, match="available: all, routine"):
        cli._options_for_corpus("missing", cli.RunOptions())
    explicit = tmp_path / "chosen.csv"
    assert cli._options_for_corpus("missing", cli.RunOptions(corpus=explicit)).corpus == explicit
    assert corpus_files(tmp_path / "corpuses") == {"routine": routine}
    write_corpus(tmp_path / "corpuses" / "all.csv", [dataset()])
    with pytest.raises(ValueError, match="path-safe and not 'all'"):
        corpus_files(tmp_path / "corpuses")


def test_a_corpus_resolves_its_keys_through_the_fixture_manifest(tmp_path: Path) -> None:
    stored = dataset()
    absent = dataset().model_copy(update={"dataset": "Repo/absent", "input_file": "absent.txt"})
    manifest = write_manifest(tmp_path / "downloads.csv", [stored, absent], missing={"Repo/absent"})

    selection = resolve_corpus(["Repo/absent", "Repo/vendor"], manifest)

    assert selection.datasets == [
        absent.model_copy(update={"input_file": "store/Repo/absent", "vendor_parameter_file": ""}),
        stored,
    ]
    assert selection.not_downloaded == {"Repo/absent"}
    assert resolve_corpus(None, manifest).datasets == [stored], "all: every downloaded dataset"
    with pytest.raises(ValueError, match=r"unknown to the fixture manifest .*Repo/typo"):
        resolve_corpus(["Repo/typo"], manifest)
    with pytest.raises(ValueError, match="No fixture manifest"):
        resolve_corpus([], tmp_path / "elsewhere.csv")


def test_strict_refuses_a_corpus_with_datasets_not_downloaded(tmp_path: Path) -> None:
    from apb_studio.corpus import cli

    absent = dataset()
    options = cli.RunOptions(
        corpus=write_corpus(tmp_path / "routine.csv", [absent]),
        downloads=write_manifest(tmp_path / "downloads.csv", [absent], missing={absent.dataset}),
        data_root=tmp_path,
        output_root=tmp_path / "output",
        apb_executable=Path(sys.executable),
        strict=True,
    )

    with pytest.raises(ValueError, match=r"Repo/vendor; run `fixture download routine`"):
        cli._run_corpus("routine", options)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    ("software_name", "storage_format", "suffix"),
    [
        ("DIA-NN", "hdf5", ".h5mu"),
        ("Spectronaut", "parquet", ".parquet"),
        ("MaxQuant", "duckdb", ".duckdb"),
    ],
)
def test_aggregate_workflow_is_two_steps_configured_by_software(
    tmp_path: Path,
    software_name: str,
    storage_format: StorageFormat,
    suffix: str,
) -> None:
    workflow_table = tmp_path / "workflow_aggregate.csv"
    write_rows(
        workflow_table,
        ["software_name", "method"],
        [
            {
                "software_name": software_name,
                "method": "mean",
            }
        ],
    )
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset().model_copy(update={"software_name": software_name}),
        workflow_table=workflow_table,
        format=storage_format,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb2": tmp_path / "apb2", "apb-aggregate": tmp_path / "apb-aggregate"},
    )

    planned = aggregate_steps(context)

    assert [step.name for step in planned] == ["convert", "aggregate-mean"]
    assert planned[0].command[3] == "--params"
    assert planned[0].outputs[0].path.suffix == suffix
    assert planned[0].outputs[0].format == storage_format
    assert planned[0].command[planned[0].command.index("--format") + 1] == storage_format
    assert planned[1].command[1:] == [
        str(planned[0].outputs[0].path),
        str(planned[1].outputs[0].path),
        "mean",
        "--layers",
        "all",
    ]
    assert planned[0].outputs[1].path.name.endswith(f"{planned[0].outputs[0].path.suffix}.apb.json")
    assert planned[0].outputs[1].role == "representation"
    assert planned[1].outputs[0].path.suffix == suffix
    assert planned[1].outputs[0].format == storage_format
    assert planned[1].outputs[1].path.name.endswith(f"{suffix}.apb.json")


def test_aggregate_table_covers_every_corpus_software_with_explicit_policy() -> None:
    root = Path(__file__).parents[1]
    table = root / "workflow_tables" / "workflow_aggregate.csv"
    # Software whose every rule variant catalogues ion identification confidence.
    confidence_software = {"AlphaPept", "DIA-NN", "MaxQuant", "Spectronaut"}

    for row in committed_corpus(None):
        workflow = join_workflow(row.model_dump(), table, on=("software_name",))
        assert workflow == {
            "software_name": row.software_name,
            "method": "all;rlm_confidence_case;rlm_confidence_precision"
            if row.software_name in confidence_software
            else "all",
        }


def _aggregate_context(tmp_path: Path, method: str) -> WorkflowContext:
    workflow_table = tmp_path / "workflow_aggregate.csv"
    write_rows(
        workflow_table,
        ["software_name", "method"],
        [
            {
                "software_name": "DIA-NN",
                "method": method,
            }
        ],
    )
    return WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset(),
        workflow_table=workflow_table,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb2": tmp_path / "apb2", "apb-aggregate": tmp_path / "apb-aggregate"},
    )


def test_listed_aggregate_methods_chain_onto_one_final_result(tmp_path: Path) -> None:
    planned = aggregate_steps(_aggregate_context(tmp_path, "all; rlm_confidence_case"))

    assert [step.name for step in planned] == [
        "convert",
        "aggregate-all",
        "aggregate-rlm_confidence_case",
    ]
    convert, first, second = planned
    assert first.inputs == [convert.outputs[0]]
    assert first.command[3] == "all"
    assert first.outputs[0].role == "aggregated"
    assert first.outputs[0].path.name == "aggregated_all.h5mu"
    assert second.inputs == [first.outputs[0]]
    assert second.command[1:] == [
        str(first.outputs[0].path),
        str(second.outputs[0].path),
        "rlm_confidence_case",
        "--layers",
        "all",
    ]
    assert second.outputs[0].role == "result"
    assert second.outputs[0].path.name == "aggregated.h5mu"
    assert all(step.outputs[1].role == "representation" for step in planned)


def test_aggregate_workflow_rejects_a_repeated_method(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repeats a method"):
        aggregate_steps(_aggregate_context(tmp_path, "all;mean;all"))


def test_aggregate_workflow_rejects_an_empty_method(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nonempty method"):
        aggregate_steps(_aggregate_context(tmp_path, "all;"))


@pytest.mark.parametrize(
    ("storage_format", "suffix"),
    [("hdf5", ".h5mu"), ("duckdb", ".duckdb"), ("parquet", ".parquet")],
)
def test_medpolish_workflow_aggregates_only_primary_without_a_resource_table(
    tmp_path: Path, storage_format: StorageFormat, suffix: str
) -> None:
    context = _aggregate_context(tmp_path, "all;rlm_confidence_case").model_copy(
        update={"workflow_table": None, "format": storage_format}
    )

    convert, aggregate = aggregate_medpolish_steps(context)

    assert aggregate.name == "aggregate-medpolish"
    assert aggregate.command[1:] == [
        str(convert.outputs[0].path),
        str(aggregate.outputs[0].path),
        "medpolish",
        "--layers",
        "primary",
    ]
    assert aggregate.inputs == [convert.outputs[0]]
    assert aggregate.outputs[0].role == "result"
    assert aggregate.outputs[0].path.name == f"aggregated{suffix}"
    assert convert.command[convert.command.index("--format") + 1] == storage_format
    assert aggregate.outputs[1].role == "representation"
    assert aggregate.outputs[1].path.name == f"aggregated{suffix}.apb.json"
    implementations = discovery.workflow_implementation_paths("aggregate_medpolish")
    assert discovery.WORKFLOWS / "aggregate.py" in implementations


def test_compound_software_uses_the_base_parameter_parser(tmp_path: Path) -> None:
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset().model_copy(update={"software_name": "FragPipe (DIA-NN quant)"}),
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb2": tmp_path / "apb2"},
    )
    step = convert_steps(context)[0]
    command = step.command
    assert command[command.index("--software") + 1] == "fragpipe"
    timing_file = context.output_dir / "converted.timings.json"
    assert command[command.index("--timings-output") + 1] == str(timing_file)
    assert step.outputs[-1] == Artifact(role="tool_timings", path=timing_file)


def test_msmu_export_checks_the_module_fasta_the_table_names(tmp_path: Path) -> None:
    table = tmp_path / "workflow_proteobench.csv"
    table.write_text("module,fasta,level\ndia_aif,fasta/hye.fasta,ion\n", encoding="utf-8")
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset(),
        workflow_table=table,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb-export": tmp_path / "apb-export"},
    )

    step = export_msmu_steps(context)[0]
    fasta = resolve_file(tmp_path, "fasta/hye.fasta")
    assert step.command[step.command.index("--fasta") + 1] == str(fasta)
    assert Artifact(role="fasta", path=fasta) in step.inputs

    elsewhere = context.model_copy(
        update={"dataset": dataset().model_copy(update={"module": "dia_plasma"})}
    )
    assert "--fasta" not in export_msmu_steps(elsewhere)[0].command, "no row, no FASTA check"


def test_no_param_workflow_uses_tsv_software_mapping_without_parameter_file(tmp_path: Path) -> None:
    table = tmp_path / "workflow_no_param.tsv"
    table.write_text("software_name\tsoftware\nFragPipe (DIA-NN quant)\tDIA-NN\n", encoding="utf-8")
    source = tmp_path / "vendor.txt"
    source.write_text("vendor input", encoding="utf-8")
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset().model_copy(update={"software_name": "FragPipe (DIA-NN quant)"}),
        workflow_table=table,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb2": tmp_path / "apb2"},
    )

    step = convert_no_param_steps(context)[0]

    assert step.command[step.command.index("--software") + 1] == "DIA-NN"
    assert "--params" not in step.command
    assert [item.role for item in step.inputs] == ["vendor_table"]
    assert workflow_table_name("convert_no_param") == "workflow_no_param.tsv"


def test_no_param_workflow_does_not_depend_on_a_parameter_file(tmp_path: Path) -> None:
    source = tmp_path / "vendor.txt"
    source.write_text("vendor input", encoding="utf-8")
    corpus = tmp_path / "corpus.csv"
    write_corpus(corpus, [dataset()])
    table = tmp_path / "workflow_no_param.tsv"
    table.write_text("software_name\tsoftware\nDIA-NN\tDIA-NN\n", encoding="utf-8")
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert_no_param",
        format="hdf5",
        workflow_table=table,
        downloads=write_manifest(tmp_path / "downloads.csv", [dataset()]),
        tools={"apb2": Path(sys.executable)},
        cores=1,
    )

    root, manifest = prepare_run([dataset()], output_root=tmp_path / "outputs", settings=settings)
    dependencies = dataset_dependencies(root, manifest, dataset(), manifest.reports[0])

    assert source.resolve() in dependencies
    assert (tmp_path / "params.txt").resolve() not in dependencies


def test_proteobench_plasma_workflow_exports_the_modules_layer(tmp_path: Path) -> None:
    """The module, not the table, picks the un-normalised layer: ``--layer X``."""
    table = tmp_path / "workflow_proteobench_plasma.tsv"
    table.write_text("module\tsoftware_name\tfasta\tlevel\ndia_aif\tDIA-NN\tfasta/HYE.fasta\tion\n")
    context = proteobench_context(tmp_path).model_copy(
        update={
            "workflow_table": table,
            "tools": {"apb-proteobench": tmp_path / "apb", "multiqc": tmp_path / "multiqc"},
        }
    )

    export, report = proteobench_plasma_steps(context)

    assert workflow_table_name("proteobench_plasma") == "workflow_proteobench_plasma.tsv"
    assert export.command[export.command.index("--layer") + 1] == "X"
    assert export.command[export.command.index("--module") + 1] == "dia_aif"
    assert report.name == "pmultiqc"


def test_proteobench_plasma_table_covers_the_proteobench_plasma_corpus() -> None:
    root = Path(__file__).parents[1]
    table = root / "workflow_tables" / "workflow_proteobench_plasma.tsv"
    rows = committed_corpus("proteobench_plasma")

    assert rows
    assert {row.module for row in rows} == {"dia_plasma"}
    for row in rows:
        workflow = join_workflow(row.model_dump(), table, on=("module", "software_name"))
        assert tuple(workflow) == PROTEOBENCH_PLASMA_COLUMNS


def test_no_param_software_table_covers_proteobench_corpus() -> None:
    root = Path(__file__).parents[1]
    table = root / "workflow_tables" / "workflow_no_param.tsv"

    for row in committed_corpus("proteobench"):
        mapping = join_workflow(row.model_dump(), table, on=("software_name",))
        assert mapping["software"]


@pytest.mark.parametrize(
    ("storage_format", "suffix"),
    [("hdf5", ".h5ad"), ("parquet", ".parquet"), ("duckdb", ".duckdb")],
)
@pytest.mark.parametrize("secondary", [False, True])
@pytest.mark.parametrize("parameters", [False, True])
def test_convert_ion_workflow_selects_only_ion_and_keeps_timing_artifacts(
    tmp_path: Path,
    storage_format: StorageFormat,
    suffix: str,
    secondary: bool,
    parameters: bool,
) -> None:
    folder = tmp_path / "submission"
    folder.mkdir()
    primary = folder / "input_file.tsv"
    primary.write_text("vendor input", encoding="utf-8")
    secondary_file = folder / "input_file_secondary.tsv"
    if secondary:
        secondary_file.write_text("secondary input", encoding="utf-8")
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset().model_copy(
            update={
                "input_file": "submission/input_file.tsv",
                "vendor_parameter_file": "submission/params.txt" if parameters else "",
            }
        ),
        format=storage_format,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb2": tmp_path / "apb2"},
    )

    [step] = convert_ion_steps(context)

    assert step.name == "convert"
    assert step.command[:4] == [
        str(context.tool("apb2")),
        "convert",
        str(folder if secondary else primary),
        "ion",
    ]
    assert step.command[step.command.index("--format") + 1] == storage_format
    assert step.command[step.command.index("--software") + 1] == "diann"
    assert step.command[step.command.index("--timings-output") + 1] == str(
        context.output_dir / "converted.timings.json"
    )
    assert [artifact.role for artifact in step.inputs] == [
        "vendor_table",
        *(["vendor_secondary"] if secondary else []),
        *(["vendor_parameter_file"] if parameters else []),
    ]
    assert [artifact.role for artifact in step.outputs] == [
        "result",
        "representation",
        "tool_timings",
    ]
    assert step.outputs[0].path == context.output_dir / f"converted{suffix}"
    assert step.outputs[0].format == storage_format
    assert step.outputs[1].path == context.output_dir / f"converted{suffix}.apb.json"
    assert step.outputs[2].path == context.output_dir / "converted.timings.json"


def _good_bad_and_absent(data_root: Path) -> list[Dataset]:
    """Two stored inputs, one the fake tool fails on, and one dataset never downloaded."""
    data_root.mkdir()
    (data_root / "params.txt").write_text("parameters")
    rows = []
    for name in ("good", "bad"):
        (data_root / f"{name}.txt").write_text(name)
        rows.append(
            dataset().model_copy(update={"dataset": f"Repo/{name}", "input_file": f"{name}.txt"})
        )
    absent = dataset().model_copy(
        update={"dataset": "Repo/absent", "input_file": "store/Repo/absent"}
    )
    rows.append(absent)
    write_manifest(data_root / "downloads.csv", rows, missing={absent.dataset})
    return rows


def test_snakemake_settles_and_force_replaces_results(tmp_path: Path) -> None:
    """A tool failure is a completed result, including through the actual scheduler."""
    from apb_studio.corpus import cli
    from apb_studio.corpus.cli import RunOptions

    data_root = tmp_path / "vendor files"
    rows = _good_bad_and_absent(data_root)
    absent = rows[-1]
    executable = tmp_path / "fake apb"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys\nfrom pathlib import Path\n"
        "if sys.argv[1] == '--version':\n"
        "    print('fake-apb 1.0'); raise SystemExit(0)\n"
        "if sys.argv[1] == 'convert':\n"
        "    if Path(sys.argv[2]).read_text() == 'bad':\n"
        "        print('intentional failure', file=sys.stderr); raise SystemExit(7)\n"
        "    fmt = sys.argv[sys.argv.index('--format') + 1]\n"
        "    suffix = {'hdf5': '.h5mu', 'parquet': '.parquet', 'duckdb': '.duckdb'}[fmt]\n"
        "    output = Path(sys.argv[sys.argv.index('--output') + 1]).with_suffix(suffix)\n"
        "else:\n"
        "    output = Path(sys.argv[3])\n"
        "output.write_text('test artifact')\n"
        "output.with_name(output.name + '.apb.json').write_text('{}')\n"
        "if '--timings-output' in sys.argv:\n"
        "    Path(sys.argv[sys.argv.index('--timings-output') + 1]).write_text('{}')\n"
    )
    executable.chmod(0o755)
    corpus = tmp_path / "corpuses" / "mixed.csv"
    write_corpus(corpus, rows)
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=data_root,
        workflow="convert",
        format="duckdb",
        workflow_table=None,
        downloads=data_root / "downloads.csv",
        tools={"apb2": executable},
        cores=2,
    )
    root, manifest = prepare_run(
        rows,
        output_root=tmp_path / "output",
        settings=settings,
        not_downloaded=frozenset({absent.dataset}),
    )

    def invoke(*, cores: int = 2, dry_run: bool = False, force: bool = False) -> None:
        cli._run_corpus(
            "routine",
            RunOptions(
                corpus=corpus,
                data_root=data_root,
                output_root=tmp_path / "output",
                apb_executable=executable,
                storage_format="duckdb",
                cores=cores,
                dry_run=dry_run,
                force=force,
            ),
        )

    invoke()
    reports = [
        DatasetReport.model_validate_json((root / link.path).read_text())
        for link in manifest.reports
    ]
    assert [report.status for report in reports] == ["succeeded", "failed", "not_downloaded"]
    assert reports[0].steps[-1].outputs[0].format == "duckdb"
    assert [step.status for step in reports[1].steps] == ["failed"]
    assert reports[2].steps == []
    assert manifest.not_downloaded == [absent.dataset]
    index = json.loads((root / "corpus_index.json").read_text())
    assert len(index["reports"]) == 3
    assert all(not Path(link["path"]).is_absolute() for link in index["reports"])
    assert json.loads((root / "operation.json").read_text())["status"] == "succeeded"
    invoke(dry_run=True)
    assert "Nothing to be done" in (root / "dry-run.log").read_text()
    before = [(root / link.path).read_text() for link in manifest.reports]
    invoke(cores=1)
    assert [(root / link.path).read_text() for link in manifest.reports] == before

    changed_input = data_root / "good.txt"
    changed_input.write_text("good changed")
    invoke()
    after = [(root / link.path).read_text() for link in manifest.reports]
    assert after[0] != before[0]
    assert after[1] == before[1]

    old_artifacts = list((root / "artifacts").glob("*/*"))
    history = root / "history" / "old-attempt"
    history.mkdir(parents=True)
    (history / "old-output.bin").write_bytes(b"obsolete")
    invoke(dry_run=True, force=True)
    assert [(root / link.path).read_text() for link in manifest.reports] == after
    assert (history / "old-output.bin").is_file()
    invoke(force=True)
    assert not (root / "history").exists()
    assert all(not path.exists() for path in old_artifacts)
    assert (root / manifest.reports[0].path).read_text() != after[0]
    assert (data_root / "good.txt").read_text() == "good changed"


def test_stable_run_updates_source_and_selection_snapshots(tmp_path: Path) -> None:
    row = dataset()
    other = row.model_copy(update={"dataset": "Repo/other", "input_file": "other.txt"})
    corpus = tmp_path / "corpuses" / "routine.csv"
    write_corpus(corpus, [row, other])
    table = tmp_path / "workflow_tables" / "workflow_convert.csv"
    write_rows(
        table,
        ["software_name", "start_level"],
        [{"software_name": "DIA-NN", "start_level": "fragment"}],
    )
    settings = ExecutionSettings(
        corpus_name="routine",
        corpus=corpus,
        data_root=tmp_path / "vendors",
        workflow="convert",
        format="hdf5",
        workflow_table=table,
        downloads=write_manifest(tmp_path / "downloads.csv", [row, other]),
        tools={"apb2": Path(sys.executable)},
        cores=2,
    )
    first, manifest = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    assert load_datasets(first / manifest.corpus) == [row]
    assert load_corpus(first / "corpus.csv") == [row.dataset, other.dataset]
    assert (first / table.name).read_text() == table.read_text()
    assert (first / table.name).resolve() in runs.dataset_dependencies(
        first, manifest, row, manifest.reports[0]
    )
    snapshot = json.loads((first / "execution_settings.json").read_text())
    assert snapshot["corpus"] == str(corpus)
    assert snapshot["workflow_table"] == str(table)
    assert snapshot["data_root"] == str(tmp_path / "vendors")
    write_corpus(corpus, [row])
    second, another = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    assert another.created_at == manifest.created_at
    assert second == first
    assert load_corpus(first / "corpus.csv") == [row.dataset]
    write_record(first / "operation.json", Operation(status="succeeded"))
    publish_catalog(first.parents[2])
    catalog = json.loads((first.parents[2] / "index.json").read_text())
    assert catalog["runs"] == ["routine/convert/hdf5/run.json"]


def test_configure_reports_files_and_settings_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from apb_studio.corpus import cli

    settings_file = tmp_path / "config" / "settings.json"
    settings = StudioSettings(
        test_data_root=tmp_path / "workspace" / "test_data_download",
        output_root=tmp_path / "outputs",
    )
    settings_file.parent.mkdir(parents=True)
    settings_source = json.dumps(settings.model_dump(mode="json"))
    settings_file.write_text(settings_source, encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_corpus(workspace / "corpuses" / "routine.csv", [dataset()])
    write_corpus(workspace / "corpuses" / "problems.csv", [dataset()])
    write_manifest(settings.test_data_root / "downloads.csv", [dataset()])
    monkeypatch.setattr(cli, "settings_path", lambda: settings_file)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)

    cli.configure()

    rendered = json.loads(capsys.readouterr().out)
    assert rendered["settings_file"] == {"path": str(settings_file), "exists": True}
    assert rendered["settings"] == settings.model_dump(mode="json")
    assert rendered["run_defaults"] == {
        "workflow": "convert",
        "format": "hdf5",
        "cores": 3,
        "force": True,
    }
    assert rendered["configuration_files"] == {
        "corpuses": str(workspace / "corpuses"),
        "downloads": str(settings.test_data_root / "downloads.csv"),
        "workflow_tables": str(workspace / "workflow_tables"),
    }
    assert rendered["corpuses"] == {
        "problems": str(workspace / "corpuses" / "problems.csv"),
        "routine": str(workspace / "corpuses" / "routine.csv"),
    }
    assert "routine_selection" not in rendered["configuration_files"]
    assert str(Path(cli.__file__).resolve()) not in json.dumps(rendered)
    assert settings_file.read_text(encoding="utf-8") == settings_source


def test_aggregate_configuration_discovers_its_exact_workflow_table(tmp_path: Path) -> None:
    from apb_studio.corpus import cli

    corpus = tmp_path / "corpuses" / "small.csv"
    write_corpus(corpus, [dataset()])
    settings = cli._execution_settings(
        "routine",
        cli.RunOptions(
            corpus=corpus,
            data_root=tmp_path / "vendor-files",
            workflow="aggregate",
            apb_executable=Path(sys.executable),
            aggregate_executable=Path(sys.executable),
        ),
    )

    assert settings.workflow_table == (Path("workflow_tables") / "workflow_aggregate.csv").resolve()
    assert settings.tools["apb-aggregate"] == Path(sys.executable).resolve()


def proteobench_context(
    tmp_path: Path,
    *,
    fmt: StorageFormat = "hdf5",
    level: str = "ion",
) -> WorkflowContext:
    """Build a context whose FASTA resolves inside the data root; the module is packaged."""
    table = tmp_path / "workflow_proteobench.csv"
    write_rows(
        table,
        ["module", "fasta", "level", "sdrf"],
        [
            {
                "module": "dia_aif",
                "fasta": "fasta/HYE.fasta",
                "level": level,
                "sdrf": "sdrf/dia_aif.sdrf.tsv",
            }
        ],
    )
    return WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset(),
        workflow_table=table,
        format=fmt,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={
            "apb2": tmp_path / "apb2",
            "apb-fasta": tmp_path / "apb-fasta",
            "apb-proteobench": tmp_path / "apb-proteobench",
        },
    )


def test_three_call_proteobench_chains_its_own_intermediate_files(tmp_path: Path) -> None:
    """Each declared output is the next step's declared input, so the chain is inspectable."""
    planned = proteobench_steps(proteobench_context(tmp_path))

    assert [step.name for step in planned] == ["convert", "verify-peptides", "benchmark"]
    assert planned[0].outputs[0].path.name == "converted.h5mu"
    assert planned[0].outputs[-1].role == "tool_timings"
    assert planned[0].outputs[-1].path.name == "converted.timings.json"
    assert planned[1].inputs[0].path == planned[0].outputs[0].path
    assert planned[1].outputs[0].path.name == "fasta-checked.h5mu"
    assert planned[2].inputs[0].path == planned[1].outputs[0].path
    assert planned[2].outputs[0].role == "result"
    assert planned[2].outputs[0].path.name == "scored.h5mu"
    assert [step.outputs[1].role for step in planned] == ["representation"] * 3
    assert planned[1].command[1] == "verify-peptides"
    assert planned[2].command[1] == "benchmark"
    assert planned[2].command[3] == "dia_aif", "the packaged module, named"


def test_one_call_proteobench_declares_every_input_of_the_single_command(tmp_path: Path) -> None:
    """The single call names the same file inputs the three-call chain reads separately."""
    context = proteobench_context(tmp_path)
    planned = proteobench_run_steps(context)

    assert [step.name for step in planned] == ["run"]
    assert [artifact.role for artifact in planned[0].inputs] == [
        "vendor_table",
        "vendor_parameter_file",
        "fasta",
    ]
    assert planned[0].command[planned[0].command.index("--module") + 1] == "dia_aif"
    assert planned[0].command[1:3] == ["run", "quant"]
    assert planned[0].command[0] == str(context.tool("apb-proteobench"))
    assert planned[0].outputs[0].path.name == "scored.h5mu"
    assert planned[0].command[planned[0].command.index("--software") + 1] == "diann"
    timing_dir = Path(planned[0].command[planned[0].command.index("--timings-dir") + 1])
    assert [
        artifact.path for artifact in planned[0].outputs if artifact.role == "tool_timings"
    ] == [
        timing_dir / "apb2.convert.timings.json",
        timing_dir / "apb-fasta.verify-peptides.timings.json",
        timing_dir / "apb-proteobench.benchmark.timings.json",
    ]
    scores = Path(planned[0].command[planned[0].command.index("--scores") + 1])
    assert scores == context.output_dir / "scores.json"
    assert Artifact(role="proteobench_scores", path=scores) in planned[0].outputs
    assert "--proteins" not in planned[0].command, "apb-proteobench's default, matched"


def test_vendor_run_differs_only_by_its_proteins(tmp_path: Path) -> None:
    context = proteobench_context(tmp_path)

    (default,) = proteobench_run_steps(context)
    (vendor,) = proteobench_run_vendor_steps(context)

    assert workflow_tools("proteobench_run_vendor") == ("apb-proteobench",)
    assert workflow_table_name("proteobench_run_vendor") == "workflow_proteobench.csv"
    assert vendor.command[vendor.command.index("--proteins") + 1] == "vendor"
    assert [part for part in vendor.command if part not in ("--proteins", "vendor")] == (
        default.command
    )
    assert vendor.outputs == default.outputs


def test_proteobench_plasma_run_scores_the_modules_layer_without_a_report(
    tmp_path: Path,
) -> None:
    table = tmp_path / "workflow_proteobench_plasma.tsv"
    table.write_text("module\tsoftware_name\tfasta\tlevel\ndia_aif\tDIA-NN\tfasta/HYE.fasta\tion\n")
    context = proteobench_context(tmp_path).model_copy(update={"workflow_table": table})

    (run,) = proteobench_plasma_run_steps(context)

    assert workflow_tools("proteobench_plasma_run") == ("apb-proteobench",)
    assert workflow_table_name("proteobench_plasma_run") == "workflow_proteobench_plasma.tsv"
    assert run.command[1:3] == ["run", "quant"]
    assert "--layer" not in run.command, "the module picks the layer"
    assert run.command[run.command.index("--level") + 1] == "ion"
    assert run.outputs[0].path.name == "scored.h5ad", "one level"
    assert "--scores" in run.command


def test_pmultiqc_workflow_times_export_and_report_as_separate_steps(tmp_path: Path) -> None:
    """The integrated APB call includes serialization before the timed report call."""
    context = proteobench_context(tmp_path).model_copy(
        update={
            "tools": {
                "apb-proteobench": tmp_path / "apb-proteobench",
                "multiqc": tmp_path / "multiqc",
            }
        }
    )
    secondary = tmp_path / "vendor_secondary.txt"
    secondary.write_text("secondary", encoding="utf-8")

    planned = proteobench_pmultiqc_steps(context)

    assert [step.name for step in planned] == ["proteobench-export", "pmultiqc"]
    export = planned[0]
    report = planned[1]
    assert export.command[1:3] == ["run", "quant"]
    assert export.command[3] == str(secondary.parent)
    assert export.command[export.command.index("--level") + 1] == "ion"
    assert export.command[export.command.index("--layer") + 1] == "X"
    assert export.outputs[0].path.name == "scored.h5ad"
    assert [artifact.role for artifact in export.inputs] == [
        "vendor_table",
        "vendor_secondary",
        "vendor_parameter_file",
        "fasta",
    ]
    assert export.command[export.command.index("--module") + 1] == "dia_aif"
    result_performance = Path(export.command[export.command.index("--result-performance") + 1])
    assert result_performance.name == "result_performance.csv"
    export_artifact = next(
        artifact for artifact in export.outputs if artifact.role == "proteobench_export"
    )
    assert export_artifact.path == result_performance.parent
    assert report.inputs == [export_artifact]
    timing_dir = Path(export.command[export.command.index("--timings-dir") + 1])
    assert [artifact.path for artifact in export.outputs if artifact.role == "tool_timings"] == [
        timing_dir / "apb2.convert.timings.json",
        timing_dir / "apb-fasta.verify-peptides.timings.json",
        timing_dir / "apb-proteobench.benchmark.timings.json",
    ]
    assert report.command[1] == "--proteobench-plugin"
    assert report.command[2] == "--interactive"
    assert report.command[3] == str(result_performance.parent)
    assert [artifact.path.name for artifact in report.outputs] == [
        "multiqc_report.html",
        "multiqc_report_data",
    ]


def test_pmultiqc_workflow_rejects_a_non_ion_level(tmp_path: Path) -> None:
    context = proteobench_context(tmp_path, level="protein").model_copy(
        update={"tools": {"apb-proteobench": tmp_path / "apb", "multiqc": tmp_path / "multiqc"}}
    )

    with pytest.raises(ValueError, match="requires level ion"):
        proteobench_pmultiqc_steps(context)


def test_both_proteobench_workflows_read_one_shared_resource_table() -> None:
    """A sibling workflow declares WORKFLOW_TABLE rather than duplicating the CSV."""
    assert workflow_table_name("proteobench") == "workflow_proteobench.csv"
    assert workflow_table_name("proteobench_pmultiqc") == "workflow_proteobench.csv"
    assert workflow_table_name("proteobench_run") == "workflow_proteobench.csv"
    assert workflow_table_name("proteobench_run_vendor") == "workflow_proteobench.csv"
    assert workflow_table_name("convert") == "workflow_convert.csv"
    assert workflow_table_name("convert_ion") == "workflow_convert_ion.csv"


@pytest.mark.parametrize(
    ("storage_format", "suffix"),
    [("hdf5", ".h5mu"), ("parquet", ".parquet"), ("duckdb", ".duckdb")],
)
def test_proteobench_workflows_use_the_selected_storage_format(
    storage_format: StorageFormat,
    suffix: str,
    tmp_path: Path,
) -> None:
    context = proteobench_context(tmp_path, fmt=storage_format)

    staged = proteobench_steps(context)
    direct = proteobench_run_steps(context)

    assert [step.outputs[0].path.suffix for step in staged] == [suffix] * 3
    assert [step.outputs[0].format for step in staged] == [storage_format] * 3
    assert staged[0].command[staged[0].command.index("--format") + 1] == storage_format
    assert direct[0].outputs[0].path.suffix == suffix
    assert direct[0].outputs[0].format == storage_format


@pytest.mark.parametrize(
    ("storage_format", "suffix"),
    [("hdf5", ".h5ad"), ("parquet", ".parquet"), ("duckdb", ".duckdb")],
)
def test_pmultiqc_workflow_uses_a_single_level_result(
    storage_format: StorageFormat,
    suffix: str,
    tmp_path: Path,
) -> None:
    context = proteobench_context(tmp_path, fmt=storage_format).model_copy(
        update={"tools": {"apb-proteobench": tmp_path / "apb", "multiqc": tmp_path / "multiqc"}}
    )

    export = proteobench_pmultiqc_steps(context)[0]

    assert export.outputs[0].path.suffix == suffix
    assert export.outputs[0].format == storage_format


def test_proteobench_workflows_require_their_resource_table(tmp_path: Path) -> None:
    context = proteobench_context(tmp_path).model_copy(update={"workflow_table": None})
    for build in (proteobench_steps, proteobench_pmultiqc_steps, proteobench_run_steps):
        with pytest.raises(ValueError, match="workflow_proteobench.csv is required"):
            build(context)


def test_proteobench_table_covers_every_scoring_corpus_module() -> None:
    """The packaged scoring table resolves a FASTA and level for its explicit corpus."""
    root = Path(__file__).parents[1]
    table = root / "workflow_tables" / "workflow_proteobench.csv"

    for row in committed_corpus("proteobench"):
        workflow = join_workflow(row.model_dump(), table, on=("module",))
        assert workflow["module"] == row.module
        assert workflow["fasta"].startswith("fasta/")
        assert workflow["level"] == "ion"


def test_proteobench_table_satisfies_every_proteobench_workflow() -> None:
    """The checked-in table, not acquisition, owns the ProteoBench workflow columns."""
    rows = read_rows(Path(__file__).parents[1] / "workflow_tables" / "workflow_proteobench.csv")

    for columns in (PROTEOBENCH_COLUMNS, PROTEOBENCH_RUN_COLUMNS, PROTEOBENCH_PMULTIQC_COLUMNS):
        assert all(tuple(row) == columns for row in rows)
    config = packaged_config()
    assert sorted((row["module"], row["fasta"], row["sdrf"]) for row in rows) == sorted(
        (
            module,
            f"fasta/{config.fasta_for_module(module)}",
            f"sdrf/{config.sdrf_for_module(module)}",
        )
        for module in config.module_names
        if module not in SEPARATELY_SCORED
    ), "each quant module needs one row naming the FASTA and SDRF config/proteobench.toml fetches"


def test_entrapment_workflow_runs_the_entrapment_command_on_the_protein_database(
    tmp_path: Path,
) -> None:
    table = tmp_path / "workflow_proteobench_entrapment.csv"
    write_rows(
        table,
        list(PROTEOBENCH_ENTRAPMENT_COLUMNS),
        [
            {
                "module": "entrapment_dia_astral",
                "fasta": "fasta/entrapment.parquet",
            }
        ],
    )
    context = proteobench_context(tmp_path).model_copy(
        update={
            "workflow_table": table,
            "dataset": dataset().model_copy(update={"module": "entrapment_dia_astral"}),
        }
    )

    planned = proteobench_entrapment_steps(context)

    assert [step.name for step in planned] == ["run-entrapment"]
    command = planned[0].command
    assert command[1:3] == ["run", "entrapment"]
    assert command[4] == str(tmp_path / "fasta/entrapment.parquet")
    assert "--pairs" not in command
    assert command[command.index("--module") + 1] == "entrapment_dia_astral"
    assert [artifact.role for artifact in planned[0].inputs] == [
        "vendor_table",
        "vendor_parameter_file",
        "fasta",
    ]
    assert planned[0].outputs[0].path.name == "scored.h5ad", "one level"
    scores = Path(command[command.index("--scores") + 1])
    assert Artifact(role="proteobench_scores", path=scores) in planned[0].outputs


def test_entrapment_table_names_what_acquisition_fetches() -> None:
    rows = read_rows(
        Path(__file__).parents[1] / "workflow_tables" / "workflow_proteobench_entrapment.csv"
    )
    config = packaged_config()

    assert all(tuple(row) == PROTEOBENCH_ENTRAPMENT_COLUMNS for row in rows)
    assert [row["module"] for row in rows] == ["entrapment_dia_astral"]
    for row in rows:
        database = Path(config.fasta_for_module(row["module"])).with_suffix(".parquet")
        assert row["fasta"] == f"fasta/{database}", "the protein database acquisition writes"


def test_proteobench_corpus_excludes_peptidoform_and_sage_datasets() -> None:
    all_rows = committed_corpus(None)
    proteobench_rows = committed_corpus("proteobench")

    assert len(proteobench_rows) == 197
    quant_modules = set(packaged_config().module_names) - SEPARATELY_SCORED
    expected = {
        row.input_file: row
        for row in all_rows
        if row.module in quant_modules
        and row.module != "dda_peptidoform"
        and row.software_name != "Sage"
        and row.vendor_parameter_file
        # A garbled sample name loses a run; kept in corpuses/problems.csv instead.
        and "5691d485" not in row.input_file
    }
    assert {row.input_file: row for row in proteobench_rows} == expected
    assert {row.module for row in all_rows} >= {"dia_plasma", "entrapment_dia_astral", "directlfq"}


def test_a_workflow_table_declaration_must_name_a_workflow_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed WORKFLOW_TABLE is refused, not silently turned into a path."""
    import types

    for bad in (None, "resources.csv", "workflow_x.txt"):
        module = types.SimpleNamespace(WORKFLOW_TABLE=bad)
        monkeypatch.setattr(discovery.importlib, "import_module", lambda _n, m=module: m)
        with pytest.raises(ValueError, match="must declare WORKFLOW_TABLE"):
            discovery.workflow_table_name("convert")


def test_the_workflow_cli_requires_named_tool_pairs() -> None:
    """--tool NAME=PATH is the only way a workflow receives an executable."""
    from apb_studio.corpus import workflow_cli

    tools = workflow_cli._tools
    assert tools(["apb2=/bin/true", "apb-fasta=/bin/false"]) == {
        "apb2": Path("/bin/true"),
        "apb-fasta": Path("/bin/false"),
    }
    for bad in ([], ["apb2"], ["=/bin/true"], ["apb2="]):
        with pytest.raises(ValueError):
            tools(bad)
    with pytest.raises(ValueError, match="Duplicate --tool apb2"):
        tools(["apb2=/bin/true", "apb2=/bin/false"])


def test_a_workflow_only_reaches_the_executables_it_declared(tmp_path: Path) -> None:
    """Asking for an undeclared tool is a workflow error, not a silent PATH lookup."""
    context = proteobench_context(tmp_path)
    with pytest.raises(ValueError, match="apb-aggregate was not resolved"):
        context.tool("apb-aggregate")


def test_the_workflows_command_lists_every_packaged_workflow(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--names provides a machine-readable workflow inventory."""
    from apb_studio.corpus.cli import workflows

    workflows(names=True)
    printed = capsys.readouterr().out.split()
    assert printed == available_workflows()
    assert "proteobench_run" in printed


def test_the_workflows_command_reports_each_workflow_tools_and_table() -> None:
    """Without --names it answers what a workflow needs before anyone runs it."""
    from loguru import logger

    from apb_studio.corpus.cli import workflows

    lines: list[str] = []
    sink = logger.add(lines.append, format="{message}")
    try:
        workflows()
    finally:
        logger.remove(sink)
    reported = "".join(lines)
    assert "proteobench | tools: apb2, apb-fasta, apb-proteobench" in reported
    assert "table: workflow_proteobench.csv" in reported
    # convert needs no resource table, and the listing says so rather than implying one exists.
    assert "workflow_convert.csv (absent)" in reported


def test_every_packaged_workflow_declares_a_tool_and_conventional_table_name() -> None:
    """Discovery requires no central workflow registry."""
    for name in available_workflows():
        assert workflow_tools(name)
        assert workflow_table_name(name).startswith("workflow_")


def test_cleaning_deletes_a_run_recorded_under_an_older_manifest_schema(tmp_path: Path) -> None:
    """Deleting a run must not require the manifest schema the current code writes."""
    root = tmp_path / "convert-hdf5-legacy"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "a.json").write_text("{}")
    (root / "corpus_index.json").write_text("{}")
    # A pre-tools-map manifest: named executable fields, no tools/tool_versions.
    (root / "run.json").write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": "convert-hdf5-legacy",
            "workflow": "convert",
            "format": "hdf5",
            "data_root": str(tmp_path / "vendor-files"),
            "apb_executable": "/usr/bin/apb2",
            "apb_version": "0.0.1",
            "cores": 1,
            "workflow_source": "workflow_convert.py",
            "reports": [],
        })
    )

    deleted = delete_run(root)

    assert deleted == root
    assert not root.exists()


def test_clean_command_deletes_current_and_legacy_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The all-runs command must reclaim outputs from both directory layouts."""
    store = tmp_path / "corpus"
    data_root = tmp_path / "fixtures"
    data_root.mkdir()
    current = store / "routine" / "convert" / "hdf5"
    legacy = store / "convert-hdf5-deadbeef"
    settings = store / "settings" / "saved"
    settings.mkdir(parents=True)
    (settings / "execution_settings.json").write_text("{}")
    for root in (current, legacy):
        root.mkdir(parents=True)
        (root / "run.json").write_text(
            json.dumps({"data_root": str(data_root.resolve())}),
            encoding="utf-8",
        )
        (root / "artifact.bin").write_bytes(b"output")
    monkeypatch.setattr(cli, "_viewer_root", lambda _output_root: store)

    cli.clean()

    assert not current.exists()
    assert not legacy.exists()
    assert (settings / "execution_settings.json").is_file()


def test_cleaning_refuses_a_symlinked_run_directory(tmp_path: Path) -> None:
    data_root = tmp_path / "fixtures"
    data_root.mkdir()
    root = tmp_path / "runs" / "actual"
    root.mkdir(parents=True)
    (root / "run.json").write_text(
        json.dumps({"data_root": str(data_root.resolve())}),
        encoding="utf-8",
    )
    symlink = tmp_path / "linked-run"
    symlink.symlink_to(root, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked run"):
        delete_run(symlink)


def test_forced_cleanup_refuses_a_symlinked_history_before_deleting_results(tmp_path: Path) -> None:
    data_root = tmp_path / "fixtures"
    data_root.mkdir()
    root = tmp_path / "run"
    (root / "artifacts").mkdir(parents=True)
    artifact = root / "artifacts" / "output.h5mu"
    artifact.write_bytes(b"current result")
    (root / "run.json").write_text(json.dumps({"data_root": str(data_root)}))
    (root / "history").symlink_to(data_root, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinks in managed run paths"):
        clear_results(root)

    assert artifact.read_bytes() == b"current result"
    assert data_root.is_dir()


def test_cleaning_refuses_a_manifest_without_a_usable_data_root(tmp_path: Path) -> None:
    """The fixture-overlap guard needs data_root, so an unusable one stops deletion."""
    for payload, expected in (
        ({"run_id": "x"}, "records no data_root"),
        ({"run_id": "x", "data_root": "relative/path"}, "not absolute"),
    ):
        root = tmp_path / f"run-{len(payload)}"
        root.mkdir()
        (root / "run.json").write_text(json.dumps(payload))
        with pytest.raises(ValueError, match=expected):
            delete_run(root)


def test_clean_command_does_not_create_a_missing_run_directory(tmp_path: Path) -> None:
    """A mistyped explicit target must fail without leaving a lock-only phantom run."""
    missing = tmp_path / "missing-run"
    with pytest.raises(FileNotFoundError, match="No corpus run manifest"):
        delete_run(missing)
    assert not missing.exists()


@pytest.mark.parametrize(
    ("target", "extension"),
    [
        ("msmu", ".h5mu"),
        ("prolfqua", ".h5ad"),
        ("proteopy", ".h5ad"),
        ("alphapepttools", ".h5mu"),
    ],
)
def test_export_workflows_call_apb_export_from_its_own_environment(
    tmp_path: Path, target: str, extension: str
) -> None:
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset(),
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        tools={"apb-export": tmp_path / "apb-export"},
    )
    module = importlib.import_module(f"apb_studio.workflows.workflow_export_{target}")

    (step,) = module.steps(context)

    assert workflow_tools(f"export_{target}") == ("apb-export",)
    assert step.command[:2] == [str(tmp_path / "apb-export"), target]
    assert step.command[step.command.index("--software") + 1] == "diann"
    output = context.output_dir / f"{target}{extension}"
    assert step.command[3] == str(output)
    sidecar = Artifact(role="representation", path=output.with_name(f"{output.name}.apb.json"))
    assert step.outputs == [Artifact(role="export", path=output), sidecar]
