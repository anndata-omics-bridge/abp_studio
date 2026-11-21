"""Workflow-owned vendor-parameter dependencies at the corpus boundary."""

from pathlib import Path

from apb_studio.corpus.models import Dataset
from apb_studio.corpus.tables import resolve_file


def required_parameter_inputs(data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Require the parameter files a scoring or export workflow consumes."""
    if not dataset.vendor_parameter_files:
        raise ValueError(f"Vendor input {dataset.input_file} has no vendor parameter file")
    return tuple(resolve_file(data_root, path) for path in dataset.vendor_parameter_files)


def optional_parameter_inputs(data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Track supplied parameters while accepting vendor tables that have none."""
    return tuple(resolve_file(data_root, path) for path in dataset.vendor_parameter_files)


def ignored_parameter_inputs(data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Declare that a parameter-free conversion never reads vendor parameters."""
    return ()
