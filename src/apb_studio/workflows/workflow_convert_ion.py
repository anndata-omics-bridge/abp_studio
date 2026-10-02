"""Convert only the ion level to the selected APB2 format."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation, single_level_result_path
from apb_studio.workflows.software import parameter_software

TOOLS = ("apb2",)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Read and write the ion level only, retaining APB2's phase timing artifact."""
    dataset = context.dataset
    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    apb2 = context.tool("apb2")
    basename = context.output_dir / "converted"
    target = single_level_result_path(context.output_dir, "converted", context.format)
    timing_file = context.output_dir / "converted.timings.json"
    command = [
        str(apb2),
        "convert",
        str(vendor_source),
        "ion",
        "--params",
        str(parameters),
        "--software",
        parameter_software(dataset.software_name),
        "--output",
        str(basename),
        "--format",
        context.format,
        "--timings-output",
        str(timing_file),
    ]
    return [
        StepSpec(
            name="convert",
            command=command,
            inputs=[
                Artifact(role="vendor_table", path=source),
                *[
                    Artifact(role="vendor_secondary", path=secondary)
                    for secondary in secondary_inputs
                ],
                Artifact(role="vendor_parameter_file", path=parameters),
            ],
            outputs=[
                Artifact(role="result", path=target, format=context.format),
                representation(target),
                Artifact(role="tool_timings", path=timing_file),
            ],
        )
    ]


if __name__ == "__main__":
    main("convert_ion", steps)
