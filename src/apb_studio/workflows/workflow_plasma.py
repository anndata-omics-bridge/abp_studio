"""Plasma ProteoBench export and pMultiQC report, scoring the layer the table names per software.

Upstream's plasma module scores un-normalised DIA-NN quantities, unlike the other quant modules,
so the layer comes from ``workflow_plasma.tsv`` rather than the APB primary layer.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.tables import join_workflow
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.proteobench_export import export_and_report_steps

TOOLS = ("apb-proteobench", "multiqc")
WORKFLOW_COLUMNS = ("module", "software_name", "fasta", "level", "layer")
WORKFLOW_TABLE = "workflow_plasma.tsv"


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Export the table's layer for this module and software, then render the report."""
    if context.workflow_table is None:
        raise ValueError(f"{WORKFLOW_TABLE} is required")
    workflow = join_workflow(
        context.dataset.model_dump(), context.workflow_table, on=("module", "software_name")
    )
    if tuple(workflow) != WORKFLOW_COLUMNS or not workflow["layer"]:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    return export_and_report_steps(
        context, fasta=workflow["fasta"], level=workflow["level"], layer=workflow["layer"]
    )


if __name__ == "__main__":
    main("plasma", steps)
