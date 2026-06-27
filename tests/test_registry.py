"""Guard the registry/corpus contract that both the Snakefile and dashboard depend on."""

from apb_studio.registry import REGISTRY_PATH, load_corpus, load_registry

_REPO_ROOT = REGISTRY_PATH.parents[1]
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


def test_example_corpus_loads():
    corpus = load_corpus(_REPO_ROOT / "config" / "corpus.example.yaml")
    assert {"input_root", "output_root", "modules"} <= corpus.keys()
    for module in corpus["modules"].values():
        assert {"vendor", "rule", "annotation_dir", "levels", "datasets"} <= module.keys()
