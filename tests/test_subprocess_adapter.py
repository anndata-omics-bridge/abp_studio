"""The apb-convert shell-out seam: argv construction + command.json sidecar."""

from __future__ import annotations

import json

from apb_studio.conversion import subprocess_adapter as adapter


def test_result_filename() -> None:
    assert adapter.result_filename("ion") == "result.h5ad"
    assert adapter.result_filename("protein") == "result.h5ad"
    assert adapter.result_filename("mudata") == "result.h5mu"


def test_build_convert_argv_level_is_positional() -> None:
    argv = adapter.build_convert_argv(
        "/data/report.tsv", "protein", params="/p/log.txt", slug="diann", output="/out/result.h5ad"
    )
    assert argv == [
        "apb",
        "convert",
        "/data/report.tsv",
        "protein",
        "--params",
        "/p/log.txt",
        "--software",
        "diann",
        "--output",
        "/out/result.h5ad",
    ]


def test_build_convert_argv_mudata_omits_level() -> None:
    argv = adapter.build_convert_argv(
        "/data/report.tsv", "mudata", params="/p/log.txt", slug="diann", output="/out/result.h5mu"
    )
    assert argv[:3] == ["apb", "convert", "/data/report.tsv"]
    assert argv[3] == "--params"  # no positional level for the MuData target
    assert "mudata" not in argv


def test_start_conversion_writes_command_json_and_launches(tmp_path) -> None:
    calls = {}

    class FakeRunner:
        @staticmethod
        def start_job(argv, outdir, *, log_file=None, run_key=None):
            calls.update(argv=argv, outdir=outdir, log_file=log_file, run_key=run_key)
            return "JOB"

    job = adapter.start_conversion(
        "/data/report.tsv",
        slug="diann",
        target="ion",
        params="/p/log.txt",
        outdir=tmp_path / "run",
        runner=FakeRunner,
        input_rel="rel/input.tsv",
        run_key="k1",
    )

    assert job == "JOB"
    assert calls["argv"][:2] == ["apb", "convert"]
    assert calls["run_key"] == "k1"
    sidecar = json.loads((tmp_path / "run" / "command.json").read_text())
    assert sidecar == {
        "input_file_path": "rel/input.tsv",
        "slug": "diann",
        "target": "ion",
        "param_path": "/p/log.txt",
    }
