"""Complete ion-level ProteoBench export and pMultiQC report workflow."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation, single_level_result_path
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("module", "fasta", "level")
WORKFLOW_TABLE = "workflow_proteobench.csv"
TOOLS = ("apb-proteobench", "multiqc")


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Export one ion benchmark and render its pMultiQC report in measured steps."""
    if context.workflow_table is None:
        raise ValueError("workflow_proteobench.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("module",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")
    if workflow["level"] != "ion":
        raise ValueError("proteobench_pmultiqc requires level ion")

    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    module = dataset.module
    fasta = resolve_file(context.data_root, workflow["fasta"])
    scored = single_level_result_path(context.output_dir, "scored", context.format)
    export = context.output_dir / "proteobench-export"
    result_performance = export / "result_performance.csv"
    report_dir = context.output_dir / "pmultiqc"
    report = report_dir / "multiqc_report.html"
    report_data = report_dir / "multiqc_report_data"
    timings_dir = context.output_dir / "timings"

    return [
        StepSpec(
            name="proteobench-export",
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
                "--level",
                workflow["level"],
                "--x",
                "--output",
                str(scored),
                "--result-performance",
                str(result_performance),
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
                Artifact(role="proteobench_export", path=export),
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
        StepSpec(
            name="pmultiqc",
            command=[
                str(context.tool("multiqc")),
                "--proteobench-plugin",
                "--interactive",
                str(export),
                "--outdir",
                str(report_dir),
                "--filename",
                report.name,
                "--data-dir",
            ],
            inputs=[Artifact(role="proteobench_export", path=export)],
            outputs=[
                Artifact(role="pmultiqc_report", path=report),
                Artifact(role="pmultiqc_data", path=report_data),
            ],
        ),
    ]


if __name__ == "__main__":
    main("proteobench_pmultiqc", steps)
