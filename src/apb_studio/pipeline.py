"""Registry-driven core — the single source of truth (decision 5).

Turns (stage registry + corpus config) into concrete `Target`s: an output path, a fully-rendered
`apb` command (argv), and the upstream inputs that feed it. The Snakefile and the dashboard both
call these functions; neither restates stage knowledge, so the registry and the GUI cannot drift.

The stage graph is a DAG: nodes are artifacts (= the kanban baskets), edges are tools (= stages).
`expand_targets` derives every edge from the registry's `depends_on` (no hardcoded wiring), so
adding a stage is a registry edit — the topology is data (§13). The kanban renders the path case.

See TODO/TODO_workflow_dashboard_plan.md §7, §8, §13.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from apb_studio.registry import load_corpus, load_registry  # noqa: F401 (re-exported for callers)

# Vendors whose `apb convert` (no --level) emits a multi-level MuData. Every other vendor is
# single-level and MUST declare `level` in the corpus config (decision 16); otherwise apb's
# single-level fallback writes a plain AnnData that would land under a .h5mu name.
MULTI_LEVEL_VENDORS = frozenset({"diann", "spectronaut"})

# The quantification level apb's packaged rules emit for each SINGLE-level vendor (mirrors apb's
# supported vendor/level table). The level is a property of the VENDOR, not of the benchmark module's
# name — e.g. WOMBAT is peptidoform even inside an "…_ion_…" module — so `make scaffold` declares
# this per dataset (decision 16) rather than taking the module-name level. A vendor not listed here
# falls back to the module-name level.
SINGLE_LEVEL_VENDOR_LEVELS = {
    "maxquant": "ion",
    "fragpipe": "ion",
    "peaks": "ion",
    "wombat": "peptidoform",
}

# Quantification levels apb can emit as a standalone AnnData (used for the convert wildcard).
LEVELS = ("ion", "fragment", "peptidoform", "peptide", "protein")

# The basket a dataset sits in before any stage has run (the DAG source). Kept here so the
# dashboard and baskets() agree on the label without hardcoding it in the GUI.
INPUTS_BASKET = "inputs"

# Wildcard-constraint regexes the Snakefile uses to route one `{artifact}` wildcard to the right
# stage rule (the three are disjoint, so there is no ambiguity).
CONVERT_ARTIFACT_RE = r"mudata\.h5mu|(?:" + "|".join(LEVELS) + r")\.h5ad"
ANNOTATE_ARTIFACT_RE = r"annotated\.(?:h5mu|h5ad)"
FASTA_ARTIFACT_RE = r"annotated_fasta\.(?:h5mu|h5ad)"

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class CleanGuardError(Exception):
    """Raised when a Clean would delete a path under `input_root` — never an input (§8.3)."""


@dataclass(frozen=True)
class Target:
    """One (module, dataset, stage) unit of work."""

    module: str
    dataset: str
    stage: str                       # registry stage name
    output: Path                     # absolute, under output_root
    command: list[str]               # fully-rendered argv (ready for shell / preview)
    inputs: list[Path] = field(default_factory=list)
    vendor: str = ""                 # the dataset's software (decision 14) — carried for baskets()
    level: str | None = None         # the dataset's level (single-level vendor) or None (multi-level)


def convert_artifact(dataset_cfg: dict) -> str:
    """The convert stage's filename for a dataset (decision 16).

    A dataset carries its own `vendor` and optional `level` (the *module* is the benchmark — the
    shared raw runs — and holds datasets from several tools). `mudata.h5mu` when the dataset omits
    `level` (a multi-level vendor); `<level>.h5ad` otherwise. The PRECONDITION (a single-level vendor
    must declare `level`) is enforced by `validate_dataset`.
    """
    level = dataset_cfg.get("level")
    return f"{level}.h5ad" if level else "mudata.h5mu"


def convert_suffix(dataset_cfg: dict) -> str:
    """`.h5ad` for a single-level (level-bearing) dataset, else `.h5mu` — annotate/fasta track this."""
    return ".h5ad" if dataset_cfg.get("level") else ".h5mu"


def validate_dataset(module: str, dataset_cfg: dict) -> None:
    """Validate a dataset's `vendor`/`level` (decision 16). Vendor + level are PER DATASET."""
    name = dataset_cfg.get("name", "?")
    vendor = dataset_cfg.get("vendor")
    if not vendor:
        raise ValueError(f"{module}/{name}: missing required 'vendor'")
    level = dataset_cfg.get("level")
    if not level and vendor not in MULTI_LEVEL_VENDORS:
        raise ValueError(
            f"{module}/{name}: vendor {vendor!r} is single-level — declare a 'level' "
            f"(decision 16). Only {sorted(MULTI_LEVEL_VENDORS)} may omit it."
        )
    if level is not None and level not in LEVELS:
        # Keep the convert artifact name (<level>.h5ad) inside the Snakefile's wildcard constraint;
        # an unknown level would otherwise yield a target no rule can build.
        raise ValueError(
            f"{module}/{name}: level {level!r} is not a known quantification level — one of {LEVELS}"
        )


