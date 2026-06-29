"""Framework-agnostic support for the test-data browser GUI (ui/test_tool.py).

The ProteoBench test-data catalog, converted-runs tracking, and result summaries. Conversion
itself is NOT here — the browser shells out to the ``apb convert`` CLI via
``apb_studio.conversion.subprocess_adapter``. Read-only rule/metadata logic is reused from the
``anndata_proteomics`` package (no duplication); kept free of any marimo import so it is unit-testable.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from anndata_proteomics.converters.pipeline import (
    MUDATA,
    _param_version,
    available_targets,
    software_slug,
)
from anndata_proteomics.params.anndata_io import (
    get_search_parameters_path,
    read_search_parameters,
)
from anndata_proteomics.readers.result import load_converted_result
from anndata_proteomics.test_data import DOWNLOADED_DB, TEST_DATA_DIR

# Background-job conversions write their result + console.log + command.json into a per-run subdir.
CONVERTED_DIR = TEST_DATA_DIR.parent / "logs" / "ui_converted"
CONVERTED_COLUMNS = [
    "run_name",
    "timestamp",
    "software_name",
    "software_version",
    "slug",
    "target",
    "status",
    "result_type",
    "nr_prec",
    "size_mb",
    "input_file_path",
    "param_path",
    "output_dir",
    "result_path",
    "log_path",
]

# Converting these targets on a large input is memory-heavy (the fragment explode); warn first.
_HEAVY_TARGETS = {"fragment", MUDATA}
_HEAVY_SIZE_MB = 100.0
_RUN_DIR_RE = re.compile(r"^(?P<timestamp>\d{8}T\d{6})_(?P<slug>[a-z0-9]+)_(?P<target>[a-z0-9_]+)$")


def dataset_path(input_file_path: str) -> Path:
    """Absolute path to a cached ProteoBench input file (relative to the test-data cache)."""
    return TEST_DATA_DIR / "json_dir" / input_file_path


def _headers(path: Path) -> set[str]:
    """Read just the column names of a cached input (cheap; for convertibility checks)."""
    path = Path(path)
    if path.suffix == ".parquet":
        return set(pq.read_schema(path).names)
    return set(pd.read_csv(path, sep="\t", nrows=0).columns)


def param_path_for(input_file_path: str) -> Path | None:
    """The co-located ProteoBench param file (``param_0..*``) next to a dataset's input file."""
    candidates = sorted(dataset_path(input_file_path).parent.glob("param_0.*"))
    return candidates[0] if candidates else None


def load_catalog() -> pd.DataFrame:
    """Read the ProteoBench test-data index into a catalog DataFrame.

    Per-row columns added: ``size_mb``, ``slug``, ``param_path`` (co-located param file or ""),
    ``targets`` (tuple — convertible only when a param file gives a version whose rule matches the
    data columns), ``targets_str``. Only ``status == "ok"`` rows are kept. Empty when the cache
    index is absent (gitignored — regenerate via the apb ``test_data_download/Makefile``).
    """
    if not DOWNLOADED_DB.exists():
        return pd.DataFrame(
            columns=[
                "software_name",
                "software_version",
                "nr_prec",
                "size_mb",
                "slug",
                "param_path",
                "targets",
                "targets_str",
                "input_file_path",
            ]
        )
    rows = []
    by_path: dict[str, tuple[tuple[str, ...], str]] = {}  # rel -> (targets, param_path)
    with open(DOWNLOADED_DB) as f:
        for row in csv.DictReader(f):
            if row.get("status") != "ok":
                continue
            slug = software_slug(row["software_name"])
            rel = row["input_file_path"]
            if rel not in by_path:
                param = param_path_for(rel)
                try:
                    if param is None:
                        targets: tuple[str, ...] = ()
                    else:
                        version = _param_version(param, slug)
                        headers = _headers(dataset_path(rel))
                        targets = tuple(available_targets(slug, version, headers))
                except (OSError, ValueError):  # missing/unreadable cached file
                    targets = ()
                by_path[rel] = (targets, str(param) if param else "")
            targets, param_str = by_path[rel]
            size_bytes = (
                int(row["input_file_size_bytes"])
                if row.get("input_file_size_bytes", "").isdigit()
                else 0
            )
            rows.append(
                {
                    "software_name": row["software_name"],
                    "software_version": row.get("software_version", ""),
                    "nr_prec": int(row["nr_prec"]) if row.get("nr_prec", "").isdigit() else 0,
                    "size_mb": round(size_bytes / 1e6, 1),
                    "slug": slug,
                    "param_path": param_str,
                    "targets": targets,
                    "targets_str": ", ".join(targets) if targets else "—",
                    "input_file_path": rel,
                }
            )
    return pd.DataFrame(rows)


