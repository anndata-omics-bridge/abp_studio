"""One-call ProteoBench workflow: the same scoring, in a single in-memory apb-proteobench run."""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.tables import join_workflow
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.proteobench_scoring import run_quant_step

WORKFLOW_COLUMNS = ("module", "fasta", "level")
WORKFLOW_TABLE = "workflow_proteobench.csv"
TOOLS = ("apb-proteobench",)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Score one module in memory and persist the selected APB2 format and its scores JSON."""
    if context.workflow_table is None:
        raise ValueError("workflow_proteobench.csv is required")
    workflow = join_workflow(context.dataset.model_dump(), context.workflow_table, on=("module",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    return [run_quant_step(context, workflow["fasta"])]


if __name__ == "__main__":
    main("proteobench_run", steps)
