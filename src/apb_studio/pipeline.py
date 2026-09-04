"""Registry-driven target expansion and corpus progress state.

APB2's parsing-rule JSONs decide which conversion branches an input supports. This module expands
each discovered branch through the registry's stage DAG, producing the concrete paths and commands
shared by Snakemake and the dashboard.
"""

from __future__ import annotations

import csv
import json
import math
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apb2.parserV2.vendor_parse_rules.schema.base import LEVELS as APB2_LEVELS

from apb_studio.registry import (
    DEFAULT_PIPELINE,
    PipelineDocument,
    load_pipeline_document,
    load_registry,
)

MUDATA = "mudata"
MUDATA_LABEL = "MuData"
"""How the MuData container is labelled in the Level column; it is not a quantification level."""
LEVELS = tuple(APB2_LEVELS)

APB2 = "apb2"
CONVERTERS = (APB2,)
"""APB2 is the only converter used by new Corpus Runner snapshots."""

BRANCHES = (MUDATA, *LEVELS)
"""The APB2 MuData container and standalone quantification levels."""


@dataclass(frozen=True, slots=True)
class Pipeline:
    """One named selection from the stage catalogue: which converters, which stages.

    Resolved, not declarative: ``stages`` holds the catalogue entries themselves, in topological
    order, so a pipeline is self-contained and a persisted run needs no second lookup to know what
    it ran.
    """

    name: str
    description: str
    converters: tuple[str, ...]
    stages: tuple[dict[str, Any], ...]

    @property
    def stage_names(self) -> tuple[str, ...]:
        """The selected stage names, in the order they run."""
        return tuple(str(stage["name"]) for stage in self.stages)

    def column_suffix(self, converter: str) -> str:
        """What one converter appends to a stage's column key within this run.

        The suffix exists to separate two chains sharing a grid row, so the first converter needs
        none. A run with a single converter has nothing to disambiguate, and a ``Converted2``
        column with no ``Converted`` beside it would be noise.
        """
        index = self.converters.index(converter)
        return "" if index == 0 else str(index + 1)

    def column(self, stage_name: str, converter: str) -> str:
        """The row/column key one stage occupies for one converter."""
        return f"{stage_name}{self.column_suffix(converter)}"

    @property
    def columns(self) -> tuple[str, ...]:
        """Every stage column, one converter's whole chain before the next one's."""
        return tuple(
            self.column(name, converter)
            for converter in self.converters
            for name in self.stage_names
        )


def load_pipeline(name: str = DEFAULT_PIPELINE) -> Pipeline:
    """Resolve one named pipeline against the packaged stage catalogue."""
    return resolve_pipeline(load_pipeline_document(name), load_registry())


def resolve_pipeline(document: PipelineDocument, registry: list[dict[str, Any]]) -> Pipeline:
    """Bind a pipeline document to catalogue entries, rejecting anything it cannot name."""
    unknown_converters = [name for name in document.converters if name not in CONVERTERS]
    if unknown_converters:
        raise ValueError(
            f"Pipeline {document.name!r} names unknown converter(s) {unknown_converters}; "
            f"known converters are: {', '.join(CONVERTERS)}"
        )
    if not document.converters:
        raise ValueError(f"Pipeline {document.name!r} selects no converter.")
    catalogue = {str(stage["name"]): stage for stage in registry}
    unknown_stages = [name for name in document.stages if name not in catalogue]
    if unknown_stages:
        raise ValueError(
            f"Pipeline {document.name!r} names unknown stage(s) {unknown_stages}; "
            f"the catalogue declares: {', '.join(catalogue)}"
        )
    if not document.stages:
        raise ValueError(f"Pipeline {document.name!r} selects no stage.")
    selected = set(document.stages)
    # A selection must be closed under `depends_on`. A stage reads its parent's artifact, so
    # dropping the parent is not a shortcut. Refusing here reports an invalid workflow before
    # any command runs.
    for name in document.stages:
        missing = [dep for dep in (catalogue[name].get("depends_on") or []) if dep not in selected]
        if missing:
            raise ValueError(
                f"Pipeline {document.name!r} selects stage {name!r} without its "
                f"dependencies {missing}; a stage reads its parent's artifact."
            )
    # Catalogue order, not document order: `depends_on` decides what runs before what, and a
    # pipeline that lists its stages out of order is a preference, not a topology.
    return Pipeline(
        name=document.name,
        description=document.description,
        converters=tuple(document.converters),
        stages=tuple(catalogue[name] for name in stage_order(registry) if name in selected),
    )


