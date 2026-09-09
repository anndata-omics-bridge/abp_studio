"""One-call ProteoBench workflow: the same scoring, in a single in-memory apb-proteobench run."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("module", "module_toml", "fasta")
WORKFLOW_TABLE = "workflow_proteobench.csv"
TOOLS = ("apb-proteobench",)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Score one module in a single call, so no intermediate H5MU reaches disk."""
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
    scored = context.output_dir / "scored.h5mu"

    return [
        StepSpec(
            name="run",
            command=[
                str(context.tool("apb-proteobench")),
                "run",
                str(source),
                str(fasta),
                "--params",
                str(parameters),
                "--params-software",
                parameter_software(dataset.software_name),
                "--module",
                str(module),
                "--output",
                str(scored),
            ],
            inputs=[
                Artifact(role="vendor_table", path=source),
                Artifact(role="vendor_parameter_file", path=parameters),
                Artifact(role="fasta", path=fasta),
                Artifact(role="module_settings", path=module),
            ],
            outputs=[
                Artifact(role="result", path=scored, format="hdf5"),
                representation(scored),
            ],
        ),
    ]


if __name__ == "__main__":
    main("proteobench_run", steps)
