"""Acceptance tests for JSON-supported branch fan-out in the real Snakefile."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from anndata_proteomics.converters import pipeline as conversion_pipeline
from anndata_proteomics.converters.recognize import _expected_long_columns
from anndata_proteomics.params.registry import parse_params
from anndata_proteomics.rules.loader import resolve_rule_for_version

from apb_studio import capabilities, run_history
from apb_studio.pipeline import (
    RUN_SNAPSHOT_SCHEMA_VERSION,
    ResolvedFixture,
    RunSnapshot,
    Target,
    benchmark_path,
    expand_resolved_targets,
    failure_marker_path,
    write_run_snapshot,
)
from apb_studio.registry import REGISTRY_PATH, load_registry

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SNAKEFILE = REGISTRY_PATH.parent.parent / "workflow" / "Snakefile"
_LOCAL_SNAKEMAKE = _REPO_ROOT / ".venv" / "bin" / "snakemake"
_SNAKEMAKE = str(_LOCAL_SNAKEMAKE) if _LOCAL_SNAKEMAKE.exists() else shutil.which("snakemake")
_APB_PARAMS = _REPO_ROOT.parent / "apb" / "tests" / "params"


def _long_headers(software: str, parameter_path: Path) -> tuple[str, ...]:
    """Required headers of every matching packaged long-format level rule."""
    version = parse_params(parameter_path, software=software).software_version
    headers: set[str] = set()
    for level in conversion_pipeline.LEVELS:
        rule = resolve_rule_for_version(software, level, version)
        if rule is None or rule.input_shape != "long":
            continue
        headers.update(_expected_long_columns(rule))
        if rule.fragments is not None and rule.fragments.label_strategy == "column":
            headers.add(rule.fragments.label_column)
    return tuple(sorted(headers))


def _fragpipe_headers(parameter_path: Path) -> tuple[str, ...]:
    """Required FragPipe wide columns, including one sample's required intensity."""
    version = parse_params(parameter_path, software="fragpipe").software_version
    rule = resolve_rule_for_version("fragpipe", "ion", version)
    assert rule is not None
    return (*sorted(rule.columns.var.select.values()), "run1 Intensity")


def _snakemake_env(tmp_path: Path) -> dict[str, str]:
    return {**os.environ, "XDG_CACHE_HOME": str(tmp_path / "cache")}


def _runtime_cache(tmp_path: Path) -> str:
    path = tmp_path / "runtime-source-cache"
    path.mkdir()
    return str(path)


