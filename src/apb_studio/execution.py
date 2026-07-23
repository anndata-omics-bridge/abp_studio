"""Drive the pipeline from the dashboard: turn a scope×stage selection into a Snakemake invocation
run as a background job, or a Clean that deletes the selected outputs.

Command rendering and target/path derivation live in `pipeline` (the single source of truth);
this module adds only the Snakemake-CLI + background-runner glue.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from anndata_proteomics.converters import pipeline as conversion_pipeline
from anndata_proteomics.proteobench.config import (
    load_module_settings,
    load_tool_settings,
)
from anndata_proteomics.test_data import find_proteobench_tool_settings

from apb_studio import capabilities, provenance
from apb_studio.disk import atomic_write_text
from apb_studio.fixture_inventory import FixtureRecord, load_fixture_inventory
from apb_studio.jobrunner import Job, JobStatus, inspect_job, start_job
from apb_studio.module_resources import load_module_resources
from apb_studio.pipeline import (
    RUN_SNAPSHOT_SCHEMA_VERSION,
    ResolvedFixture,
    RunSnapshot,
    Target,
    coverage,
    expand_resolved_targets,
    failure_marker_path,
    load_run_snapshot,
    load_registry,
    reject_input_paths,
    runnable_targets,
    select_targets,
    write_run_snapshot,
)
from apb_studio.settings import load_settings

STUDIO_ROOT = Path(__file__).resolve().parents[2]
SNAKEFILE = STUDIO_ROOT / "workflow" / "Snakefile"
_JOBS: dict[str, Job] = {}
_RUNS: dict[str, Path] = {}
_ALIAS_SCHEMA_VERSION = 1


def load_overview(
    job_id: str | None = None,
    *,
    settings_path: Path | None = None,
    discover: Callable[
        [Path, Path, str], capabilities.CapabilityDiscovery
    ] = capabilities.discover_capabilities,
) -> tuple[list[Target], list[dict], RunSnapshot | None, str | None]:
    """Load the pinned active run or resolve the current Fixture Manager inventory.

    The function never raises across the dashboard boundary. A known job pins its snapshot only
    while running; after it finishes, newly downloaded fixtures enter the next overview.
    """
    try:
        snapshot = _running_snapshot(job_id)
        if snapshot is None:
            snapshot = resolve_current_run(
                settings_path=settings_path,
                discover=discover,
            )
        targets = list(snapshot.targets)
        return targets, coverage(targets), snapshot, None
    except Exception as exc:  # noqa: BLE001 - callback boundary must remain readable
        return (
            [],
            [],
            None,
            (
                "Could not resolve the Fixture Manager inventory and Corpus Runner settings.\n\n"
                f"Details: {type(exc).__name__}: {exc}"
            ),
        )


def resolve_current_run(
    *,
    run_id: str = "",
    settings_path: Path | None = None,
    persist_aliases: bool = False,
    discover: Callable[
        [Path, Path, str], capabilities.CapabilityDiscovery
    ] = capabilities.discover_capabilities,
) -> RunSnapshot:
    """Resolve every complete local fixture into one frozen in-memory run."""
    settings = load_settings(settings_path)
    inventory = load_fixture_inventory(settings.test_data_root)
    resources = load_module_resources(settings.test_data_root)
    discoveries = [
        (fixture, _discover_fixture(fixture, discover))
        for fixture in inventory.complete_local
    ]
    aliases = resolve_output_aliases(
        discoveries,
        settings.output_root,
        persist=persist_aliases,
    )
    fixtures = []
    for fixture, discovery in discoveries:
        input_path = fixture.input_path
        parameter_path = fixture.parameter_path
        if input_path is None or parameter_path is None:
            raise ValueError(
                f"Complete fixture {fixture.identity!r} has no unique input and parameter."
            )
        resource = resources.for_module(fixture.module)
        annotation_path = resource.annotation_path if resource is not None else None
        module_settings_error = (
            resource.annotation_error if resource is not None else None
        )
        proteobench_level = None
        if annotation_path is not None and module_settings_error is None:
            try:
                proteobench_level = load_module_settings(
                    annotation_path
                ).general.level
            except Exception as error:  # noqa: BLE001 - frozen as a BLOCKED diagnostic
                module_settings_error = (
                    f"Invalid ProteoBench module settings {annotation_path}: "
                    f"{type(error).__name__}: {error}"
                )
        tool_settings_path = find_proteobench_tool_settings(
            module=fixture.module,
            vendor=(
                discovery.software_slug
                or conversion_pipeline.software_slug(fixture.catalog_software_name)
            ),
            test_data_dir=settings.test_data_root,
        )
        tool_settings_error = None
        if tool_settings_path is not None:
            try:
                load_tool_settings(tool_settings_path)
            except Exception as error:  # noqa: BLE001 - frozen as a BLOCKED diagnostic
                tool_settings_error = (
                    f"Invalid ProteoBench tool settings {tool_settings_path}: "
                    f"{type(error).__name__}: {error}"
                )
        fixtures.append(
            ResolvedFixture(
                module=fixture.module,
                repo_name=fixture.repo_name,
                intermediate_hash=fixture.intermediate_hash,
                dataset=aliases[fixture.identity],
                software=fixture.catalog_software_name,
                vendor=(
                    discovery.software_slug
                    or conversion_pipeline.software_slug(fixture.catalog_software_name)
                ),
                input_path=input_path,
                parameter_path=parameter_path,
                branches=tuple(discovery.branches),
                capability_status=discovery.status.value,
                diagnostic=discovery.diagnostic,
                annotation_path=annotation_path,
                fasta_path=resource.fasta_path if resource is not None else None,
                annotation_error=(
                    resource.annotation_error if resource is not None else None
                ),
                fasta_error=resource.fasta_error if resource is not None else None,
                tool_settings_path=tool_settings_path,
                module_settings_error=module_settings_error,
                tool_settings_error=tool_settings_error,
                proteobench_level=proteobench_level,
            )
        )
    registry = load_registry()
    resolved = tuple(fixtures)
    return RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        test_data_root=settings.test_data_root,
        output_root=settings.output_root,
        registry_digest=_registry_digest(registry),
        apb_version=provenance.apb_version(),
        fixtures=resolved,
        targets=tuple(
            expand_resolved_targets(registry, resolved, settings.output_root)
        ),
    )


def _discover_fixture(
    fixture: FixtureRecord,
    discover: Callable[[Path, Path, str], capabilities.CapabilityDiscovery],
) -> capabilities.CapabilityDiscovery:
    """Run structured APB capability discovery for one complete fixture."""
    input_path = fixture.input_path
    parameter_path = fixture.parameter_path
    if input_path is None or parameter_path is None:
        raise ValueError(f"Fixture is not complete: {fixture.identity!r}")
    return discover(
        input_path,
        parameter_path,
        fixture.catalog_software_name,
    )


def _registry_digest(registry: list[dict]) -> str:
    """Return a stable digest of the stage registry used to render commands."""
    source = json.dumps(registry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def output_alias_path(output_root: Path | str) -> Path:
    """Return the persistent fixture-to-output-alias map."""
    return Path(output_root) / ".apb_studio" / "output_aliases.json"


def resolve_output_aliases(
    discoveries: list[tuple[FixtureRecord, capabilities.CapabilityDiscovery]],
    output_root: Path | str,
    *,
    persist: bool,
) -> dict[tuple[str, str, str], str]:
    """Resolve stable aliases, seeding existing output directories by hash suffix."""
    root = Path(output_root)
    stored = _load_output_aliases(root)
    resolved = dict(stored)
    used = {(identity[1], alias): identity for identity, alias in resolved.items()}

    for fixture, discovery in discoveries:
        identity = fixture.identity
        alias = resolved.get(identity)
        if alias is not None:
            _validate_alias(alias)
            continue
        vendor = discovery.software_slug or conversion_pipeline.software_slug(
            fixture.catalog_software_name
        )
        alias = _existing_output_alias(root, fixture)
        if alias is None or used.get((fixture.repo_name, alias), identity) != identity:
            alias = _available_output_alias(
                vendor,
                fixture.intermediate_hash,
                fixture.repo_name,
                used,
                identity,
            )
        _validate_alias(alias)
        resolved[identity] = alias
        used[(fixture.repo_name, alias)] = identity

    if persist and resolved != stored:
        _save_output_aliases(root, resolved)
    return {fixture.identity: resolved[fixture.identity] for fixture, _ in discoveries}


def _existing_output_alias(
    output_root: Path,
    fixture: FixtureRecord,
) -> str | None:
    """Find the unique pre-migration output directory for one fixture hash."""
    module_root = output_root / fixture.repo_name
    if not module_root.is_dir():
        return None
    suffix = f"-{fixture.intermediate_hash[:8]}"
    matches = sorted(
        path.name
        for path in module_root.iterdir()
        if path.is_dir() and path.name.endswith(suffix)
    )
    return matches[0] if len(matches) == 1 else None


def _available_output_alias(
    vendor: str,
    intermediate_hash: str,
    repo_name: str,
    used: dict[tuple[str, str], tuple[str, str, str]],
    identity: tuple[str, str, str],
) -> str:
    """Return a deterministic alias, extending the hash only on collision."""
    widths = [*range(8, len(intermediate_hash), 4), len(intermediate_hash)]
    for width in dict.fromkeys(widths):
        alias = f"{vendor}-{intermediate_hash[:width]}"
        owner = used.get((repo_name, alias))
        if owner is None or owner == identity:
            return alias

    identity_digest = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()
    base = f"{vendor}-{intermediate_hash}"
    for width in range(8, len(identity_digest) + 1, 4):
        alias = f"{base}-{identity_digest[:width]}"
        owner = used.get((repo_name, alias))
        if owner is None or owner == identity:
            return alias
    raise ValueError(f"Could not allocate a unique output alias for {identity!r}.")


def _validate_alias(alias: str) -> None:
    """Reject aliases that could escape their repository output directory."""
    if not alias or alias in {".", ".."} or Path(alias).name != alias:
        raise ValueError(f"Invalid output alias: {alias!r}")


def _load_output_aliases(
    output_root: Path,
) -> dict[tuple[str, str, str], str]:
    """Load the app-owned alias map, returning an empty map before first launch."""
    path = output_alias_path(output_root)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != _ALIAS_SCHEMA_VERSION
    ):
        raise ValueError(f"Unsupported output alias map: {path}")
    aliases: dict[tuple[str, str, str], str] = {}
    owners: dict[tuple[str, str], tuple[str, str, str]] = {}
    for item in data.get("aliases", []):
        identity = (
            str(item["module"]),
            str(item["repo_name"]),
            str(item["intermediate_hash"]),
        )
        alias = str(item["output_alias"])
        _validate_alias(alias)
        if identity in aliases:
            raise ValueError(
                f"Duplicate fixture identity in output alias map: {identity!r}"
            )
        alias_key = (identity[1], alias)
        owner = owners.get(alias_key)
        if owner is not None and owner != identity:
            raise ValueError(
                f"Output alias {alias!r} for repository {identity[1]!r} "
                f"is assigned to both {owner!r} and {identity!r}."
            )
        aliases[identity] = alias
        owners[alias_key] = identity
    return aliases


def _save_output_aliases(
    output_root: Path,
    aliases: dict[tuple[str, str, str], str],
) -> None:
    """Atomically save all known fixture aliases without dropping old fixtures."""
    rows = [
        {
            "module": identity[0],
            "repo_name": identity[1],
            "intermediate_hash": identity[2],
            "output_alias": alias,
        }
        for identity, alias in sorted(aliases.items())
    ]
    data = {"schema_version": _ALIAS_SCHEMA_VERSION, "aliases": rows}
    source = json.dumps(data, indent=2, sort_keys=True)
    atomic_write_text(output_alias_path(output_root), f"{source}\n")


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
        for t in select_targets(
            targets, scope=scope, module=module, dataset=dataset, stage=stage
        )
    ]


def snakemake_argv(
    snakefile: Path | str,
    run_path: Path | str,
    *,
    targets: list[Path] | None = None,
    dry_run: bool = False,
    cores: int = 1,
    snakemake_exe: str | None = None,
) -> list[str]:
    """Build a Snakemake argv consuming one generated run JSON."""
    local_executable = STUDIO_ROOT / ".venv" / "bin" / "snakemake"
    exe = (
        snakemake_exe
        or (str(local_executable) if local_executable.exists() else None)
        or shutil.which("snakemake")
        or "snakemake"
    )
    argv = [
        exe,
        "-s",
        str(snakefile),
        "--configfile",
        str(run_path),
        "--cores",
        str(cores),
    ]
    # --keep-going: a corpus is ~50 independent datasets; one bad one (e.g. an unparsable params
    # file) must not abort the whole run — the good datasets still build, failures show per dataset.
    argv.append("--keep-going")
    if dry_run:
        argv.append("-n")
    argv += [str(t) for t in (targets or [])]
    return argv


def run_pipeline(
    snakefile: Path | str,
    run_path: Path | str,
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
        raise ValueError(
            "no targets selected — refusing to launch (empty would build the whole corpus)"
        )
    argv = snakemake_argv(
        snakefile,
        run_path,
        targets=targets,
        cores=cores,
        snakemake_exe=snakemake_exe,
    )
    return start(argv, log_file, cwd=cwd)


def run_snapshot_path(snapshot: RunSnapshot) -> Path:
    """Return the canonical path of a launched run snapshot."""
    if not snapshot.run_id:
        raise ValueError("A preview without a run id has no run snapshot path.")
    return snapshot.output_root / ".apb_studio" / "runs" / snapshot.run_id / "run.json"


def corpus_log_path(
    snapshot: RunSnapshot | None = None,
    *,
    job_id: str | None = None,
) -> Path:
    """Return one run's Snakemake log, preferring its job-to-snapshot mapping."""
    job_id = job_id or active_corpus_job_id()
    if job_id is not None and job_id in _RUNS:
        return _RUNS[job_id].parent / "snakemake.log"
    if snapshot is not None and snapshot.run_id:
        return run_snapshot_path(snapshot).parent / "snakemake.log"
    if snapshot is None:
        output_root = load_settings().output_root
    else:
        output_root = snapshot.output_root
    return output_root / ".apb_studio" / "snakemake.log"


