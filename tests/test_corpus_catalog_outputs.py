"""The run catalog exposes observed scientific file extensions, independently of storage labels."""

import json
from pathlib import Path

from apb_studio.corpus import catalog, cli


def _run(root: Path, name: str, reports: list[dict[str, object]]) -> Path:
    directory = root / name / "workflow" / "hdf5"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps({"schema_version": 2, "reports": reports}))
    (directory / "operation.json").write_text(json.dumps({"status": "succeeded"}))
    return directory


def _output(path: str, role: str = "result", size: int | None = 100) -> dict[str, object]:
    return {"role": role, "path": path, "size_bytes": size, "format": "hdf5"}


def _report(path: Path, outputs: list[dict[str, object]], status: str = "succeeded") -> None:
    path.write_text(json.dumps({"steps": [{"status": status, "outputs": outputs}]}))


def test_catalog_uses_actual_final_scientific_extensions_and_ignores_sidecars(
    tmp_path: Path,
) -> None:
    directory = _run(tmp_path, "mixed", [{"path": "first.json"}, {"path": "second.json"}])
    (directory / "first.json").write_text(
        json.dumps({
            "steps": [
                {"status": "succeeded", "outputs": [_output("converted.h5mu", "converted")]},
                {
                    "status": "succeeded",
                    "outputs": [
                        _output("exported.h5ad", "export"),
                        _output("exported.h5ad.apb.json", "representation"),
                    ],
                },
                {
                    "status": "succeeded",
                    "outputs": [
                        _output("result_performance.csv", "proteobench_scores"),
                        _output("report.html", "pmultiqc_report"),
                        _output("timings.json", "tool_timings"),
                    ],
                },
            ]
        })
    )
    _report(directory / "second.json", [_output("converted.h5mu")])
    outputs = catalog.build_catalog(tmp_path)["output_extensions"]
    assert outputs == {"mixed/workflow/hdf5/run.json": [".h5ad", ".h5mu"]}


def test_catalog_output_cache_tracks_changed_and_deleted_reports(tmp_path: Path) -> None:
    directory = _run(tmp_path, "live", [{"path": "final.json", "progress": "live.json"}])
    _report(directory / "live.json", [_output("partial.duckdb")])
    key = "live/workflow/hdf5/run.json"
    assert catalog.build_catalog(tmp_path)["output_extensions"][key] == [".duckdb"]
    _report(directory / "final.json", [_output("converted.parquet/")])
    assert catalog.build_catalog(tmp_path)["output_extensions"][key] == [".parquet"]
    _report(directory / "final.json", [_output("scored.h5ad")])
    assert catalog.build_catalog(tmp_path)["output_extensions"][key] == [".h5ad"]
    (directory / "final.json").unlink()
    (directory / "live.json").unlink()
    assert catalog.build_catalog(tmp_path)["output_extensions"][key] == []


def test_catalog_never_guesses_hdf5_extension_for_unobserved_outputs(tmp_path: Path) -> None:
    directory = _run(tmp_path, "empty", [{"path": "failed.json"}, {"path": "missing-size.json"}])
    _report(directory / "failed.json", [_output("failed.h5mu")], "failed")
    _report(directory / "missing-size.json", [_output("expected.h5ad", size=None)])
    assert catalog.build_catalog(tmp_path)["output_extensions"] == {
        "empty/workflow/hdf5/run.json": []
    }


def test_catalog_report_links_cannot_leave_the_run_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    _report(outside, [_output("secret.h5ad")])
    directory = _run(tmp_path, "unsafe", [{"path": str(outside)}, {"path": "linked.json"}])
    (directory / "linked.json").symlink_to(outside)
    assert catalog.build_catalog(tmp_path)["output_extensions"] == {
        "unsafe/workflow/hdf5/run.json": []
    }


def test_ordinary_corpus_runs_delete_previous_results_by_default() -> None:
    assert cli.RunOptions().force
    assert cli.DEFAULT_IMMEDIATE_OPTIONS.force
    assert cli._immediate_run_options(cli.DEFAULT_IMMEDIATE_OPTIONS).force
