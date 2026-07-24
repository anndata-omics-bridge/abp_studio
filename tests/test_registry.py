"""Guard the stage registry shared by the Snakefile and dashboard."""

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
    # baskets()/basket_names() render one basket per stage from this label (decision 10 / §13).
    for stage in load_registry():
        assert stage.get("basket"), f"stage {stage['name']!r} needs a `basket` label"


def test_non_root_stages_declare_artifact_and_resource():
    # A non-root (depends_on non-empty) stage's output basename + gating resource are data, so
    # expand_targets stays registry-driven (no hardcoded edges/filenames).
    for stage in load_registry():
        if stage["depends_on"]:
            assert stage.get("artifact"), f"{stage['name']!r} needs an `artifact` basename"
            assert stage.get("resource") or stage.get("resources"), (
                f"{stage['name']!r} needs `resource`/`resources` (module key + gate)"
            )


def test_registry_does_not_encode_fixture_levels() -> None:
    source = REGISTRY_PATH.read_text()

    assert "level: ion" not in source
    assert "modules:" not in source