def prepare_run(
    *,
    settings_path: Path | None = None,
    discover: Callable[
        [Path, Path, str], capabilities.CapabilityDiscovery
    ] = capabilities.discover_capabilities,
) -> tuple[RunSnapshot, Path, list[Target]]:
    """Freeze the current inventory and return its generated JSON and runnable targets."""
    snapshot = resolve_current_run(
        run_id=uuid.uuid4().hex,
        settings_path=settings_path,
        persist_aliases=True,
        discover=discover,
    )
    selected = runnable_targets(list(snapshot.targets))
    if not selected:
        raise ValueError("Corpus has no runnable stages.")
    path = write_run_snapshot(snapshot, run_snapshot_path(snapshot))
    return snapshot, path, selected


def launch_corpus(
    *,
    cores: int = 3,
    settings_path: Path | None = None,
) -> str:
    """Freeze and launch every currently runnable corpus stage."""
    if any(inspect_job(job).running for job in _JOBS.values()):
        raise RuntimeError("A corpus run is already active.")
    snapshot, path, selected = prepare_run(settings_path=settings_path)
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = run_pipeline(
        SNAKEFILE,
        path,
        corpus_log_path(snapshot),
        targets=[target.output for target in selected],
        cores=cores,
        cwd=STUDIO_ROOT,
    )
    _RUNS[job_id] = path
    return job_id


