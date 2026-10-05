"""One ``apb-export TARGET`` call: vendor output in, the file the target's tool opens.

apb-export runs from its own environment. Studio declares it in a workflow's TOOLS and finds it
on PATH or through ``--export-executable``, never through Studio's own lock.
"""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.workflows.software import parameter_software

TOOL = "apb-export"
EXTENSIONS = {
    "alphapepttools": ".h5mu",
    "msmu": ".h5mu",
    "prolfqua": ".h5ad",
    "proteopy": ".h5ad",
}
"""The file each target's tool opens, as apb-export's export rules declare it."""


def export_step(context: WorkflowContext, target: str) -> StepSpec:
    """Convert the dataset's vendor files and write ``target``'s file in one call."""
    dataset = context.dataset
    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    output = context.output_dir / f"{target}{EXTENSIONS[target]}"
    return StepSpec(
        name=f"export-{target}",
        command=[
            str(context.tool(TOOL)),
            target,
            str(vendor_source),
            str(output),
            "--params",
            str(parameters),
            "--software",
            parameter_software(dataset.software_name),
        ],
        inputs=[
            Artifact(role="vendor_table", path=source),
            *[Artifact(role="vendor_secondary", path=secondary) for secondary in secondary_inputs],
            Artifact(role="vendor_parameter_file", path=parameters),
        ],
        outputs=[Artifact(role="export", path=output)],
    )
