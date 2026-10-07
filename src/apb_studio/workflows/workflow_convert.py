"""Reference linear workflow: convert directly to the selected APB2 format."""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.parameters import optional_parameter_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.conversion import conversion_step

TOOLS = ("apb2",)
PARAMETER_INPUTS = optional_parameter_inputs


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert all compatible levels; vendor parsing and level detection stay in APB2."""
    return [conversion_step(context)]


if __name__ == "__main__":
    main("convert", steps)
