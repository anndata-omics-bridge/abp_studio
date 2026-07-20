"""Tests for the provenance sidecar (decision 17)."""

import json
from pathlib import Path

import yaml

from apb_studio.pipeline import Target, expand_targets, load_registry
from apb_studio.provenance import (
    apb_version,
    main,
    prune_for_target,
    read_params_warning,
    record,
    write_for_target,
)


def _t(out_dir, stage="convert", name="mudata.h5mu"):
    return Target(
        "m", "d", stage, Path(out_dir) / name, ["apb", stage, "x"], [Path("/in/x")]
    )


def test_record_shape():
    rec = record(_t("/out"), timestamp="2026-06-29T00:00:00+00:00", version="0.1.0")
    assert rec == {
        "stage": "convert",
        "artifact": "mudata.h5mu",
        "command": ["apb", "convert", "x"],
        "inputs": ["/in/x"],
        "apb_version": "0.1.0",
        "timestamp": "2026-06-29T00:00:00+00:00",
    }


def test_write_for_target_creates_and_merges_by_stage(tmp_path):
    convert = _t(tmp_path, stage="convert", name="mudata.h5mu")
    annotate = _t(tmp_path, stage="annotate", name="annotated.h5mu")
    path = write_for_target(convert, timestamp="t1", version="0.1.0")
    assert path == tmp_path / "provenance.json"
    write_for_target(annotate, timestamp="t2", version="0.1.0")
    data = json.loads(path.read_text())
    assert set(data) == {"convert", "annotate"}  # both stages coexist, keyed by stage
    assert data["annotate"]["timestamp"] == "t2"


def test_prune_for_target_drops_stage_and_removes_empty_file(tmp_path):
    convert = _t(tmp_path, stage="convert", name="mudata.h5mu")
    annotate = _t(tmp_path, stage="annotate", name="annotated.h5mu")
    write_for_target(convert, timestamp="t1")
    write_for_target(annotate, timestamp="t2")
    path = tmp_path / "provenance.json"
    prune_for_target(convert)  # one stage left
    assert set(json.loads(path.read_text())) == {"annotate"}
    prune_for_target(annotate)  # now empty → file removed
    assert not path.exists()


def test_corrupt_sidecar_is_backed_up_not_lost(tmp_path):
    path = tmp_path / "provenance.json"
    path.write_text("}{ not json")
    write_for_target(_t(tmp_path, stage="convert"), timestamp="t")
    assert (tmp_path / "provenance.json.bak").exists()  # corrupt file preserved
    assert set(json.loads(path.read_text())) == {"convert"}  # fresh, valid


def test_main_writes_sidecar_for_an_output(tmp_path):
    corpus = {
        "input_root": "/in",
        "output_root": str(tmp_path / "out"),
        "modules": {
            "m": {
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
    config = tmp_path / "corpus.yaml"
    config.write_text(yaml.safe_dump(corpus))
    convert = next(
        t for t in expand_targets(load_registry(), corpus) if t.stage == "convert"
    )
    assert main(["--config", str(config), "--output", str(convert.output)]) == 0
    data = json.loads((convert.output.parent / "provenance.json").read_text())
    assert "convert" in data and data["convert"]["artifact"] == "mudata.h5mu"


def test_main_ignores_unknown_output(tmp_path):
    corpus = {"input_root": "/in", "output_root": "/out", "modules": {}}
    config = tmp_path / "corpus.yaml"
    config.write_text(yaml.safe_dump(corpus))
    assert main(["--config", str(config), "--output", "/out/nope/mudata.h5mu"]) == 0


def test_apb_version_returns_str_or_none():
    assert apb_version() is None or isinstance(apb_version(), str)


# --- warning capture: apb degraded (e.g. unparsable params) but still produced the artifact -------


def test_record_includes_warning_only_when_present():
    assert "warning" not in record(_t("/out"), timestamp="t")
    rec = record(_t("/out"), timestamp="t", warning="ParamsError: not a DIA-NN file")
    assert rec["warning"] == "ParamsError: not a DIA-NN file"


def test_read_params_warning_from_artifact(tmp_path):
    import anndata as ad
    import numpy as np

    art = tmp_path / "mudata.h5mu"  # a plain AnnData written under any name (root uns)
    adata = ad.AnnData(np.zeros((2, 2), dtype="float32"))
    adata.uns["anndata_proteomics"] = {
        "search_parameters_error": "ParamsError: not a DIA-NN file"
    }
    adata.write_h5ad(art)
    assert read_params_warning(art) == "ParamsError: not a DIA-NN file"

    clean = tmp_path / "clean.h5ad"
    ad.AnnData(np.zeros((2, 2), dtype="float32")).write_h5ad(clean)
    assert read_params_warning(clean) is None
    assert read_params_warning(tmp_path / "does-not-exist.h5ad") is None