def _running_snapshot(job_id: str | None) -> RunSnapshot | None:
    """Load the requested or server-active snapshot while its process is running."""
    active_id = active_corpus_job_id()
    candidates = tuple(dict.fromkeys(item for item in (job_id, active_id) if item))
    for candidate in candidates:
        if candidate not in _JOBS or candidate not in _RUNS:
            continue
        if inspect_job(_JOBS[candidate]).running:
            return load_run_snapshot(_RUNS[candidate])
    return None


def active_corpus_job_id() -> str | None:
    """Return the server-owned running corpus job, independent of browser state."""
    for job_id, job in reversed(tuple(_JOBS.items())):
        if inspect_job(job).running:
            return job_id
    return None


def inspect_corpus_job(job_id: str | None) -> JobStatus | None:
    """Return the current corpus-job snapshot, or ``None`` for an unknown id."""
    job_id = job_id or active_corpus_job_id()
    if not job_id or job_id not in _JOBS:
        return None
    return inspect_job(_JOBS[job_id])


def corpus_job_running(job_id: str | None) -> bool:
    """Return whether a known corpus job is still active."""
    status = inspect_corpus_job(job_id)
    return status is not None and status.running


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
        failure_marker = failure_marker_path(target.output)
        if failure_marker.exists():
            failure_marker.unlink()
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
        select_targets(
            targets, scope=scope, module=module, dataset=dataset, stage=stage
        ),
        input_root=input_root,
    )
