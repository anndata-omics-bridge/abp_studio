"""msmu's MuData: APB2's ion level as its psm modality.

apb-export converts and exports in one call, from its own environment.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.export import TOOL, export_step

TOOLS = (TOOL,)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """One export of the dataset for msmu."""
    return [export_step(context, "msmu")]


if __name__ == "__main__":
    main("export_msmu", steps)
