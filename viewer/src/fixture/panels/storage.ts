import type { ColumnDefinition } from '../../shared/tabulator.js'
import type { Fact, TableView } from '../types.js'

// What the store holds and how big it is.

const COLUMNS: ColumnDefinition[] = [
  { title: '', field: 'key', width: 220 },
  { title: '', field: 'value' }
]

export function storageView (rows: Fact[]): TableView {
  return {
    key: 'storage',
    backend: 'table',
    title: 'Storage',
    rows,
    columns: COLUMNS,
    options: { layout: 'fitColumns', headerVisible: false }
  }
}
