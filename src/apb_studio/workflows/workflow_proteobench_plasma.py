"""Plasma ProteoBench export and pMultiQC report, scoring the layer the module selects.

Upstream's plasma module scores un-normalised DIA-NN quantities, unlike the other quant modules.
apb-proteobench's ``dia_plasma`` module asks apb-catalog for each software's un-normalised layer,
so ``--layer X`` scores it; the table names only the FASTA and level per software.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.tables import join_workflow
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.proteobench_export import export_and_report_steps

TOOLS = ("apb-proteobench", "multiqc")
WORKFLOW_COLUMNS = ("module", "software_name", "fasta", "level")
WORKFLOW_TABLE = "workflow_proteobench_plasma.tsv"


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Export the module's layer for this module and software, then render the report."""
    if context.workflow_table is None:
        raise ValueError(f"{WORKFLOW_TABLE} is required")
    workflow = join_workflow(
        context.dataset.model_dump(), context.workflow_table, on=("module", "software_name")
    )
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    return export_and_report_steps(
        context, fasta=workflow["fasta"], level=workflow["level"], layer="X"
    )


if __name__ == "__main__":
    main("proteobench_plasma", steps)
