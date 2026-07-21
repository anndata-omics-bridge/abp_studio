"""Phase-1 acceptance: `snakemake -n` resolves the DAG for both a multi-level and a single-level
module. Exercises the real Snakefile (wildcard routing, rule all, convert→annotate edges) against a
self-contained fixture corpus with touched stand-in inputs.
"""

import shutil
import subprocess

import pytest
import yaml

from apb_studio.registry import REGISTRY_PATH

_REPO_ROOT = REGISTRY_PATH.parents[1]
_SNAKEFILE = _REPO_ROOT / "workflow" / "Snakefile"
_SNAKEMAKE = shutil.which("snakemake")


def _fixture_corpus(tmp_path):
    in_root, out_root = tmp_path / "in", tmp_path / "out"
    files = {
        "quant_lfq_ion_DIA_AIF/run1/report.tsv": None,
        "quant_lfq_ion_DIA_AIF/run1/report.log.txt": None,
        "quant_lfq_ion_DDA_QExactive/runA/evidence.txt": None,
        "quant_lfq_ion_DDA_QExactive/runA/parameters.txt": None,
        "diann_annotation.json": None,
        "mq_annotation.json": None,
    }
    for rel in files:
        p = in_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    corpus = {
        "input_root": str(in_root),
        "output_root": str(out_root),
        "modules": {
            "quant_lfq_ion_DIA_AIF": {
                "annotation": str(in_root / "diann_annotation.json"),
                "datasets": [
                    {
                        "name": "diann-run1",
                        "vendor": "diann",
                        "input": "quant_lfq_ion_DIA_AIF/run1/report.tsv",
                        "params": "quant_lfq_ion_DIA_AIF/run1/report.log.txt",
                    }
                ],
            },
            "quant_lfq_ion_DDA_QExactive": {
                "annotation": str(in_root / "mq_annotation.json"),
                "datasets": [
                    {
                        "name": "maxquant-runA",
                        "vendor": "maxquant",
                        "level": "ion",
                        "input": "quant_lfq_ion_DDA_QExactive/runA/evidence.txt",
                        "params": "quant_lfq_ion_DDA_QExactive/runA/parameters.txt",
                    }
                ],
            },
        },
    }
    path = tmp_path / "corpus.yaml"
    path.write_text(yaml.safe_dump(corpus, sort_keys=False))
    return path


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_dry_run_resolves_default_dag(tmp_path):
    config = _fixture_corpus(tmp_path)
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
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    # Default goal = convert + annotate for both modules (4 jobs + the `all` aggregator).
    assert "convert" in out and "annotate" in out


@pytest.mark.skipif(_SNAKEMAKE is None, reason="snakemake not installed")
def test_dry_run_routes_single_and_multi_level_artifacts(tmp_path):
    config = _fixture_corpus(tmp_path)
    out_root = tmp_path / "out"
    targets = [
        str(
            out_root / "quant_lfq_ion_DIA_AIF/diann-run1/mudata.h5mu"
        ),  # multi-level → MuData
        str(
            out_root / "quant_lfq_ion_DDA_QExactive/maxquant-runA/ion.h5ad"
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
            *targets,
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
