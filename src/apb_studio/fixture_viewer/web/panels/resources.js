// Which FASTA each module uses, and whether it is on disk.

const PRESENT = { formatter: 'tickCross', hozAlign: 'center', width: 90 }

const COLUMNS = [
  { title: 'Module', field: 'module', width: 150 },
  { title: 'FASTA', field: 'fasta' },
  { title: 'Present', field: 'fasta_present', ...PRESENT }
]

/**
 * Describe the resources table.
 *
 * @param {object[]} rows Rows of resources.csv.
 * @returns {object} A table view.
 */
export function resourcesView (rows) {
  const typed = rows.map((row) => ({
    ...row,
    fasta_present: row.fasta_present === 'True'
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
