"""ProteoBench entrapment workflow: one apb-proteobench call from vendor files to FDP scores."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import join_workflow, resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext, main
from apb_studio.workflows.artifacts import representation, single_level_result_path
from apb_studio.workflows.proteobench_scoring import SCORES_NAME
from apb_studio.workflows.software import parameter_software

WORKFLOW_COLUMNS = ("module", "fasta")
TOOLS = ("apb-proteobench",)


def steps(context: WorkflowContext) -> list[StepSpec]:
    """Convert, verify and score one entrapment upload for every precursor q-value kind.

    ``fasta`` names the entrapment FASTA's Parquet protein database, which also gives each
    peptide its label and pair.
    """
    if context.workflow_table is None:
        raise ValueError("workflow_proteobench_entrapment.csv is required")

    dataset = context.dataset
    workflow = join_workflow(dataset.model_dump(), context.workflow_table, on=("module",))
    if tuple(workflow) != WORKFLOW_COLUMNS:
        raise ValueError(f"{context.workflow_table} must have exactly {','.join(WORKFLOW_COLUMNS)}")

    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    fasta = resolve_file(context.data_root, workflow["fasta"])
    scored = single_level_result_path(context.output_dir, "scored", context.format)
    scores = context.output_dir / SCORES_NAME
    timings_dir = context.output_dir / "timings"

    return [
        StepSpec(
            name="run-entrapment",
            command=[
                str(context.tool("apb-proteobench")),
                "run",
                "entrapment",
                str(vendor_source),
                str(fasta),
                "--params",
                str(parameters),
                "--software",
                parameter_software(dataset.software_name),
                "--module",
                dataset.module,
                "--output",
                str(scored),
                "--scores",
                str(scores),
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
                Artifact(role="proteobench_scores", path=scores),
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
    main("proteobench_entrapment", steps)
