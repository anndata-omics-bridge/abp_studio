"""Execution failures remain reports; input joins and final publication stay strict."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from apb_studio.corpus import discovery, runner, runs
from apb_studio.corpus.clean import archive_results
from apb_studio.corpus.discovery import available_workflows, workflow_path, workflow_tools
from apb_studio.corpus.models import (
    Artifact,
    Dataset,
    DatasetReport,
    ExecutionSettings,
    InputMetadata,
    Record,
    StepResult,
    StorageFormat,
    write_record,
)
from apb_studio.corpus.runner import run_steps
from apb_studio.corpus.runs import prepare_run, publish_catalog, publish_index, select_datasets
from apb_studio.corpus.tables import (
    CORPUS_COLUMNS,
    INPUT_METADATA_COLUMNS,
    join_input_metadata,
    join_workflow,
    load_corpus,
    resolve_file,
    write_rows,
)
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.corpus_export import export_corpus, export_proteobench_table
from apb_studio.fixture_store import Store
from apb_studio.workflows.workflow_aggregate import steps as aggregate_steps
from apb_studio.workflows.workflow_convert import steps as convert_steps


def dataset() -> Dataset:
    return Dataset(
        input_file="vendor.txt",
        vendor_parameter_file="params.txt",
        module="dia_aif",
        software_name="DIA-NN",
    )


def test_csv_minimal_schema_and_explicit_joins(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.csv"
    row = dataset().model_dump()
    write_rows(corpus, CORPUS_COLUMNS, [row])
    assert load_corpus(corpus) == [dataset()]
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
    write_rows(corpus, CORPUS_COLUMNS, [row, row])
    with pytest.raises(ValueError, match="Duplicate input_file"):
        load_corpus(corpus)
    corpus.write_text("input_file,status\nx,ok\n")
    with pytest.raises(ValueError, match="exactly"):
        load_corpus(corpus)
    with pytest.raises(ValueError, match="escapes"):
        resolve_file(tmp_path, "../outside")


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


def test_export_reads_local_pairs_and_copies_only_resource_columns(tmp_path: Path) -> None:
    store = Store(tmp_path / "store")
    folder = store.submission_dir("repo", "hash")
    folder.mkdir(parents=True)
    (folder / "input_file.txt").write_text("data")
    (folder / "param_0..txt").write_text("params")
    write_rows(
        store.catalog_csv,
        ["repo_name", "intermediate_hash", "module", "software_name"],
        [
            {
                "repo_name": "repo",
                "intermediate_hash": "hash",
                "module": "dia_aif",
                "software_name": "DIA-NN",
            }
        ],
    )
    store.downloads_csv.write_text("unreadable download history")
    corpus = export_corpus(store)
    assert corpus == tmp_path / "corpuses" / "all.csv"
    assert load_corpus(corpus)[0].vendor_parameter_file.endswith("param_0..txt")
    write_rows(
        store.resources_csv,
        ["module", "module_toml", "fasta", "fasta_present"],
        [
            {
                "module": "dia_aif",
                "module_toml": "modules/a.toml",
                "fasta": "fasta/a",
                "fasta_present": "True",
            }
        ],
    )
    exported = export_proteobench_table(store, tmp_path / "tables")
    assert exported.name == "workflow_proteobench.csv"
    assert "present" not in exported.read_text()
    (folder / "param_0.second").write_text("ambiguous")
    assert load_corpus(export_corpus(store)) == []


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
    second = first.model_copy(update={"input_file": "other.txt"})
    for row, content in ((first, "data"), (second, "another")):
        (tmp_path / row.input_file).write_text(content)
    (tmp_path / first.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpuses" / "all.csv"
    write_rows(corpus, CORPUS_COLUMNS, [first.model_dump(), second.model_dump()])
    downloads = tmp_path / "downloads.csv"
    write_rows(
        downloads,
        ["input_file_path", "input_file_size_bytes"],
        [
            {"input_file_path": first.input_file, "input_file_size_bytes": "4"},
            {"input_file_path": second.input_file, "input_file_size_bytes": "7"},
        ],
    )
    settings = ExecutionSettings(
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        downloads=downloads,
        apb_executable=Path(sys.executable),
        cores=1,
    )

    root, manifest = prepare_run([second], output_root=tmp_path / "output", settings=settings)

    assert manifest.input_metadata == "input_metadata.csv"
    assert load_corpus(root / manifest.corpus) == [second]
    settings_json = json.loads((root / "execution_settings.json").read_text())
    assert settings_json["downloads"] == str(downloads)
    assert (root / manifest.input_metadata).read_text().splitlines() == [
        ",".join(INPUT_METADATA_COLUMNS),
        "other.txt,7",
    ]
    assert manifest.settings_id is not None
    settings_snapshot = root.parent / "settings" / manifest.settings_id / "input_metadata.csv"
    assert settings_snapshot.read_text().splitlines() == [
        ",".join(INPUT_METADATA_COLUMNS),
        "vendor.txt,4",
        "other.txt,7",
    ]


def test_run_snapshots_and_index_validation(tmp_path: Path) -> None:
    row = dataset()
    (tmp_path / row.input_file).write_text("data")
    (tmp_path / row.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpuses" / "all.csv"
    write_rows(corpus, CORPUS_COLUMNS, [row.model_dump()])
    settings = ExecutionSettings(
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        apb_executable=Path(sys.executable),
        cores=1,
    )
    root, manifest = prepare_run(
        [row],
        output_root=tmp_path / "output",
        settings=settings,
    )
    again, _ = prepare_run(
        [row],
        output_root=tmp_path / "output",
        settings=settings,
    )
    assert again == root
    assert manifest.workflow_table is None
    assert manifest.source_corpus == "corpus.csv"
    assert manifest.corpus == "selected_corpus.csv"
    saved = ExecutionSettings.model_validate_json((root / "execution_settings.json").read_text())
    assert saved.corpus == corpus
    assert saved.workflow_table is None
    assert load_corpus(root / "corpus.csv") == [row]
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
    legacy = root.parent / "legacy-run"
    write_record(legacy / "run.json", manifest.model_copy(update={"settings_id": None}))
    publish_catalog(root.parent)
    assert (root / "corpus_index.json").exists()
    assert json.loads((root.parent / "index.json").read_text())["runs"] == [f"{root.name}/run.json"]
    with pytest.raises(ValueError, match="overlaps"):
        archive_results(root)
    for invalid in ({"schema_version": 2}, {"unknown": True}, {"runtime_seconds": float("nan")}):
        with pytest.raises(ValidationError):
            DatasetReport.model_validate({**report.model_dump(), **invalid})


def test_run_identity_tracks_shared_workflow_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = dataset()
    (tmp_path / row.input_file).write_text("data")
    (tmp_path / row.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpus.csv"
    write_rows(corpus, CORPUS_COLUMNS, [row.model_dump()])
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "__init__.py").write_text("")
    selected = workflows / "workflow_convert.py"
    selected.write_text("TOOLS = ('apb2',)\n")
    helper = workflows / "artifacts.py"
    helper.write_text("REPRESENTATION_SUFFIX = '.apb.json'\n")
    snakefile = tmp_path / "Snakefile"
    snakefile.write_text("rule all:\n    input: []\n")
    monkeypatch.setattr(discovery, "WORKFLOWS", workflows)
    monkeypatch.setattr(runs, "SNAKEFILE", snakefile)
    monkeypatch.setattr(runs, "_tool_version", lambda _executable: "apb2 1.0")
    settings = ExecutionSettings(
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        apb_executable=Path(sys.executable),
        cores=1,
    )

    first, _ = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    helper.write_text("REPRESENTATION_SUFFIX = '.changed.json'\n")
    second, _ = prepare_run([row], output_root=tmp_path / "output", settings=settings)

    assert helper in discovery.workflow_implementation_paths("convert")
    assert first != second


def test_run_identity_tracks_editable_apb_source_without_importing_apb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = dataset()
    (tmp_path / row.input_file).write_text("data")
    (tmp_path / row.vendor_parameter_file).write_text("parameters")
    corpus = tmp_path / "corpus.csv"
    write_rows(corpus, CORPUS_COLUMNS, [row.model_dump()])
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
        corpus=corpus,
        data_root=tmp_path,
        workflow="convert",
        format="hdf5",
        workflow_table=None,
        apb_executable=Path(sys.executable),
        cores=1,
    )
    launcher_digest = runs._file_digest(settings.apb_executable)

    first, _ = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    source.write_text("VALUE = 2\n")
    second, _ = prepare_run([row], output_root=tmp_path / "output", settings=settings)

    assert runs._file_digest(settings.apb_executable) == launcher_digest
    assert first != second


def test_every_workflow_declares_the_executables_it_needs() -> None:
    """The workflow owns which tools it needs; generic code must not name them."""
    assert workflow_tools("convert") == ("apb2",)
    assert workflow_tools("aggregate") == ("apb2", "apb-aggregate")
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
        resolve_tools(RunOptions(workflow="convert"))


def test_discovery_and_named_selection(tmp_path: Path) -> None:
    assert available_workflows() == ["aggregate", "convert"]
    assert workflow_path("convert").name == "workflow_convert.py"
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


@pytest.mark.parametrize(
    ("software_name", "start_level", "storage_format", "suffix"),
    [
        ("DIA-NN", "fragment", "hdf5", ".h5mu"),
        ("Spectronaut", "fragment", "parquet", ".parquet"),
        ("MaxQuant", "ion", "duckdb", ".duckdb"),
    ],
)
def test_aggregate_workflow_is_two_steps_configured_by_software(
    tmp_path: Path,
    software_name: str,
    start_level: str,
    storage_format: StorageFormat,
    suffix: str,
) -> None:
    workflow_table = tmp_path / "workflow_aggregate.csv"
    write_rows(
        workflow_table,
        ["software_name", "start_level", "method"],
        [{"software_name": software_name, "start_level": start_level, "method": "mean"}],
    )
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset().model_copy(update={"software_name": software_name}),
        workflow_table=workflow_table,
        format=storage_format,
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        apb_executable=tmp_path / "apb2",
        aggregate_executable=tmp_path / "apb-aggregate",
    )

    planned = aggregate_steps(context)

    assert [step.name for step in planned] == ["convert", "aggregate"]
    assert planned[0].command[3] == start_level
    assert planned[1].command[1:4] == [start_level, "protein", "mean"]
    assert planned[0].outputs[0].path.suffix == ".h5ad"
    assert planned[0].outputs[1].path.name.endswith(".h5ad.apb.json")
    assert planned[0].outputs[1].role == "representation"
    assert planned[1].outputs[0].path.suffix == suffix
    assert planned[1].outputs[0].format == storage_format
    assert planned[1].outputs[1].path.name.endswith(f"{suffix}.apb.json")


def test_aggregate_table_covers_every_corpus_software_with_explicit_policy() -> None:
    root = Path(__file__).parents[1]
    table = root / "workflow_tables" / "workflow_aggregate.csv"
    fragment_software = {"DIA-NN", "Spectronaut"}

    for row in load_corpus(root / "corpuses" / "all.csv"):
        workflow = join_workflow(row.model_dump(), table, on=("software_name",))
        expected = "fragment" if row.software_name in fragment_software else "ion"
        assert workflow == {
            "software_name": row.software_name,
            "start_level": expected,
            "method": "mean",
        }


def test_compound_software_uses_the_base_parameter_parser(tmp_path: Path) -> None:
    context = WorkflowContext(
        corpus=tmp_path / "corpus.csv",
        data_root=tmp_path,
        dataset=dataset().model_copy(update={"software_name": "FragPipe (DIA-NN quant)"}),
        output_dir=tmp_path / "outputs",
        report=tmp_path / "report.json",
        apb_executable=tmp_path / "apb2",
    )
    command = convert_steps(context)[0].command
    assert command[command.index("--params-software") + 1] == "fragpipe"


def test_snakemake_mixed_outcomes_settles_and_force_preserves_history(tmp_path: Path) -> None:
    """A tool failure is a completed result, including through the actual scheduler."""
    from apb_studio.corpus.cli import RunOptions, run

    data_root = tmp_path / "vendor files"
    data_root.mkdir()
    (data_root / "params.txt").write_text("parameters")
    rows = []
    for name in ("good", "bad"):
        (data_root / f"{name}.txt").write_text(name)
        rows.append(dataset().model_copy(update={"input_file": f"{name}.txt"}))
    executable = tmp_path / "fake apb"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys\nfrom pathlib import Path\n"
        "if sys.argv[1] == '--version':\n"
        "    print('fake-apb 1.0'); raise SystemExit(0)\n"
        "if sys.argv[1] == 'convert':\n"
        "    if Path(sys.argv[2]).read_text() == 'bad':\n"
        "        print('intentional failure', file=sys.stderr); raise SystemExit(7)\n"
        "    output = Path(sys.argv[sys.argv.index('--output') + 1]).with_suffix('.h5mu')\n"
        "else:\n"
        "    output = Path(sys.argv[3])\n"
        "output.write_text('test artifact')\n"
        "output.with_name(output.name + '.apb.json').write_text('{}')\n"
    )
    executable.chmod(0o755)
    corpus = tmp_path / "corpuses" / "mixed.csv"
    write_rows(corpus, CORPUS_COLUMNS, [row.model_dump() for row in rows])
    settings = ExecutionSettings(
        corpus=corpus,
        data_root=data_root,
        workflow="convert",
        format="duckdb",
        workflow_table=None,
        apb_executable=executable,
        cores=2,
    )
    root, manifest = prepare_run(
        rows,
        output_root=tmp_path / "output",
        settings=settings,
    )

    def invoke(*, dry_run: bool = False, force: bool = False) -> None:
        run(
            RunOptions(
                corpus=corpus,
                data_root=data_root,
                output_root=tmp_path / "output",
                apb_executable=executable,
                storage_format="duckdb",
                cores=2,
                dry_run=dry_run,
                force=force,
            )
        )

    invoke()
    reports = [
        DatasetReport.model_validate_json((root / link.path).read_text())
        for link in manifest.reports
    ]
    assert [report.status for report in reports] == ["succeeded", "failed"]
    assert reports[0].steps[-1].outputs[0].format == "duckdb"
    assert [step.status for step in reports[1].steps] == ["failed", "skipped"]
    index = json.loads((root / "corpus_index.json").read_text())
    assert len(index["reports"]) == 2
    assert all(not Path(link["path"]).is_absolute() for link in index["reports"])
    assert json.loads((root / "operation.json").read_text())["status"] == "succeeded"
    invoke(dry_run=True)
    assert "Nothing to be done" in (root / "dry-run.log").read_text()
    previous = (root / manifest.reports[0].path).read_text()
    invoke(force=True)
    history = list((root / "history").iterdir())
    assert len(history) == 1
    assert (history[0] / manifest.reports[0].path).read_text() == previous
    assert (root / manifest.reports[0].path).read_text() != previous
    assert (data_root / "good.txt").read_text() == "good"


def test_settings_group_runs_but_freeze_each_source_and_selection(tmp_path: Path) -> None:
    row = dataset()
    other = row.model_copy(update={"input_file": "other.txt"})
    corpus = tmp_path / "corpuses" / "all.csv"
    write_rows(corpus, CORPUS_COLUMNS, [row.model_dump(), other.model_dump()])
    table = tmp_path / "workflow_tables" / "workflow_convert.csv"
    write_rows(
        table,
        ["software_name", "start_level"],
        [{"software_name": "DIA-NN", "start_level": "fragment"}],
    )
    settings = ExecutionSettings(
        corpus=corpus,
        data_root=tmp_path / "vendors",
        workflow="convert",
        format="hdf5",
        workflow_table=table,
        apb_executable=Path(sys.executable),
        cores=2,
    )
    first, manifest = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    assert load_corpus(first / manifest.corpus) == [row]
    assert load_corpus(first / "corpus.csv") == [row, other]
    assert (first / table.name).read_text() == table.read_text()
    snapshot = json.loads((first / "execution_settings.json").read_text())
    assert snapshot["corpus"] == str(corpus)
    assert snapshot["workflow_table"] == str(table)
    assert snapshot["data_root"] == str(tmp_path / "vendors")
    write_rows(corpus, CORPUS_COLUMNS, [row.model_dump()])
    second, another = prepare_run([row], output_root=tmp_path / "output", settings=settings)
    assert another.settings_id == manifest.settings_id
    assert second != first
    assert load_corpus(first / "corpus.csv") == [row, other]
    publish_catalog(first.parent)
    catalog = json.loads((first.parent / "index.json").read_text())
    assert len(catalog["settings"]) == 1
    assert len(catalog["runs"]) == 2


def test_configure_publishes_explicit_tables_without_a_run(tmp_path: Path) -> None:
    from apb_studio.corpus.cli import RunOptions, configure

    corpus = tmp_path / "corpuses" / "small.csv"
    write_rows(corpus, CORPUS_COLUMNS, [dataset().model_dump()])
    output = tmp_path / "output"
    configure(
        RunOptions(
            corpus=corpus,
            data_root=tmp_path / "vendor-files",
            output_root=output,
            apb_executable=Path(sys.executable),
        )
    )
    catalog = json.loads((output / "corpus" / "index.json").read_text())
    assert catalog["runs"] == []
    assert len(catalog["settings"]) == 1
    path = output / "corpus" / catalog["settings"][0]
    settings = ExecutionSettings.model_validate_json(path.read_text())
    assert settings.corpus == corpus
    assert settings.workflow_table is None
    assert settings.data_root == tmp_path / "vendor-files"
    assert load_corpus(path.parent / "corpus.csv") == [dataset()]


def test_aggregate_configuration_discovers_its_exact_workflow_table(tmp_path: Path) -> None:
    from apb_studio.corpus.cli import RunOptions, configure

    corpus = tmp_path / "corpuses" / "small.csv"
    write_rows(corpus, CORPUS_COLUMNS, [dataset().model_dump()])
    output = tmp_path / "output"
    configure(
        RunOptions(
            corpus=corpus,
            data_root=tmp_path / "vendor-files",
            output_root=output,
            workflow="aggregate",
            apb_executable=Path(sys.executable),
            aggregate_executable=Path(sys.executable),
        )
    )
    catalog = json.loads((output / "corpus" / "index.json").read_text())
    path = output / "corpus" / catalog["settings"][0]
    settings = ExecutionSettings.model_validate_json(path.read_text())
    assert settings.workflow_table == (Path("workflow_tables") / "workflow_aggregate.csv").resolve()
    assert settings.aggregate_executable == Path(sys.executable).resolve()
