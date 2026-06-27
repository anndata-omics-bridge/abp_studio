# Review: APB workflow dashboard plan

Review target: [TODO_workflow_dashboard_plan.md](TODO_workflow_dashboard_plan.md)

This is a companion review, not a rewrite of the plan. It compares the written plan against the
current `apb_studio` scaffold and the current APB CLI in `../apb`.

## Findings

### High: APB CLI contract drift

The plan, stage registry, and Snakefile describe a CLI contract that does not match the current
APB implementation.

Evidence:
- The plan expects one stage-oriented subcommand per pipeline stage:
  `apb convert --level <L>`, `apb assemble-mudata`, `apb annotate`, and later
  `apb annotate-fasta`
  ([plan](TODO_workflow_dashboard_plan.md)).

COMMENT: I think it is not a good idea - this forces to reread the file several times.

- The registry command templates use options and subcommands that APB does not currently expose:
  `apb convert --input ... --level ... --rule ...`, `apb assemble-mudata ...`, and
  `apb annotate --annotation ...`
  ([registry](../config/registry.yaml)).
- The Snakefile mirrors the same intended commands in its `shell:` blocks
  ([Snakefile](../workflow/Snakefile)).
- Current APB exposes positional `convert(data, rule_toml=None, output=None)`,
  `annotate(data, annotation_toml, output=None)`, and `fasta(data, *fasta_files, ...)`; it has no
  `--level` option, no `assemble-mudata` subcommand, and no `annotate-fasta` subcommand
  ([APB CLI](../../apb/src/anndata_proteomics/scripts/cli.py)).

This is the first thing to settle. Either APB should grow the stage-oriented contract described by
the plan, or `apb_studio` should adapt its registry/Snakefile/dashboard model to the smaller CLI
that exists now.

### High: Environment is currently unsatisfiable

`pyproject.toml` declares `requires-python = ">=3.10"` while depending on `snakemake>=8`.
Snakemake 8+ requires Python 3.11+, so `uv` tries to solve for Python 3.10 and fails before tests
or Snakemake can run.

Evidence:
- Python range: [pyproject.toml](../pyproject.toml)
- Observed failures: `uv run pytest -q`, `uv run snakemake -s workflow/Snakefile --configfile
  config/corpus.example.yaml -n --cores 1`, and `uv run snakemake -s workflow/Snakefile
  --configfile config/corpus.example.yaml --lint -n --cores 1` all fail during dependency
  resolution with the same Python/Snakemake incompatibility.

The minimum correction is to align `requires-python` with the dependency set, most likely
`>=3.11`.

### Medium: Registry is not yet a true source of truth

The plan says the registry drives stages, output patterns, command templates, dashboard columns,
and stage pickers. The scaffold only partly follows that.

Evidence:
- The Snakefile reads `config/registry.yaml`, but the rules and targets are manually written and
  only conceptually mirror the registry ([Snakefile](../workflow/Snakefile)).
- The dashboard gets stage names from the registry for the dropdown, but coverage rows are
  hardcoded for `convert`, `assemble-mudata`, and `annotate`
  ([dashboard.py](../src/apb_studio/dashboard.py)).

The next implementation plan should define exactly which registry fields are executable
contracts and move target expansion/coverage derivation into reusable Python code that both the
dashboard and Snakefile can use.

### Medium: Annotation input model is underspecified

The plan and example corpus use `annotation_dir`, but current APB `annotate` consumes one
annotation TOML. The review cannot tell how a ProteoBench module folder maps to the exact TOML
used for each artifact.

The plan should require a concrete mapping from module/dataset/artifact to annotation TOML before
the `annotate` stage is implemented. If the intended contract is directory-based annotation, that
logic belongs in APB or a clearly named `apb_studio` resolver, not as an implicit assumption in
the Snakefile.

### Medium: Run/clean scoping needs design before implementation

The `scope x stage x verb` model is a good product shape, but the plan does not define how each
selection becomes Snakemake targets or safe deletions.

Missing decisions:
- How `all`, module, and dataset scopes map to concrete target paths.
- Whether `clean` uses Snakemake metadata, registry globs, or direct output-root deletion.
- Whether clean operations delete only APB-produced artifacts or also logs/provenance.
- How destructive actions are previewed and confirmed before execution.

These choices should be specified before wiring dashboard buttons to background jobs.

### Low: Stale wording and document hygiene

Several plan/docs details are stale or misleading:
- README and local rules still say the `apb` CLI does not exist, but current APB now has an `apb`
  console script.
- The plan still carries repo-name placeholders even though the repo is now `apb_studio`.
- FASTA annotation is marked as future `fasta-annotate`, but APB now exposes `apb fasta`.
- The plan ends with a stray closing code fence.

## Recommended Corrections

1. Resolve the CLI mismatch before building more dashboard behavior. Prefer an explicit decision:
   either APB owns the stage-oriented CLI in the plan, or `apb_studio` adapts to current APB
   commands.
2. Fix the Python requirement so the project environment resolves. With `snakemake>=8`, the
   project should not advertise Python 3.10 support.
3. Promote registry handling into tested shared code. The Snakefile and dashboard should consume
   the same target-expansion and coverage helpers rather than duplicating stage knowledge.
4. Replace the vague `annotation_dir` contract with a specific annotation TOML mapping or a named
   resolver with tests.
5. Specify run/clean target generation and deletion policy before implementing background job
   execution.
6. Refresh stale README/plan wording after the CLI direction is chosen.

## Validation Notes

Attempted validation from the `apb_studio` repo:

```bash
uv run pytest -q
uv run snakemake -s workflow/Snakefile --configfile config/corpus.example.yaml -n --cores 1
uv run snakemake -s workflow/Snakefile --configfile config/corpus.example.yaml --lint -n --cores 1
```

All three currently fail before project code runs because dependency resolution cannot satisfy
`requires-python = ">=3.10"` together with `snakemake>=8`.

This review artifact itself requires no runtime validation beyond confirming that the file exists
and contains the findings above.

## Assumptions

- The original plan remains intact for now.
- This review is intentionally critical and actionable; it is not a replacement design.
- The next engineering step should be a small planning update that chooses the APB CLI contract
  before changing the Snakefile/dashboard behavior.
