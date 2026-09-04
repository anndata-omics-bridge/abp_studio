"""Deterministic, vendor-spread fixture sampling for headless corpus gates."""

from __future__ import annotations

from pathlib import Path

from apb_studio.pipeline import (
    Target,
    dataset_names,
    level_names,
    level_targets,
    sample_fixture_targets,
    selected_dataset_targets,
)


def _target(vendor: str, dataset: str, stage: str) -> Target:
    return Target(
        module=f"module_{vendor}",
        dataset=dataset,
        stage=stage,
        output=Path(f"/out/{dataset}/{stage}"),
        command=["apb", stage],
        vendor=vendor,
    )


def _corpus() -> list[Target]:
    return [
        _target(vendor, f"{vendor}-{index}", stage)
        for vendor in ("diann", "maxquant", "spectronaut")
        for index in range(4)
        for stage in ("convert", "annotate")
    ]


def test_sampling_keeps_every_stage_of_each_selected_fixture() -> None:
    sampled = sample_fixture_targets(_corpus(), 3)
    fixtures = {(target.module, target.dataset) for target in sampled}
    assert len(fixtures) == 3
    assert len(sampled) == 6, "both stages of all three fixtures"


def test_sampling_spreads_across_vendors_before_repeating_one() -> None:
    """A ten-fixture gate must exercise many parsers, not ten files from one tool."""
    sampled = sample_fixture_targets(_corpus(), 3)
    assert {target.vendor for target in sampled} == {"diann", "maxquant", "spectronaut"}


def test_sampling_is_deterministic() -> None:
    corpus = _corpus()
    assert sample_fixture_targets(corpus, 5) == sample_fixture_targets(list(reversed(corpus)), 5)


def test_a_non_positive_limit_runs_the_whole_corpus() -> None:
    corpus = _corpus()
    assert sample_fixture_targets(corpus, 0) == corpus
    assert sample_fixture_targets(corpus, -1) == corpus


def test_a_limit_above_the_corpus_size_returns_every_fixture() -> None:
    corpus = _corpus()
    sampled = sample_fixture_targets(corpus, 99)
    assert {(target.module, target.dataset) for target in sampled} == {
        (target.module, target.dataset) for target in corpus
    }


def test_named_datasets_are_selected_by_alias_or_module_qualified_name() -> None:
    corpus = _corpus()

    selected, unmatched = selected_dataset_targets(
        corpus,
        ["diann-1", "module_maxquant/maxquant-1", "  ", "diann-1"],
    )

    assert unmatched == []
    assert dataset_names(selected) == ["module_diann/diann-1", "module_maxquant/maxquant-1"]
    # Every stage of a named dataset comes along; naming a dataset is not naming a stage.
    assert len({target.stage for target in selected}) == len({
        target.stage for target in corpus if target.dataset == "diann-1"
    })


def test_a_name_matching_nothing_is_reported_rather_than_dropped() -> None:
    selected, unmatched = selected_dataset_targets(_corpus(), ["diann-1", "typo-9"])

    assert unmatched == ["typo-9"]
    assert dataset_names(selected) == ["module_diann/diann-1"]

    empty, all_unmatched = selected_dataset_targets(_corpus(), ["nope"])
    assert empty == []
    assert all_unmatched == ["nope"]


def test_levels_select_branches_including_the_mudata_container() -> None:
    corpus = [
        Target(
            module="m",
            dataset="d",
            stage="convert",
            output=Path(f"/out/{branch}.h5ad"),
            command=[],
            branch=branch,
            level=None if branch.startswith("mudata") else branch.removesuffix(".apb2"),
        )
        for branch in ("mudata", "mudata.apb2", "ion", "ion.apb2", "protein")
    ]

    assert level_names(corpus) == ["ion", "mudata", "protein"]
    assert [target.branch for target in level_targets(corpus, ["ion"])] == ["ion", "ion.apb2"]
    assert [target.branch for target in level_targets(corpus, ["mudata"])] == [
        "mudata",
        "mudata.apb2",
    ]
    assert [target.branch for target in level_targets(corpus, ["ion", "protein"])] == [
        "ion",
        "ion.apb2",
        "protein",
    ]
    assert level_targets(corpus, ["peptide"]) == []
