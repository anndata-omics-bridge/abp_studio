"""Tests for the registry-driven core (src/apb_studio/pipeline.py) — the single source of truth."""

import subprocess
import sys
from pathlib import Path

import pytest

from apb_studio.pipeline import (
    CleanGuardError,
    Target,
    basket_names,
    baskets,
    clean_paths,
    convert_artifact,
    coverage,
    descendants,
    expand_targets,
    problems,
    render_command,
    stage_by_basket,
    stage_order,
    targets_for,
    validate_dataset,
)
from apb_studio.registry import REGISTRY_PATH, load_corpus, load_registry

_REPO_ROOT = REGISTRY_PATH.parents[1]
_REGISTRY = load_registry()
_EXAMPLE = load_corpus(_REPO_ROOT / "config" / "corpus.example.yaml")


# --- convert_artifact + decision-16 validation (vendor/level are PER DATASET) -----------------


def test_convert_artifact_multilevel_is_mudata():
    assert convert_artifact({"vendor": "diann"}) == "mudata.h5mu"


def test_convert_artifact_single_level_is_h5ad():
    assert convert_artifact({"vendor": "maxquant", "level": "ion"}) == "ion.h5ad"


def test_single_level_vendor_without_level_raises():
    with pytest.raises(ValueError, match="single-level"):
        validate_dataset("m", {"name": "d", "vendor": "maxquant"})


def test_multi_level_vendor_without_level_ok():
    validate_dataset("m", {"name": "d", "vendor": "diann"})  # no raise


def test_missing_vendor_raises():
    with pytest.raises(ValueError, match="vendor"):
        validate_dataset("m", {"name": "d"})


def test_unknown_level_raises():
    # A typo'd / non-canonical level would yield an artifact name no Snakemake rule can build.
    with pytest.raises(ValueError, match="known quantification level"):
        validate_dataset("m", {"name": "d", "vendor": "diann", "level": "protien"})


def test_annotation_is_optional_convert_only_module():
    # A module with no annotation is valid → it yields only convert targets (no annotate/fasta).
    corpus = {
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
                ],
            }
        },
    }
    assert {t.stage for t in expand_targets(_REGISTRY, corpus)} == {"convert"}


def test_one_module_can_hold_multiple_vendors():
    # The whole point: a module is the benchmark; its datasets are different tools, each with its
    # own vendor/level → different convert artifacts under one (clean) module name.
    corpus = {
        "input_root": "/in",
        "output_root": "/out",
        "modules": {
            "quant_lfq_ion_DDA": {
                "datasets": [
                    {
                        "name": "diann-a",
                        "vendor": "diann",
                        "input": "a.tsv",
                        "params": "a.log",
                    },
                    {
                        "name": "peaks-b",
                        "vendor": "peaks",
                        "level": "ion",
                        "input": "b.txt",
                        "params": "b.txt",
                    },
                ]
            }
        },
    }
    convert = {
        t.dataset: t.output.name
        for t in expand_targets(_REGISTRY, corpus)
        if t.stage == "convert"
    }
    assert convert == {"diann-a": "mudata.h5mu", "peaks-b": "ion.h5ad"}


def test_default_goals_derive_from_optional_flag():
    # The Snakefile's `rule all` builds every non-optional stage (convert + annotate), not a
    # hardcoded stage name; fasta is the only optional stage.
    stages = load_registry()
    optional = {s["name"] for s in stages if s.get("optional")}
    names = {s["name"] for s in stages}
    assert optional == {"fasta"}
    assert names - optional == {"convert", "annotate"}


# --- render_command ---------------------------------------------------------------------------


def test_render_command_substitutes_and_tokenizes():
    cmd = render_command(
        "apb convert {input} --software {vendor} --output {output}",
        {"input": Path("/in/r.tsv"), "vendor": "diann", "output": Path("/out/m.h5mu")},
    )
    assert cmd == [
        "apb",
        "convert",
        "/in/r.tsv",
        "--software",
        "diann",
        "--output",
        "/out/m.h5mu",
    ]


def test_render_command_value_with_space_stays_one_token():
    cmd = render_command("apb convert {input}", {"input": Path("/in/my data.tsv")})
    assert cmd == ["apb", "convert", "/in/my data.tsv"]


