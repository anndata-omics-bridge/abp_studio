// The submissions table: one row per catalogued submission, joined with what is
// on disk. Pure: rows in, view descriptor out.

const YES_NO = { formatter: 'tickCross', formatterParams: { allowEmpty: true }, hozAlign: 'center', width: 85 }

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

// A header that does not fit is a header nobody can read, so the three strategy flags
// carry a short title and say the whole of it on hover.
const SMALLEST = 'Smallest submission per '

const COLUMNS = [
  { title: 'Module', field: 'module', headerFilter: 'list', headerFilterParams: { valuesLookup: true, clearable: true }, width: 130 },
  { title: 'Software', field: 'software_name', headerFilter: 'list', headerFilterParams: { valuesLookup: true, clearable: true }, width: 170 },
  { title: 'Version', field: 'software_version', width: 130 },
  { title: 'Features', field: 'nr_feature', hozAlign: 'right', width: 95 },
  { title: 'Status', field: 'status', headerFilter: 'list', headerFilterParams: { valuesLookup: true, clearable: true }, width: 120 },
  { title: 'MB', field: 'size_mb', hozAlign: 'right', formatter: megabytes, width: 80 },
  { title: 'Rows', field: 'rows', hozAlign: 'right', width: 95 },
  { title: 'Cols', field: 'columns', hozAlign: 'right', width: 80 },
  { title: 'Format', field: 'format', width: 95 },
  { title: 'Min/ver', field: 'smallest_per_software_version', ...YES_NO, headerTooltip: `${SMALLEST}software version` },
  { title: 'Min/sw', field: 'smallest_per_software', ...YES_NO, headerTooltip: `${SMALLEST}software` },
  { title: 'Min/mod', field: 'smallest_per_module', ...YES_NO, headerTooltip: `${SMALLEST}module` },
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
