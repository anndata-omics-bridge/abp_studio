"""Convert all compatible levels, then median-polish only the source's primary X layer."""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.parameters import optional_parameter_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.aggregate import aggregation_steps

TOOLS = ("apb2", "apb-aggregate")
PARAMETER_INPUTS = optional_parameter_inputs


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Run one median-polish rollup to the coarsest reachable identity, without a table."""
    return aggregation_steps(context, ("medpolish",), "primary")


if __name__ == "__main__":
    main("aggregate_medpolish", steps)
