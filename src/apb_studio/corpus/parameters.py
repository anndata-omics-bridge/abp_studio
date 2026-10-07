"""Workflow-owned vendor-parameter dependencies at the corpus boundary."""

from pathlib import Path

from apb_studio.corpus.models import Dataset
from apb_studio.corpus.tables import resolve_file


def required_parameter_inputs(data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Require the parameter file a scoring or export workflow consumes."""
    if not dataset.vendor_parameter_file:
        raise ValueError(f"Vendor input {dataset.input_file} has no vendor parameter file")
    return (resolve_file(data_root, dataset.vendor_parameter_file),)


def optional_parameter_inputs(data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Track supplied parameters while accepting vendor tables that have none."""
    if not dataset.vendor_parameter_file:
        return ()
    return (resolve_file(data_root, dataset.vendor_parameter_file),)


def ignored_parameter_inputs(data_root: Path, dataset: Dataset) -> tuple[Path, ...]:
    """Declare that a parameter-free conversion never reads vendor parameters."""
    return ()
