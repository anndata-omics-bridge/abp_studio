"""Three-call ProteoBench workflow: convert, verify peptides, then annotate and score."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("module", "module_toml", "fasta")
TOOLS = ("apb2", "apb-fasta", "apb-proteobench")


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Score one module through three separately measured tool calls over shared H5MU files."""
    if context.workflow_table is None:
        raise ValueError("workflow_proteobench.csv is required")
    if context.format != "hdf5":
        raise ValueError("ProteoBench scoring reads and writes H5MU; pass --format hdf5")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("module",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")

    source = resolve_file(context.data_root, dataset.input_file)
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    module = resolve_file(context.data_root, workflow["module_toml"])
    fasta = resolve_file(context.data_root, workflow["fasta"])
    basename = context.output_dir / "converted"
    converted = basename.with_suffix(".h5mu")
    verified = context.output_dir / "fasta-checked.h5mu"
    scored = context.output_dir / "scored.h5mu"

    return [
        StepSpec(
            name="convert",
            command=[
                str(context.tool("apb2")),
                "convert",
                str(source),
                "--params",
                str(parameters),
                "--params-software",
                parameter_software(dataset.software_name),
                "--output",
                str(basename),
            ],
            inputs=[
                Artifact(role="vendor_table", path=source),
                Artifact(role="vendor_parameter_file", path=parameters),
            ],
            outputs=[
                Artifact(role="converted", path=converted, format="hdf5"),
                representation(converted),
            ],
        ),
        StepSpec(
            name="verify-peptides",
            command=[
                str(context.tool("apb-fasta")),
                "verify-peptides",
                str(converted),
                str(fasta),
                "--output",
                str(verified),
            ],
            inputs=[
                Artifact(role="converted", path=converted, format="hdf5"),
                Artifact(role="fasta", path=fasta),
            ],
            outputs=[
                Artifact(role="fasta_verified", path=verified, format="hdf5"),
                representation(verified),
            ],
        ),
        StepSpec(
            name="benchmark",
            command=[
                str(context.tool("apb-proteobench")),
                "benchmark",
                str(verified),
                str(module),
                str(scored),
            ],
            inputs=[
                Artifact(role="fasta_verified", path=verified, format="hdf5"),
                Artifact(role="module_settings", path=module),
            ],
            outputs=[
                Artifact(role="result", path=scored, format="hdf5"),
                representation(scored),
            ],
        ),
    ]


if __name__ == "__main__":
    main("proteobench", steps)