# Wildcard-constraint regexes the Snakefile uses to route one `{artifact}` wildcard to the right
# stage rule (the four are disjoint, so there is no ambiguity).
_LEVEL_RE = "|".join(LEVELS)
_BRANCH_RE = rf"(?:{_LEVEL_RE})"
CONVERT_ARTIFACT_RE = rf"{MUDATA}\.h5mu|{_BRANCH_RE}\.h5ad"
FASTA_ARTIFACT_RE = rf"{MUDATA}\.fasta\.h5mu|{_BRANCH_RE}\.fasta\.h5ad"
AGGREGATE_ARTIFACT_RE = rf"{MUDATA}\.aggregate-(?:ion|fragment)\.h5mu"
PROTEOBENCH_ARTIFACT_RE = rf"{MUDATA}\.proteobench\.h5mu|{_BRANCH_RE}\.proteobench\.h5ad"
RAW_PROTEOBENCH_ARTIFACT_RE = rf"{MUDATA}\.raw-proteobench\.h5mu"

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class CleanGuardError(Exception):
    """Raised when a Clean would delete a path under `input_root` — never an input (§8.3)."""


class UnsupportedSnapshotSchema(ValueError):
    """Raised for a snapshot written by another schema version.

    Distinct from a malformed snapshot: an output root accumulates runs across schema versions, so
    reading one written before the current schema is ordinary history and not a fault to report.
    """


@dataclass(frozen=True)
class Target:
    """One ``(module, dataset, branch, stage)`` unit of work."""

    module: str
    dataset: str
    stage: str  # registry stage name
    output: Path  # absolute, under output_root
    command: list[str]  # fully-rendered argv (ready for shell / preview)
    inputs: list[Path] = field(default_factory=list)
    vendor: str = ""
    level: str | None = None
    branch: str = MUDATA
    blocked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedFixture:
    """One complete local fixture resolved against APB2's parsing rules."""

    module: str
    repo_name: str
    intermediate_hash: str
    dataset: str
    software: str
    vendor: str
    input_path: Path
    parameter_path: Path
    branches: tuple[str, ...]
    capability_status: str
    diagnostic: str | None = None
    annotation_path: Path | None = None
    fasta_path: Path | None = None
    annotation_error: str | None = None
    fasta_error: str | None = None
    module_settings_error: str | None = None
    parameter_vendor: str = ""

    @property
    def identity(self) -> tuple[str, str, str]:
        """Return the stable fixture identity used by the output-alias store."""
        return self.module, self.repo_name, self.intermediate_hash


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """Immutable execution input generated by Corpus Runner for one launch."""

    schema_version: int
    run_id: str
    created_at: str
    test_data_root: Path
    output_root: Path
    registry_digest: str
    apb_version: str | None
    pipeline: Pipeline
    fixtures: tuple[ResolvedFixture, ...]
    targets: tuple[Target, ...]


RUN_SNAPSHOT_SCHEMA_VERSION = 2


def run_snapshot_data(snapshot: RunSnapshot) -> dict[str, Any]:
    """Return the JSON-compatible representation of one generated run."""
    return {
        "schema_version": snapshot.schema_version,
        "run_id": snapshot.run_id,
        "created_at": snapshot.created_at,
        "test_data_root": str(snapshot.test_data_root),
        "output_root": str(snapshot.output_root),
        "registry_digest": snapshot.registry_digest,
        "apb_version": snapshot.apb_version,
        # The resolved stages travel with the run, so a persisted snapshot renders its own
        # columns and runs its own stages without consulting the packaged catalogue again.
        "pipeline": {
            "name": snapshot.pipeline.name,
            "description": snapshot.pipeline.description,
            "converters": list(snapshot.pipeline.converters),
            "stages": [dict(stage) for stage in snapshot.pipeline.stages],
        },
        "fixtures": [
            {
                "module": fixture.module,
                "repo_name": fixture.repo_name,
                "intermediate_hash": fixture.intermediate_hash,
                "dataset": fixture.dataset,
                "software": fixture.software,
                "vendor": fixture.vendor,
                "parameter_vendor": fixture.parameter_vendor,
                "input_path": str(fixture.input_path),
                "parameter_path": str(fixture.parameter_path),
                "branches": list(fixture.branches),
                "capability_status": fixture.capability_status,
                "diagnostic": fixture.diagnostic,
                "annotation_path": (
                    str(fixture.annotation_path) if fixture.annotation_path is not None else None
                ),
                "fasta_path": (str(fixture.fasta_path) if fixture.fasta_path is not None else None),
                "annotation_error": fixture.annotation_error,
                "fasta_error": fixture.fasta_error,
                "module_settings_error": fixture.module_settings_error,
            }
            for fixture in snapshot.fixtures
        ],
        "targets": [
            {
                "module": target.module,
                "dataset": target.dataset,
                "stage": target.stage,
                "output": str(target.output),
                "command": list(target.command),
                "inputs": [str(path) for path in target.inputs],
                "vendor": target.vendor,
                "level": target.level,
                "branch": target.branch,
                "blocked_reason": target.blocked_reason,
            }
            for target in snapshot.targets
        ],
    }


