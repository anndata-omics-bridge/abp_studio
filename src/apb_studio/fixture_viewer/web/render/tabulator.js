import { TabulatorFull } from '../vendor/tabulator.js'
import { removeSection, sectionFor, updateSection } from './section.js'

// The table backend. Construction is asynchronous: Tabulator builds the table after
// the constructor returns, and calling `replaceData` before `tableBuilt` fires throws.
// `mount` waits for that event.

const DEFAULTS = {
  layout: 'fitColumns',
  placeholder: 'No rows',
  columnDefaults: { headerHozAlign: 'left', resizable: true }
}

export const tableRenderer = {
  name: 'table',

  /**
   * Build a table into a new section of the host.
   *
   * @param {HTMLElement} host The panel host.
   * @param {object} view The view to render.
   * @returns {Promise<object>} The handle for later calls.
   */
  async mount (host, view) {
    const { section, body } = sectionFor(host, view)
    const table = new TabulatorFull(body, {
      ...DEFAULTS,
      ...view.options,
      data: view.rows,
      columns: view.columns
    })
    await new Promise((resolve) => table.on('tableBuilt', resolve))
    const handle = { section, body, table, view }
    for (const name of Object.keys(view.events ?? {})) {
      table.on(name, (...args) => handle.view.events?.[name]?.(...args))
    }
    return handle
  },

  /**
   * Replace a table's rows in place.
   *
   * @param {object} handle The handle from `mount`.
   * @param {object} view The new view.
   * @returns {Promise<void>} Resolves when the rows are in.
   */
  async update (handle, view) {
    handle.view = view
    updateSection(handle.body, view)
    await handle.table.replaceData(view.rows)
  },

  /**
   * Re-measure a table revealed from zero width.
   *
   * @param {object} handle The handle from `mount`.
   */
  resize (handle) {
    handle.table.redraw(true)
  },

  /**
   * Tear a table down.
   *
   * @param {object} handle The handle from `mount`.
   */
  destroy (handle) {
    handle.table.destroy()
    removeSection(handle.body)
  }
}
