// The submissions table: one row per catalogued submission, joined with what is
// on disk. Pure: rows in, view descriptor out.

const YES_NO = { formatter: 'tickCross', formatterParams: { allowEmpty: true }, hozAlign: 'center', width: 70 }

/**
 * Format megabytes with one decimal.
 *
 * @param {object} cell A Tabulator cell.
 * @returns {string} The display text.
 */
function megabytes (cell) {
  const value = cell.getValue()
  return value === null || value === undefined ? '' : value.toFixed(1)
}

const COLUMNS = [
  { title: 'Module', field: 'module', headerFilter: 'list', headerFilterParams: { valuesLookup: true, clearable: true }, width: 130 },
  { title: 'Software', field: 'software_name', headerFilter: 'list', headerFilterParams: { valuesLookup: true, clearable: true }, width: 170 },
  { title: 'Version', field: 'software_version', width: 130 },
  { title: 'Features', field: 'nr_feature', hozAlign: 'right', width: 90 },
  { title: 'Status', field: 'status', headerFilter: 'list', headerFilterParams: { valuesLookup: true, clearable: true }, width: 120 },
  { title: 'MB', field: 'size_mb', hozAlign: 'right', formatter: megabytes, width: 80 },
  { title: 'Rows', field: 'rows', hozAlign: 'right', width: 90 },
  { title: 'Cols', field: 'columns', hozAlign: 'right', width: 60 },
  { title: 'Format', field: 'format', width: 90 },
  { title: 'Per sw/version', field: 'smallest_per_software_version', ...YES_NO, width: 110 },
  { title: 'Per software', field: 'smallest_per_software', ...YES_NO, width: 100 },
  { title: 'Per module', field: 'smallest_per_module', ...YES_NO, width: 90 },
  { title: 'Hash', field: 'intermediate_hash', width: 320 }
]

/**
 * Describe the submissions table.
 *
 * @param {object[]} rows Joined submission rows.
 * @param {object} events Tabulator event handlers, e.g. `rowClick`.
 * @returns {object} A table view.
 */
export function catalogView (rows, events = {}) {
  return {
    key: 'catalog',
    backend: 'table',
    title: `Submissions (${rows.length})`,
    rows,
    columns: COLUMNS,
    options: { layout: 'fitDataFill', height: '55vh', selectableRows: 1, initialSort: [{ column: 'module', dir: 'asc' }] },
    events
  }
}
