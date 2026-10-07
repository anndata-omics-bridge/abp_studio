"""Plasma ProteoBench scores without the pMultiQC report, for the layer the table names.

Upstream's plasma module scores un-normalised DIA-NN quantities,
as in ``workflow_proteobench_plasma``.
The layer comes from ``workflow_proteobench_plasma.tsv`` rather than the APB primary layer.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.tables import join_workflow
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.proteobench_scoring import run_quant_step

TOOLS = ("apb-proteobench",)
WORKFLOW_COLUMNS = ("module", "software_name", "fasta", "level", "layer")
WORKFLOW_TABLE = "workflow_proteobench_plasma.tsv"


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Score the table's layer for this module and software and write its scores JSON."""
    if context.workflow_table is None:
        raise ValueError(f"{WORKFLOW_TABLE} is required")
    workflow = join_workflow(
        context.dataset.model_dump(), context.workflow_table, on=("module", "software_name")
    )
    if tuple(workflow) != WORKFLOW_COLUMNS or not workflow["layer"]:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    return [run_quant_step(context, workflow["fasta"], workflow["level"], workflow["layer"])]


if __name__ == "__main__":
    main("proteobench_plasma_run", steps)
