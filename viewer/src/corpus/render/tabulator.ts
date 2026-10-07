import type { ColumnDefinition, Options, Tabulator } from '../../shared/tabulator.js'
import { TabulatorFull } from '../../shared/tabulator.js'

// The table boundary follows the fixture viewer's adapter: TabulatorFull is pinned
// behind one module, construction waits for tableBuilt, and callers own the handle.

const DEFAULTS: Options = {
  layout: 'fitDataFill',
  placeholder: 'No rows',
  columnDefaults: { headerHozAlign: 'left', resizable: true }
}

/** Mount one table and wait until its methods are ready. */
export async function mountTable (host: HTMLElement, rows: object[], columns: ColumnDefinition[], options: Options = {}): Promise<Tabulator> {
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
  await new Promise<void>(resolve => table.on('tableBuilt', resolve))
  return table
}