def run_snapshot_from_data(data: dict[str, Any]) -> RunSnapshot:
    """Validate and decode a generated run JSON object."""
    version = data.get("schema_version")
    if version != RUN_SNAPSHOT_SCHEMA_VERSION:
        raise UnsupportedSnapshotSchema(
            "Unsupported run snapshot schema version "
            f"{version!r}; expected {RUN_SNAPSHOT_SCHEMA_VERSION}."
        )
    pipeline_data = data["pipeline"]
    pipeline = Pipeline(
        name=str(pipeline_data["name"]),
        description=str(pipeline_data["description"]),
        converters=tuple(str(name) for name in pipeline_data["converters"]),
        stages=tuple(dict(stage) for stage in pipeline_data["stages"]),
    )
    fixtures = tuple(
        ResolvedFixture(
            module=str(item["module"]),
            repo_name=str(item["repo_name"]),
            intermediate_hash=str(item["intermediate_hash"]),
            dataset=str(item["dataset"]),
            software=str(item["software"]),
            vendor=str(item["vendor"]),
            input_path=Path(item["input_path"]),
            parameter_path=Path(item["parameter_path"]),
            branches=tuple(str(branch) for branch in item.get("branches", [])),
            capability_status=str(item["capability_status"]),
            diagnostic=(str(item["diagnostic"]) if item.get("diagnostic") is not None else None),
            annotation_path=(
                Path(item["annotation_path"]) if item.get("annotation_path") is not None else None
            ),
            fasta_path=(Path(item["fasta_path"]) if item.get("fasta_path") is not None else None),
            annotation_error=(
                str(item["annotation_error"]) if item.get("annotation_error") is not None else None
            ),
            fasta_error=(str(item["fasta_error"]) if item.get("fasta_error") is not None else None),
            module_settings_error=(
                str(item["module_settings_error"])
                if item.get("module_settings_error") is not None
                else None
            ),
            parameter_vendor=str(item.get("parameter_vendor", item["vendor"])),
        )
        for item in data.get("fixtures", [])
    )
    targets = tuple(
        Target(
            module=str(item["module"]),
            dataset=str(item["dataset"]),
            stage=str(item["stage"]),
            output=Path(item["output"]),
            command=[str(token) for token in item.get("command", [])],
            inputs=[Path(path) for path in item.get("inputs", [])],
            vendor=str(item.get("vendor", "")),
            level=str(item["level"]) if item.get("level") is not None else None,
            branch=str(item.get("branch", MUDATA)),
            blocked_reason=(
                str(item["blocked_reason"]) if item.get("blocked_reason") is not None else None
            ),
        )
        for item in data.get("targets", [])
    )
    snapshot = RunSnapshot(
        schema_version=RUN_SNAPSHOT_SCHEMA_VERSION,
        run_id=str(data["run_id"]),
        created_at=str(data["created_at"]),
        test_data_root=Path(data["test_data_root"]),
        output_root=Path(data["output_root"]),
        registry_digest=str(data["registry_digest"]),
        apb_version=(str(data["apb_version"]) if data.get("apb_version") is not None else None),
        pipeline=pipeline,
        fixtures=fixtures,
        targets=targets,
    )
    _validate_snapshot_paths(snapshot)
    return snapshot


def _validate_snapshot_paths(snapshot: RunSnapshot) -> None:
    """Reject malformed snapshots whose outputs escape the frozen output root."""
    output_root = snapshot.output_root.resolve()
    for target in snapshot.targets:
        output = target.output.resolve()
        if output_root != output and output_root not in output.parents:
            raise ValueError(
                f"Run target {target.output} is outside output root {snapshot.output_root}."
            )


def write_run_snapshot(snapshot: RunSnapshot, path: Path) -> Path:
    """Create one run JSON exactly once and return its path."""
    destination = path
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(run_snapshot_data(snapshot), stream, indent=2)
        stream.write("\n")
    return destination


