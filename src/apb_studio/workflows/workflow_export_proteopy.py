"""ProteoPy's AnnData: APB2's protein level; ion-only vendors have none.

apb-export converts and exports in one call, from its own environment.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.export import TOOL, export_step

TOOLS = (TOOL,)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """One export of the dataset for proteopy."""
    return [export_step(context, "proteopy")]


if __name__ == "__main__":
    main("export_proteopy", steps)
