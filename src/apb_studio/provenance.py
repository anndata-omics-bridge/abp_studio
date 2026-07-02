"""Per-artifact provenance sidecars (decision 17) — apb stores search parameters in the result's
``uns`` but writes no sidecar, so apb_studio writes one.

``provenance.json`` sits in each dataset's output dir, keyed by stage, recording the rendered
command (which carries ``--software``/``--params``), the inputs, the apb version, and a timestamp.
It is written by the **Snakefile** right after each rule succeeds (``python -m apb_studio.provenance
--config <corpus> --output <artifact>``), so every artifact gets a sidecar regardless of whether the
run was driven by the dashboard or the CLI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from apb_studio.pipeline import Target, expand_targets, load_corpus, load_registry


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
    target: Target, *, timestamp: str, version: str | None = None, warning: str | None = None
) -> dict:
    """The provenance record for one Target (pure). The rendered command carries vendor/params.

    ``warning`` carries a problem apb reported while still producing the artifact — e.g.
    ``search_parameters_error`` when a param file could not be parsed (apb degrades rather than
    crashing). apb_studio surfaces it per dataset (``pipeline.problems`` → the basket ``problem``
    column) so a converted-but-degraded dataset is not shown as cleanly done.
    """
    rec = {
        "stage": target.stage,
        "artifact": target.output.name,
        "command": list(target.command),
        "inputs": [str(p) for p in target.inputs],
        "apb_version": version,
        "timestamp": timestamp,
    }
    if warning:
        rec["warning"] = warning
    return rec


def read_params_warning(output: Path) -> str | None:
    """Best-effort: read apb's ``uns['anndata_proteomics']['search_parameters_error']`` from the
    artifact (AnnData root uns *or* any MuData modality). Returns a joined message, or None if absent
    / unreadable / h5py missing. Runs once per rule (build time), never on a dashboard refresh."""
    try:
        import h5py
    except Exception:  # noqa: BLE001 - h5py optional; degrade to "no warning"
        return None
    try:
        with h5py.File(output, "r") as f:
            names: list[str] = []
            f.visititems(
                lambda n, o: names.append(n)
                if n.endswith("anndata_proteomics/search_parameters_error")
                and isinstance(o, h5py.Dataset)
                else None
            )
            msgs = []
            for n in names:
                v = f[n][()]
                msgs.append(v.decode() if isinstance(v, (bytes, bytearray)) else str(v))
        uniq = list(dict.fromkeys(m for m in msgs if m))
        return "; ".join(uniq) or None
    except Exception:  # noqa: BLE001 - a malformed/locked artifact must not break provenance
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_sidecar(path: Path) -> dict:
    """Read an existing provenance.json into a dict; tolerate corrupt/odd-shaped files (start fresh
    but back the bad file up so prior history is not silently lost)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        try:
            path.replace(path.with_suffix(".json.bak"))
        except OSError:
            pass
        return {}
    return data


def write_for_target(
    target: Target, *, timestamp: str | None = None, version: str | None = None
) -> Path:
    """Write/merge ``provenance.json`` next to the target's output, keyed by stage. Returns the path."""
    path = target.output.parent / "provenance.json"
    data = _load_sidecar(path)
    warning = read_params_warning(target.output) if target.output.exists() else None
    data[target.stage] = record(
        target, timestamp=timestamp or _now(), version=version, warning=warning
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def prune_for_target(target: Target) -> None:
    """Drop a stage's entry from its sibling ``provenance.json`` (called when its artifact is cleaned),
    so the sidecar never outlives the artifact it documents. Removes the file once empty."""
    path = target.output.parent / "provenance.json"
    if not path.exists():
        return
    data = _load_sidecar(path)
    data.pop(target.stage, None)
    if data:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        path.unlink()


def main(argv: list[str] | None = None) -> int:
    """CLI used by the Snakefile post-rule: write provenance for the target that produced --output."""
    parser = argparse.ArgumentParser(prog="apb_studio.provenance")
    parser.add_argument("--config", required=True, help="corpus config YAML")
    parser.add_argument("--output", required=True, help="the artifact path that was just produced")
    args = parser.parse_args(argv)

    corpus = load_corpus(args.config)
    target_path = str(Path(args.output))
    target = next(
        (t for t in expand_targets(load_registry(), corpus) if str(t.output) == target_path), None
    )
    if target is None:  # output not in the corpus → nothing to record
        return 0
    write_for_target(target, version=apb_version())
    return 0


if __name__ == "__main__":
    sys.exit(main())
