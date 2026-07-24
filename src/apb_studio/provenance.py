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

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from apb_studio.pipeline import RunSnapshot, Target, load_run_snapshot


def apb_version(apb_exe: str | None = None) -> str | None:
    """Best-effort apb version: installed package metadata, else ``apb --version``, else None."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("anndata-proteomics")
        except PackageNotFoundError:
            pass
    except Exception:  # noqa: BLE001 - metadata lookup is best-effort
        pass
    exe = apb_exe or shutil.which("apb")
    if exe:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True)
            return out.stdout.strip() or None
        except (OSError, subprocess.CalledProcessError):
            return None
    return None


def record(
    target: Target,
    *,
    timestamp: str,
    version: str | None = None,
    warning: str | None = None,
    run: RunSnapshot | None = None,
) -> dict[str, Any]:
    """The provenance record for one Target (pure). The rendered command carries vendor/params.

    ``warning`` carries a problem apb reported while still producing the artifact — e.g.
    ``search_parameters_error`` when a param file could not be parsed (apb degrades rather than
    crashing). apb_studio surfaces it per dataset (``pipeline.problems`` → the basket ``problem``
    column) so a converted-but-degraded dataset is not shown as cleanly done.
    """
    rec: dict[str, Any] = {
        "stage": target.stage,
        "artifact": target.output.name,
        "command": list(target.command),
        "inputs": [str(p) for p in target.inputs],
        "apb_version": version,
        "timestamp": timestamp,
    }
    if warning:
        rec["warning"] = warning
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


def read_params_warning(output: Path) -> str | None:
    """Read APB's search-parameter warning from AnnData or any MuData modality.

    Returns a joined message, or None if absent, unreadable, or h5py is missing. Runs once per rule
    at build time, never on a dashboard refresh.
    """
    try:
        import h5py
    except Exception:  # noqa: BLE001 - h5py optional; degrade to "no warning"
        return None
    try:
        with h5py.File(output, "r") as f:
            names: list[str] = []
            f.visititems(
                lambda n, o: (
                    names.append(n)
                    if n.endswith("anndata_proteomics/search_parameters_error")
                    and isinstance(o, h5py.Dataset)
                    else None
                )
            )
            msgs = []
            for n in names:
                node = cast(h5py.Dataset, f[n])
                v = node[()]
                msgs.append(v.decode() if isinstance(v, (bytes, bytearray)) else str(v))
        uniq = list(dict.fromkeys(m for m in msgs if m))
        return "; ".join(uniq) or None
    except Exception:  # noqa: BLE001 - a malformed/locked artifact must not break provenance
        return None


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
    warning = read_params_warning(target.output) if target.output.exists() else None
    data = record(
        target,
        timestamp=timestamp or _now(),
        version=version,
        warning=warning,
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


def main(argv: list[str] | None = None) -> int:
    """Write provenance for the target produced by the Snakefile rule."""
    parser = argparse.ArgumentParser(prog="apb_studio.provenance")
    parser.add_argument("--run", required=True, help="generated Corpus Runner JSON")
    parser.add_argument("--output", required=True, help="the artifact path that was just produced")
    args = parser.parse_args(argv)

    run = load_run_snapshot(args.run)
    target_path = str(Path(args.output))
    target = next(
        (t for t in run.targets if str(t.output) == target_path),
        None,
    )
    if target is None:
        print(
            f"Refusing provenance for output outside this run: {target_path}",
            file=sys.stderr,
        )
        return 2
    if not target.output.is_file():
        print(
            f"Rule command completed without creating its artifact: {target.output}",
            file=sys.stderr,
        )
        return 1
    write_for_target(
        target,
        version=run.apb_version or apb_version(),
        run=run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
