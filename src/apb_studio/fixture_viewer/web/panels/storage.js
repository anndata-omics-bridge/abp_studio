// What the store holds and how big it is.

const COLUMNS = [
  { title: '', field: 'key', width: 220 },
  { title: '', field: 'value' }
]

/**
 * Describe the storage facts table.
 *
 * @param {Array<{key: string, value: string}>} rows Key/value rows.
 * @returns {object} A table view.
 */
export function storageView (rows) {
  return {
    key: 'storage',
    backend: 'table',
    title: 'Storage',
    rows,
    columns: COLUMNS,
    options: { layout: 'fitColumns', headerVisible: false }
  }
}
