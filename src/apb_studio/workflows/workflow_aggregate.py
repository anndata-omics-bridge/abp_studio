"""Linear aggregation workflow: convert configured source levels, then aggregate to protein.

The ``method`` cell lists one or more apb-aggregate selections separated by ``;``. Each runs as
its own step and adds its layers to the previous step's result.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.parameters import optional_parameter_inputs
from apb_studio.corpus.tables import join_workflow
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.aggregate import aggregation_steps

WORKFLOW_COLUMNS = ("software_name", "method")
TOOLS = ("apb2", "apb-aggregate")
PARAMETER_INPUTS = optional_parameter_inputs


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert configured source levels, then run each listed aggregate on the previous result."""
    if context.workflow_table is None:
        raise ValueError("workflow_aggregate.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("software_name",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    methods = [selection.strip() for selection in workflow["method"].split(";")]
    if not all(methods):
        raise ValueError("workflow_aggregate.csv requires nonempty method values")
    if len(set(methods)) != len(methods):
        raise ValueError(f"workflow_aggregate.csv repeats a method in {workflow['method']!r}")

    return aggregation_steps(context, methods, "all")


if __name__ == "__main__":
    main("aggregate", steps)
