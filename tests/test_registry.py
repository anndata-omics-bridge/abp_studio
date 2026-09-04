"""Guard the stage registry shared by the Snakefile and dashboard."""

from pathlib import Path

import pytest
from apb2.cli import app as apb2_app
from apb_aggregate.cli import app as aggregate_app
from apb_fasta.cli import app as fasta_app
from apb_proteobench.cli import app as proteobench_app
from pydantic import ValidationError

from apb_studio.pipeline import (
    CONVERTERS,
    ResolvedFixture,
    expand_resolved_targets,
    load_pipeline,
    resolve_pipeline,
)
from apb_studio.registry import (
    REGISTRY_PATH,
    PipelineDocument,
    available_pipelines,
    load_pipeline_document,
    load_registry,
)

_REQUIRED_STAGE_KEYS = {"name", "scope", "output_pattern", "depends_on"}
_APPS = {
    "apb2": apb2_app,
    "apb-aggregate": aggregate_app,
    "apb-fasta": fasta_app,
    "apb-proteobench": proteobench_app,
}
_VALID_SCOPES = {"dataset", "module", "corpus"}


def test_registry_stages_have_required_keys():
    stages = load_registry()
    assert stages, "registry must define at least one stage"
    for stage in stages:
        missing = _REQUIRED_STAGE_KEYS - stage.keys()
        assert not missing, f"stage {stage.get('name')!r} missing keys: {missing}"
        assert stage["scope"] in _VALID_SCOPES
        # A stage declares one command, or — the DAG root, which is the stage that *is* a
        # converter — one per converter, covering every converter a branch may name.
        if "commands" in stage:
            assert set(stage["commands"]) == set(CONVERTERS), (
                f"stage {stage['name']!r} must declare a command for every converter"
            )
        else:
            assert stage.get("command"), f"stage {stage['name']!r} needs `command`"


def test_depends_on_references_known_stages():
    names = {s["name"] for s in load_registry()}
    for stage in load_registry():
        for dep in stage["depends_on"]:
            assert dep in names, f"{stage['name']!r} depends on unknown stage {dep!r}"


def test_every_stage_declares_a_basket_label():
    # The compact dashboard column heading is derived from this label.
    for stage in load_registry():
        assert stage.get("basket"), f"stage {stage['name']!r} needs a `basket` label"


def test_non_root_stages_declare_artifact():
    # A non-root stage's output basename is data, so resolved-fixture expansion stays
    # registry-driven. Only stages that consume an external module resource declare one.
    for stage in load_registry():
        if stage["depends_on"]:
            assert stage.get("artifact"), f"{stage['name']!r} needs an `artifact` basename"


def test_registry_does_not_encode_module_specific_fixture_levels() -> None:
    source = REGISTRY_PATH.read_text()

    assert "modules:" not in source


def test_every_rendered_registry_command_matches_its_cli_cyclopts_contract(
    tmp_path: Path,
) -> None:
    """Every rendered command must parse against the APB CLI it names."""
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
        branches=("mudata", "ion", "fragment"),
        capability_status="supported",
        annotation_path=tmp_path / "annotation.toml",
        fasta_path=tmp_path / "proteome.fasta",
    )
    targets = expand_resolved_targets(load_pipeline(), (fixture,), tmp_path / "out")

    assert targets
    assert {target.command[0] for target in targets} == {
        "apb2",
        "apb-aggregate",
        "apb-fasta",
        "apb-proteobench",
    }
    function_names = {
        "convert": "convert",
        "aggregate-ion": "aggregate",
        "aggregate-fragment": "aggregate",
        "fasta": "verify_peptides",
        "proteobench": "benchmark",
    }
    for target in targets:
        app = _APPS[target.command[0]]
        command, _bound, ignored = app.parse_args(
            target.command[1:],
            exit_on_error=False,
        )
        assert command.__name__ == function_names[target.stage]
        assert ignored == {}


def test_every_packaged_pipeline_resolves_against_the_catalogue() -> None:
    assert available_pipelines() == (
        "apb2-convert",
        "apb2-full",
        "convert",
        "direct",
        "full",
    )
    assert load_pipeline("convert").columns == ("convert",)
    assert load_pipeline("direct").columns == ("raw-proteobench",)
    for name in available_pipelines():
        selection = load_pipeline(name)
        assert selection.name == name
        assert selection.converters
        assert selection.stages
        # A selection never restates a stage: every entry is the catalogue's own object.
        assert all(stage in load_registry() for stage in selection.stages)


def test_pipeline_document_is_a_selection_not_a_definition() -> None:
    with pytest.raises(ValueError, match="Unknown pipeline"):
        load_pipeline_document("no-such-pipeline")
    with pytest.raises(ValidationError):
        PipelineDocument.model_validate({
            "name": "x",
            "description": "d",
            "converters": ["apb2"],
            "stages": ["convert"],
            "command": "apb2 convert",
        })


def test_pipeline_selection_is_rejected_when_it_cannot_run(tmp_path: Path) -> None:
    catalogue = load_registry()
    with pytest.raises(ValueError, match="unknown converter"):
        resolve_pipeline(
            PipelineDocument(name="x", description="d", converters=("apb3",), stages=("convert",)),
            catalogue,
        )
    with pytest.raises(ValueError, match="unknown stage"):
        resolve_pipeline(
            PipelineDocument(name="x", description="d", converters=("apb2",), stages=("score",)),
            catalogue,
        )
    with pytest.raises(ValueError, match="without its dependencies"):
        resolve_pipeline(
            PipelineDocument(
                name="x",
                description="d",
                converters=("apb2",),
                stages=("convert", "proteobench"),
            ),
            catalogue,
        )
    document = tmp_path / "renamed.yaml"
    document.write_text(
        "name: full\ndescription: d\nconverters: [apb2]\nstages: [convert]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="declares name"):
        load_pipeline_document("renamed", tmp_path)


def test_pipeline_stage_order_follows_depends_on_not_the_document() -> None:
    reversed_selection = resolve_pipeline(
        PipelineDocument(
            name="x",
            description="d",
            converters=("apb2",),
            stages=(
                "proteobench",
                "aggregate-fragment",
                "aggregate-ion",
                "fasta",
                "convert",
            ),
        ),
        load_registry(),
    )
    assert reversed_selection.stage_names == (
        "convert",
        "fasta",
        "aggregate-ion",
        "aggregate-fragment",
        "proteobench",
    )


def test_empty_selection_is_refused() -> None:
    catalogue = load_registry()
    with pytest.raises(ValueError, match="selects no converter"):
        resolve_pipeline(
            PipelineDocument(name="x", description="d", converters=(), stages=("convert",)),
            catalogue,
        )
    with pytest.raises(ValueError, match="selects no stage"):
        resolve_pipeline(
            PipelineDocument(name="x", description="d", converters=("apb2",), stages=()),
            catalogue,
        )