def filter_catalog(
    catalog: pd.DataFrame,
    *,
    target: str | None = None,
    software: str | None = None,
    max_size_mb: float | None = None,
) -> pd.DataFrame:
    """Apply the GUI filters: by conversion target, by software, by size."""
    df = catalog
    if target:
        df = df[df["targets"].apply(lambda ts: target in ts)]
    if software and software != "All":
        df = df[df["software_name"] == software]
    if max_size_mb is not None:
        df = df[df["size_mb"] <= max_size_mb]
    return df.reset_index(drop=True)


def is_heavy(target: str, size_mb: float) -> bool:
    """Whether converting ``target`` on a ``size_mb`` input is likely memory-heavy."""
    return target in _HEAVY_TARGETS and size_mb >= _HEAVY_SIZE_MB


def _empty_converted_runs() -> pd.DataFrame:
    return pd.DataFrame(columns=CONVERTED_COLUMNS)


def _parse_run_dir_name(name: str) -> dict[str, str]:
    match = _RUN_DIR_RE.match(name)
    if match is None:
        return {"timestamp": "", "slug": "", "target": ""}
    return match.groupdict()


def _result_file(run_dir: Path) -> Path | None:
    for name in ("result.h5mu", "result.h5ad"):
        path = run_dir / name
        if path.is_file():
            return path
    return None


def _command_metadata(run_dir: Path) -> dict[str, str]:
    """Read the conversion command sidecar written by subprocess_adapter (``command.json``)."""
    path = run_dir / "command.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    keys = {"input_file_path", "slug", "target", "param_path"}
    return {key: str(value) for key, value in data.items() if key in keys}