def render_command(template: str, ctx: dict) -> list[str]:
    """Substitute `{placeholder}`s in a registry command template → an argv list.

    Plain per-token substitution (so a value with spaces stays one argv element); raises on any
    unfilled `{placeholder}`. There is no optional-group grammar — `--level` is appended by
    `expand_targets`, not encoded in the template (§7.2).
    """
    missing = sorted({m.group(1) for m in _PLACEHOLDER.finditer(template)} - set(ctx))
    if missing:
        raise KeyError(f"unfilled placeholder(s) {missing} in command template {template!r}")
    return [_PLACEHOLDER.sub(lambda m: str(ctx[m.group(1)]), token) for token in template.split()]


# --- stage-graph helpers (topology is data — decision 5 / §13) --------------------------------

def stage_order(registry: list[dict]) -> list[str]:
    """Stage names in a topological order derived from `depends_on` (never a hardcoded list, §13.3)."""
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


def basket_label(stage: dict) -> str:
    """The kanban basket a dataset reaches after this stage (the registry `basket` field)."""
    return stage.get("basket", stage["name"])


def basket_names(registry: list[dict]) -> list[str]:
    """Ordered basket labels for the flow strip / stacked tables: inputs, then one per stage (§8.3)."""
    by_name = {s["name"]: s for s in registry}
    return [INPUTS_BASKET] + [basket_label(by_name[name]) for name in stage_order(registry)]


def stage_by_basket(registry: list[dict]) -> dict[str, str]:
    """Map each non-`inputs` basket label back to the stage that defines it (for Clean, §8.3)."""
    return {basket_label(s): s["name"] for s in registry}


def descendants(registry: list[dict], stage: str) -> set[str]:
    """Stages that transitively DEPEND ON `stage` (its downstream in the DAG).

    Basket Clean deletes `stage` AND its descendants for the selected datasets (cascade, §8.3): a
    convert artifact can't be removed while a downstream annotate/fasta derives from it, and cascading
    also sweeps a *stray* downstream artifact left by a partial run or manual copy — so a Clean always
    leaves a contiguous prefix, never an orphan, regardless of the prior on-disk state.
    """
    children: dict[str, set[str]] = defaultdict(set)
    for s in registry:
        for dep in (s.get("depends_on") or []):
            children[dep].add(s["name"])
    out: set[str] = set()
    stack = [stage]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def _resolve(value: str, base: Path) -> Path:
    """Resolve a config path: absolute as-is, else relative to `base`."""
    p = Path(value)
    return p if p.is_absolute() else base / p


def _nearest_upstream(deps: list[str], emitted: dict[str, Path], reg: dict[str, dict]) -> Path | None:
    """Nearest already-emitted upstream artifact for a stage's `depends_on` (§13.1 reconnection).

    Walk the `depends_on` graph until an emitted stage is found, so an optional *intermediate* stage
    that was skipped for this dataset is transparent — its successor reconnects to the last present
    artifact. Returns None only above the root (which always emits, so downstream always finds one).
    """
    for dep in deps:
        if dep in emitted:
            return emitted[dep]
    for dep in deps:
        up = _nearest_upstream(list(reg.get(dep, {}).get("depends_on") or []), emitted, reg)
        if up is not None:
            return up
    return None