def load_run_snapshot(path: Path) -> RunSnapshot:
    """Load and validate a Corpus Runner-generated run JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Run snapshot must contain one JSON object.")
    return run_snapshot_from_data(data)


def apb2_branch(level: str) -> str:
    """Return the APB2 branch name for one level or the MuData container."""
    return level


def branch_converter(branch: str) -> str:
    """Return the sole converter for a supported branch."""
    if branch not in BRANCHES:
        raise ValueError(f"unknown conversion branch {branch!r}; expected one of {BRANCHES}")
    return APB2


def branch_level(branch: str) -> str | None:
    """The quantification level one branch converts, or ``None`` for the MuData container."""
    if branch == MUDATA:
        return None
    return branch


def command_template(stage: dict[str, Any], converter: str) -> str:
    """Return one stage command, including compatibility with older snapshot catalogues."""
    commands = stage.get("commands")
    if commands is None:
        return str(stage["command"])
    if converter not in commands:
        raise KeyError(f"stage {stage['name']!r} declares no command for converter {converter!r}")
    return str(commands[converter])


def convert_artifact(branch: str) -> str:
    """Return the converted artifact name for a discovered branch."""
    if branch not in BRANCHES:
        raise ValueError(f"unknown conversion branch {branch!r}; expected one of {BRANCHES}")
    return f"{branch}{convert_suffix(branch)}"


def convert_suffix(branch: str) -> str:
    """Return ``.h5mu`` for MuData and ``.h5ad`` for standalone levels."""
    return ".h5mu" if branch_level(branch) is None else ".h5ad"


def stage_artifact(stage: dict[str, Any], branch: str) -> str:
    """Return the branch-qualified artifact name produced by one stage."""
    if not stage.get("depends_on") and "artifact" not in stage:
        return convert_artifact(branch)
    return f"{branch}.{stage['artifact']}{convert_suffix(branch)}"


def render_command(template: str, ctx: dict[str, Any]) -> list[str]:
    """Substitute `{placeholder}`s in a registry command template → an argv list.

    Plain per-token substitution (so a value with spaces stays one argv element); raises on any
    unfilled `{placeholder}`. A placeholder that occupies a complete token may resolve to the
    empty string; that token is omitted. This gives apb2's optional positional level one canonical
    template without introducing optional-group syntax.
    """
    missing = sorted({m.group(1) for m in _PLACEHOLDER.finditer(template)} - set(ctx))
    if missing:
        raise KeyError(f"unfilled placeholder(s) {missing} in command template {template!r}")
    rendered = [
        _PLACEHOLDER.sub(lambda match: str(ctx[match.group(1)]), token)
        for token in template.split()
    ]
    return [token for token in rendered if token]


# --- stage-graph helpers (topology is data — decision 5 / §13) --------------------------------


def stage_order(registry: list[dict[str, Any]]) -> list[str]:
    """Derive topological stage order from `depends_on`, never a hardcoded list (§13.3)."""
    deps = {s["name"]: list(s.get("depends_on") or []) for s in registry}
    order: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        for dep in deps.get(name, []):
            visit(dep)
        order.append(name)

    for stage in registry:
        visit(stage["name"])
    return order


def basket_label(stage: dict[str, Any]) -> str:
    """Return the compact dashboard label for a registry stage."""
    return stage.get("basket", stage["name"])


def _resource_names(stage: dict[str, Any]) -> tuple[str, ...]:
    """Return a stage's optional resource placeholders."""
    resources = stage.get("resources")
    if resources is not None:
        return tuple(str(name) for name in resources)
    resource = stage.get("resource")
    return (resource,) if resource is not None else ()


def _resolved_resource(
    fixture: ResolvedFixture,
    name: str,
) -> tuple[Path | None, str | None]:
    """Resolve a registry resource name against one frozen fixture."""
    if name == "module_settings":
        return fixture.annotation_path, fixture.module_settings_error
    return (
        getattr(fixture, f"{name}_path", None),
        getattr(fixture, f"{name}_error", None),
    )


def _nearest_upstream(
    deps: list[str],
    emitted: dict[str, Path],
    reg: dict[str, dict[str, Any]],
) -> Path:
    """Nearest already-emitted upstream artifact for a stage's `depends_on` (§13.1 reconnection).

    Walk the `depends_on` graph until an emitted stage is found, so an optional *intermediate* stage
    that was skipped for this dataset is transparent — its successor reconnects to the last present
    artifact. The DAG root always emits, so a well-formed registry always yields one.
    """
    found = _emitted_ancestor(deps, emitted, reg)
    if found is None:
        raise ValueError(f"No emitted upstream stage for dependencies {deps}.")
    return found


def _emitted_ancestor(
    deps: list[str],
    emitted: dict[str, Path],
    reg: dict[str, dict[str, Any]],
) -> Path | None:
    """Walk `depends_on` breadth-first for the first emitted artifact."""
    for dep in deps:
        if dep in emitted:
            return emitted[dep]
    for dep in deps:
        up = _emitted_ancestor(list(reg.get(dep, {}).get("depends_on") or []), emitted, reg)
        if up is not None:
            return up
    return None


