"""Tests for comparing two stage columns of one run."""

from __future__ import annotations

from typing import Any

import pytest

from apb_studio import comparison

_COLUMN_DEFS: list[dict[str, Any]] = [
    {"field": "module", "headerName": "Module"},
    {"field": "dataset", "headerName": "Dataset"},
    {"field": "software", "headerName": "Software"},
    {"field": "level", "headerName": "Level"},
    {"field": "convert", "headerName": "Converted"},
    {"field": "convert2", "headerName": "Converted2"},
]


def _row(
    *,
    dataset: str = "diann-1",
    software: str = "DIA-NN",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "module": "Results_quant_ion_DDA",
        "dataset": dataset,
        "software": software,
        "level": "ion",
        "_stage_details": details
        if details is not None
        else {
            "convert": {"state": "completed", "duration_seconds": "2.7", "bytes": "4194304"},
            "convert2": {"state": "completed", "duration_seconds": "1.9", "bytes": "2097152"},
        },
    }


def test_axes_are_the_stage_columns_of_the_grid_on_screen() -> None:
    assert comparison.stage_axes(_COLUMN_DEFS) == [
        {"label": "Converted", "value": "convert"},
        {"label": "Converted2", "value": "convert2"},
    ]
    assert comparison.stage_axes([]) == []
    # A column without a field is not an axis.
    assert comparison.stage_axes([{"headerName": "grouped"}]) == []


@pytest.mark.parametrize(
    ("metric_name", "expected"),
    [("runtime", (2.7, 1.9)), ("size", (4.0, 2.0))],
)
def test_each_metric_reads_its_own_recorded_value(
    metric_name: str,
    expected: tuple[float, float],
) -> None:
    points = comparison.scatter_points(
        [_row()],
        x_column="convert",
        y_column="convert2",
        metric=comparison.METRICS[metric_name],
    )

    assert len(points) == 1
    assert (points[0].x, points[0].y) == expected
    assert points[0].label == "Results_quant_ion_DDA / diann-1 / ion"
    assert points[0].software == "DIA-NN"


def test_a_missing_value_is_absent_evidence_not_a_zero() -> None:
    rows = [
        _row(),
        # stage never ran
        _row(dataset="sage-2", details={"convert": {"state": "completed", "bytes": "8"}}),
        # artifact predates benchmark metadata, so it has a size but no runtime
        _row(
            dataset="peaks-3",
            details={
                "convert": {"state": "completed", "bytes": "8"},
                "convert2": {"state": "completed", "bytes": "4"},
            },
        ),
        # rows the grid produced for an unresolved fixture carry no details mapping
        {"module": "m", "dataset": "broken", "software": "X", "level": "Unresolved"},
        {"module": "m", "dataset": "odd", "_stage_details": "not a mapping"},
    ]

    timed = comparison.scatter_points(
        rows, x_column="convert", y_column="convert2", metric=comparison.RUNTIME
    )
    sized = comparison.scatter_points(
        rows, x_column="convert", y_column="convert2", metric=comparison.ARTIFACT_SIZE
    )

    assert [point.label.split(" / ")[1] for point in timed] == ["diann-1"]
    assert [point.label.split(" / ")[1] for point in sized] == ["diann-1", "peaks-3"]


def test_equality_span_covers_both_columns_so_the_axes_can_clip_it() -> None:
    def _points(pairs: list[tuple[float, float]]) -> list[comparison.ScatterPoint]:
        return [comparison.ScatterPoint(label="l", software="s", x=x, y=y) for x, y in pairs]

    assert comparison.equality_span(_points([(2.0, 3.0), (26.0, 2280.0)])) == (2.0, 2280.0)
    assert comparison.equality_span(_points([(5.0, 5.0)])) == (5.0, 5.0)
    assert comparison.equality_span([]) is None


def test_each_scale_pins_an_axis_to_its_own_data() -> None:
    linear = comparison.scale_for("linear")
    log = comparison.scale_for("log")

    # Zero-based, because a runtime or a size cannot be negative.
    assert linear.bounds([2.0, 26.0]) == [0.0, 26.0 + 24.0 * 0.05]
    # A single value still yields a usable range rather than a zero-width one.
    single = linear.bounds([4.0])
    assert single is not None and single[0] == 0.0 and single[1] > 4.0
    assert linear.bounds([]) is None

    # Log ranges are log10 units, which is what a Plotly log axis reads.
    log_bounds = log.bounds([1.0, 100.0])
    assert log_bounds == [-0.1, 2.1]
    # Non-positive values cannot be placed on a log axis, so there is no range to pin.
    assert log.bounds([0.0, -3.0]) is None
    assert [scale["value"] for scale in comparison.axis_scales()] == ["linear", "log"]
    assert comparison.DEFAULT_SCALE == "linear"
