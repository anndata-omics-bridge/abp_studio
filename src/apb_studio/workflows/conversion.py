"""Full compatible-level conversion shared by conversion and aggregation workflows."""

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.parameters import optional_parameter_inputs
from apb_studio.corpus.tables import resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.workflows.artifacts import representation, result_path
from apb_studio.workflows.software import parameter_software, result_software


def conversion_step(context: WorkflowContext, result_role: str = "result") -> StepSpec:
    """Convert every compatible level, using vendor parameters when the dataset supplies them."""
    dataset = context.dataset
    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = optional_parameter_inputs(context.data_root, dataset)
    software = (
        parameter_software(dataset.software_name)
        if parameters
        else result_software(dataset.software_name)
    )
    target = result_path(context.output_dir, "converted", context.format)
    timing_file = context.output_dir / "converted.timings.json"
    return StepSpec(
        name="convert",
        command=[
            str(context.tool("apb2")),
            "convert",
            str(vendor_source),
            *[argument for path in parameters for argument in ("--params", str(path))],
            "--software",
            software,
            "--output",
            str(target.with_suffix("")),
            "--format",
            context.format,
            "--timings-output",
            str(timing_file),
        ],
        inputs=[
            Artifact(role="vendor_table", path=source),
            *[Artifact(role="vendor_secondary", path=secondary) for secondary in secondary_inputs],
            *[Artifact(role="vendor_parameter_file", path=path) for path in parameters],
        ],
        outputs=[
            Artifact(role=result_role, path=target, format=context.format),
            representation(target),
            Artifact(role="tool_timings", path=timing_file),
        ],
    )
