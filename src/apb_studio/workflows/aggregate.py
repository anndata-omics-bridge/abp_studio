"""Shared conversion and abundance-layer aggregation steps."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.workflows.artifacts import representation, result_path
from apb_studio.workflows.conversion import conversion_step


def aggregation_steps(
    context: WorkflowContext, methods: Sequence[str], layers: Literal["primary", "all"]
) -> list[StepSpec]:
    """Convert every compatible level, then chain methods on the requested abundance layers."""
    convert = conversion_step(context, "converted")
    planned = [convert]
    source_artifact = convert.outputs[0]
    for position, method in enumerate(methods, start=1):
        last = position == len(methods)
        aggregated = result_path(
            context.output_dir, "aggregated" if last else f"aggregated_{method}", context.format
        )
        output = Artifact(
            role="result" if last else "aggregated", path=aggregated, format=context.format
        )
        planned.append(
            StepSpec(
                name=f"aggregate-{method}",
                command=[
                    str(context.tool("apb-aggregate")),
                    str(source_artifact.path),
                    str(aggregated),
                    method,
                    "--layers",
                    layers,
                ],
                inputs=[source_artifact],
                outputs=[output, representation(aggregated)],
            )
        )
        source_artifact = output
    return planned
