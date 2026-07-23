"""Tests for execution.py (scope×stage → Snakemake job / Clean) and the jobrunner."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apb_studio import execution, provenance, settings
from apb_studio.capabilities import CapabilityDiscovery, CapabilityStatus
from apb_studio.execution import (
    clean_selection,
    clean_targets,
    load_overview,
    prepare_run,
    run_pipeline,
    selected_outputs,
    snakemake_argv,
)
from apb_studio.fixture_inventory import load_fixture_inventory
from apb_studio.jobrunner import inspect_job, make_run_key, start_job, terminate_job
from apb_studio.pipeline import (
    CleanGuardError,
    Target,
    descendants,
    expand_targets,
    load_registry,
    targets_for,
)


def _targets(out="/out"):
    return [
        Target(
            "m1",
            "d",
            "convert",
            Path(f"{out}/m1/d/mudata.h5mu"),
            ["apb", "convert"],
            [],
        ),
        Target(
            "m1",
            "d",
            "annotate",
            Path(f"{out}/m1/d/mudata.annotated.h5mu"),
            ["apb", "annotate"],
            [],
        ),
        Target(
            "m2", "d", "convert", Path(f"{out}/m2/d/ion.h5ad"), ["apb", "convert"], []
        ),
    ]


def _fixture_settings(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "fixtures"
    output_root = tmp_path / "outputs"
    fixture_dir = data_root / "json_dir" / "Results_quant_ion_DIA" / "abcdef123456"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "input_file.tsv").write_text("x\n")
    (fixture_dir / "param_0.txt").write_text("params\n")
    (data_root / "raw_file_db_full.csv").write_text(
        "module,repo_name,intermediate_hash,software_name,software_version\n"
        "dia_qtof,Results_quant_ion_DIA,abcdef123456,DIA-NN,2.0\n"
    )
    annotation = data_root / "annotation.toml"
    fasta = data_root / "proteome.fasta"
    annotation.write_text('[[samples]]\nraw_file = "run"\ncondition = "A"\n')
    fasta.write_text(">P1\nPEPTIDE\n")
    (data_root / "module_resources.csv").write_text(
        f"module,annotation_path,fasta_path\ndia_qtof,{annotation},{fasta}\n"
    )
    settings_path = tmp_path / "settings.json"
    settings.update_settings(
        test_data_root=data_root,
        output_root=output_root,
        path=settings_path,
    )
    return settings_path, data_root, output_root


def _supported_discovery(*_args: object) -> CapabilityDiscovery:
    return CapabilityDiscovery(
        ("mudata", "ion"),
        status=CapabilityStatus.SUPPORTED,
        software_slug="diann",
        software_version="2.0",
    )


# --- snakemake_argv / selected_outputs --------------------------------------------------------


def test_snakemake_argv_default_goal():
    argv = snakemake_argv("Snakefile", "run.json", snakemake_exe="snakemake")
    assert argv == [
        "snakemake",
        "-s",
        "Snakefile",
        "--configfile",
        "run.json",
        "--cores",
        "1",
        "--keep-going",
    ]


def test_snakemake_argv_is_resilient_keep_going():
    # A corpus is many independent datasets; one failure must not abort the rest.
    assert "--keep-going" in snakemake_argv(
        "Snakefile", "run.json", snakemake_exe="snakemake"
    )


def test_snakemake_argv_with_targets_and_dry_run():
    argv = snakemake_argv(
        "Snakefile",
        "run.json",
        targets=[Path("/out/x.h5mu")],
        dry_run=True,
        snakemake_exe="snakemake",
    )
    assert "-n" in argv and "/out/x.h5mu" in argv


def test_selected_outputs_filters_by_scope_and_stage():
    targets = _targets()
    assert len(selected_outputs(targets)) == 3
    assert len(selected_outputs(targets, stage="convert")) == 2
    assert selected_outputs(targets, scope="module", module="m2") == [
        Path("/out/m2/d/ion.h5ad")
    ]


# --- run_pipeline uses an injectable launcher (no real process) -------------------------------


def test_run_pipeline_builds_job_via_injected_start():
    calls = {}

    def fake_start(argv, log_file, *, cwd=None):
        calls["argv"] = argv
        calls["log_file"] = log_file
        return "JOB"

    job = run_pipeline(
        "Snakefile",
        "run.json",
        "/tmp/log",
        targets=[Path("/out/x.h5mu")],
        snakemake_exe="snakemake",
        start=fake_start,
    )
    assert job == "JOB"
    assert calls["argv"][0] == "snakemake" and "/out/x.h5mu" in calls["argv"]
    assert calls["log_file"] == "/tmp/log"


def test_run_pipeline_refuses_empty_targets():
    # An empty target list would fall through to Snakemake's default goal (the whole corpus).
    with pytest.raises(ValueError, match="nothing selected|whole corpus"):
        run_pipeline(
            "Snakefile",
            "run.json",
            "/tmp/log",
            targets=[],
            start=lambda *a, **k: "JOB",
        )


def test_run_pipeline_none_targets_means_default_goal():
    calls = {}
    run_pipeline(
        "Snakefile",
        "run.json",
        "/tmp/log",
        targets=None,
        snakemake_exe="snakemake",
        start=lambda argv, log, **k: calls.setdefault("argv", argv),
    )
    # No target paths appended → Snakemake builds its default goal (argv ends at the flags).
    assert calls["argv"][-1] == "--keep-going"  # no trailing target paths
    assert not any(a.endswith((".h5mu", ".h5ad")) for a in calls["argv"])


def test_launch_corpus_keeps_existing_targets_for_snakemake_staleness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path, _data_root, _output_root = _fixture_settings(tmp_path)
    snapshot, run_path, selected = prepare_run(
        settings_path=settings_path,
        discover=_supported_discovery,
    )
    target = next(item for item in selected if item.stage == "convert")
    target.output.parent.mkdir(parents=True, exist_ok=True)
    target.output.touch()
    captured: dict[str, object] = {}

    monkeypatch.setattr(execution, "_JOBS", {})
    monkeypatch.setattr(execution, "_RUNS", {})
    monkeypatch.setattr(
        execution, "prepare_run", lambda **_kwargs: (snapshot, run_path, selected)
    )

    def fake_run_pipeline(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(execution, "run_pipeline", fake_run_pipeline)

    job_id = execution.launch_corpus(settings_path=settings_path)

    assert job_id
    assert target.output in captured["targets"]
    assert captured["args"][1] == run_path
    assert execution._RUNS[job_id] == run_path


# --- clean_selection deletes outputs, never inputs --------------------------------------------


def test_clean_selection_deletes_selected_outputs(tmp_path):
    out = tmp_path / "out"
    targets = _targets(out=str(out))
    for t in targets:
        t.output.parent.mkdir(parents=True, exist_ok=True)
        t.output.touch()
    deleted = clean_selection(targets, input_root=str(tmp_path / "in"), stage="convert")
    assert {p.name for p in deleted} == {"mudata.h5mu", "ion.h5ad"}
    assert not (out / "m1/d/mudata.h5mu").exists()
    assert (out / "m1/d/mudata.annotated.h5mu").exists()


def test_clean_selection_refuses_input_root():
    bad = [Target("m", "d", "convert", Path("/in/r.tsv"), [], [])]
    with pytest.raises(CleanGuardError, match="input_root"):
        clean_selection(bad, input_root="/in")


# --- clean_targets: the row-set primitive the kanban baskets use ------------------------------


def test_clean_targets_deletes_only_the_given_rows(tmp_path):
    # Basket Clean = clean the selected rows' artifact at that basket's stage (via targets_for).
    out = tmp_path / "out"
    targets = _targets(out=str(out))
    for t in targets:
        t.output.parent.mkdir(parents=True, exist_ok=True)
        t.output.touch()
    selected = targets_for(
        targets, {("m1", "d")}, stage="convert"
    )  # one row, one stage
    deleted = clean_targets(selected, input_root=str(tmp_path / "in"))
    assert deleted == [out / "m1/d/mudata.h5mu"]
    assert not (out / "m1/d/mudata.h5mu").exists()
    assert (out / "m1/d/mudata.annotated.h5mu").exists()
    assert (out / "m2/d/ion.h5ad").exists()  # other module untouched


def test_clean_targets_refuses_input_root():
    bad = [Target("m", "d", "convert", Path("/in/r.tsv"), [], [])]
    with pytest.raises(CleanGuardError, match="input_root"):
        clean_targets(bad, input_root="/in")


def test_clean_targets_removes_sidecar_log_and_failure_marker(tmp_path):
    # Rule diagnostics must go with a cleaned artifact so its next state is pending.
    out = tmp_path / "out"
    targets = _targets(out=str(out))
    conv = next(t for t in targets if t.stage == "convert" and t.module == "m1")
    conv.output.parent.mkdir(parents=True, exist_ok=True)
    conv.output.touch()
    Path(f"{conv.output}.log").write_text("boom")
    Path(f"{conv.output}.failed").write_text("exit 1\n")
    clean_targets([conv], input_root=str(tmp_path / "in"))
    assert not conv.output.exists()
    assert not Path(f"{conv.output}.log").exists()
    assert not Path(f"{conv.output}.failed").exists()


def test_clean_cascade_removes_stray_downstream_artifact(tmp_path):
    # Holey on-disk state: convert + fasta present, annotate MISSING (partial run / manual copy).
    # The dataset shows in `converted`; a basket Clean must cascade (convert + its descendants) so
    # the stray annotated_fasta.* is swept too — no orphan left behind (§8.3, review Medium #1).
    reg = load_registry()
    corpus = {
        "input_root": str(tmp_path / "in"),
        "output_root": str(tmp_path / "out"),
        "modules": {
            "m": {
                "annotation": "/a.toml",
                "fasta": "/p.fasta",
                "datasets": [
                    {
                        "name": "diann-d",
                        "vendor": "diann",
                        "input": "r.tsv",
                        "params": "r.log",
                    }
                ],
            }
        },
    }
    targets = expand_targets(
        reg,
        corpus,
        discover=lambda *_args: CapabilityDiscovery(("mudata",)),
    )
    for stage in ("convert", "fasta"):  # annotate deliberately absent
        t = next(x for x in targets if x.stage == stage)
        t.output.parent.mkdir(parents=True, exist_ok=True)
        t.output.touch()

    keys = {("m", "diann-d")}
    cascade = [
        "convert",
        *descendants(reg, "convert"),
    ]  # what a `converted` Clean sweeps
    to_clean = [t for s in cascade for t in targets_for(targets, keys, stage=s)]
    deleted = clean_targets(to_clean, input_root=str(tmp_path / "in"))

    assert {p.name for p in deleted} == {
        "mudata.h5mu",
        "mudata.fasta.h5mu",
    }
    assert not any(t.output.exists() for t in targets)  # nothing orphaned


def test_clean_selection_prunes_provenance(tmp_path):
    out = tmp_path / "out"
    targets = _targets(out=str(out))
    for t in targets:
        t.output.parent.mkdir(parents=True, exist_ok=True)
        t.output.touch()
    conv = next(t for t in targets if t.stage == "convert" and t.module == "m1")
    provenance.write_for_target(conv, timestamp="t")
    sidecar = provenance.sidecar_path(conv.output)
    assert sidecar.exists()
    clean_selection(
        targets, input_root=str(tmp_path / "in"), scope="module", module="m1"
    )
    assert not sidecar.exists()


# --- jobrunner end-to-end on a tiny real subprocess -------------------------------------------


def test_jobrunner_runs_and_captures_output(tmp_path):
    log = tmp_path / "console.log"
    job = start_job(["sh", "-c", "echo hello-jobrunner"], log)
    job.process.wait(timeout=10)
    status = inspect_job(job)
    assert status.success and not status.running
    assert "hello-jobrunner" in status.log_text
    assert terminate_job(job) is False  # already finished


def test_jobrunner_unbuffers_python_output(tmp_path):
    captured = {}

    class FakeProcess:
        pass

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    start_job(["python", "script.py"], tmp_path / "console.log", popen=fake_popen)

    assert captured["env"]["PYTHONUNBUFFERED"] == "1"


def test_jobrunner_preserves_explicit_unbuffered_setting(tmp_path):
    captured = {}

    class FakeProcess:
        pass

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    start_job(
        ["python", "script.py"],
        tmp_path / "console.log",
        env={"PYTHONUNBUFFERED": "0"},
        popen=fake_popen,
    )

    assert captured["env"]["PYTHONUNBUFFERED"] == "0"


def test_make_run_key_changes_with_inputs():
    assert make_run_key("a", 1) == make_run_key("a", 1)
    assert make_run_key("a", 1) != make_run_key("a", 2)


# --- inventory-driven overview and generated run snapshots ------------------------------------


def test_load_overview_resolves_shared_inventory(tmp_path: Path) -> None:
    settings_path, data_root, output_root = _fixture_settings(tmp_path)

    targets, rows, snapshot, error = load_overview(
        settings_path=settings_path,
        discover=_supported_discovery,
    )

    assert error is None
    assert snapshot is not None
    assert snapshot.test_data_root == data_root.resolve()
    assert snapshot.output_root == output_root.resolve()
    assert len(snapshot.fixtures) == 1
    assert {(target.branch, target.stage) for target in targets} == {
        (branch, stage)
        for branch in ("mudata", "ion")
        for stage in ("convert", "annotate", "fasta", "proteobench")
    }
    assert len(rows) == len(targets)


def test_persisted_invalid_resources_block_stages_before_execution(
    tmp_path: Path,
) -> None:
    settings_path, data_root, _output_root = _fixture_settings(tmp_path)
    annotation = data_root / "annotation.toml"
    fasta = data_root / "proteome.fasta"
    annotation.write_text("[general]\nlevel = 'ion'\n")
    fasta.write_text("not FASTA\n")

    snapshot, _path, selected = prepare_run(
        settings_path=settings_path,
        discover=_supported_discovery,
    )

    annotate = next(
        target
        for target in snapshot.targets
        if target.branch == "mudata" and target.stage == "annotate"
    )
    fasta_target = next(
        target
        for target in snapshot.targets
        if target.branch == "mudata" and target.stage == "fasta"
    )
    assert annotate.command == []
    assert annotate.blocked_reason is not None
    assert "Invalid annotation resource" in annotate.blocked_reason
    assert fasta_target.command == []
    assert fasta_target.blocked_reason is not None
    assert "Invalid FASTA resource" in fasta_target.blocked_reason
    assert {target.stage for target in selected} == {"convert"}


def test_prepare_run_writes_internal_json_and_alias_map(tmp_path: Path) -> None:
    settings_path, _data_root, output_root = _fixture_settings(tmp_path)
    legacy = output_root / "Results_quant_ion_DIA" / "legacy-abcdef12"
    legacy.mkdir(parents=True)

    snapshot, path, selected = prepare_run(
        settings_path=settings_path,
        discover=_supported_discovery,
    )

    assert path == output_root / ".apb_studio" / "runs" / snapshot.run_id / "run.json"
    assert path.is_file()
    assert selected
    assert snapshot.fixtures[0].dataset == "legacy-abcdef12"
    assert execution.output_alias_path(output_root).is_file()
    document = json.loads(path.read_text())
    assert document["schema_version"] == 1
    assert "modules" not in document


def test_output_aliases_remain_unique_after_the_full_hash_is_occupied(
    tmp_path: Path,
) -> None:
    _settings_path, data_root, output_root = _fixture_settings(tmp_path)
    fixture = load_fixture_inventory(data_root).complete_local[0]
    fixtures = [
        fixture.model_copy(update={"module": module})
        for module in ("module_a", "module_b", "module_c")
    ]
    discoveries = [(item, _supported_discovery()) for item in fixtures]

    aliases = execution.resolve_output_aliases(
        discoveries,
        output_root,
        persist=False,
    )

    assert len(set(aliases.values())) == 3
    assert aliases[fixtures[0].identity] == "diann-abcdef12"
    assert aliases[fixtures[1].identity] == "diann-abcdef123456"
    assert aliases[fixtures[2].identity].startswith("diann-abcdef123456-")


def test_output_alias_store_rejects_two_fixtures_owning_one_alias(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs"
    path = execution.output_alias_path(output_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "aliases": [
                    {
                        "module": "module_a",
                        "repo_name": "repo",
                        "intermediate_hash": "hash_a",
                        "output_alias": "diann-shared",
                    },
                    {
                        "module": "module_b",
                        "repo_name": "repo",
                        "intermediate_hash": "hash_b",
                        "output_alias": "diann-shared",
                    },
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="assigned to both"):
        execution.resolve_output_aliases([], output_root, persist=False)


def test_active_run_snapshot_survives_browser_state_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path, data_root, _output_root = _fixture_settings(tmp_path)
    pinned, run_path, _selected = prepare_run(
        settings_path=settings_path,
        discover=_supported_discovery,
    )
    state = {"running": True}
    monkeypatch.setattr(execution, "_JOBS", {"active": object()})
    monkeypatch.setattr(execution, "_RUNS", {"active": run_path})
    monkeypatch.setattr(
        execution,
        "inspect_job",
        lambda _job: SimpleNamespace(running=state["running"]),
    )

    second_dir = data_root / "json_dir" / "Results_quant_ion_DIA" / "fedcba654321"
    second_dir.mkdir(parents=True)
    (second_dir / "input_file.tsv").write_text("x\n")
    (second_dir / "param_0.txt").write_text("params\n")
    with (data_root / "raw_file_db_full.csv").open("a") as stream:
        stream.write("dia_qtof,Results_quant_ion_DIA,fedcba654321,DIA-NN,2.0\n")

    _targets, _rows, active_snapshot, error = load_overview(
        None,
        settings_path=settings_path,
        discover=_supported_discovery,
    )

    assert error is None
    assert execution.active_corpus_job_id() == "active"
    assert active_snapshot == pinned

    state["running"] = False
    _targets, _rows, refreshed_snapshot, error = load_overview(
        None,
        settings_path=settings_path,
        discover=_supported_discovery,
    )

    assert error is None
    assert execution.active_corpus_job_id() is None
    assert refreshed_snapshot is not None
    assert len(refreshed_snapshot.fixtures) == 2


def test_load_overview_returns_readable_settings_error(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("not JSON")

    targets, rows, snapshot, error = load_overview(settings_path=settings_path)

    assert targets == []
    assert rows == []
    assert snapshot is None
    assert error and "Fixture Manager inventory" in error and "JSONDecodeError" in error
