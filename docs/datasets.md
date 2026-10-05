# External datasets

Two Zenodo records hold search-engine outputs that ProteoBench submissions do not provide. The Fixture Manager acquires each into its own corpus; `config/zenodo.toml` lists the records, their datasets and the files each dataset stores.

| Record | Acquire | Corpus | Workflows |
| --- | --- | --- | --- |
| MaxQuant entrapment | `uv run fixture corpus maxquant-entrapment` | `maxquant_entrapment` | any conversion workflow |
| directLFQ mirror | `uv run fixture corpus directlfq` | `directlfq` | `convert_no_param` only: no parameter files |

Each dataset lands decompressed and MD5-verified in `test_data_download/zenodo/<record>/<dataset>/`, and gets a `downloads.csv` row keyed by `zenodo/<record>` and the dataset name. A dataset of related tables is one corpus row naming its folder; APB reads the tables inside by their MaxQuant names. A dataset without a parameter file has an empty `vendor_parameter_file`, which workflows reading vendor parameters refuse.

## ProteoBench entrapment DIA — MaxQuant 2.8.1.0 related tables

The only complete set of related MaxQuant tables available to Studio. ProteoBench submissions carry the ion-level table alone, so APB's multi-table joins (peptide, peptidoform and protein levels joined to the ion level) are otherwise exercised only by synthetic unit-test tables.

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

- DOI: [10.5281/zenodo.22301508](https://doi.org/10.5281/zenodo.22301508); concept DOI 10.5281/zenodo.22301507
- Size: 16 tables, 6.8 GB gzipped, 37.4 GB uncompressed
- Layout: original archive path flattened with `__` as separator; `manifest.tsv` maps each file to its original path with checksums
- Companion repository: [extend_directflq_benchmark](https://github.com/wolski/extend_directflq_benchmark), whose `BENCHMARKS.md` maps datasets to the paper's figures

Contents:

- MaxQuant `evidence.txt` and `peptides.txt`: BoxCar (PXD006109), Kuster 200 HeLa replicates (PXD015087), Kuster tissue (PXD010154), yeast interactome
- Spectronaut / DIA-NN reports: LargeFC (main, SN15 re-run, DIA-NN re-run), Charité DIA-NN, iq long-format example
- `quicktests`: three shortened DIA-NN, MaxQuant and Spectronaut inputs

Limits for APB:

- No parameter files: conversion needs `--software`, as in the `convert_no_param` workflow
- No `proteinGroups.txt`: MaxQuant sets cover ion and peptide levels only
