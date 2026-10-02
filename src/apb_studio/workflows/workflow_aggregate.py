"""Linear aggregation workflow: convert configured source levels, then aggregate to protein."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import (
    representation,
    result_path,
    single_level_result_path,
)
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("software_name", "start_level", "fallback_level", "method")
TOOLS = ("apb2", "apb-aggregate")


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert configured source levels and aggregate the preferred available one."""
    if context.workflow_table is None:
        raise ValueError("workflow_aggregate.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("software_name",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    start_level = workflow["start_level"]
    fallback_level = workflow["fallback_level"]
    method = workflow["method"]
    if not start_level or not method:
        raise ValueError("workflow_aggregate.csv requires nonempty start_level and method values")
    if fallback_level == start_level:
        raise ValueError("workflow_aggregate.csv fallback_level must differ from start_level")

    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    converted = (
        result_path(context.output_dir, "converted", context.format)
        if fallback_level
        else single_level_result_path(context.output_dir, "converted", context.format)
    )
    aggregated = result_path(context.output_dir, "aggregated", context.format)
    convert_command = [
        str(context.tool("apb2")),
        "convert",
        str(vendor_source),
    ]
    if not fallback_level:
        convert_command.append(start_level)
    convert_command.extend([
        "--params",
        str(parameters),
        "--software",
        parameter_software(dataset.software_name),
        "--output",
        str(converted.with_suffix("")),
        "--format",
        context.format,
    ])
    aggregate_command = [
        str(context.tool("apb-aggregate")),
        start_level,
        "protein",
        method,
        str(converted),
        str(aggregated),
    ]
    if fallback_level:
        aggregate_command.extend(["--fallback-source-level", fallback_level])

    return [
        StepSpec(
            name="convert",
            command=convert_command,
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
            ],
        ),
        StepSpec(
            name="aggregate",
            command=aggregate_command,
            inputs=[Artifact(role="converted", path=converted, format=context.format)],
            outputs=[
                Artifact(role="result", path=aggregated, format=context.format),
                representation(aggregated),
            ],
        ),
    ]


if __name__ == "__main__":
    main("aggregate", steps)