def _fixture_run(tmp_path: Path) -> Path:
    in_root, out_root = tmp_path / "in", tmp_path / "out"
    files = (
        "diann_annotation.toml",
        "diann.fasta",
        "spectronaut_annotation.toml",
        "spectronaut.fasta",
        "fragpipe_annotation.toml",
        "fragpipe.fasta",
    )
    for rel in files:
        p = in_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix == ".toml":
            p.write_text('[[samples]]\nraw_file = "run1"\ncondition = "A"\n')
        else:
            p.touch()

    diann_dir = in_root / "quant_lfq_ion_DIA_AIF" / "run1"
    diann_dir.mkdir(parents=True)
    diann_params = _APB_PARAMS / "Version1_9_Predicted_Library_report.log.txt"
    (diann_dir / "report.tsv").write_text("\t".join(_long_headers("diann", diann_params)) + "\n")
    shutil.copyfile(
        diann_params,
        diann_dir / "report.log.txt",
    )

    spectronaut_dir = in_root / "quant_lfq_ion_DIA_Spectronaut" / "runS"
    spectronaut_dir.mkdir(parents=True)
    spectronaut_params = (
        _APB_PARAMS / "spectronaut_Experiment1_ExperimentSetupOverview_BGS_Factory_Settings.txt"
    )
    (spectronaut_dir / "report.tsv").write_text(
        "\t".join(_long_headers("spectronaut", spectronaut_params)) + "\n"
    )
    shutil.copyfile(spectronaut_params, spectronaut_dir / "settings.txt")

    fragpipe_dir = in_root / "quant_lfq_ion_DDA_QExactive" / "runA"
    fragpipe_dir.mkdir(parents=True)
    fragpipe_params = _APB_PARAMS / "fragpipe_fdr_test.workflow"
    (fragpipe_dir / "combined_ion.tsv").write_text(
        "\t".join(_fragpipe_headers(fragpipe_params)) + "\n"
    )
    shutil.copyfile(
        fragpipe_params,
        fragpipe_dir / "fragpipe.workflow",
    )

    fixture_inputs = (
        (
            "dia_aif",
            "quant_lfq_ion_DIA_AIF",
            "hash-diann",
            "diann-run1",
            "DIA-NN",
            diann_dir / "report.tsv",
            diann_dir / "report.log.txt",
            in_root / "diann_annotation.toml",
            in_root / "diann.fasta",
        ),
        (
            "dia_spectronaut",
            "quant_lfq_ion_DIA_Spectronaut",
            "hash-spectronaut",
            "spectronaut-runS",
            "Spectronaut",
            spectronaut_dir / "report.tsv",
            spectronaut_dir / "settings.txt",
            in_root / "spectronaut_annotation.toml",
            in_root / "spectronaut.fasta",
        ),
        (
            "dda_qexactive",
            "quant_lfq_ion_DDA_QExactive",
            "hash-fragpipe",
            "fragpipe-runA",
            "FragPipe",
            fragpipe_dir / "combined_ion.tsv",
            fragpipe_dir / "fragpipe.workflow",
            in_root / "fragpipe_annotation.toml",
            in_root / "fragpipe.fasta",
        ),
    )
    fixtures = []
    for (
        module,
        repo_name,
        intermediate_hash,
        dataset,
        software,
        input_path,
        parameter_path,
        annotation,
        fasta,
    ) in fixture_inputs:
        discovery = capabilities.discover_capabilities(
            input_path,
            parameter_path,
            software,
        )
        assert discovery.branches, discovery.diagnostic
        fixtures.append(
            ResolvedFixture(
                module=module,
                repo_name=repo_name,
                intermediate_hash=intermediate_hash,
                dataset=dataset,
                software=software,
                vendor=discovery.software_slug or software.lower(),
                input_path=input_path,
                parameter_path=parameter_path,
                branches=discovery.branches,
                capability_status=discovery.status.value,
                annotation_path=annotation,
                fasta_path=fasta,
            )
        )
    resolved = tuple(fixtures)
    targets = expand_resolved_targets(load_registry(), resolved, out_root)
    snapshot = RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id="dag-test",
        created_at="2026-07-22T00:00:00+00:00",
        test_data_root=in_root,
        output_root=out_root,
        registry_digest="test-registry",
        apb_version=None,
        fixtures=resolved,
        targets=tuple(targets),
    )
    path = tmp_path / "run.json"
    write_run_snapshot(snapshot, path)
    return path


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_dry_run_resolves_default_dag(tmp_path: Path) -> None:
    assert _SNAKEMAKE is not None
    config = _fixture_run(tmp_path)
    proc = subprocess.run(
        [
            _SNAKEMAKE,
            "-s",
            str(_SNAKEFILE),
            "--configfile",
            str(config),
            "-n",
            "--cores",
            "1",
            "--runtime-source-cache-path",
            _runtime_cache(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=_snakemake_env(tmp_path),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "convert" in out
    assert "annotate" in out
    assert "fasta" in out
    assert "proteobench" in out
    assert "spectronaut-runS/mudata.fasta.h5mu" in out
    assert "spectronaut-runS/ion.fasta.h5ad" in out
    assert "spectronaut-runS/protein.fasta.h5ad" in out
    assert "spectronaut-runS/fragment.fasta.h5ad" in out
    assert "spectronaut-runS/mudata.proteobench.h5mu" in out
    assert "spectronaut-runS/ion.proteobench.h5ad" in out
    assert "spectronaut-runS/protein.proteobench.h5ad" in out
    assert "spectronaut-runS/fragment.proteobench.h5ad" in out


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_dry_run_routes_single_and_multi_level_artifacts(tmp_path: Path) -> None:
    assert _SNAKEMAKE is not None
    config = _fixture_run(tmp_path)
    out_root = tmp_path / "out"
    targets = [
        str(out_root / "quant_lfq_ion_DIA_AIF/diann-run1/mudata.h5mu"),  # multi-level → MuData
        str(
            out_root / "quant_lfq_ion_DDA_QExactive/fragpipe-runA/ion.h5ad"
        ),  # single-level → <level>.h5ad
    ]
    proc = subprocess.run(
        [
            _SNAKEMAKE,
            "-s",
            str(_SNAKEFILE),
            "--configfile",
            str(config),
            "-n",
            "--cores",
            "1",
            "--runtime-source-cache-path",
            _runtime_cache(tmp_path),
            *targets,
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=_snakemake_env(tmp_path),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _single_command_run(
    tmp_path: Path,
    command: list[str],
    *,
    run_id: str,
) -> tuple[Path, Path]:
    """Write a one-target run snapshot for real shell-behavior tests."""
    input_root = tmp_path / "in"
    input_root.mkdir()
    input_path = input_root / "input.tsv"
    parameter_path = input_root / "params.txt"
    input_path.write_text("header\n")
    parameter_path.write_text("params\n")
    output = tmp_path / "out" / "module" / "fixture" / "ion.h5ad"
    fixture = ResolvedFixture(
        module="module",
        repo_name="module",
        intermediate_hash="fixture-hash",
        dataset="fixture",
        software="Test",
        vendor="test",
        input_path=input_path,
        parameter_path=parameter_path,
        branches=("ion",),
        capability_status="supported",
    )
    target = Target(
        module="module",
        dataset="fixture",
        stage="convert",
        output=output,
        command=command,
        inputs=[input_path, parameter_path],
        vendor="test",
        level="ion",
        branch="ion",
    )
    snapshot = RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id=run_id,
        created_at="2026-07-22T00:00:00+00:00",
        test_data_root=input_root,
        output_root=tmp_path / "out",
        registry_digest="test-registry",
        apb_version=None,
        fixtures=(fixture,),
        targets=(target,),
    )
    run_path = tmp_path / f"{run_id}.json"
    write_run_snapshot(snapshot, run_path)
    return run_path, output


def _run_real_target(
    tmp_path: Path,
    run_path: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one concrete target through the real Snakefile."""
    assert _SNAKEMAKE is not None
    return subprocess.run(
        [
            _SNAKEMAKE,
            "-s",
            str(_SNAKEFILE),
            "--configfile",
            str(run_path),
            "--cores",
            "1",
            "--runtime-source-cache-path",
            _runtime_cache(tmp_path),
            str(output),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=_snakemake_env(tmp_path),
    )


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_successful_rule_writes_elapsed_time_benchmark(tmp_path: Path) -> None:
    output = tmp_path / "out/module/fixture/ion.h5ad"
    command = [
        "sh",
        "-c",
        (f"mkdir -p {shlex.quote(str(output.parent))} && touch {shlex.quote(str(output))}"),
    ]
    run_path, resolved_output = _single_command_run(
        tmp_path,
        command,
        run_id="benchmark-test",
    )

    proc = _run_real_target(tmp_path, run_path, resolved_output)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    benchmark = benchmark_path(resolved_output)
    assert benchmark.is_file()
    header, values = benchmark.read_text(encoding="utf-8").splitlines()
    elapsed = dict(zip(header.split("\t"), values.split("\t"), strict=True))["s"]
    assert float(elapsed) >= 0


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_clean_rule_removes_all_managed_state_and_records_success(tmp_path: Path) -> None:
    assert _SNAKEMAKE is not None
    run_path, resolved_output = _single_command_run(
        tmp_path,
        ["sh", "-c", "unused"],
        run_id="clean-test",
    )
    resolved_output.parent.mkdir(parents=True)
    resolved_output.write_text("artifact", encoding="utf-8")
    for suffix in (".log", ".failed", ".benchmark.tsv", ".provenance.json"):
        Path(f"{resolved_output}{suffix}").write_text("state", encoding="utf-8")
    run_history.start_operation(run_path, "clean", started_at="before")

    proc = subprocess.run(
        [
            _SNAKEMAKE,
            "-s",
            str(_SNAKEFILE),
            "--configfile",
            str(run_path),
            "--cores",
            "1",
            "--runtime-source-cache-path",
            _runtime_cache(tmp_path),
            "clean",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=_snakemake_env(tmp_path),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not resolved_output.exists()
    assert not any(
        Path(f"{resolved_output}{suffix}").exists()
        for suffix in (
            ".log",
            ".failed",
            ".benchmark.tsv",
            ".provenance.json",
        )
    )
    assert (tmp_path / "in/input.tsv").is_file()
    operation = run_history.load_operation(run_path)
    assert operation is not None
    assert operation.status == "succeeded"


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_failed_rule_writes_authoritative_marker_and_log(tmp_path: Path) -> None:
    """Exercise the real shell pipeline: a tee log alone is never failure state."""
    run_path, output = _single_command_run(
        tmp_path,
        ["sh", "-c", "echo deliberate-failure >&2; exit 7"],
        run_id="failure-test",
    )

    proc = _run_real_target(tmp_path, run_path, output)

    assert proc.returncode != 0
    assert not output.exists()
    assert "deliberate-failure" in Path(f"{output}.log").read_text()
    assert failure_marker_path(output).read_text().strip() == "exit 7"


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_success_without_declared_artifact_is_a_failed_rule(tmp_path: Path) -> None:
    run_path, output = _single_command_run(
        tmp_path,
        ["sh", "-c", "echo success-without-artifact"],
        run_id="missing-output-test",
    )

    proc = _run_real_target(tmp_path, run_path, output)

    assert proc.returncode != 0
    assert not output.exists()
    log = Path(f"{output}.log").read_text()
    assert "success-without-artifact" in log
    assert "without creating its artifact" in log
    assert failure_marker_path(output).read_text().strip() == "exit 1"


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_apb_command_resolves_from_snakemake_virtualenv(tmp_path: Path) -> None:
    run_path, output = _single_command_run(
        tmp_path,
        ["apb", "--version"],
        run_id="apb-executable-test",
    )

    proc = _run_real_target(tmp_path, run_path, output)

    assert proc.returncode != 0  # the version command intentionally creates no artifact
    log = Path(f"{output}.log").read_text()
    assert "command not found" not in log
    assert "Rule command completed without creating its artifact" in log