def test_render_command_raises_on_unfilled_placeholder():
    with pytest.raises(KeyError, match="params"):
        render_command("apb convert {input} --params {params}", {"input": "x"})


# --- expand_targets on the example corpus -----------------------------------------------------


def _targets():
    return expand_targets(_REGISTRY, _EXAMPLE, output_root="/out", input_root="/in")


def test_expand_targets_diann_dataset_is_mudata():
    t = next(
        x
        for x in _targets()
        if x.module == "quant_lfq_ion_DIA_AIF" and x.stage == "convert"
    )
    assert t.output == Path("/out/quant_lfq_ion_DIA_AIF/diann-run1/mudata.h5mu")
    assert "--level" not in t.command
    assert t.command[:3] == [
        "apb",
        "convert",
        "/in/quant_lfq_ion_DIA_AIF/run1/report.tsv",
    ]
    assert t.command[-2:] == [
        "--output",
        "/out/quant_lfq_ion_DIA_AIF/diann-run1/mudata",
    ]


def test_expand_targets_maxquant_dataset_is_level_h5ad_with_level_flag():
    t = next(
        x
        for x in _targets()
        if x.module == "quant_lfq_ion_DDA_QExactive" and x.stage == "convert"
    )
    assert t.output == Path("/out/quant_lfq_ion_DDA_QExactive/maxquant-runA/ion.h5ad")
    assert t.command[-2:] == ["--level", "ion"]
    out_idx = t.command.index("--output")
    assert t.command[out_idx + 1].endswith("ion")


def test_annotate_input_tracks_convert_artifact_suffix():
    ann = next(
        x
        for x in _targets()
        if x.module == "quant_lfq_ion_DDA_QExactive" and x.stage == "annotate"
    )
    # single-level dataset → annotate consumes ion.h5ad and writes annotated.h5ad (suffix tracks).
    assert ann.inputs[0] == Path(
        "/out/quant_lfq_ion_DDA_QExactive/maxquant-runA/ion.h5ad"
    )
    assert ann.inputs[1].name == "annotation.json"  # source JSON also tracked
    assert ann.output == Path(
        "/out/quant_lfq_ion_DDA_QExactive/maxquant-runA/annotated.h5ad"
    )


def test_annotate_input_tracks_mudata_for_multilevel():
    ann = next(
        x
        for x in _targets()
        if x.module == "quant_lfq_ion_DIA_AIF" and x.stage == "annotate"
    )
    assert ann.inputs[0] == Path("/out/quant_lfq_ion_DIA_AIF/diann-run1/mudata.h5mu")
    assert ann.output == Path("/out/quant_lfq_ion_DIA_AIF/diann-run1/annotated.h5mu")


def test_fasta_target_only_when_module_declares_fasta():
    # The example declares no `fasta:`, so no fasta targets exist.
    assert not [t for t in _targets() if t.stage == "fasta"]


