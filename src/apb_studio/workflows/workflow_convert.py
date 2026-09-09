"""Reference linear workflow: convert, then reformat when requested."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import resolve_file
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation
from apb_studio.workflows.software import parameter_software

TOOLS = ("apb2",)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert all compatible levels; vendor parsing and level detection stay in APB2."""
    dataset = context.dataset
    source = resolve_file(context.data_root, dataset.input_file)
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    apb2 = context.tool("apb2")
    basename = context.output_dir / "converted"
    hdf5 = basename.with_suffix(".h5mu")
    command = [
        str(apb2),
        "convert",
        str(source),
        "--params",
        str(parameters),
        "--params-software",
        parameter_software(dataset.software_name),
        "--output",
        str(basename),
    ]
    result = [
        StepSpec(
            name="convert",
            command=command,
            inputs=[
                Artifact(role="vendor_table", path=source),
                Artifact(role="vendor_parameter_file", path=parameters),
            ],
            outputs=[
                Artifact(role="converted", path=hdf5, format="hdf5"),
                representation(hdf5),
            ],
        )
    ]
    if context.format != "hdf5":
        target = basename.with_suffix(f".{context.format}")
        result.append(
            StepSpec(
                name="reformat",
                command=[str(apb2), "reformat", str(hdf5), str(target)],
                inputs=[Artifact(role="converted", path=hdf5, format="hdf5")],
                outputs=[
                    Artifact(role="result", path=target, format=context.format),
                    representation(target),
                ],
            )
        )
    return result


if __name__ == "__main__":
    main("convert", steps)
