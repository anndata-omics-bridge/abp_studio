"""Complete ion-level ProteoBench export and pMultiQC report workflow."""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.tables import join_workflow
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.proteobench_export import export_and_report_steps

TOOLS = ("apb-proteobench", "multiqc")
WORKFLOW_COLUMNS = ("module", "fasta", "level")
WORKFLOW_TABLE = "workflow_proteobench.csv"


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Export the primary layer of one ion benchmark and render its pMultiQC report."""
    if context.workflow_table is None:
        raise ValueError("workflow_proteobench.csv is required")
    workflow = join_workflow(context.dataset.model_dump(), context.workflow_table, on=("module",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    return export_and_report_steps(
        context, fasta=workflow["fasta"], level=workflow["level"], layer="X"
    )


if __name__ == "__main__":
    main("proteobench_pmultiqc", steps)
