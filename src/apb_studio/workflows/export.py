"""One ``apb-export TARGET`` call: vendor output in, the target's file and its APB sidecar out.

apb-export runs from its own environment. Studio declares it in a workflow's TOOLS and finds it
on PATH or through ``--export-executable``, never through Studio's own lock.
"""

from __future__ import annotations

from pathlib import Path

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import read_rows, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.workflows.artifacts import representation
from apb_studio.workflows.software import parameter_software

TOOL = "apb-export"
EXTENSIONS = {
    "alphapepttools": ".h5mu",
    "msmu": ".h5mu",
    "prolfqua": ".h5ad",
    "proteopy": ".h5ad",
}
"""The file each target's tool opens, as apb-export's export rules declare it."""


def module_fasta(context: WorkflowContext) -> Path | None:
    """The FASTA the workflow table names for the dataset's module; none is no FASTA check."""
    if context.workflow_table is None:
        return None
    for row in read_rows(context.workflow_table):
        if row["module"] == context.dataset.module:
            return resolve_file(context.data_root, row["fasta"])
    return None


def export_step(context: WorkflowContext, target: str, fasta: Path | None = None) -> StepSpec:
    """Convert the vendor files, FASTA-check them if given one, write ``target``'s file."""
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
            *(["--fasta", str(fasta)] if fasta is not None else []),
        ],
        inputs=[
            Artifact(role="vendor_table", path=source),
            *[Artifact(role="vendor_secondary", path=secondary) for secondary in secondary_inputs],
            Artifact(role="vendor_parameter_file", path=parameters),
            *([Artifact(role="fasta", path=fasta)] if fasta is not None else []),
        ],
        outputs=[Artifact(role="export", path=output), representation(output)],
    )
