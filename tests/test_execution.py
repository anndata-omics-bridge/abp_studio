"""Tests for execution.py (scope×stage → Snakemake job / Clean) and the jobrunner."""

from pathlib import Path

import pytest
import yaml

from apb_studio import provenance
from apb_studio.execution import (
    clean_selection,
    clean_targets,
    load_overview,
    run_pipeline,
    selected_outputs,
    snakemake_argv,
)
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
            Path(f"{out}/m1/d/annotated.h5mu"),
            ["apb", "annotate"],
            [],
        ),
        Target(
            "m2", "d", "convert", Path(f"{out}/m2/d/ion.h5ad"), ["apb", "convert"], []
        ),
    ]


# --- snakemake_argv / selected_outputs --------------------------------------------------------


def test_snakemake_argv_default_goal():
    argv = snakemake_argv("Snakefile", "corpus.yaml", snakemake_exe="snakemake")
    assert argv == [
        "snakemake",
        "-s",
        "Snakefile",
        "--configfile",
        "corpus.yaml",
        "--cores",
        "1",
        "--keep-going",
    ]


def test_snakemake_argv_is_resilient_keep_going():
    # A corpus is many independent datasets; one failure must not abort the rest.
    assert "--keep-going" in snakemake_argv(
        "Snakefile", "corpus.yaml", snakemake_exe="snakemake"
    )


def test_snakemake_argv_with_targets_and_dry_run():
    argv = snakemake_argv(
        "Snakefile",
        "corpus.yaml",
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
        "corpus.yaml",
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
            "corpus.yaml",
            "/tmp/log",
            targets=[],
            start=lambda *a, **k: "JOB",
        )


def test_run_pipeline_none_targets_means_default_goal():
    calls = {}
    run_pipeline(
        "Snakefile",
        "corpus.yaml",
        "/tmp/log",
        targets=None,
        snakemake_exe="snakemake",
        start=lambda argv, log, **k: calls.setdefault("argv", argv),
    )
    # No target paths appended → Snakemake builds its default goal (argv ends at the flags).
    assert calls["argv"][-1] == "--keep-going"  # no trailing target paths
    assert not any(a.endswith((".h5mu", ".h5ad")) for a in calls["argv"])


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
    assert (out / "m1/d/annotated.h5mu").exists()  # annotate not selected → kept


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
    assert (out / "m1/d/annotated.h5mu").exists()  # downstream untouched
    assert (out / "m2/d/ion.h5ad").exists()  # other module untouched


def test_clean_targets_refuses_input_root():
    bad = [Target("m", "d", "convert", Path("/in/r.tsv"), [], [])]
    with pytest.raises(CleanGuardError, match="input_root"):
        clean_targets(bad, input_root="/in")


def test_clean_targets_removes_sidecar_log(tmp_path):
    # The per-rule <artifact>.log must go with the artifact, else a cleaned dataset would be
    # mis-flagged as "failed" (artifact gone + log lingering).
    out = tmp_path / "out"
    targets = _targets(out=str(out))
    conv = next(t for t in targets if t.stage == "convert" and t.module == "m1")
    conv.output.parent.mkdir(parents=True, exist_ok=True)
    conv.output.touch()
    Path(f"{conv.output}.log").write_text("boom")
    clean_targets([conv], input_root=str(tmp_path / "in"))
    assert not conv.output.exists()
    assert not Path(f"{conv.output}.log").exists()


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
                "annotation": "/a.json",
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
    targets = expand_targets(reg, corpus)
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

    assert {p.name for p in deleted} == {"mudata.h5mu", "annotated_fasta.h5mu"}
    assert not any(t.output.exists() for t in targets)  # nothing orphaned


def test_clean_selection_prunes_provenance(tmp_path):
    out = tmp_path / "out"
    targets = _targets(out=str(out))
    for t in targets:
        t.output.parent.mkdir(parents=True, exist_ok=True)
        t.output.touch()
    conv = next(t for t in targets if t.stage == "convert" and t.module == "m1")
    provenance.write_for_target(conv, timestamp="t")
    assert (out / "m1/d/provenance.json").exists()
    clean_selection(
        targets, input_root=str(tmp_path / "in"), scope="module", module="m1"
    )
    # m1's cleaned artifacts → their provenance entries pruned → empty sidecar removed.
    assert not (out / "m1/d/provenance.json").exists()


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


# --- load_overview never raises: bad config → readable message, not a traceback ---------------


def _write(tmp_path, corpus):
    p = tmp_path / "corpus.yaml"
    p.write_text(yaml.safe_dump(corpus))
    return p


def test_load_overview_valid_config(tmp_path):
    cfg = _write(
        tmp_path,
        {
            "input_root": "/in",
            "output_root": "/out",
            "modules": {
                "m": {
                    "datasets": [
                        {
                            "name": "diann-d",
                            "vendor": "diann",
                            "input": "r.tsv",
                            "params": "r.log",
                        }
                    ]
                }
            },
        },
    )
    targets, rows, corpus, error = load_overview(cfg)
    assert error is None and len(targets) == 1 and corpus["output_root"] == "/out"


def test_load_overview_missing_file_is_message_not_raise():
    targets, rows, corpus, error = load_overview("/nope/corpus.yaml")
    assert targets == [] and corpus == {}
    assert error and "not found" in error and "make scaffold" in error


def test_load_overview_old_schema_is_message_not_raise(tmp_path):
    # Old schema (vendor at module level, dataset has no vendor) → expand_targets raises → message.
    cfg = _write(
        tmp_path,
        {
            "input_root": "/in",
            "output_root": "/out",
            "modules": {
                "m__fragpipe": {
                    "vendor": "fragpipe",
                    "level": "ion",
                    "datasets": [{"name": "d", "input": "r.tsv", "params": "r.log"}],
                }
            },
        },
    )
    targets, rows, corpus, error = load_overview(cfg)
    assert targets == [] and error and "make scaffold" in error and "vendor" in error
