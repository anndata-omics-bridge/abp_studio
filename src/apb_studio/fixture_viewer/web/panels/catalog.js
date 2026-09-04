// The submissions table: one row per catalogued submission, joined with what is
// on disk. Pure: rows in, view descriptor out.

// A tick has no width of its own, so the header decides: no fixed width here either.
const FLAG = {
  formatter: 'tickCross',
  formatterParams: { allowEmpty: true },
  hozAlign: 'center',
  headerHozAlign: 'center'
}

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

// A header filter needs more room than its title, so those columns carry a floor and
// nothing carries a fixed width: `fitDataFill` then sizes each to the wider of header
// and content, which is what stops a title being clipped or a column wasting space.
const FILTERED = {
  headerFilter: 'list',
  headerFilterParams: { valuesLookup: true, clearable: true },
  minWidth: 110
}
const SMALLEST = 'Smallest submission per '

const COLUMNS = [
  { title: 'Module', field: 'module', ...FILTERED },
  { title: 'Software', field: 'software_name', ...FILTERED },
  { title: 'Version', field: 'software_version' },
  { title: 'Features', field: 'nr_feature', hozAlign: 'right' },
  { title: 'Status', field: 'status', ...FILTERED },
  { title: 'MB', field: 'size_mb', hozAlign: 'right', formatter: megabytes },
  { title: 'Rows', field: 'rows', hozAlign: 'right' },
  { title: 'Cols', field: 'columns', hozAlign: 'right' },
  { title: 'Format', field: 'format' },
  { title: 'Min/ver', field: 'smallest_per_software_version', ...FLAG, headerTooltip: `${SMALLEST}software version` },
  { title: 'Min/sw', field: 'smallest_per_software', ...FLAG, headerTooltip: `${SMALLEST}software` },
  { title: 'Min/mod', field: 'smallest_per_module', ...FLAG, headerTooltip: `${SMALLEST}module` },
  // fitDataFill has to put leftover width somewhere; the hash is the one column that
  // can use it, so it takes the slack instead of Version taking it at random.
  { title: 'Hash', field: 'intermediate_hash', minWidth: 320, widthGrow: 3 }
]

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
