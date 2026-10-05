"""prolfquapp's AnnData: APB2's ion level with its analysis configuration.

apb-export converts and exports in one call, from its own environment.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.export import TOOL, export_step

TOOLS = (TOOL,)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """One export of the dataset for prolfqua."""
    return [export_step(context, "prolfqua")]


if __name__ == "__main__":
    main("export_prolfqua", steps)
