# APB Studio

APB Studio provides two local applications over the APB CLI:

- **Fixture Manager** owns ProteoBench fixture and resource inventory.
- **Corpus Runner** resolves APB-supported branches and executes them through
  Snakemake.

The applications share typed, disk-backed settings. APB owns conversion,
annotation, FASTA handling, ProteoBench scoring, capability resolution, and
artifact summaries; Studio owns orchestration and presentation.

See [Architecture](architecture.md) for the data-flow contract and
[Development](development.md) for the complete local quality gate.
