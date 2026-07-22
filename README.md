# APB Studio

APB Studio provides two local applications over the
[`anndata_proteomics` (APB)](../apb) CLI:

- **Fixture Manager** catalogs, selects, downloads, and inspects ProteoBench fixtures and their
  annotation/FASTA resources.
- **Corpus Runner** derives every branch supported by APB, launches the complete runnable corpus,
  and shows stage progress, artifact summaries, and exact failure logs.

## Sources of truth

| Information | Owner |
| --- | --- |
| Catalog, download queue, report, and cached fixture files | Fixture Manager via `apb-testdata` |
| Active test-data root | Fixture Manager setting |
| ProteoBench module annotations and FASTA resources | Fixture Manager downloads/resource inventory |
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
`Converted`, `Annotated`, and `FASTA annotated`. Each supported fixture fans out to MuData plus all
supported standalone levels. Unsupported or invalid local fixtures remain visible as one
unresolved row.

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
summary; clicking another terminal state shows its diagnostic.

## Fixture Manager

The Fixture Manager owns the canonical cache lifecycle. Its fixture table combines the generated
catalog, selection, and download-report CSVs with live filesystem checks. It downloads
ProteoBench `module_settings.toml` observation annotations and APB's FASTA resources, then resolves
both by module without requiring manual annotation paths.

Its Configuration workspace catalogs APB parsing-rule JSON documents. The AnnData
workspace keeps MuData and standalone `.h5ad` outputs distinct and displays APB's stored summaries.

## Quick start

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
uv pip install -e ../apb

make fixture-manager   # Fixture Manager, default Dash port 8050
make corpus-runner     # Corpus Runner, default Dash port 8051
```

Use `make corpus-runner APP_PORT=8052` if port 8051 is occupied. The preferred console commands
are `apb-studio-fixture-manager` and `apb-studio-corpus-runner`. `make testdata-app`, `make app`,
`apb-studio-testdata`, and `apb-studio` remain compatibility aliases.

Run the test suite with `make test`.

## Historical design

The current migration plan is [TODO/TODO_corpus_application.md](TODO/TODO_corpus_application.md).
The original dashboard specification is archived at
[TODO/Archive/TODO_workflow_dashboard_plan.md](TODO/Archive/TODO_workflow_dashboard_plan.md).
