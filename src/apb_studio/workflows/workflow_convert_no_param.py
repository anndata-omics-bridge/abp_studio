"""Convert a known producer's quant result using APB2 column evidence alone."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation, result_path

TOOLS = ("apb2",)
WORKFLOW_TABLE = "workflow_no_param.tsv"
WORKFLOW_COLUMNS = ("software_name", "software")
USES_VENDOR_PARAMETERS = False


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert without consulting the corpus's vendor parameter file."""
    if context.workflow_table is None:
        raise ValueError(f"{WORKFLOW_TABLE} is required")
    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("software_name",))
    if tuple(workflow) != WORKFLOW_COLUMNS or not workflow["software"]:
        raise ValueError(f"{context.workflow_table} must have exactly {WORKFLOW_COLUMNS}")
    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    basename = context.output_dir / "converted"
    target = result_path(context.output_dir, "converted", context.format)
    timing_file = context.output_dir / "converted.timings.json"
    return [
        StepSpec(
            name="convert_no_param",
            command=[
                str(context.tool("apb2")),
                "convert",
                str(vendor_source),
                "--software",
                workflow["software"],
                "--output",
                str(basename),
                "--format",
                context.format,
                "--timings-output",
                str(timing_file),
            ],
            inputs=[
                Artifact(role="vendor_table", path=source),
                *[
                    Artifact(role="vendor_secondary", path=secondary)
                    for secondary in secondary_inputs
                ],
            ],
            outputs=[
                Artifact(role="result", path=target, format=context.format),
                representation(target),
                Artifact(role="tool_timings", path=timing_file),
            ],
        )
    ]


if __name__ == "__main__":
    main("convert_no_param", steps)