def _stage_applies(
    stage: dict[str, Any],
    fixture: ResolvedFixture,
    branch: str,
) -> bool:
    """Return whether one stage applies to this resolved fixture branch."""
    allowed_branches = stage.get("branches")
    if allowed_branches is not None and branch not in allowed_branches:
        return False
    required_level = stage.get("requires_level")
    return required_level is None or required_level in fixture.branches


def expand_resolved_targets(
    pipeline: Pipeline,
    fixtures: tuple[ResolvedFixture, ...] | list[ResolvedFixture],
    output_root: Path,
) -> list[Target]:
    """Expand frozen fixture branches into concrete stage targets for one pipeline.

    Every selected stage receives a target, even when its own module resource is absent. Such a
    target carries ``blocked_reason`` and is excluded from Snakemake while its independent
    ancestors stay runnable. This preserves the complete branch topology needed for truthful
    status propagation.

    A branch whose converter the pipeline does not select contributes nothing at all.
    """
    reg = {stage["name"]: stage for stage in pipeline.stages}
    order = list(pipeline.stage_names)
    out_root = output_root
    targets: list[Target] = []

    for fixture in fixtures:
        for branch in fixture.branches:
            converter = branch_converter(branch)
            if converter not in pipeline.converters:
                continue
            base = out_root / fixture.repo_name / fixture.dataset
            level = branch_level(branch)
            emitted: dict[str, Path] = {}

            for name in order:
                stage = reg[name]
                if not _stage_applies(stage, fixture, branch):
                    continue
                dependencies = list(stage.get("depends_on") or [])
                blocked_reason: str | None = None
                output = base / stage_artifact(stage, branch)

                if not dependencies:
                    inputs = [fixture.input_path, fixture.parameter_path]
                    context: dict[str, Any] = {
                        "input": fixture.input_path,
                        "output": output.with_suffix(""),
                        "output_path": output,
                        "vendor": fixture.vendor,
                        "parameter_vendor": (fixture.parameter_vendor or fixture.vendor),
                        "params": fixture.parameter_path,
                        "level": level or "",
                    }
                else:
                    # Every stage emits a target here, so a dependency always has an artifact.
                    upstream = _nearest_upstream(dependencies, emitted, reg)
                    inputs = [upstream]
                    context = {
                        "input": upstream,
                        "output": output,
                        "output_path": output,
                    }

                for resource_name in _resource_names(stage):
                    resource_path, resource_error = _resolved_resource(
                        fixture,
                        resource_name,
                    )
                    if resource_error is not None:
                        blocked_reason = resource_error
                    elif resource_path is None:
                        blocked_reason = f"Missing module resource: {resource_name}"
                    else:
                        context[resource_name] = resource_path
                        inputs.append(resource_path)

                command = (
                    render_command(command_template(stage, converter), context)
                    if blocked_reason is None
                    else []
                )

                emitted[name] = output
                targets.append(
                    Target(
                        module=fixture.repo_name,
                        dataset=fixture.dataset,
                        stage=name,
                        output=output,
                        command=command,
                        inputs=inputs,
                        vendor=fixture.vendor,
                        level=branch_level(branch),
                        branch=branch,
                        blocked_reason=blocked_reason,
                    )
                )
    return targets


def coverage(targets: list[Target]) -> list[dict[str, Any]]:
    """One row per Target with `done = output.exists()` — filesystem-as-DB (decision 4)."""
    return [
        {
            "module": t.module,
            "dataset": t.dataset,
            "branch": t.branch,
            "stage": t.stage,
            "artifact": t.output.name,
            "done": t.output.exists(),
        }
        for t in targets
    ]


def target_blocker(
    target: Target,
    targets: list[Target],
    *,
    existing_artifacts_satisfy: bool = True,
) -> str | None:
    """Return the first missing external prerequisite in a target's upstream chain.

    ``existing_artifacts_satisfy`` is true for display state: a completed artifact is usable even
    when an old source has since disappeared. Snakemake target selection sets it false so every
    declared input chain is valid before asking Snakemake to assess timestamps.
    """
    by_output = {item.output: item for item in targets}
    memo: dict[Path, str | None] = {}

    def visit(item: Target) -> str | None:
        if item.output in memo:
            return memo[item.output]
        if existing_artifacts_satisfy and item.output.exists():
            memo[item.output] = None
            return None
        if item.blocked_reason is not None:
            memo[item.output] = item.blocked_reason
            return item.blocked_reason
        memo[item.output] = None
        for input_path in item.inputs:
            upstream = by_output.get(input_path)
            if upstream is not None:
                blocker = visit(upstream)
                if blocker is not None:
                    memo[item.output] = blocker
                    return blocker
            elif not input_path.exists():
                blocker = f"Missing prerequisite: {input_path}"
                memo[item.output] = blocker
                return blocker
        return None

    return visit(target)


