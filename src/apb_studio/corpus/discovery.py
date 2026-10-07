"""Packaged workflow discovery, and the tools and resource table each workflow declares."""

import importlib
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

from apb_studio.corpus.models import Dataset
from apb_studio.corpus.parameters import required_parameter_inputs

WORKFLOWS = Path(__file__).parents[1] / "workflows"
SNAKEFILE = Path(__file__).parents[1] / "workflow" / "Snakefile"


def workflow_path(name: str) -> Path:
    """Resolve one concrete workflow without importing or executing its code."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid workflow name: {name!r}")
    path = WORKFLOWS / f"workflow_{name}.py"
    if not path.is_file():
        raise ValueError(
            f"Unknown workflow {name!r}; available: {', '.join(available_workflows())}"
        )
    return path


def workflow_implementation_paths(name: str) -> tuple[Path, ...]:
    """Return the selected workflow and every shared workflow implementation module."""
    selected = workflow_path(name)
    shared = (path for path in WORKFLOWS.rglob("*.py") if not path.name.startswith("workflow_"))
    return tuple(sorted({selected, *shared}))


def available_workflows() -> list[str]:
    """Return only concrete packaged workflow names."""
    return sorted(path.stem.removeprefix("workflow_") for path in WORKFLOWS.glob("workflow_*.py"))


def _workflow_module(name: str) -> ModuleType:
    workflow_path(name)
    return importlib.import_module(f"apb_studio.workflows.workflow_{name}")


def workflow_tools(name: str) -> tuple[str, ...]:
    """Ask the workflow which executables it needs; each workflow owns that fact itself."""
    tools = getattr(_workflow_module(name), "TOOLS", None)
    if not isinstance(tools, tuple) or not all(isinstance(tool, str) for tool in tools):
        raise ValueError(f"workflow_{name}.py must declare TOOLS as a tuple of executable names")
    return tools


def workflow_parameter_inputs(name: str, data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Ask the workflow which vendor-parameter dependencies this dataset supplies."""
    declared = getattr(_workflow_module(name), "PARAMETER_INPUTS", required_parameter_inputs)
    if not callable(declared):
        raise ValueError(f"workflow_{name}.py must declare PARAMETER_INPUTS as a callable")
    inputs = cast(Callable[[Path, Dataset], tuple[Path, ...]], declared)
    return inputs(data_root, dataset)


def workflow_table_name(name: str) -> str:
    """Ask the workflow which resource table it reads, so sibling workflows can share one."""
    declared = getattr(_workflow_module(name), "WORKFLOW_TABLE", f"workflow_{name}.csv")
    valid = isinstance(declared, str) and re.fullmatch(
        r"workflow_[a-z][a-z0-9_]*\.(?:csv|tsv)", declared
    )
    if not valid:
        raise ValueError(
            f"workflow_{name}.py must declare WORKFLOW_TABLE as a workflow_<name>.csv "
            "or workflow_<name>.tsv file name"
        )
    return declared
