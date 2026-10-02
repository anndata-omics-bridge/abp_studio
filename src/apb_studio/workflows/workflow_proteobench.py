"""Three-call ProteoBench workflow: convert, verify peptides, then annotate and score."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation, result_path
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("module", "fasta", "level")
TOOLS = ("apb2", "apb-fasta", "apb-proteobench")


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Score one module through three separately measured storage-neutral tool calls."""
    if context.workflow_table is None:
        raise ValueError("workflow_proteobench.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("module",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")

    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    module = dataset.module
    fasta = resolve_file(context.data_root, workflow["fasta"])
    basename = context.output_dir / "converted"
    converted = result_path(context.output_dir, "converted", context.format)
    verified = result_path(context.output_dir, "fasta-checked", context.format)
    scored = result_path(context.output_dir, "scored", context.format)
    convert_timings = context.output_dir / "converted.timings.json"

    return [
        StepSpec(
            name="convert",
            command=[
                str(context.tool("apb2")),
                "convert",
                str(vendor_source),
                "--params",
                str(parameters),
                "--software",
                parameter_software(dataset.software_name),
                "--output",
                str(basename),
                "--format",
                context.format,
                "--timings-output",
                str(convert_timings),
            ],
            inputs=[
                Artifact(role="vendor_table", path=source),
                *[
                    Artifact(role="vendor_secondary", path=secondary)
                    for secondary in secondary_inputs
                ],
                Artifact(role="vendor_parameter_file", path=parameters),
            ],
            outputs=[
                Artifact(role="converted", path=converted, format=context.format),
                representation(converted),
                Artifact(role="tool_timings", path=convert_timings),
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
                Artifact(role="converted", path=converted, format=context.format),
                Artifact(role="fasta", path=fasta),
            ],
            outputs=[
                Artifact(role="fasta_verified", path=verified, format=context.format),
                representation(verified),
            ],
        ),
        StepSpec(
            name="benchmark",
            command=[
                str(context.tool("apb-proteobench")),
                "benchmark",
                str(verified),
                module,
                str(scored),
            ],
            inputs=[
                Artifact(role="fasta_verified", path=verified, format=context.format),
            ],
            outputs=[
                Artifact(role="result", path=scored, format=context.format),
                representation(scored),
            ],
        ),
    ]


if __name__ == "__main__":
    main("proteobench", steps)