def runnable_targets(targets: list[Target]) -> list[Target]:
    """Return targets Snakemake can safely assess, including existing outputs.

    Existing artifacts remain in the target set so Snakemake, rather than the dashboard, decides
    whether they are stale. Targets with any missing external prerequisite are excluded so one bad
    resource cannot prevent DAG construction for independent branches.
    """
    return [
        target
        for target in targets
        if target_blocker(
            target,
            targets,
            existing_artifacts_satisfy=False,
        )
        is None
    ]


def _log_error(logpath: Path) -> str | None:
    """The apb error summary from a per-rule log (Snakefile tees each rule to ``<artifact>.log``).

    Prefers the exception line (``ValueError: …`` / ``…Error: …``); else the last non-empty line.
    Used to surface why a convert, FASTA, aggregate, or ProteoBench stage failed when its artifact
    is absent.
    """
    try:
        lines = [
            ln.strip() for ln in logpath.read_text(errors="replace").splitlines() if ln.strip()
        ]
    except OSError:
        return None
    if not lines:
        return None
    for line in reversed(lines):
        if re.match(r"^[\w.]*(Error|Exception):", line):
            return line
    return lines[-1]


def failure_marker_path(output: Path) -> Path:
    """Return the marker written only after a rule command exits unsuccessfully."""
    return Path(f"{output}.failed")


def benchmark_path(output: Path) -> Path:
    """Return the Snakemake benchmark file adjacent to a stage artifact."""
    return Path(f"{output}.benchmark.tsv")


