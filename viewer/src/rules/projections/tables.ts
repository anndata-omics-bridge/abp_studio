import type { Column, Field, Row, Table, TableView, Value } from '../types.js'

// Rows in, view descriptors out. Pure, as the catalog viewer's table projections are.

// A column with at most this many distinct values filters by a value list, others by text.
const LIST_FILTER_LIMIT = 40

/** Whether a value says nothing: missing, an empty text, list or object. */
export function isEmpty (value: Value | undefined): boolean {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.values(value).every(isEmpty)
  return false
}

/** One cell as text: lists joined by `; `, objects as `key=value` without the empty ones. */
export function cellText (value: Value | undefined): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(cellText).join('; ')
  if (typeof value === 'object') {
    return Object.entries(value).filter(([, item]) => !isEmpty(item))
      .map(([key, item]) => `${key}=${typeof item === 'object' && item !== null && !Array.isArray(item) ? `{${cellText(item)}}` : cellText(item)}`)
      .join('; ')
  }
  return String(value)
}

/** Rows with the columns that hold a value in some row: `preferred` first, then the others in
 * first-seen order. */
export function tableOf (rows: Row[], preferred: string[] = []): Table {
  const seen: string[] = []
  for (const row of rows) {
    for (const column of Object.keys(row)) if (!seen.includes(column)) seen.push(column)
  }
  const ordered = [...preferred.filter(column => seen.includes(column)), ...seen.filter(column => !preferred.includes(column))]
  return { columns: ordered.filter(column => rows.some(row => !isEmpty(row[column]))), rows }
}

function columnsOf (table: Table, fields: Field[]): Column[] {
  const descriptions = new Map(fields.map(field => [field.name, field.description]))
  return table.columns.map(field => {
    const distinct = new Set(table.rows.map(row => cellText(row[field])))
    return {
      field,
      title: field,
      tooltip: descriptions.get(field) ?? '',
      filter: distinct.size <= LIST_FILTER_LIMIT ? 'list' : 'input'
    }
  })
}

/** One table to show, its header tooltips and legend from the column descriptions given. */
export function tableView (key: string, title: string, description: string, table: Table, fields: Field[] = []): TableView {
  const legend = fields.filter(field => field.description !== '' && table.columns.includes(field.name))
  return { key, title, description, columns: columnsOf(table, fields), rows: table.rows, legend }
}
