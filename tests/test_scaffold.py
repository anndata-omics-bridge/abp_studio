"""Tests for the corpus generator (src/apb_studio/scaffold.py)."""

from apb_studio.scaffold import (
    build_corpus,
    detect_level,
    discover,
    find_input,
    read_headers,
)


def _fake_recognizer(headers):
    """Stand-in for apb.recognize_software: diann if a DIA-NN column is present, else peaks, else None."""
    if "Precursor.Id" in headers:
        return "diann"
    if "Peptide" in headers:
        return "peaks"
    return None


def _dataset(
    root,
    module,
    ds,
    header_cols,
    *,
    input_name="input_file.tsv",
    param_name="param_0..txt",
):
    d = root / module / ds
    d.mkdir(parents=True)
    (d / input_name).write_text("\t".join(header_cols) + "\nrow\n", encoding="utf-8")
    (d / param_name).write_text("version: x\n", encoding="utf-8")
    return d


def test_detect_level_from_module_name():
    assert detect_level("Results_quant_ion_DIA_AIF") == "ion"
    assert detect_level("Results_quant_peptidoform_DDA") == "peptidoform"
    assert detect_level("something_unlabelled") is None


def test_read_headers_tsv(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("Peptide\tQuality\t-10LgP\nrow\n")
    assert read_headers(p) == ["Peptide", "Quality", "-10LgP"]


def test_find_input_prefers_named_then_largest(tmp_path):
    d = tmp_path / "ds"
    d.mkdir()
    (d / "comment.txt").write_text("x")
    (d / "input_file.tsv").write_text("a\tb\n")
    assert find_input(d).name == "input_file.tsv"


def test_discover_skips_dirs_without_input_or_param(tmp_path):
    root = tmp_path / "data"
    _dataset(root, "Results_quant_ion_DIA_AIF", "h1", ["Precursor.Id"])
    empty = root / "Results_quant_ion_DIA_AIF" / "h_empty"
    empty.mkdir()
    found = list(discover(root))
    assert {(m, d) for m, d, _, _ in found} == {("Results_quant_ion_DIA_AIF", "h1")}


def test_build_corpus_clean_module_names_vendor_per_dataset(tmp_path):
    root = tmp_path / "data"
    _dataset(root, "Results_quant_ion_DIA_AIF", "h_diann", ["Precursor.Id", "Run"])
    _dataset(
        root,
        "Results_quant_ion_DIA_AIF",
        "h_peaks",
        ["Peptide", "Quality"],
        input_name="input_file.txt",
    )
    _dataset(
        root,
        "Results_quant_peptidoform_DDA",
        "h_pep",
        ["Peptide"],
        param_name="parameters.txt",
    )
    _dataset(root, "Results_quant_ion_DIA_AIF", "h_unknown", ["Mystery"])  # → skipped

    corpus, skipped = build_corpus(root, recognizer=_fake_recognizer)

    assert corpus["input_root"] == str(root)
    assert skipped == ["Results_quant_ion_DIA_AIF/h_unknown"]
    # Modules are the CLEAN ProteoBench names — vendor is a per-DATASET field, not in the name.
    assert set(corpus["modules"]) == {
        "Results_quant_ion_DIA_AIF",
        "Results_quant_peptidoform_DDA",
    }

    aif = {
        d["vendor"]: d
        for d in corpus["modules"]["Results_quant_ion_DIA_AIF"]["datasets"]
    }
    assert "level" not in aif["diann"]  # multi-level → mudata.h5mu
    assert aif["peaks"]["level"] == "ion"  # single-level → PEAKS's vendor-native level
    assert aif["diann"]["name"] == "diann-h_diann"
    assert aif["diann"]["input"] == "Results_quant_ion_DIA_AIF/h_diann/input_file.tsv"
    assert aif["diann"]["params"] == "Results_quant_ion_DIA_AIF/h_diann/param_0..txt"

    pep = corpus["modules"]["Results_quant_peptidoform_DDA"]["datasets"]
    # PEAKS is ion-level in apb regardless of the benchmark module's name (vendor-native level).
    assert pep[0]["vendor"] == "peaks" and pep[0]["level"] == "ion"


def test_build_corpus_output_is_pipeline_valid(tmp_path):
    # The generated corpus must pass expand_targets (decision-16 validation, path building, etc.).
    from apb_studio.pipeline import expand_targets, load_registry

    root = tmp_path / "data"
    _dataset(root, "Results_quant_ion_DIA_AIF", "h_diann", ["Precursor.Id"])
    _dataset(
        root,
        "Results_quant_ion_DDA",
        "h_peaks",
        ["Peptide"],
        input_name="input_file.txt",
    )
    corpus, _ = build_corpus(root, recognizer=_fake_recognizer)

    targets = expand_targets(load_registry(), corpus)
    # Convert-only (no annotation declared): one convert target per dataset, no annotate/fasta.
    assert {t.stage for t in targets} == {"convert"}
    by_artifact = {t.output.name for t in targets}
    assert "mudata.h5mu" in by_artifact  # diann → multi-level
    assert "ion.h5ad" in by_artifact  # peaks → single-level


def test_build_corpus_level_is_vendor_native_not_module_name(tmp_path):
    # A WOMBAT submission inside an "…_ion_…" module must be declared peptidoform (its apb rule
    # level), NOT the module-name "ion" — that mismatch is what made `apb convert --level ion` fail.
    root = tmp_path / "data"
    _dataset(
        root,
        "Results_quant_ion_DDA",
        "h_wombat",
        ["WombatCol"],
        input_name="input_file.csv",
    )
    _dataset(
        root, "Results_quant_ion_DDA", "h_mq", ["MqCol"], input_name="input_file.txt"
    )

    def rec(headers):
        return {"WombatCol": "wombat", "MqCol": "maxquant"}.get(headers[0])

    corpus, _ = build_corpus(root, recognizer=rec)
    by_vendor = {
        d["vendor"]: d for d in corpus["modules"]["Results_quant_ion_DDA"]["datasets"]
    }
    assert (
        by_vendor["wombat"]["level"] == "peptidoform"
    )  # vendor-native, not the module's "ion"
    assert by_vendor["maxquant"]["level"] == "ion"
