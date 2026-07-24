# APB Studio

APB Studio provides two local applications over the
[`anndata_proteomics` (APB)](../apb) CLI:

- **Fixture Manager** catalogs, selects, downloads, and inspects ProteoBench fixtures and their
  module, per-tool scoring, and FASTA resources.
- **Corpus Runner** derives every branch supported by APB, launches the complete runnable corpus,
  and shows stage progress, artifact summaries, and exact failure logs.

## Sources of truth

| Information | Owner |
| --- | --- |
| Catalog, download queue, report, and cached fixture files | Fixture Manager via `apb-testdata` |
| Active test-data root | Fixture Manager setting |
| ProteoBench module TOMLs, golden-verified per-tool scoring TOMLs, and FASTA resources | Fixture Manager downloads/resource inventory |
| MuData and standalone levels | APB JSON rules resolved against local inputs and parameters |
| Output root | Corpus Runner setting |
| Scope and provenance of one launch | Corpus Runner-generated `run.json` |
| Completion and runtime failure | Artifacts and authoritative rule failure markers |

The applications share typed settings stored in the operating system's application-config
directory. The corpus is every complete local fixture under the active test-data root; the
selection CSV controls the download queue only. A complete fixture has exactly one `input_file.*`
and one `param_0.*`.

There is no user-maintained `corpus.yaml`. No fixture table or application setting declares a
level such as `ion`: APB parses the parameter version and input headers, then resolves the matching
packaged parsing-rule JSON. The ignored legacy `config/corpus.yaml`, if present in a checkout, is
left untouched but is no longer read.

## Corpus Runner

The Corpus Runner shows one compact table with `Module`, `Dataset`, `Software`, `Level`,
`Converted`, `Annotated`, `FASTA annotated`, and `ProteoBench scored`. Each supported fixture fans
out to MuData plus all supported standalone levels. Annotation, FASTA, and ProteoBench scoring are
independent children of conversion, so one missing resource does not block the other enrichments.
Unsupported or invalid local fixtures remain visible as one unresolved row.

`Run corpus` freezes fixture identities, resolved branches, paths, resources, output aliases, and
APB/registry versions into:

```text
<output_root>/.apb_studio/runs/<run-id>/run.json
```

That JSON file is internal execution state, not user configuration. Snakemake consumes the frozen
snapshot with `--keep-going`; a fixture downloaded during a run joins only after that run finishes
and the application reloads.

The stage states have precise meanings:

| State | Meaning |
| --- | --- |
| blank | Runnable or normally waiting for an upstream stage |
| `DONE` | The expected artifact exists |
| `UNSUPPORTED` | APB has no registered capability for the software, or no parsing-rule JSON matches |
| `BLOCKED` | A required input/resource is invalid or absent, or an upstream stage terminated |
| `FAILED` | Snakemake attempted that exact rule and its failure marker exists |

Only `FAILED` is red and offers a downloadable rule log. A leftover log alone never means failure,
and an artifact wins over an old failure marker. Clicking `DONE` shows APB's cumulative artifact
summary; clicking another terminal state shows its diagnostic. `Clear selected stage…` removes a
selected `DONE` or `FAILED` stage plus its downstream artifacts for that branch after confirmation;
fixture inputs and sibling branches are never touched, and clearing is disabled while a corpus run
is active. Newly executed stages include Snakemake's persisted elapsed time directly in their state,
for example `DONE · 2m 14s`; existing artifacts remain plain `DONE` until Snakemake runs them again.

## Fixture Manager

The Fixture Manager owns the canonical cache lifecycle. Its fixture table combines the generated
catalog, selection, and download-report CSVs with live filesystem checks. It downloads
ProteoBench `module_settings.toml` files, golden-verified per-tool scoring TOMLs, and APB's FASTA
resources, then resolves them without requiring manual paths. The same module TOML supplies sample
annotation and the ProteoBench experiment-design contract; these remain independent execution
stages.

Its Data workspace retains the fixture file, submission JSON, and parameter views. Its
Configuration workspace catalogs and edits APB parsing-rule JSON documents. Conversion execution
and converted-artifact inspection belong exclusively to Corpus Runner. In Resources, clicking an
annotation or FASTA status/path cell previews the annotation content or the first 40 FASTA lines.

## Quick start

```bash
uv sync --frozen

make fixture-manager   # Fixture Manager, default Dash port 8050
make corpus-runner     # Corpus Runner, default Dash port 8051
```

Use `make corpus-runner APP_PORT=8052` if port 8051 is occupied. The preferred console commands
are `apb-studio-fixture-manager` and `apb-studio-corpus-runner`.
`apb-studio-testdata` and `apb-studio` remain compatibility aliases.

For development, install all locked checks and run the local CI stages:

```bash
uv sync --frozen --extra dev --group docs
uv run pre-commit run --hook-stage pre-commit --all-files
uv run pre-commit run --hook-stage pre-push --all-files
```

See [docs/development.md](docs/development.md) for the security audit and
individual checks.

## Historical design

The implemented migration plan is archived at
[TODO/Archive/TODO_corpus_application.md](TODO/Archive/TODO_corpus_application.md).
The original dashboard specification is at
[TODO/Archive/TODO_workflow_dashboard_plan.md](TODO/Archive/TODO_workflow_dashboard_plan.md).
