import type { Column, Field, Filter, Resource, Row, Table, TableView, Value } from '../types.js'

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

/** A Table Schema key's columns: one name, or a list of names. */
function keyColumns (value: unknown): string[] {
  if (typeof value === 'string') return [value]
  return Array.isArray(value) ? value.filter((column): column is string => typeof column === 'string') : []
}

/** Each column's key mark from a schema: `[PK]` for a one-column primary key, `[K]` for a column
 * of a primary key of several, `[FK]` for a column of a foreign key; none for other columns. */
export function keyMarks (schema: Record<string, unknown>): Map<string, string> {
  const primary = keyColumns(schema.primaryKey)
  const foreign = new Set((Array.isArray(schema.foreignKeys) ? schema.foreignKeys : [])
    .flatMap((key: unknown) => isRecord(key) ? keyColumns(key.fields) : []))
  const marks = new Map<string, string>()
  for (const column of new Set([...primary, ...foreign])) {
    const parts = [
      ...(primary.includes(column) ? [primary.length === 1 ? '[PK]' : '[K]'] : []),
      ...(foreign.has(column) ? ['[FK]'] : [])
    ]
    marks.set(column, parts.join(' '))
  }
  return marks
}

/** The stored tables datapackage.json declares, in its order, with each column's description and
 * key mark. */
export function parseResources (datapackage: unknown): Resource[] {
  const resources = isRecord(datapackage) ? datapackage.resources : undefined
  if (!Array.isArray(resources)) throw new Error('datapackage.json lists no resources')
  return resources.map((resource: unknown) => {
    const name = named(resource, 'a resource')
    const record = resource as Record<string, unknown>
    if (typeof record.path !== 'string') throw new Error(`datapackage.json resource ${name} has no path`)
    const schema = isRecord(record.schema) ? record.schema : {}
    const fields = schema.fields
    if (!Array.isArray(fields)) throw new Error(`datapackage.json resource ${name} has no schema fields`)
    const marks = keyMarks(schema)
    return {
      name,
      path: record.path,
      description: described(record.description),
      fields: fields.map((field: unknown) => {
        const column = named(field, `a field of ${name}`)
        const mark = marks.get(column)
        return {
          name: column,
          description: described((field as Record<string, unknown>).description),
          ...(mark === undefined ? {} : { mark })
        }
      })
    }
  })
}

/** Where a field of a level lives, as entry ids name it. */
export const LOCATIONS = ['obs', 'var', 'layers', 'varm']

// APB's levels from protein down; a level not listed follows them in first-seen order.
const LEVEL_ORDER = ['protein', 'peptide', 'peptidoform', 'peptidoform_ion', 'peptidoform_fragment']

/** The levels the rows name, protein first; `*`, every level, is no level of its own. */
export function levelsOf (rows: Row[]): string[] {
  const named = [...new Set(rows.map(row => cellText(row.level)))].filter(level => level !== '' && level !== '*')
  const rank = (level: string): number => {
    const at = LEVEL_ORDER.indexOf(level)
    return at === -1 ? LEVEL_ORDER.length : at
  }
  return named.sort((one, other) => rank(one) - rank(other))
}

/** A row's level and location: its own columns, or for a catalog.csv row the two halves of its
 * location, `<level>/<attribute>`. */
function placeOf (row: Row): { level: string; location: string } {
  if ('level' in row) return { level: cellText(row.level), location: cellText(row.location) }
  const [level = '', location = ''] = cellText(row.location).split('/')
  return { level, location }
}

/** The rows a filter chooses: of its set, on its level or on every level (`*`), in its
 * location; an empty choice keeps every row. */
export function chosen (rows: Row[], filter: Filter): Row[] {
  return rows.filter(row => {
    const { level, location } = placeOf(row)
    return (filter.set === '' || row.set === filter.set) &&
      (filter.level === '' || level === filter.level || level === '*') &&
      (filter.location === '' || location === filter.location)
  })
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
  const marks = new Map(fields.map(field => [field.name, field.mark]))
  return table.columns.map(field => {
    const distinct = new Set(table.rows.map(row => cellText(row[field])))
    const mark = marks.get(field)
    return {
      field,
      title: mark === undefined ? field : `${field} ${mark}`,
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

/** One stored table, the rows the filter chooses, columns as stored; the filter chooses only
 * what the table's columns hold. */
export function storedView (resource: Resource, table: Table, filter: Filter): TableView {
  const has = (column: string): boolean => table.columns.includes(column)
  const rows = chosen(table.rows, {
    set: has('set') ? filter.set : '',
    level: has('level') || has('location') ? filter.level : '',
    location: has('location') ? filter.location : ''
  })
  return tableView(resource.name, resource.path, resource.description, { columns: table.columns, rows }, resource.fields)
}
