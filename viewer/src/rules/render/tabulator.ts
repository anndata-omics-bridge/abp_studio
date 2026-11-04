import type { ColumnDefinition, Options, Tabulator } from '../../shared/tabulator.js'
import { TabulatorFull } from '../../shared/tabulator.js'
import { cellText } from '../projections/tables.js'
import type { Column, Row, TableView } from '../types.js'

// The table boundary follows the other viewers' adapters: TabulatorFull is pinned behind
// one module, construction waits for tableBuilt, and callers own the handle.

const ROW = '_row'

const DEFAULTS: Options = {
  layout: 'fitDataFill',
  placeholder: 'No rows',
  maxHeight: '75vh',
  // Field names such as `qualifier.kind` are flat keys, not paths into nested data.
  nestedFieldSeparator: false,
  columnDefaults: { headerHozAlign: 'left', resizable: true }
}

function definition (column: Column): ColumnDefinition {
  return {
    title: column.title,
    field: column.field,
    minWidth: 90,
    // Patterns and notes run long; a cell shows their start and its hover the whole text.
    maxWidth: 360,
    tooltip: true,
    ...(column.tooltip ? { headerTooltip: column.tooltip } : {}),
    ...(column.filter === 'list'
      ? { headerFilter: 'list', headerFilterParams: { valuesLookup: 'all', clearable: true } }
      : { headerFilter: 'input' })
  }
}

/** Mount one view as a titled section; `select` hears which of the view's rows was clicked. */
export async function mountTable (host: HTMLElement, view: TableView, select?: (row: Row) => void): Promise<Tabulator> {
  const section = document.createElement('section')
  section.className = 'view'
  const heading = document.createElement('h3')
  heading.textContent = view.title
  section.append(heading)
  if (view.description) {
    const description = document.createElement('p')
    description.textContent = view.description
    section.append(description)
  }
  if (view.legend.length > 0) {
    const legend = document.createElement('details')
    legend.className = 'legend'
    const summary = document.createElement('summary')
    summary.textContent = 'Columns'
    const list = document.createElement('dl')
    for (const field of view.legend) {
      const name = document.createElement('dt')
      name.textContent = field.name
      const text = document.createElement('dd')
      text.textContent = field.description
      list.append(name, text)
    }
    legend.append(summary, list)
    section.append(legend)
  }
  const body = document.createElement('div')
  section.append(body)
  host.append(section)
  // Tabulator shows each cell as text; the row number leads clicks back to the row given.
  const data = view.rows.map((row, index) => ({
    ...Object.fromEntries(view.columns.map(({ field }) => [field, cellText(row[field])])),
    [ROW]: index
  }))
  const table = new TabulatorFull(body, { ...DEFAULTS, index: ROW, data, columns: view.columns.map(definition) })
  await new Promise<void>(resolve => table.on('tableBuilt', resolve))
  if (select) {
    table.on('rowClick', (_event, tableRow) => {
      const index: unknown = tableRow.getIndex()
      const row = typeof index === 'number' ? view.rows[index] : undefined
      if (row) select(row)
    })
  }
  return table
}
