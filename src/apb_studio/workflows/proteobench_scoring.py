"""One in-memory ``apb-proteobench run quant`` call: the scored result and its scores JSON."""

from __future__ import annotations

from apb_studio.corpus.models import Artifact, StepSpec
from apb_studio.corpus.tables import resolve_file, resolve_secondary_inputs
from apb_studio.corpus.workflow_cli import WorkflowContext
from apb_studio.workflows.artifacts import representation, result_path, single_level_result_path
from apb_studio.workflows.software import parameter_software

SCORES_NAME = "scores.json"
"""The ProteoBench datapoint JSON each scoring workflow writes beside its result."""


def run_quant_step(
    context: WorkflowContext, fasta: str, level: str | None = None, layer: str | None = None
) -> StepSpec:
    """Score one module in memory; persist the selected APB2 format and the scores JSON.

    ``level`` and ``layer`` default to every compatible level and the APB primary layer.
    """
    dataset = context.dataset
    source = resolve_file(context.data_root, dataset.input_file)
    secondary_inputs = resolve_secondary_inputs(context.data_root, dataset.input_file)
    vendor_source = source.parent if secondary_inputs else source
    parameters = resolve_file(context.data_root, dataset.vendor_parameter_file)
    fasta_path = resolve_file(context.data_root, fasta)
    output = single_level_result_path if level is not None else result_path
    scored = output(context.output_dir, "scored", context.format)
    scores = context.output_dir / SCORES_NAME
    timings_dir = context.output_dir / "timings"
    selection = [
        *(["--level", level] if level is not None else []),
        *(["--layer", layer] if layer is not None else []),
    ]
    return StepSpec(
        name="run",
        command=[
            str(context.tool("apb-proteobench")),
            "run",
            "quant",
            str(vendor_source),
            str(fasta_path),
            "--params",
            str(parameters),
            "--software",
            parameter_software(dataset.software_name),
            "--module",
            dataset.module,
            *selection,
            "--output",
            str(scored),
            "--scores",
            str(scores),
            "--timings-dir",
            str(timings_dir),
        ],
        inputs=[
            Artifact(role="vendor_table", path=source),
            *[Artifact(role="vendor_secondary", path=secondary) for secondary in secondary_inputs],
            Artifact(role="vendor_parameter_file", path=parameters),
            Artifact(role="fasta", path=fasta_path),
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
    )