def _catalog_lookup(catalog: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if catalog.empty:
        return {}
    return {
        str(row["input_file_path"]): {
            "software_name": row.get("software_name", ""),
            "software_version": row.get("software_version", ""),
            "nr_prec": row.get("nr_prec", ""),
            "size_mb": row.get("size_mb", ""),
            "param_path": row.get("param_path", ""),
        }
        for _, row in catalog.iterrows()
    }


def _stored_search_parameters(obj) -> dict[str, Any] | None:
    params = read_search_parameters(obj)
    if params is None:
        return None
    out = params.model_dump(mode="json", exclude_none=True)
    path = get_search_parameters_path(obj)
    if path:
        out["search_parameters_path"] = path
    return out


def _artifact_search_parameters(result_path: Path) -> dict[str, Any] | None:
    try:
        obj = load_converted_result(result_path)
    except Exception:  # noqa: BLE001 - table metadata falls back to log/catalog.
        return None
    if hasattr(obj, "mod"):
        params = _stored_search_parameters(obj)
        if params is not None:
            return params
        for modality in obj.mod.values():
            params = _stored_search_parameters(modality)
            if params is not None:
                return params
        return None
    return _stored_search_parameters(obj)


def list_converted_runs(converted_dir: Path | str = CONVERTED_DIR) -> pd.DataFrame:
    """Scan converted-output folders into a stable DataFrame for the GUI table."""
    root = Path(converted_dir).expanduser()
    if not root.exists():
        return _empty_converted_runs()

    catalog_by_input = _catalog_lookup(load_catalog())
    rows: list[dict[str, str]] = []
    for run_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        parsed = _parse_run_dir_name(run_dir.name)
        result = _result_file(run_dir)
        log_path = run_dir / "console.log"
        command = _command_metadata(run_dir)
        input_file_path = command.get("input_file_path", "")
        catalog_row = catalog_by_input.get(input_file_path, {})
        artifact_params = _artifact_search_parameters(result) if result is not None else None
        if result is not None:
            status = "finished"
            result_type = result.suffix.removeprefix(".")
            result_path = str(result)
        elif log_path.exists():
            status = "incomplete"
            result_type = ""
            result_path = ""
        else:
            status = "empty"
            result_type = ""
            result_path = ""
        rows.append(
            {
                "run_name": run_dir.name,
                "timestamp": parsed["timestamp"],
                "software_name": str(
                    (artifact_params or {}).get(
                        "software_name", catalog_row.get("software_name", "")
                    )
                ),
                "software_version": str(
                    (artifact_params or {}).get(
                        "software_version", catalog_row.get("software_version", "")
                    )
                ),
                "slug": command.get("slug", parsed["slug"]),
                "target": command.get("target", parsed["target"]),
                "status": status,
                "result_type": result_type,
                "nr_prec": str(catalog_row.get("nr_prec", "")),
                "size_mb": str(catalog_row.get("size_mb", "")),
                "input_file_path": input_file_path,
                "param_path": str(
                    (artifact_params or {}).get(
                        "search_parameters_path",
                        command.get("param_path", str(catalog_row.get("param_path", ""))),
                    )
                ),
                "output_dir": str(run_dir),
                "result_path": result_path,
                "log_path": str(log_path) if log_path.exists() else "",
            }
        )
    if not rows:
        return _empty_converted_runs()
    return pd.DataFrame(rows, columns=CONVERTED_COLUMNS)


def converted_runs_table(runs: pd.DataFrame) -> pd.DataFrame:
    """User-facing converted-runs table with no internal filesystem-path columns."""
    columns = [
        "run_name",
        "software_name",
        "software_version",
        "target",
        "status",
        "result_type",
        "nr_prec",
        "size_mb",
    ]
    if runs.empty:
        return pd.DataFrame(columns=columns)
    return runs[columns].copy()


def _matrix_stats(matrix: np.ndarray) -> dict[str, float]:
    flat = np.asarray(matrix, dtype="float64").ravel()
    valid = flat[~np.isnan(flat)]
    if valid.size == 0:
        return {"min": float("nan"), "max": float("nan"), "mean": float("nan"), "nan_pct": 100.0}
    return {
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "mean": float(np.mean(valid)),
        "nan_pct": round(100 * (flat.size - valid.size) / flat.size, 1),
    }


def _search_parameters_summary(obj) -> dict[str, Any] | None:
    params = _stored_search_parameters(obj)
    if params is None:
        return None
    headline = [
        "software_name",
        "software_version",
        "search_engine_version",
        "quantification_method",
        "ident_fdr_psm",
        "ident_fdr_peptide",
        "ident_fdr_protein",
        "enable_match_between_runs",
    ]
    ordered = {key: params[key] for key in headline if key in params}
    ordered.update({key: value for key, value in params.items() if key not in ordered})
    return ordered


def _mudata_search_parameters_summary(obj) -> dict[str, Any] | None:
    params = _search_parameters_summary(obj)
    if params is not None:
        return params
    summaries = {name: _search_parameters_summary(modality) for name, modality in obj.mod.items()}
    present = {name: summary for name, summary in summaries.items() if summary is not None}
    if not present:
        return None
    first = next(iter(present.values()))
    mismatches = [name for name, summary in present.items() if summary != first]
    out = dict(first)
    out["source"] = "modalities"
    out["modalities"] = list(present)
    if mismatches:
        out["mismatched_modalities"] = mismatches
    return out


def _summarize_anndata(obj, *, include_search_parameters: bool = True) -> dict:
    summary = {
        "kind": "AnnData",
        "shape": (int(obj.n_obs), int(obj.n_vars)),
        "obs_columns": list(obj.obs.columns),
        "var_columns": list(obj.var.columns),
        "layers": list(obj.layers.keys()),
        "uns_keys": list(obj.uns.keys()),
        "x_stats": _matrix_stats(obj.X),
    }
    if include_search_parameters:
        summary["search_parameters"] = _search_parameters_summary(obj)
    return summary


def summarize(obj) -> dict:
    """Summary dict for an AnnData, or per-modality for a MuData. GUI-renderable."""
    if hasattr(obj, "mod"):  # MuData
        search_parameters = _mudata_search_parameters_summary(obj)
        return {
            "kind": "MuData",
            "n_obs": int(obj.n_obs),
            "uns_keys": list(obj.uns.keys()),
            "search_parameters": search_parameters,
            "modalities": {
                name: _summarize_anndata(ad, include_search_parameters=search_parameters is None)
                for name, ad in obj.mod.items()
            },
        }
    return _summarize_anndata(obj)
