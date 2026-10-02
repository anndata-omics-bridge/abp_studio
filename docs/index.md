# APB Studio

APB Studio provides two local applications over the APB2 toolchain:

- **Fixture Manager** owns ProteoBench fixture and resource inventory.
- **Corpus Runner** schedules concrete Python workflows through Snakemake, writes per-dataset JSON reports, and exposes settings and progress to the JavaScript corpus viewer.

The applications share typed, disk-backed settings. APB2 and its focused tools own conversion, annotation, FASTA handling, aggregation, ProteoBench scoring, capability resolution, and artifact summaries; Studio owns orchestration and presentation.

See [Architecture](architecture.md) for the data-flow contract,
[Adding a workflow](workflows.md) for the one file a new pipeline needs, and
[Development](development.md) for the complete local quality gate.
