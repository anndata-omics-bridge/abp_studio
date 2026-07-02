"""Drive the pipeline from the dashboard: turn a scope×stage selection into a Snakemake invocation
run as a background job, or a Clean that deletes the selected outputs.

Command rendering and target/path derivation live in `pipeline` (the single source of truth);
this module adds only the Snakemake-CLI + background-runner glue. No marimo import.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from apb_studio import provenance
from apb_studio.jobrunner import Job, start_job
from apb_studio.pipeline import (
    Target,
    coverage,
    expand_targets,
    load_corpus,
    load_registry,
    reject_input_paths,
    select_targets,
)


def load_overview(config_path: Path | str) -> tuple[list[Target], list[dict], dict, str | None]:
    """Load the corpus → (targets, coverage_rows, corpus, error). NEVER raises.

    A missing / malformed / old-schema config becomes a user-facing ``error`` message string (the
    dashboard renders it instead of crashing); on success ``error`` is None and corpus is the loaded
    dict. Defaults are empty so every caller/cell stays well-defined on failure.
    """
    try:
        corpus = load_corpus(config_path)
        targets = expand_targets(load_registry(), corpus)
        return targets, coverage(targets), corpus, None
    except FileNotFoundError:
        return [], [], {}, (
            f"Corpus config not found: `{config_path}`.\n\n"
            "Run `make scaffold` to generate `config/corpus.yaml`, or point the box above at an "
            "existing config file."
        )
    except Exception as exc:  # noqa: BLE001 - surface ANY config problem as a readable UI message
        return [], [], {}, (
            f"Could not load `{config_path}` — it looks invalid or from an older schema.\n\n"
            "Re-generate it with `make scaffold` (writes the current schema), then reload.\n\n"
            f"Details: {type(exc).__name__}: {exc}"
        )


def selected_outputs(
    targets: list[Target],
    *,
    scope: str = "all",
    module: str | None = None,
    dataset: str | None = None,
    stage: str = "all",
) -> list[Path]:
    """The output paths a (scope, stage) Run would (re)build."""
    return [
        t.output
        for t in select_targets(targets, scope=scope, module=module, dataset=dataset, stage=stage)
    ]


def snakemake_argv(
    snakefile: Path | str,
    config_path: Path | str,
    *,
    targets: list[Path] | None = None,
    dry_run: bool = False,
    cores: int = 1,
    snakemake_exe: str | None = None,
) -> list[str]:
    """Build a `snakemake` argv for the given targets (default goal when targets is empty/None)."""
    exe = snakemake_exe or shutil.which("snakemake") or "snakemake"
    argv = [exe, "-s", str(snakefile), "--configfile", str(config_path), "--cores", str(cores)]
    # --keep-going: a corpus is ~50 independent datasets; one bad one (e.g. an unparsable params
    # file) must not abort the whole run — the good datasets still build, failures show per dataset.
    argv.append("--keep-going")
    if dry_run:
        argv.append("-n")
    argv += [str(t) for t in (targets or [])]
    return argv


def run_pipeline(
    snakefile: Path | str,
    config_path: Path | str,
    log_file: Path | str,
    *,
    targets: list[Path] | None = None,
    cores: int = 1,
    snakemake_exe: str | None = None,
    cwd: Path | str | None = None,
    start=start_job,
) -> Job:
    """Launch Snakemake over `targets` as a background job; returns the Job (poll via inspect_job).

    `targets=None` means the default goal (build everything). An EMPTY list is refused: it would
    otherwise emit no target args and fall through to Snakemake's default goal — silently building
    the whole corpus when the caller meant "nothing is selected".
    """
    if targets is not None and len(targets) == 0:
        raise ValueError("no targets selected — refusing to launch (empty would build the whole corpus)")
    argv = snakemake_argv(
        snakefile, config_path, targets=targets, cores=cores, snakemake_exe=snakemake_exe
    )
    return start(argv, log_file, cwd=cwd)


def clean_targets(targets: list[Target], *, input_root: Path | str) -> list[Path]:
    """Delete an explicit set of Targets' outputs (guarded); returns the deleted paths.

    The row-set primitive the kanban baskets use: a basket Clean passes the Targets for the selected
    rows at that basket's defining stage (`pipeline.targets_for`). Guarded by `reject_input_paths`
    (raises before anything is deleted). Prunes each cleaned stage from its sibling ``provenance.json``
    so a sidecar never outlives its artifact.
    """
    reject_input_paths([t.output for t in targets], input_root)
    deleted = []
    for target in targets:
        if target.output.exists():
            if target.output.is_dir():
                shutil.rmtree(target.output)
            else:
                target.output.unlink()
            deleted.append(target.output)
        # Drop the per-rule log too, else a cleaned dataset (artifact gone, log lingering) would be
        # mis-flagged as "failed" by pipeline.problems. Missing → pending, as intended.
        log = Path(f"{target.output}.log")
        if log.exists():
            log.unlink()
        provenance.prune_for_target(target)
    return deleted


def clean_selection(
    targets: list[Target],
    *,
    input_root: Path | str,
    scope: str = "all",
    module: str | None = None,
    dataset: str | None = None,
    stage: str = "all",
) -> list[Path]:
    """Delete the outputs a (scope, stage) Clean selects; returns the deleted paths.

    Thin wrapper over `clean_targets` for the scope×stage selector (Snakefile/CLI callers). Both go
    through `reject_input_paths`, so neither can touch a path under `input_root`.
    """
    return clean_targets(
        select_targets(targets, scope=scope, module=module, dataset=dataset, stage=stage),
        input_root=input_root,
    )
