"""One-call ProteoBench workflow: the same scoring, in a single in-memory apb-proteobench run."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation, result_path
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("module", "fasta", "level")
WORKFLOW_TABLE = "workflow_proteobench.csv"
TOOLS = ("apb-proteobench",)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Score one module in memory and persist only the selected APB2 format."""
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
    scored = result_path(context.output_dir, "scored", context.format)
    timings_dir = context.output_dir / "timings"

    return [
        StepSpec(
            name="run",
            command=[
                str(context.tool("apb-proteobench")),
                "run",
                str(vendor_source),
                str(fasta),
                "--params",
                str(parameters),
                "--software",
                parameter_software(dataset.software_name),
                "--module",
                module,
                "--output",
                str(scored),
                "--timings-dir",
                str(timings_dir),
            ],
            inputs=[
                Artifact(role="vendor_table", path=source),
                *[
                    Artifact(role="vendor_secondary", path=secondary)
                    for secondary in secondary_inputs
                ],
                Artifact(role="vendor_parameter_file", path=parameters),
                Artifact(role="fasta", path=fasta),
            ],
            outputs=[
                Artifact(role="result", path=scored, format=context.format),
                representation(scored),
                Artifact(role="tool_timings", path=timings_dir / "apb2.convert.timings.json"),
                Artifact(
                    role="tool_timings",
                    path=timings_dir / "apb-fasta.verify-peptides.timings.json",
                ),
                Artifact(
                    role="tool_timings",
                    path=timings_dir / "apb-proteobench.benchmark.timings.json",
                ),
            ],
        ),
    ]


if __name__ == "__main__":
    main("proteobench_run", steps)
