# Problem corpus

`problems.csv` collects the submissions that fail, or convert into questionable results, for a known reason; one row per submission. Run it with `uv run corpus run problems --workflow <name>`. Failures were confirmed on 8 October with `scripts/routine_corpuses.fish`, `scripts/export_corpuses.fish` and `aggregate`.

## Failing

| Submission | Module | Software | Problem | Fails in |
| --- | --- | --- | --- | --- |
| `fc1bf3c2` | dda_astral | Sage | Peptide-level `lfq.tsv`, no ion level | `convert_ion`, every ion export, ProteoBench scoring |
| `51b4f2e8`, `557e8c64`, `e6d810fc` | dda_peptidoform | WOMBAT | Peptidoform table, no ion level | `convert_ion`, every ion export |
| `aa1d53e8`, `5691d485` | dia_astral, dia_diapasef | PEAKS | Target identity with a missing value | `aggregate`, `aggregate_medpolish` |
| `5691d485` | dia_diapasef | PEAKS | Module sample `ttSCP_diaPASEF_Condition_A_Sample_Alpha_02_11500` absent from quantification | every ProteoBench workflow |

## Converting, with peptides matching the FASTA only as I/L

| Submission | Module | Software | Problem |
| --- | --- | --- | --- |
| `91a49761` | dia_aif | FragPipe (DIA-NN quant) | 82 peptides match their FASTA protein only with I/L equivalence |
