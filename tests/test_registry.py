"""Guard the stage registry shared by the Snakefile and dashboard."""

from pathlib import Path

from anndata_proteomics.scripts.cli import app as apb_app

from apb_studio.pipeline import ResolvedFixture, expand_resolved_targets
from apb_studio.registry import REGISTRY_PATH, load_registry

_REQUIRED_STAGE_KEYS = {"name", "scope", "output_pattern", "command", "depends_on"}
_VALID_SCOPES = {"dataset", "module", "corpus"}


def test_registry_stages_have_required_keys():
    stages = load_registry()
    assert stages, "registry must define at least one stage"
    for stage in stages:
        missing = _REQUIRED_STAGE_KEYS - stage.keys()
        assert not missing, f"stage {stage.get('name')!r} missing keys: {missing}"
        assert stage["scope"] in _VALID_SCOPES


def test_depends_on_references_known_stages():
    names = {s["name"] for s in load_registry()}
    for stage in load_registry():
        for dep in stage["depends_on"]:
            assert dep in names, f"{stage['name']!r} depends on unknown stage {dep!r}"


def test_every_stage_declares_a_basket_label():
    # The compact dashboard column heading is derived from this label.
    for stage in load_registry():
        assert stage.get("basket"), f"stage {stage['name']!r} needs a `basket` label"


def test_non_root_stages_declare_artifact_and_resource():
    # A non-root (depends_on non-empty) stage's output basename + gating resource are data, so
    # resolved-fixture expansion stays registry-driven (no hardcoded edges/filenames).
    for stage in load_registry():
        if stage["depends_on"]:
            assert stage.get("artifact"), f"{stage['name']!r} needs an `artifact` basename"
            assert stage.get("resource"), f"{stage['name']!r} needs `resource` (module key + gate)"


def test_registry_does_not_encode_fixture_levels() -> None:
    source = REGISTRY_PATH.read_text()

    assert "level: ion" not in source
    assert "modules:" not in source


def test_every_rendered_registry_command_matches_the_apb_cyclopts_contract(
    tmp_path: Path,
) -> None:
    fixture = ResolvedFixture(
        module="dda",
        repo_name="results",
        intermediate_hash="abc123",
        dataset="dataset",
        software="DIA-NN",
        vendor="diann",
        parameter_vendor="diann",
        input_path=tmp_path / "input.tsv",
        parameter_path=tmp_path / "params.txt",
        branches=("mudata", "ion"),
        capability_status="supported",
        annotation_path=tmp_path / "annotation.toml",
        fasta_path=tmp_path / "proteome.fasta",
    )
    targets = expand_resolved_targets(load_registry(), (fixture,), tmp_path / "out")

    assert targets
    for target in targets:
        assert target.command[0] == "apb"
        command, _bound, ignored = apb_app.parse_args(
            target.command[1:],
            exit_on_error=False,
        )
        assert command.__name__ == target.stage
        assert ignored == {}
