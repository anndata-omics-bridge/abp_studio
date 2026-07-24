# Architecture

Dependency direction is `apb_studio → anndata_proteomics`, never the reverse.

The Fixture Manager maintains the local test-data catalog, download queue, and
module resources. The Corpus Runner asks APB which branches each fixture
supports, freezes the resolved run into `run.json`, and gives that immutable
snapshot to the packaged Snakemake workflow.

Each branch follows:

```text
convert ─┬─ annotate
         ├─ fasta
         └─ proteobench
```

Annotation, FASTA enrichment, and ProteoBench scoring are independent children
of conversion. The packaged `config/registry.yaml` owns stage topology and
command templates. Artifacts and explicit failure markers own runtime state.
