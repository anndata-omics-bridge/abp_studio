"""Per-artifact provenance sidecars (decision 17).

APB stores search parameters in the result's ``uns`` but writes no sidecar, so apb_studio writes
one adjacent ``<artifact>.provenance.json`` for every output artifact. Each sidecar records the
rendered command (which carries ``--software``/``--params``), inputs, APB version, and timestamp.
Artifact-specific filenames keep same-stage records from independent output branches distinct.

The **Snakefile** writes a sidecar right after each rule succeeds with
``python -m apb_studio.provenance --run <run.json> --output <artifact>``, whether the run was
started from the dashboard or the CLI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from cyclopts import App
from loguru import logger

from apb_studio.pipeline import RunSnapshot, Target, load_run_snapshot

app = App(
    name="apb_studio.provenance",
    help="Write the provenance sidecar for one artifact in a frozen APB Studio run.",
    help_on_error=True,
    result_action="return_value",
)


def apb_version(apb_exe: str | None = None) -> str | None:
    """Return installed APB metadata or the version reported by its executable."""
    try:
        return version("anndata-proteomics")
    except PackageNotFoundError:
        pass
    exe = apb_exe or shutil.which("apb")
    if exe is None:
        return None
    result = subprocess.run(
        [exe, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def record(
    target: Target,
    *,
    timestamp: str,
    version: str | None = None,
    run: RunSnapshot | None = None,
) -> dict[str, Any]:
    """The provenance record for one Target (pure). The rendered command carries vendor/params."""
    rec: dict[str, Any] = {
        "stage": target.stage,
        "artifact": target.output.name,
        "command": list(target.command),
        "inputs": [str(p) for p in target.inputs],
        "apb_version": version,
        "timestamp": timestamp,
    }
    if run is not None:
        fixture = next(
            (
                item
                for item in run.fixtures
                if item.repo_name == target.module and item.dataset == target.dataset
            ),
            None,
        )
        rec["run_id"] = run.run_id
        rec["registry_digest"] = run.registry_digest
        if fixture is not None:
            rec["fixture_identity"] = list(fixture.identity)
    return rec


def _now() -> str:
    return datetime.now(UTC).isoformat()


def sidecar_path(output: Path) -> Path:
    """Return the provenance sidecar adjacent to an output artifact."""
    return Path(f"{output}.provenance.json")


def _preserve_corrupt_sidecar(path: Path) -> None:
    """Back up an invalid existing sidecar before it is replaced."""
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        try:
            path.replace(path.with_suffix(".json.bak"))
        except OSError:
            pass


def write_for_target(
    target: Target,
    *,
    timestamp: str | None = None,
    version: str | None = None,
    run: RunSnapshot | None = None,
) -> Path:
    """Write the target's adjacent artifact-specific provenance and return its path."""
    path = sidecar_path(target.output)
    _preserve_corrupt_sidecar(path)
    data = record(
        target,
        timestamp=timestamp or _now(),
        version=version,
        run=run,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def prune_for_target(target: Target) -> None:
    """Remove provenance for a cleaned artifact without touching sibling branches."""
    path = sidecar_path(target.output)
    if path.exists():
        path.unlink()


@app.default
def write_provenance(
    *,
    run: Path,
    output: Path,
) -> int:
    """Write provenance for an artifact.

    Parameters
    ----------
    run
        Generated Corpus Runner JSON.
    output
        Artifact path that the completed rule produced.
    """
    snapshot = load_run_snapshot(run)
    target_path = str(output)
    target = next(
        (item for item in snapshot.targets if str(item.output) == target_path),
        None,
    )
    if target is None:
        logger.error(f"Refusing provenance for output outside this run: {target_path}")
        return 2
    if not target.output.is_file():
        logger.error(f"Rule command completed without creating its artifact: {target.output}")
        return 1
    write_for_target(
        target,
        version=snapshot.apb_version or apb_version(),
        run=snapshot,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the provenance command-line application."""
    result = app(argv)
    return int(result) if result is not None else 0


if __name__ == "__main__":
    sys.exit(main())
