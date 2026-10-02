import { TabulatorFull } from '../vendor/tabulator.js'

// The table boundary follows the fixture viewer's adapter: TabulatorFull is pinned
// behind one module, construction waits for tableBuilt, and callers own the handle.

const DEFAULTS = {
  layout: 'fitDataFill',
  placeholder: 'No rows',
  columnDefaults: { headerHozAlign: 'left', resizable: true }
}

/**
 * Mount one table.
 *
 * @param {HTMLElement} host Destination.
 * @param {object[]} rows Table rows.
 * @param {object[]} columns Tabulator columns.
 * @param {object} options Tabulator options.
 * @returns {Promise<object>} Tabulator instance.
 */
export async function mountTable (host, rows, columns, options = {}) {
  host.replaceChildren()
  const table = new TabulatorFull(host, {
    ...DEFAULTS,
    ...options,
    columnDefaults: {
      ...DEFAULTS.columnDefaults,
      ...(options.columnDefaults ?? {})
    },
    data: rows,
    columns
  })
  await new Promise(resolve => table.on('tableBuilt', resolve))
  return table
}
