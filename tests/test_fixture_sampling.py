"""Deterministic, vendor-spread fixture sampling for headless corpus gates."""

from __future__ import annotations

from pathlib import Path

from apb_studio.pipeline import Target, sample_fixture_targets


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
