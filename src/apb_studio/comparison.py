"""Compare two stage columns of one corpus run as a scatter of runtimes or artifact sizes.

The grid answers "did this stage run"; this answers "how do two of them compare". Both read the
same rows, so the comparison never re-resolves the corpus or re-reads an artifact: every value it
plots is already in the row's stage details, put there by ``pipeline.branch_rows``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

IDENTITY_FIELDS = ("module", "dataset", "software", "level")
"""Grid columns that identify a row rather than report a stage."""


@dataclass(frozen=True, slots=True)
class Metric:
    """One comparable quantity a completed stage records.

    The difference between metrics is data — which detail key, which unit — so reading one is the
    same operation for all of them and no caller asks which metric it holds.
    """

    name: str
    label: str
    detail_key: str
    divisor: float
    unit: str

    def value(self, detail: Mapping[str, str]) -> float | None:
        """This metric's value for one stage detail, or None when the stage did not record it."""
        raw = detail.get(self.detail_key)
        if raw is None:
            return None
        return float(raw) / self.divisor


RUNTIME = Metric(
    name="runtime",
    label="Runtime",
    detail_key="duration_seconds",
    divisor=1.0,
    unit="s",
)
ARTIFACT_SIZE = Metric(
    name="size",
    label="Artifact size",
    detail_key="bytes",
    divisor=1024.0 * 1024.0,
    unit="MB",
)
METRICS: dict[str, Metric] = {metric.name: metric for metric in (RUNTIME, ARTIFACT_SIZE)}
DEFAULT_METRIC = RUNTIME.name


@dataclass(frozen=True, slots=True)
class ScatterPoint:
    """One row's pair of values for the two chosen stage columns."""

    label: str
    software: str
    x: float
    y: float


def stage_axes(column_defs: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """The plottable axes of a grid, taken from the columns the grid is actually showing.

    Reading the grid's own definitions keeps the axis choices consistent with the run on screen,
    including a pinned run whose pipeline differs from the picker's.
    """
    return [
        {"label": str(column.get("headerName", column["field"])), "value": str(column["field"])}
        for column in column_defs
        if str(column.get("field", "")) not in IDENTITY_FIELDS and column.get("field")
    ]


def scatter_points(
    rows: Iterable[Mapping[str, Any]],
    *,
    x_column: str,
    y_column: str,
    metric: Metric,
) -> list[ScatterPoint]:
    """One point per row that recorded this metric for both columns.

    A row missing either value contributes nothing: a stage that has not run, or an artifact that
    predates benchmark metadata, is absent evidence and not a zero.
    """
    points: list[ScatterPoint] = []
    for row in rows:
        details = row.get("_stage_details")
        if not isinstance(details, Mapping):
            continue
        x_detail = details.get(x_column)
        y_detail = details.get(y_column)
        if not isinstance(x_detail, Mapping) or not isinstance(y_detail, Mapping):
            continue
        x_value = metric.value(x_detail)
        y_value = metric.value(y_detail)
        if x_value is None or y_value is None:
            continue
        points.append(
            ScatterPoint(
                label=" / ".join(
                    str(row.get(field, "")) for field in ("module", "dataset", "level")
                ),
                software=str(row.get("software", "")),
                x=x_value,
                y=y_value,
            )
        )
    return points


def equality_span(points: Sequence[ScatterPoint]) -> tuple[float, float] | None:
    """The full diagonal the plotted rows cover, for a ``y = x`` reference.

    It spans both columns' values because each axis is pinned to its own data, so the part of the
    line outside an axis is clipped rather than stretching it. Drawing the line from zero to the
    larger axis's maximum was the bug this replaces: one 2280 s row pushed a 26 s axis to 2300 s.
    """
    if not points:
        return None
    values = [point.x for point in points] + [point.y for point in points]
    return min(values), max(values)


@dataclass(frozen=True, slots=True)
class LinearScale:
    """Axes in the metric's own units."""

    name: str = "linear"
    label: str = "Linear axes"
    plotly_type: str = "linear"

    def bounds(self, values: Sequence[float]) -> list[float] | None:
        """The axis range to pin, so no trace outside this axis's data can widen it."""
        if not values:
            return None
        low, high = min(values), max(values)
        pad = (high - low) * 0.05 or max(abs(high) * 0.05, 1.0)
        # Runtimes and sizes are non-negative, so the axis starts at zero rather than padding
        # into values the quantity cannot take.
        return [0.0 if low >= 0.0 else low - pad, high + pad]


@dataclass(frozen=True, slots=True)
class LogScale:
    """Decades, for when a few rows dwarf the rest."""

    name: str = "log"
    label: str = "Log axes"
    plotly_type: str = "log"

    def bounds(self, values: Sequence[float]) -> list[float] | None:
        """The axis range to pin, in log10 units — what a Plotly log axis reads."""
        positive = [value for value in values if value > 0]
        if not positive:
            return None
        return [math.log10(min(positive)) - 0.1, math.log10(max(positive)) + 0.1]


type AxisScale = LinearScale | LogScale

SCALES: dict[str, AxisScale] = {scale.name: scale for scale in (LinearScale(), LogScale())}
DEFAULT_SCALE = LinearScale().name


def scale_for(name: str) -> AxisScale:
    """The axis scaling one picker value selects."""
    return SCALES[name]


def axis_scales() -> list[dict[str, str]]:
    """The axis scalings offered, for the picker."""
    return [{"label": scale.label, "value": scale.name} for scale in SCALES.values()]