def expand_targets(
    registry: list[dict],
    corpus: dict,
    output_root: Path | str | None = None,
    input_root: Path | str | None = None,
) -> list[Target]:
    """Expand (registry × corpus) into concrete `Target`s with rendered commands and input edges.

    A module is the benchmark (shared runs); each **dataset** carries its own `vendor` and optional
    `level`. Edges are derived from each stage's `depends_on` — the DAG root (`depends_on: []`) reads
    the raw dataset (`input`/`params`); every other stage consumes its nearest emitted upstream
    artifact and, if it declares a `resource`, the module-level file that resource names (which also
    GATES the stage: a module lacking the resource simply doesn't get it). Non-root output basenames
    are `f"{artifact}{suffix}"` with `{suffix}` tracking the dataset's convert artifact.
    """
    reg = {s["name"]: s for s in registry}
    order = stage_order(registry)
    out_root = Path(output_root if output_root is not None else corpus["output_root"])
    in_root = Path(input_root if input_root is not None else corpus["input_root"])

    targets: list[Target] = []
    for module, mcfg in corpus["modules"].items():
        for ds in mcfg["datasets"]:
            validate_dataset(module, ds)
            suffix = convert_suffix(ds)
            base = out_root / module / ds["name"]
            emitted: dict[str, Path] = {}  # stage name -> output path, for this dataset

            for name in order:
                stage = reg[name]
                deps = list(stage.get("depends_on") or [])

                if not deps:  # DAG root (convert): reads the raw dataset file + its params
                    output = base / convert_artifact(ds)
                    command = render_command(
                        stage["command"],
                        {
                            "input": in_root / ds["input"],
                            "output": output,
                            "vendor": ds["vendor"],
                            "params": in_root / ds["params"],
                        },
                    )
                    if ds.get("level"):
                        command += ["--level", ds["level"]]
                    inputs = [in_root / ds["input"], in_root / ds["params"]]
                else:
                    resource = stage.get("resource")
                    res_path = None
                    if resource is not None:
                        raw = mcfg.get(resource)
                        if raw is None:
                            continue  # module doesn't supply this resource → skip the stage
                        res_path = _resolve(raw, in_root)
                    upstream = _nearest_upstream(deps, emitted, reg)
                    if upstream is None:
                        continue  # no upstream emitted (its resource was absent) → skip
                    output = base / f"{stage['artifact']}{suffix}"
                    ctx = {"input": upstream, "output": output}
                    if resource is not None:
                        ctx[resource] = res_path
                    command = render_command(stage["command"], ctx)
                    inputs = [upstream] + ([res_path] if res_path is not None else [])

                emitted[name] = output
                targets.append(
                    Target(module, ds["name"], name, output, command, inputs,
                           vendor=ds["vendor"], level=ds.get("level"))
                )
    return targets


def coverage(targets: list[Target]) -> list[dict]:
    """One row per Target with `done = output.exists()` — filesystem-as-DB (decision 4)."""
    return [
        {
            "module": t.module,
            "dataset": t.dataset,
            "stage": t.stage,
            "artifact": t.output.name,
            "done": t.output.exists(),
        }
        for t in targets
    ]


def _log_error(logpath: Path) -> str | None:
    """The apb error summary from a per-rule log (Snakefile tees each rule to ``<artifact>.log``).

    Prefers the exception line (``ValueError: …`` / ``…Error: …``); else the last non-empty line.
    Used to surface *why* a convert/annotate/fasta failed when its artifact is absent.
    """
    try:
        lines = [ln.strip() for ln in logpath.read_text(errors="replace").splitlines() if ln.strip()]
    except OSError:
        return None
    if not lines:
        return None
    for line in reversed(lines):
        if re.match(r"^[\w.]*(Error|Exception):", line):
            return line
    return lines[-1]


def _provenance_warnings(sidecar: Path) -> list[str]:
    """Any ``warning`` fields recorded in a dataset's provenance.json (e.g. unparsable params)."""
    if not sidecar.exists():
        return []
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    out = []
    for stage, rec in data.items():
        if isinstance(rec, dict) and rec.get("warning"):
            out.append(f"{stage}: {rec['warning']}")
    return out


def problems(corpus: dict, targets: list[Target]) -> dict[tuple[str, str], list[str]]:
    """Per-dataset problems to surface in the baskets (§8, review round 2).

    Two sources: **static** — declared files that don't exist (a dataset's `input`/`params`, or a
    module's `annotation:`/`fasta:` resource) — caught without running anything; and **runtime** —
    warnings apb recorded while still producing an artifact (e.g. an unparsable params file), read
    from each dataset's provenance.json. Keyed by (module, dataset); empty when a dataset is clean.
    """
    in_root = Path(corpus.get("input_root", ""))
    out: dict[tuple[str, str], list[str]] = defaultdict(list)
    for module, mcfg in corpus.get("modules", {}).items():
        ann, fasta = mcfg.get("annotation"), mcfg.get("fasta")
        ann_missing = ann is not None and not _resolve(ann, in_root).exists()
        fasta_missing = fasta is not None and not _resolve(fasta, in_root).exists()
        for ds in mcfg.get("datasets", []):
            key = (module, ds["name"])
            if ds.get("input") and not _resolve(ds["input"], in_root).exists():
                out[key].append(f"input file missing: {ds['input']}")
            if ds.get("params") and not _resolve(ds["params"], in_root).exists():
                out[key].append(f"params file missing: {ds['params']}")
            if ann_missing:
                out[key].append(f"annotation TOML missing: {ann}")
            if fasta_missing:
                out[key].append(f"fasta missing: {fasta}")
    # runtime warnings from each dataset's provenance sidecar (one dir per (module, dataset))
    for (module, dataset), sidecar in {
        (t.module, t.dataset): t.output.parent / "provenance.json" for t in targets
    }.items():
        out[(module, dataset)].extend(_provenance_warnings(sidecar))
    # runtime FAILURES: a stage whose artifact is missing but whose per-rule log exists was attempted
    # and failed (e.g. "no rule covers version …"); a stage never attempted has no log (→ just pending).
    for t in targets:
        if not t.output.exists():
            err = _log_error(Path(f"{t.output}.log"))
            if err:
                out[(t.module, t.dataset)].append(f"{t.stage} failed: {err}")
    return {k: v for k, v in out.items() if v}


