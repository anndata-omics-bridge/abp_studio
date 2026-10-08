"""msmu's MuData: APB2's ion level as its psm modality.

apb-export converts and exports in one call, from its own environment. A dataset whose module
has a FASTA in the ProteoBench workflow table is FASTA-checked first, so msmu's contaminant
flags include the FASTA's; any other dataset exports with the vendor's own flags only.
"""

from __future__ import annotations

from apb_studio.corpus.models import StepSpec
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.export import TOOL, export_step, module_fasta

TOOLS = (TOOL,)
WORKFLOW_TABLE = "workflow_proteobench.csv"


def steps(context: WorkflowContext) -> list[StepSpec]:
    """One export of the dataset for msmu, FASTA-checked when its module has a FASTA."""
    return [export_step(context, "msmu", module_fasta(context))]


if __name__ == "__main__":
    main("export_msmu", steps)
