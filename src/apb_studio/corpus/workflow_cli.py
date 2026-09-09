"""One CLI contract used by every concrete workflow script."""

from __future__ import annotations

import argparse
import signal
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from uuid import uuid4

from pydantic import Field

from apb_studio.corpus.models import (
    Dataset,
    DatasetReport,
    Record,
    StepResult,
    StepSpec,
    StorageFormat,
)
from apb_studio.corpus.runner import run_steps
from apb_studio.corpus.tables import load_corpus


class WorkflowContext(Record):
    """Resolved inputs for a workflow; CSV resource interpretation belongs to the script."""

    corpus: Path
    data_root: Path
    dataset: Dataset
    workflow_table: Path | None = None
    format: StorageFormat = "hdf5"
    output_dir: Path
    report: Path
    tools: dict[str, Path] = Field(min_length=1)
    run_id: str = "standalone"

    def tool(self, name: str, /) -> Path:
        """Resolve one executable this workflow declared in its own TOOLS tuple."""
        if name not in self.tools:
            raise ValueError(f"{name} was not resolved; declare it in this workflow's TOOLS")
        return self.tools[name]


def _tools(values: list[str]) -> dict[str, Path]:
    """Parse repeated --tool NAME=PATH pairs into the mapping the workflow asks by name."""
    tools: dict[str, Path] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            raise ValueError(f"Expected --tool NAME=PATH, got {value!r}")
        if name in tools:
            raise ValueError(f"Duplicate --tool {name}")
        tools[name] = Path(path)
    if not tools:
        raise ValueError("At least one --tool NAME=PATH is required")
    return tools


def _interrupt(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt(f"Workflow interrupted by signal {signum}")


def main(name: str, steps: Callable[[WorkflowContext], list[StepSpec]]) -> None:
    """Parse identical arguments, resolve a corpus row, and execute the supplied workflow."""
    parser = argparse.ArgumentParser(description=f"Run workflow_{name}.py for one vendor input")
    for option in ("corpus", "data-root", "input-file", "output-dir", "report"):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument(
        "--tool",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="One resolved executable per declared tool; repeat the flag for each",
    )
    parser.add_argument("--workflow-table", type=Path)
    parser.add_argument("--run-id", default="standalone")
    parser.add_argument("--format", choices=("hdf5", "duckdb", "parquet"), default="hdf5")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _interrupt)
    rows = [row for row in load_corpus(Path(args.corpus)) if row.input_file == args.input_file]
    if len(rows) != 1:
        raise ValueError(f"Expected one corpus row for {args.input_file}")
    context = WorkflowContext(
        corpus=Path(args.corpus),
        data_root=Path(args.data_root),
        dataset=rows[0],
        workflow_table=args.workflow_table,
        format=args.format,
        output_dir=Path(args.output_dir) / uuid4().hex,
        report=Path(args.report),
        tools=_tools(args.tool),
        run_id=args.run_id,
    )
    report = DatasetReport(
        run_id=context.run_id,
        workflow=name,
        format=context.format,
        dataset=context.dataset,
        steps=[StepResult.model_validate(spec.model_dump()) for spec in steps(context)],
    )
    run_steps(report, context.report)