def _benchmark_seconds(output: Path) -> float | None:
    """Read one rule's elapsed seconds, tolerating old or partial metadata."""
    try:
        with benchmark_path(output).open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle, delimiter="\t"), None)
        seconds = float(row["s"]) if row is not None else math.nan
    except (OSError, KeyError, TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def format_duration(seconds: float) -> str:
    """Format elapsed seconds compactly for a stage cell."""
    if seconds < 10:
        return f"{seconds:.1f}s"
    total_seconds = round(seconds)
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, remainder = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remainder:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _failed_rule_error(output: Path) -> str | None:
    """Return a rule failure only when its authoritative failure marker exists.

    A rule's ``tee`` log is created and populated while that rule is still running, so log
    existence alone cannot distinguish live progress from failure. The Snakefile clears this
    marker immediately before each attempt and writes it only after a non-zero command exit.
    """
    marker = failure_marker_path(output)
    if not marker.exists():
        return None
    error = _log_error(Path(f"{output}.log"))
    if error is not None:
        return error
    try:
        exit_status = marker.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        exit_status = ""
    return f"Rule failed{f' ({exit_status})' if exit_status else ''}"


def _terminal_blocker(
    target: Target,
    targets: list[Target],
) -> str | None:
    """Return a terminal upstream blocker, but never a direct or pending prerequisite."""
    by_output = {item.output: item for item in targets}
    memo: dict[Path, str | None] = {}

    def visit(item: Target) -> str | None:
        if item.output in memo:
            return memo[item.output]
        if item.output.exists():
            memo[item.output] = None
            return None
        if item.blocked_reason is not None:
            memo[item.output] = item.blocked_reason
            return item.blocked_reason

        memo[item.output] = None
        for input_path in item.inputs:
            upstream = by_output.get(input_path)
            if upstream is None:
                continue
            if upstream.output.exists():
                continue
            upstream_error = _failed_rule_error(upstream.output)
            if upstream_error is not None:
                reason = f"Blocked by failed upstream stage {upstream.stage}: {upstream_error}"
                memo[item.output] = reason
                return reason
            upstream_blocker = visit(upstream)
            if upstream_blocker is not None:
                reason = f"Blocked by upstream stage {upstream.stage}: {upstream_blocker}"
                memo[item.output] = reason
                return reason
        return None

    return visit(target)


def _stage_detail(
    target: Target | None,
    *,
    targets: list[Target],
    missing_reason: str | None = None,
) -> dict[str, str]:
    """Build one JSON-compatible table-cell detail payload."""
    if target is None:
        return _missing_stage_detail(missing_reason)
    artifact = str(target.output)
    log_path = str(Path(f"{target.output}.log"))
    base = {"artifact": artifact, "log": log_path}
    if target.command:
        base["command"] = shlex.join(target.command)
    if target.output.exists():
        return _completed_stage_detail(target, base)
    return _incomplete_stage_detail(target, targets, base)


def _missing_stage_detail(reason: str | None) -> dict[str, str]:
    return {
        "state": "unsupported",
        "display": "UNSUPPORTED",
        "error": reason or "Stage target unavailable",
    }


def _completed_stage_detail(target: Target, base: dict[str, str]) -> dict[str, str]:
    duration_seconds = _benchmark_seconds(target.output)
    timing = (
        {}
        if duration_seconds is None
        else {
            "duration": format_duration(duration_seconds),
            "duration_seconds": str(duration_seconds),
        }
    )
    size_bytes = _artifact_bytes(target.output)
    size = {} if size_bytes is None else {"bytes": str(size_bytes)}
    display = "DONE" if not timing else f"DONE · {timing['duration']}"
    return {**base, **timing, **size, "state": "completed", "display": display}


def _artifact_bytes(output: Path) -> int | None:
    """The produced artifact's own size, or None when it cannot be read.

    This is the file's size, not a proxy for anything: runtime still comes only from Snakemake's
    benchmark files, never from an artifact's timestamps.
    """
    try:
        return output.stat().st_size
    except OSError:
        return None


def _incomplete_stage_detail(
    target: Target,
    targets: list[Target],
    base: dict[str, str],
) -> dict[str, str]:
    error = _failed_rule_error(target.output)
    if error is not None:
        return {**base, "state": "failed", "display": "FAILED", "error": error}
    if target.blocked_reason is not None:
        return {
            **base,
            "state": "unsupported",
            "display": "UNSUPPORTED",
            "error": target.blocked_reason,
        }
    target_outputs = {item.output for item in targets}
    missing_prerequisite = next(
        (
            input_path
            for input_path in target.inputs
            if input_path not in target_outputs and not input_path.exists()
        ),
        None,
    )
    if missing_prerequisite is not None:
        return {
            **base,
            "state": "unsupported",
            "display": "UNSUPPORTED",
            "error": f"Missing prerequisite: {missing_prerequisite}",
        }
    blocker = _terminal_blocker(target, targets)
    if blocker is not None:
        return {**base, "state": "unavailable", "display": ""}
    return {**base, "state": "pending", "display": ""}


def branch_rows(run: RunSnapshot, targets: list[Target]) -> list[dict[str, Any]]:
    """Return one compact progress row per frozen fixture branch.

    The run's own pipeline decides the columns: a grid describes one run, so the definition that
    produced it owns what the row can show.
    """
    pipeline = run.pipeline
    order = list(pipeline.stage_names)
    by_key = {
        (target.module, target.dataset, target.branch, target.stage): target for target in targets
    }
    rows: list[dict[str, Any]] = []

    for fixture in run.fixtures:
        if not fixture.branches:
            status = fixture.capability_status.lower()
            state = status if status in {"failed", "unsupported"} else "failed"
            display = state.upper()
            root_stage = pipeline.column(order[0], pipeline.converters[0])
            root_reason = fixture.diagnostic or "No supported APB branch"
            columns = list(pipeline.columns)
            details = {
                column: {"state": "unavailable", "display": ""}
                for column in columns
                if column != root_stage
            }
            details[root_stage] = {
                "state": state,
                "display": display,
                "error": root_reason,
            }
            row: dict[str, Any] = {
                "module": fixture.repo_name,
                "dataset": fixture.dataset,
                "software": fixture.vendor,
                "level": "Unresolved",
                root_stage: display,
                "_stage_details": details,
            }
            row.update({column: "" for column in columns if column != root_stage})
            rows.append(row)
            continue

        for label, branches in _levels(fixture.branches).items():
            if not any(converter in branches for converter in pipeline.converters):
                # No converter this pipeline runs produces this level; the row would be empty.
                continue
            if not any(
                (fixture.repo_name, fixture.dataset, branch, stage_name) in by_key
                for branch in branches.values()
                for stage_name in order
            ):
                # A branch-restricted root such as the direct MuData workflow deliberately emits
                # no target for this level, so it should not create an empty dashboard row.
                continue
            details: dict[str, dict[str, str]] = {}
            row = {
                "module": fixture.repo_name,
                "dataset": fixture.dataset,
                "software": fixture.vendor,
                "level": label,
            }
            for converter in pipeline.converters:
                branch = branches.get(converter)
                for stage_name in order:
                    column = pipeline.column(stage_name, converter)
                    if branch is None:
                        # This level has no such conversion at all. A level one converter cannot
                        # parse produced no branch.
                        details[column] = {"state": "unavailable", "display": ""}
                        row[column] = ""
                        continue
                    target = by_key.get((fixture.repo_name, fixture.dataset, branch, stage_name))
                    detail = _stage_detail(
                        target,
                        targets=targets,
                        missing_reason="Stage target unavailable",
                    )
                    details[column] = detail
                    row[column] = detail["display"]
            row["_stage_details"] = details
            rows.append(row)
    return rows


def _levels(branches: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Group one fixture's branches by the level they convert, keeping declared order.

    ``{"ion": {"apb2": "ion"}}`` — the row is a level and APB2 contributes its branch.
    """
    grouped: dict[str, dict[str, str]] = {}
    for branch in branches:
        branch_quantification_level = branch_level(branch)
        label = MUDATA_LABEL if branch_quantification_level is None else branch_quantification_level
        grouped.setdefault(label, {})[branch_converter(branch)] = branch
    return grouped


def reject_input_paths(paths: list[Path], input_root: Path) -> list[Path]:
    """Return paths outside `input_root`; raise `CleanGuardError` for an input path.

    Resolves both sides, so it also catches relative paths and symlink escapes. This is a **real
    exception**, not an `assert`: `assert` is stripped by `python -O`, and a destructive-action
    guard must never be optimized away.
    """
    in_root = input_root.resolve()
    for p in paths:
        resolved = p.resolve()
        if in_root == resolved or in_root in resolved.parents:
            raise CleanGuardError(f"refusing to clean {p}: it is under input_root {in_root}")
    return paths


def sample_fixture_targets(targets: list[Target], fixture_limit: int) -> list[Target]:
    """Return every target of the first *fixture_limit* fixtures, spread across vendors.

    Headless verification gates run a representative slice of the corpus rather than the
    whole catalogue: ten fixtures take minutes where 241 take about an hour. Fixtures are
    taken round-robin by vendor so a small sample exercises as many parsers and branches as
    possible instead of ten submissions from one tool, and the ordering is deterministic so
    two runs of the same limit compare directly.

    This is selection for developer gates only. Corpus Runner still triggers whole-corpus
    run and clean; do not wire this into a Dash callback.

    A non-positive limit returns every target unchanged, which is the whole-corpus run.
    """
    if fixture_limit <= 0:
        return list(targets)

    by_fixture: dict[tuple[str, str], list[Target]] = {}
    for target in targets:
        by_fixture.setdefault((target.module, target.dataset), []).append(target)

    by_vendor: dict[str, list[tuple[str, str]]] = {}
    for key, group in by_fixture.items():
        by_vendor.setdefault(group[0].vendor, []).append(key)

    queues = [sorted(keys) for _, keys in sorted(by_vendor.items())]
    ordered: list[tuple[str, str]] = []
    while len(ordered) < fixture_limit and any(queues):
        for queue in queues:
            if not queue or len(ordered) >= fixture_limit:
                continue
            ordered.append(queue.pop(0))
    return [
        target
        for key in ordered
        for target in sorted(by_fixture[key], key=lambda target: target.output)
    ]


def selected_dataset_targets(
    targets: list[Target],
    datasets: Sequence[str],
) -> tuple[list[Target], list[str]]:
    """Keep the targets of the named datasets, and report every name that matched nothing.

    A name is either a dataset alias (``diann-300beac4``) or a module-qualified one
    (``Results_quant_ion_DDA/diann-300beac4``); the qualified form settles the rare case of one
    alias existing under two modules. Names that match nothing come back to the caller instead of
    being dropped: an explicit selection whose entries silently do not apply is the very thing a
    named list exists to avoid.
    """
    wanted = {name.strip() for name in datasets if name.strip()}
    matched: set[str] = set()
    selected: list[Target] = []
    for target in targets:
        for name in (target.dataset, f"{target.module}/{target.dataset}"):
            if name in wanted:
                matched.add(name)
                selected.append(target)
                break
    return selected, sorted(wanted - matched)


def level_targets(targets: list[Target], levels: Sequence[str]) -> list[Target]:
    """Keep the targets of the named quantification levels, ``mudata`` included.

    A branch's level is its own answer — ``Target.level`` is None only for the MuData container,
    whose name is ``mudata`` — so one lookup covers every branch without asking what kind it is.
    """
    wanted = {name.strip() for name in levels if name.strip()}
    return [target for target in targets if (target.level or MUDATA) in wanted]


def dataset_names(targets: Sequence[Target]) -> list[str]:
    """The module-qualified datasets a target list covers, for reporting what will run."""
    return sorted({f"{target.module}/{target.dataset}" for target in targets})


def level_names(targets: Sequence[Target]) -> list[str]:
    """The levels a target list covers, for reporting what will run."""
    return sorted({target.level or MUDATA for target in targets})
