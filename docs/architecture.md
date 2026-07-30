# Architecture

Dependency direction is `apb_studio → anndata_proteomics`, never the reverse.

The Fixture Manager maintains the local test-data catalog, download queue, and
module resources. The Corpus Runner asks APB which branches each fixture
supports, freezes the resolved run into `run.json`, and gives that immutable
snapshot to the packaged Snakemake workflow.

The Corpus Runner UI is deliberately limited to whole-corpus `run` and `clean`
operations, both executed by the packaged Snakefile. The branch grid is
inspection-only. Dash callbacks never delete individual artifacts.

Each operation persists its immutable `run.json`, lifecycle state, and
`snakemake.log` below `<output_root>/.apb_studio/runs/<run-id>/`, allowing the
dashboard to restore the latest run and log after restart. Per-rule benchmark
files are the sole runtime source; old artifacts without one report timing as
unavailable.

`make corpus-clean` runs the same clean rule without a browser
(`scripts/clean_corpus.py`). It must freeze a snapshot first: the Snakefile
refuses to load without one, and the clean rule deletes the inventory frozen
into it.

Each branch follows:

```text
convert ─┬─ annotate ── proteobench
         └─ fasta
```

ProteoBench scoring requires the `sample_name` and `condition` added by
annotation. FASTA enrichment remains independent. The packaged
`config/registry.yaml` owns stage topology and command templates. Artifacts and
explicit failure markers own runtime state.
