"""Linear aggregation workflow: convert configured source levels, then aggregate to protein.

The ``method`` cell lists one or more apb-aggregate selections separated by ``;``. Each runs as
its own step and adds its layers to the previous step's result.
"""

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
    """Convert configured source levels, then run each listed aggregate on the previous result."""
    if context.workflow_table is None:
        raise ValueError("workflow_aggregate.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("software_name",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    start_level = workflow["start_level"]
    fallback_level = workflow["fallback_level"]
    methods = [selection.strip() for selection in workflow["method"].split(";")]
    if not start_level or not all(methods):
        raise ValueError("workflow_aggregate.csv requires nonempty start_level and method values")
    if len(set(methods)) != len(methods):
        raise ValueError(f"workflow_aggregate.csv repeats a method in {workflow['method']!r}")
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
    convert = StepSpec(
        name="convert",
        command=convert_command,
        inputs=[
            Artifact(role="vendor_table", path=source),
            *[Artifact(role="vendor_secondary", path=secondary) for secondary in secondary_inputs],
            Artifact(role="vendor_parameter_file", path=parameters),
        ],
        outputs=[
            Artifact(role="converted", path=converted, format=context.format),
            representation(converted),
        ],
    )
    planned = [convert]
    source_artifact = convert.outputs[0]
    for position, method in enumerate(methods, start=1):
        last = position == len(methods)
        aggregated = result_path(
            context.output_dir, "aggregated" if last else f"aggregated_{method}", context.format
        )
        command = [
            str(context.tool("apb-aggregate")),
            start_level,
            "protein",
            method,
            str(source_artifact.path),
            str(aggregated),
        ]
        if fallback_level:
            command.extend(["--fallback-source-level", fallback_level])
        output = Artifact(
            role="result" if last else "aggregated", path=aggregated, format=context.format
        )
        planned.append(
            StepSpec(
                name=f"aggregate-{method}",
                command=command,
                inputs=[source_artifact],
                outputs=[output, representation(aggregated)],
            )
        )
        source_artifact = output
    return planned


if __name__ == "__main__":
    main("aggregate", steps)
