# External datasets

Three Zenodo records hold search-engine outputs that ProteoBench submissions do not provide. `config/zenodo.toml` lists the records, their datasets and the files each dataset stores; `fixture download all` acquires all three, and `fixture download NAME` the datasets a corpus lists.

| Record | Acquire | Corpus | Workflows |
| --- | --- | --- | --- |
| MaxQuant entrapment | `uv run fixture download routine` | none; its folder is a `routine` dataset | any conversion workflow |
| directLFQ mirror | `uv run fixture download directlfq` | `directlfq` | `convert_no_param` only: no parameter files |
| MSstats+ DIA reports | `uv run fixture download msstats_plus` | `msstats_plus` | `convert_no_param` only: no parameter files |

Each dataset lands MD5-verified in `test_data_download/zenodo/<record>/<dataset>/`, with its tables kept gzipped and only the parameter file decompressed, or, with `--no-gzip`, fully decompressed, and gets a `downloads.csv` row keyed `zenodo/<record>/<dataset>`, the key a corpus file lists. A dataset of related tables names its folder as input; APB reads the tables inside by their MaxQuant names. A dataset without a parameter file has an empty `vendor_parameter_file_path`, which workflows reading vendor parameters refuse.

## ProteoBench entrapment DIA — MaxQuant 2.8.1.0 related tables

The only complete set of related MaxQuant tables available to Studio. ProteoBench submissions carry one ion-level table, except MSAngel's workbook, whose "Protein sets" sheet APB joins onto its ion sheet; MaxQuant's multi-table joins (peptide, peptidoform and protein levels joined to the ion level) are otherwise exercised only by synthetic unit-test tables.

- DOI: [10.5281/zenodo.23150735](https://doi.org/10.5281/zenodo.23150735)
- Tables: `evidence.txt`, `modificationSpecificPeptides.txt`, `peptides.txt`, `proteinGroups.txt`
- Also included: `mqpar.xml` (the copy MaxQuant wrote to `txt/`), `sdrf.tsv`
- Layout: gzipped, original MaxQuant names; `manifest.tsv` carries sizes, MD5 and SHA-256
- Size: 32 MB gzipped, 136 MB uncompressed
- Search: MaxQuant 2.8.1.0 MaxDIA, three Astral DIA runs (`LFQ_Astral_DIA_15min_50ng_Human_01`–`03`)
- FASTA: `ProteoBenchFASTA_Entrapment_Human_with_contaminants_entrapment_pep.fasta`, already in the fixture store for module `entrapment_dia_astral`
- Provenance: produced by the ProteoBench team for the entrapment module; verbatim mirror, not an official ProteoBench release
- Limit: the FASTA is peptide-level, so every protein group holds exactly one peptide; the record exercises reading related tables, not peptide-to-protein fan-out

## directLFQ benchmark datasets — raw search-engine exports (mirror)

The raw inputs of the directLFQ paper's benchmarks (Ammar et al., Mol Cell Proteomics 22:100581, 2023), mirrored from MPI Biochemistry datashare links that carry no DOI.

- DOI: [10.5281/zenodo.23168773](https://doi.org/10.5281/zenodo.23168773) (version 2); concept DOI 10.5281/zenodo.22301507
- Size: 19 tables, 6.95 GB gzipped, 38.0 GB uncompressed
- Version 2 adds `proteinGroups.txt` for BoxCar, Kuster200 and the yeast interactome
- Layout: original archive path flattened with `__` as separator; `manifest.tsv` maps each file to its original path with checksums
- Companion repository: [extend_directflq_benchmark](https://github.com/wolski/extend_directflq_benchmark), whose `BENCHMARKS.md` maps datasets to the paper's figures

Contents:

- MaxQuant `evidence.txt`, `peptides.txt` and `proteinGroups.txt`: BoxCar (PXD006109), Kuster 200 HeLa replicates (PXD015087), yeast interactome (1,622 timsTOF runs)
- MaxQuant `evidence.txt` and `peptides.txt` only: Kuster tissue (PXD010154); its archive has no protein table
- Not fetched since 23 October 2026: the yeast interactome. Its timsTOF `evidence.txt` leaves `Modified sequence` empty on all 8,568,474 match-between-runs rows, so apb2 refuses it
- Spectronaut / DIA-NN reports: LargeFC (main, SN15 re-run, DIA-NN re-run), Charité DIA-NN, iq long-format example
- `quicktests`: three shortened DIA-NN, MaxQuant and Spectronaut inputs

Limits for APB:

- No parameter files: conversion needs `--software`, as in the `convert_no_param` workflow
- Fractionated Kuster tissue: `evidence.txt` (324 raw files) and `peptides.txt` (9 experiments) have different samples, which APB writes to separate results; the corpus therefore runs them as two datasets, `kuster_tissue_data_evidence` and `kuster_tissue_data_peptides`

## MSstats+ DIA reports — Spectronaut and DIA-NN (mirror)

The largest inputs Studio has: 7 to 42 GB and up to 65 million rows per table. They are the reports of the MSstats+ paper (Kohler et al., Nature Communications 2026, doi:10.1038/s41467-026-78591-w), mirrored from MassIVE reanalysis RMSV000000701, with TPCPA's native report from PRIDE PXD054790, where two of them sit only inside tar archives.

- DOI: [10.5281/zenodo.23615038](https://doi.org/10.5281/zenodo.23615038)
- Size: 19 files, 21.9 GB as stored, 99.7 GB uncompressed
- Layout: MassIVE path flattened with `__`, spaces as `_`; text gzipped, Parquet as deposited; `manifest.tsv` carries MassIVE paths and checksums
- Staging scripts: `zenodo_msstats_plus/` in [extend_directflq_benchmark](https://github.com/wolski/extend_directflq_benchmark)

| Dataset | Software | Input | Rows | Runs | Uncompressed |
| --- | --- | --- | --- | --- | --- |
| K562_Spectronaut | Spectronaut 19 | fragment-level `Report.tsv` | 27,815,940 | 45 | 22.8 GB |
| CSF_Spectronaut | Spectronaut 19 | fragment-level `Report.tsv` | 8,840,227 | 47 | 7.4 GB |
| K562_DIANN | DIA-NN 2 | `report.parquet` | 3,040,701 | 40 | 0.6 GB |
| CSF_DIANN | DIA-NN 2 | `report.parquet` | 673,791 | 40 | 0.1 GB |
| Mix_of_Proteome | Spectronaut 19 | fragment-level report | 29,823,948 | 18 | 26.7 GB |
| TPCPA | DIA-NN 1.8 | `diann-report.tsv` | 65,208,190 | 1,236 | 42.1 GB |

Each dataset also stores its sample annotation (`*_annotation.csv`, TPCPA's five annotation files, the mixture's `idmapping.tsv`); APB does not read them. The DIA-NN datasets keep `report.pg_matrix.tsv` beside the Parquet report.

Limits for APB:

- No parameter files: conversion needs `--software`, as in the `convert_no_param` workflow
- Size: a single conversion reads up to 42 GB of text; run the corpus one dataset at a time with `--cores 1`
- TPCPA is the native DIA-NN 1.8 report from PRIDE PXD054790; the MSstats+ authors' corrected copy in MassIVE ends in a truncated row. apb2 does not yet convert it on a 48 GiB machine: the OS kills it in `parse.decompose` at every level