def baskets(
    targets: list[Target], registry: list[dict], problems: dict[tuple[str, str], list[str]] | None = None
) -> dict[str, list[dict]]:
    """Group DATASETS into kanban baskets (decision 10, §8).

    A dataset's basket is the furthest stage whose whole prefix (over the dataset's *applicable*
    stages) is done — a CONTIGUOUS prefix, not the bare max-done stage — so a non-contiguous on-disk
    state (a later artifact present while an earlier one is missing) reports the LOWER basket, never a
    basket whose defining artifact is absent. `next_stage`/`runnable` are per-dataset from the
    dataset's own Target set: `next_stage` is the first not-yet-done applicable stage (or None →
    terminal). Returns an ordered dict keyed by basket label (empty baskets included, for the flow
    strip). Membership is computed only from per-Target output paths, never a filename glob.
    """
    order = stage_order(registry)
    labels = {s["name"]: basket_label(s) for s in registry}
    problems = problems or {}
    result: dict[str, list[dict]] = {b: [] for b in basket_names(registry)}

    by_ds: dict[tuple[str, str], list[Target]] = defaultdict(list)
    for t in targets:
        by_ds[(t.module, t.dataset)].append(t)

    for (module, dataset), ts in by_ds.items():
        stages_here = {t.stage for t in ts}
        applicable = [s for s in order if s in stages_here]  # this dataset's stages, in topo order
        done = {t.stage: t.output.exists() for t in ts}

        basket_stage: str | None = None
        for stage in applicable:
            if done.get(stage):
                basket_stage = stage
            else:
                break
        next_stage = next((s for s in applicable if not done.get(s)), None)
        basket = INPUTS_BASKET if basket_stage is None else labels[basket_stage]

        result[basket].append({
            "module": module,
            "dataset": dataset,
            "software": ts[0].vendor,
            "level": ts[0].level or "",
            "basket": basket,
            "next_stage": next_stage,
            "runnable": next_stage is not None,
            "problem": "; ".join(problems.get((module, dataset), [])),
        })
    return result


def select_targets(
    targets: list[Target],
    *,
    scope: str = "all",
    module: str | None = None,
    dataset: str | None = None,
    stage: str = "all",
) -> list[Target]:
    """Filter targets by a scope×stage selection (the selector the Snakefile / clean_paths use)."""
    selected = targets
    if stage != "all":
        selected = [t for t in selected if t.stage == stage]
    if scope == "module":
        selected = [t for t in selected if t.module == module]
    elif scope == "dataset":
        selected = [t for t in selected if t.module == module and t.dataset == dataset]
    return selected


def targets_for(targets: list[Target], keys: set[tuple[str, str]], *, stage: str) -> list[Target]:
    """The Targets at `stage` for the selected (module, dataset) rows — the multi-row basket
    selection scope×stage cannot express (§8.2). Run feeds the outputs to run_pipeline; Clean feeds
    them to clean_targets."""
    keyset = set(keys)
    return [t for t in targets if t.stage == stage and (t.module, t.dataset) in keyset]


def reject_input_paths(paths: list[Path], input_root: Path | str) -> list[Path]:
    """Return `paths` iff none is under `input_root` (the Clean guard); raise `CleanGuardError` else.

    Resolves both sides, so it also catches relative paths and symlink escapes. Shared by
    `clean_paths` (scope×stage) and `execution.clean_targets` (row-set) so the guard is single-source.
    This is a **real exception**, NOT an `assert`: `assert` is stripped by `python -O`, and a guard on
    a destructive action must never be optimized away.
    """
    in_root = Path(input_root).resolve()
    for p in paths:
        resolved = Path(p).resolve()
        if in_root == resolved or in_root in resolved.parents:
            raise CleanGuardError(f"refusing to clean {p}: it is under input_root {in_root}")
    return paths


def clean_paths(
    targets: list[Target],
    *,
    input_root: Path | str,
    scope: str = "all",
    module: str | None = None,
    dataset: str | None = None,
    stage: str = "all",
) -> list[Path]:
    """The exact output files a scope×stage Clean would delete — never an input.

    `input_root` is REQUIRED: the guard (`reject_input_paths`) must never be silently skipped by an
    omitted argument.
    """
    paths = [
        t.output
        for t in select_targets(targets, scope=scope, module=module, dataset=dataset, stage=stage)
    ]
    return reject_input_paths(paths, input_root)
