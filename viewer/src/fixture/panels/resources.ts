import type { ColumnDefinition } from '../../shared/tabulator.js'
import type { CsvRow, TableView } from '../types.js'

// Which FASTA and SDRF each module uses, and whether each is on disk.

const PRESENT: Partial<ColumnDefinition> = { formatter: 'tickCross', hozAlign: 'center', width: 90 }

const COLUMNS: ColumnDefinition[] = [
  { title: 'Module', field: 'module', width: 150 },
  { title: 'FASTA', field: 'fasta' },
  { title: 'Present', field: 'fasta_present', ...PRESENT },
  { title: 'SDRF', field: 'sdrf' },
  { title: 'Present', field: 'sdrf_present', ...PRESENT }
]

export function resourcesView (rows: CsvRow[]): TableView {
  const typed = rows.map((row) => ({
    ...row,
    fasta_present: row.fasta_present === 'True',
    sdrf_present: row.sdrf_present === 'True'
  }))
  return {
    key: 'resources',
    backend: 'table',
    title: 'Module resources',
    rows: typed,
    columns: COLUMNS,
    options: { layout: 'fitColumns' }
  }
}