def test_fasta_target_appears_when_declared():
    corpus = {
        "input_root": "/in",
        "output_root": "/out",
        "modules": {
            "m": {
                "annotation": "/a.json",
                "fasta": "/proteome.fasta",
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
    targets = expand_targets(_REGISTRY, corpus)
    fasta = next(t for t in targets if t.stage == "fasta")
    assert fasta.output == Path("/out/m/diann-d/annotated_fasta.h5mu")
    assert fasta.inputs[0] == Path("/out/m/diann-d/annotated.h5mu")
    assert fasta.inputs[1] == Path("/proteome.fasta")
    assert "/proteome.fasta" in fasta.command


def test_fasta_extension_surfaces_with_zero_gui_code():
    """Phase-7 proof: `fasta` is in the registry (→ dashboard stage picker + coverage column appear)
    and a fasta-enabled module gets a fasta coverage row — from registry + config, no GUI edits."""
    assert "fasta" in {s["name"] for s in _REGISTRY}
    corpus = {
        "input_root": "/in",
        "output_root": "/out",
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
    stages_in_coverage = {
        row["stage"] for row in coverage(expand_targets(_REGISTRY, corpus))
    }
    assert "fasta" in stages_in_coverage


# --- coverage + clean_paths -------------------------------------------------------------------


def test_coverage_flips_done_on_touch(tmp_path):
    corpus = {
        "input_root": str(tmp_path / "in"),
        "output_root": str(tmp_path / "out"),
        "modules": {
            "m": {
                "annotation": "/a.json",
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
    targets = expand_targets(_REGISTRY, corpus)
    convert = next(t for t in targets if t.stage == "convert")
    assert {r["done"] for r in coverage(targets)} == {False}
    convert.output.parent.mkdir(parents=True)
    convert.output.touch()
    done = {(r["stage"], r["done"]) for r in coverage(targets)}
    assert ("convert", True) in done and ("annotate", False) in done


def test_clean_paths_scoping_and_input_root_guard():
    targets = _targets()
    convert_only = clean_paths(targets, stage="convert", input_root="/in")
    assert all(p.name in {"mudata.h5mu", "ion.h5ad"} for p in convert_only)
    one = clean_paths(
        targets,
        scope="dataset",
        module="quant_lfq_ion_DIA_AIF",
        dataset="diann-run1",
        input_root="/in",
    )
    assert all(str(p).startswith("/out/quant_lfq_ion_DIA_AIF/diann-run1/") for p in one)


def test_clean_paths_refuses_input_root():
    # A malicious/buggy Target whose output is under input_root must trip the guard.
    bad = [Target("m", "d", "convert", Path("/in/r.tsv"), [], [])]
    with pytest.raises(CleanGuardError, match="input_root"):
        clean_paths(bad, input_root="/in")


def test_clean_guard_survives_python_dash_O():
    # The guard protects a DESTRUCTIVE action, so it must be a real exception — `assert` is stripped
    # by `python -O`. Run the guard in an optimized subprocess and confirm it still raises.
    code = (
        "from pathlib import Path\n"
        "from apb_studio.pipeline import reject_input_paths, CleanGuardError\n"
        "try:\n"
        "    reject_input_paths([Path('/in/raw.tsv')], '/in'); print('NO_RAISE')\n"
        "except CleanGuardError:\n"
        "    print('RAISED')\n"
    )
    out = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True
    )
    assert out.stdout.strip() == "RAISED", out.stdout + out.stderr


def test_descendants_are_transitive_downstream_stages():
    assert descendants(_REGISTRY, "convert") == {"annotate", "fasta"}
    assert descendants(_REGISTRY, "annotate") == {"fasta"}
    assert descendants(_REGISTRY, "fasta") == set()


# --- Target carries vendor/level; the stage graph is topology-as-data (§13) -------------------


def test_target_carries_vendor_and_level():
    ts = _targets()
    diann = next(t for t in ts if t.dataset == "diann-run1" and t.stage == "convert")
    assert diann.vendor == "diann" and diann.level is None
    mq = next(t for t in ts if t.dataset == "maxquant-runA" and t.stage == "convert")
    assert mq.vendor == "maxquant" and mq.level == "ion"


def test_stage_order_is_topological():
    order = stage_order(_REGISTRY)
    assert order.index("convert") < order.index("annotate") < order.index("fasta")


def test_basket_names_and_stage_by_basket_derive_from_registry():
    assert basket_names(_REGISTRY) == [
        "inputs",
        "converted",
        "sample annotated",
        "fasta annotated",
    ]
    assert stage_by_basket(_REGISTRY) == {
        "converted": "convert",
        "sample annotated": "annotate",
        "fasta annotated": "fasta",
    }


def test_expand_targets_derives_edges_and_reconnects_over_skipped_optional_stage():
    # A synthetic registry with an OPTIONAL INTERMEDIATE stage `mid`. The module supplies `tail`'s
    # resource but NOT `mid`'s → `mid` is skipped and `tail` reconnects to the nearest emitted
    # upstream (convert), proving edges come from depends_on, not a hardcoded chain (§13.1/§13.3).
    reg = [
        {
            "name": "convert",
            "scope": "dataset",
            "basket": "converted",
            "output_pattern": "x",
            "command": "apb convert {input} --software {vendor} --params {params} --output {output}",
            "depends_on": [],
        },
        {
            "name": "mid",
            "scope": "dataset",
            "basket": "midb",
            "output_pattern": "x",
            "artifact": "mid",
            "command": "tool {input} {midres} --output {output}",
            "depends_on": ["convert"],
            "resource": "midres",
        },
        {
            "name": "tail",
            "scope": "dataset",
            "basket": "tailb",
            "output_pattern": "x",
            "artifact": "tail",
            "command": "tool {input} {tailres} --output {output}",
            "depends_on": ["mid"],
            "resource": "tailres",
        },
    ]
    corpus = {
        "input_root": "/in",
        "output_root": "/out",
        "modules": {
            "m": {
                "tailres": "/t.txt",
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
    assert {t.stage for t in targets} == {"convert", "tail"}  # mid skipped (no midres)
    tail = next(t for t in targets if t.stage == "tail")
    assert tail.inputs[0] == Path(
        "/out/m/diann-d/mudata.h5mu"
    )  # reconnected past `mid`


# --- baskets (decision 10, §8): one basket per dataset = furthest CONTIGUOUS stage -------------


def _basket_corpus(tmp_path, *, annotation=True, fasta=False):
    module = {
        "datasets": [
            {"name": "diann-d", "vendor": "diann", "input": "r.tsv", "params": "r.log"}
        ]
    }
    if annotation:
        module["annotation"] = "/a.json"
    if fasta:
        module["fasta"] = "/p.fasta"
    return {
        "input_root": str(tmp_path / "in"),
        "output_root": str(tmp_path / "out"),
        "modules": {"m": module},
    }


def _touch(target):
    target.output.parent.mkdir(parents=True, exist_ok=True)
    target.output.touch()


def _in_basket(bk):
    return {b: [r["dataset"] for r in rows] for b, rows in bk.items() if rows}


def test_baskets_dataset_moves_downstream_as_artifacts_appear(tmp_path):
    targets = expand_targets(_REGISTRY, _basket_corpus(tmp_path))
    assert _in_basket(baskets(targets, _REGISTRY)) == {"inputs": ["diann-d"]}

    _touch(next(t for t in targets if t.stage == "convert"))
    bk = baskets(targets, _REGISTRY)
    assert _in_basket(bk) == {"converted": ["diann-d"]}
    row = bk["converted"][0]
    assert (
        row["next_stage"] == "annotate"
        and row["runnable"]
        and row["software"] == "diann"
    )

    _touch(next(t for t in targets if t.stage == "annotate"))
    assert _in_basket(baskets(targets, _REGISTRY)) == {"sample annotated": ["diann-d"]}


def test_baskets_dataset_is_in_exactly_one_basket(tmp_path):
    targets = expand_targets(_REGISTRY, _basket_corpus(tmp_path))
    _touch(next(t for t in targets if t.stage == "convert"))
    bk = baskets(targets, _REGISTRY)
    assert sum(len(rows) for rows in bk.values()) == 1


def test_baskets_non_contiguous_reports_lower_basket(tmp_path):
    # annotate present but convert MISSING (partial run / manual delete) → the dataset reports the
    # lower basket (inputs), never a basket whose defining artifact is absent.
    targets = expand_targets(_REGISTRY, _basket_corpus(tmp_path))
    _touch(next(t for t in targets if t.stage == "annotate"))
    bk = baskets(targets, _REGISTRY)
    assert _in_basket(bk) == {"inputs": ["diann-d"]}
    assert bk["inputs"][0]["next_stage"] == "convert"


def test_baskets_convert_only_module_is_terminal_in_converted(tmp_path):
    targets = expand_targets(_REGISTRY, _basket_corpus(tmp_path, annotation=False))
    _touch(next(t for t in targets if t.stage == "convert"))
    row = baskets(targets, _REGISTRY)["converted"][0]
    assert row["runnable"] is False and row["next_stage"] is None


def test_baskets_annotation_without_fasta_is_terminal_in_sample_annotated(tmp_path):
    targets = expand_targets(
        _REGISTRY, _basket_corpus(tmp_path, annotation=True, fasta=False)
    )
    for stage in ("convert", "annotate"):
        _touch(next(t for t in targets if t.stage == stage))
    row = baskets(targets, _REGISTRY)["sample annotated"][0]
    assert row["runnable"] is False and row["next_stage"] is None


def test_targets_for_selects_the_rows_at_a_stage():
    targets = _targets()
    keys = {("quant_lfq_ion_DIA_AIF", "diann-run1")}
    sel = targets_for(targets, keys, stage="convert")
    assert len(sel) == 1 and sel[0].output.name == "mudata.h5mu"
    assert targets_for(targets, keys, stage="fasta") == []  # example declares no fasta


# --- problems: per-dataset issues surfaced in the baskets (§8, review round 2) ----------------


def test_problems_flags_missing_declared_files(tmp_path):
    # Nothing on disk → input + params both missing; module annotation JSON missing too.
    corpus = {
        "input_root": str(tmp_path / "in"),
        "output_root": str(tmp_path / "out"),
        "modules": {
            "m": {
                "annotation": "ann.json",
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
    targets = expand_targets(_REGISTRY, corpus)
    probs = problems(corpus, targets)[("m", "diann-d")]
    assert any("input file missing" in p for p in probs)
    assert any("params file missing" in p for p in probs)
    assert any("annotation JSON missing" in p for p in probs)


def test_problems_clean_when_files_exist_and_no_warning(tmp_path):
    in_root = tmp_path / "in"
    (in_root / "m").mkdir(parents=True)
    (in_root / "m" / "r.tsv").touch()
    (in_root / "m" / "r.log").touch()
    corpus = {
        "input_root": str(in_root),
        "output_root": str(tmp_path / "out"),
        "modules": {
            "m": {
                "datasets": [
                    {
                        "name": "diann-d",
                        "vendor": "diann",
                        "input": "m/r.tsv",
                        "params": "m/r.log",
                    }
                ]
            }
        },
    }
    targets = expand_targets(_REGISTRY, corpus)
    assert problems(corpus, targets) == {}


def test_problems_reads_runtime_warning_from_provenance_and_baskets_surface_it(
    tmp_path,
):
    import json as _json

    out = tmp_path / "out"
    corpus = {
        "input_root": str(tmp_path / "in"),
        "output_root": str(out),
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
    }
    targets = expand_targets(_REGISTRY, corpus)
    conv = next(t for t in targets if t.stage == "convert")
    conv.output.parent.mkdir(parents=True)
    conv.output.touch()  # converted
    (conv.output.parent / "provenance.json").write_text(
        _json.dumps(
            {
                "convert": {
                    "stage": "convert",
                    "warning": "ParamsError: not a DIA-NN file",
                }
            }
        )
    )
    probs = problems(corpus, targets)
    assert any("not a DIA-NN file" in p for p in probs[("m", "diann-d")])
    # …and it rides the basket row so the table shows it
    row = baskets(targets, _REGISTRY, problems=probs)["converted"][0]
    assert "not a DIA-NN file" in row["problem"]


def test_problems_flags_convert_failure_from_its_log(tmp_path):
    # A convert that FAILED (no artifact) but wrote a per-rule log → surface the apb error line.
    corpus = _basket_corpus(tmp_path)
    targets = expand_targets(_REGISTRY, corpus)
    conv = next(t for t in targets if t.stage == "convert")
    conv.output.parent.mkdir(parents=True)
    Path(f"{conv.output}.log").write_text(
        "INFO | vendor=peaks\nTraceback (most recent call last):\n"
        "ValueError: peaks ion: no rule covers software version '13 20250520'\n"
    )
    probs = problems(corpus, targets)[("m", "diann-d")]
    assert any(p.startswith("convert failed:") and "no rule covers" in p for p in probs)


def test_problems_missing_artifact_without_log_is_pending_not_failed(tmp_path):
    # Not-yet-run dataset: no artifact and no log → pending (never flagged as "failed").
    corpus = _basket_corpus(tmp_path)
    targets = expand_targets(_REGISTRY, corpus)
    assert not any(
        "failed" in p for p in problems(corpus, targets).get(("m", "diann-d"), [])
    )


# --- decision-5 enforcement: the Snakefile really imports the core ----------------------------


def test_snakefile_imports_pipeline_not_hardcoded():
    snakefile = (_REPO_ROOT / "workflow" / "Snakefile").read_text()
    assert "from apb_studio.pipeline import" in snakefile, (
        "Snakefile must derive work from the core"
    )
    assert "expand_targets" in snakefile
