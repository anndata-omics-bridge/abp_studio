import { TabulatorFull } from '../../shared/tabulator.js'
import type { Options, Tabulator } from '../../shared/tabulator.js'
import type { Renderer, TableView } from '../types.js'
import { removeSection, sectionFor } from './section.js'

interface TableHandle { body: HTMLElement; table: Tabulator }

const DEFAULTS: Options = {
  layout: 'fitColumns',
  placeholder: 'No rows',
  columnDefaults: { headerHozAlign: 'left', resizable: true }
}

export const tableRenderer: Renderer<TableView, TableHandle> = {
  name: 'table',
  async mount (host, view) {
    const { body } = sectionFor(host, view)
    const table = new TabulatorFull(body, {
      ...DEFAULTS,
      ...view.options,
      data: view.rows,
      columns: view.columns
    })
    // Tabulator builds asynchronously; wait before exposing the mounted table.
    await new Promise<void>((resolve) => table.on('tableBuilt', resolve))
    if (view.events?.rowClick) table.on('rowClick', view.events.rowClick)
    return { body, table }
  },
  resize (handle) {
    handle.table.redraw(true)
  },
  destroy (handle) {
    handle.table.destroy()
    removeSection(handle.body)
  }
}
