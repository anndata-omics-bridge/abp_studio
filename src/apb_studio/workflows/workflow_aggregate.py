"""Linear aggregation workflow: convert one configured level, then aggregate to protein."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("software_name", "start_level", "method")
TOOLS = ("apb2", "apb-aggregate")


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert the configured source level and aggregate it directly to protein."""
    if context.workflow_table is None:
        raise ValueError("workflow_aggregate.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("software_name",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    start_level = workflow["start_level"]
    method = workflow["method"]
    if not start_level or not method:
        raise ValueError("workflow_aggregate.csv requires nonempty start_level and method values")

    source = resolve_file(context.data_root, dataset.input_file)
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    converted = context.output_dir / "converted.h5ad"
    target_suffix = ".h5mu" if context.format == "hdf5" else f".{context.format}"
    aggregated = context.output_dir / f"aggregated{target_suffix}"

    return [
        StepSpec(
            name="convert",
            command=[
                str(context.tool("apb2")),
                "convert",
                str(source),
                start_level,
                "--params",
                str(parameters),
                "--params-software",
                parameter_software(dataset.software_name),
                "--output",
                str(converted.with_suffix("")),
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
            name="aggregate",
            command=[
                str(context.tool("apb-aggregate")),
                start_level,
                "protein",
                method,
                str(converted),
                str(aggregated),
            ],
            inputs=[Artifact(role="converted", path=converted, format="hdf5")],
            outputs=[
                Artifact(role="result", path=aggregated, format=context.format),
                representation(aggregated),
            ],
        ),
    ]


if __name__ == "__main__":
    main("aggregate", steps)
