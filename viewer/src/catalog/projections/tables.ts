import type { Column, Field, Resource, Row, Table, TableView, Value } from '../types.js'

// Stored tables as the bundle holds them: datapackage.json names the tables and
// describes their columns. Pure: rows in, view descriptors out.

// A column with at most this many distinct values filters by a value list, others by text.
const LIST_FILTER_LIMIT = 40

function isRecord (value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function described (value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function named (value: unknown, what: string): string {
  if (!isRecord(value) || typeof value.name !== 'string') throw new Error(`datapackage.json has ${what} without a name`)
  return value.name
}

/** The stored tables datapackage.json declares, in its order, with each column's description. */
export function parseResources (datapackage: unknown): Resource[] {
  const resources = isRecord(datapackage) ? datapackage.resources : undefined
  if (!Array.isArray(resources)) throw new Error('datapackage.json lists no resources')
  return resources.map((resource: unknown) => {
    const name = named(resource, 'a resource')
    const record = resource as Record<string, unknown>
    if (typeof record.path !== 'string') throw new Error(`datapackage.json resource ${name} has no path`)
    const fields = isRecord(record.schema) ? record.schema.fields : undefined
    if (!Array.isArray(fields)) throw new Error(`datapackage.json resource ${name} has no schema fields`)
    return {
      name,
      path: record.path,
      description: described(record.description),
      fields: fields.map((field: unknown) => ({
        name: named(field, `a field of ${name}`),
        description: described((field as Record<string, unknown>).description)
      }))
    }
  })
}

/** The rows of one catalogue set, or every row when no set is chosen. */
export function inSet (rows: Row[], set: string, column = 'set'): Row[] {
  return set === '' ? rows : rows.filter(row => row[column] === set)
}

/** One cell as text: lists joined by `; `, missing values empty. */
export function cellText (value: Value | undefined): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(cellText).join('; ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Rows as apb-catalog-ts returns them, with their columns in first-seen order. */
export function tableOf (rows: Row[]): Table {
  const columns: string[] = []
  for (const row of rows) {
    for (const column of Object.keys(row)) if (!columns.includes(column)) columns.push(column)
  }
  return { columns, rows }
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

/** One table to show, its header tooltips from the column descriptions given. */
export function tableView (key: string, title: string, description: string, table: Table, fields: Field[] = []): TableView {
  const legend = fields.filter(field => field.description !== '' && table.columns.includes(field.name))
  return { key, title, description, columns: columnsOf(table, fields), rows: table.rows, legend }
}

/** One stored table, rows of the chosen set only, columns as stored. */
export function storedView (resource: Resource, table: Table, set: string): TableView {
  const rows = table.columns.includes('set') ? inSet(table.rows, set) : table.rows
  return tableView(resource.name, resource.path, resource.description, { columns: table.columns, rows }, resource.fields)
}
