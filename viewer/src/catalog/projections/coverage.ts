import type { Field, Row, Table } from '../types.js'
import { cellText } from './tables.js'

// rule_coverage rows, one per cataloged or required field of each software version
// and level, regrouped two ways: which column each software version keeps each key in,
// and which levels miss a required field. Each row carries the `set` it was asked for.

const SEPARATOR = '\u001f'
const ROW_COLUMNS = ['software', 'version', 'level']

function keyOf (row: Row, columns: string[]): string {
  return columns.map(column => cellText(row[column])).join(SEPARATOR)
}

/** A row an app writes after conversion, the same for every software version. */
function written (row: Row): boolean {
  return row.producer !== null && row.producer !== undefined
}

/** A row's qualifier values, from its `qualifier.<name>` columns, as `name=value` sorted by name. */
function qualifierPairs (row: Row): string[] {
  return Object.entries(row)
    .filter(([column, value]) => column.startsWith('qualifier.') && value !== null && value !== undefined)
    .map(([column, value]) => `${column.slice('qualifier.'.length)}=${cellText(value)}`)
    .sort()
}

/** What one key stands for: its kind, the qualifier values it fixes, and where it lives. */
function keyMeaning (row: Row): string {
  const slot = cellText(row.slot)
  return [cellText(row.kind), ...qualifierPairs(row), slot === '' ? '' : `in ${slot}`].filter(part => part !== '').join(', ')
}

/** One set's keys as columns: one row per software version and level, each cell the column
 * holding that key, or `missing required` (recommended, optional) for a required key the version lacks.
 * Fields an app writes are left to appFields. */
export function keyColumns (rows: Row[]): { table: Table; keys: Field[] } {
  const keys = new Map<string, string>()
  const lines = new Map<string, Row>()
  for (const row of rows) {
    if (written(row)) continue
    const line = lines.get(keyOf(row, ROW_COLUMNS)) ?? Object.fromEntries(ROW_COLUMNS.map(column => [column, row[column] ?? null]))
    lines.set(keyOf(row, ROW_COLUMNS), line)
    if (row.key === null || row.key === undefined) continue
    const key = cellText(row.key)
    if (!keys.has(key) || keys.get(key) === '') keys.set(key, keyMeaning(row))
    const cell = row.name === null ? `missing ${cellText(row.requirement)}` : cellText(row.name)
    const before = cellText(line[key])
    line[key] = before === '' ? cell : `${before}, ${cell}`
  }
  return {
    table: { columns: [...ROW_COLUMNS, ...keys.keys()], rows: [...lines.values()] },
    keys: [...keys].map(([name, description]) => ({ name, description }))
  }
}

/** The fields apps write: one row per key and column, its levels joined, whatever the version. */
export function appFields (rows: Row[]): Table {
  const columns = ['producer', 'key', 'slot', 'table', 'name', 'needs']
  const lines = new Map<string, { row: Row; levels: string[] }>()
  for (const row of rows.filter(written)) {
    const key = keyOf(row, columns)
    const line = lines.get(key) ?? { row: Object.fromEntries(columns.map(column => [column, row[column] ?? null])), levels: [] }
    if (!line.levels.includes(cellText(row.level))) line.levels.push(cellText(row.level))
    lines.set(key, line)
  }
  return {
    columns: ['producer', 'key', 'levels', 'slot', 'table', 'name', 'needs'],
    rows: [...lines.values()].map(({ row, levels }) => ({ ...row, levels: levels.join(', ') }))
  }
}

function missingText (row: Row): string {
  return `${cellText(row.requirement)} ${cellText(row.key)} in ${cellText(row.slot)}`
}

/** What each coverage column holds, for its header tooltip and legend. */
export const COVERAGE_FIELDS: Field[] = [
  { name: 'set', description: 'The set whose requirements.csv rows judge the result.' },
  { name: 'software', description: 'The quantification software.' },
  { name: 'version', description: 'The software versions one APB2 rule converts, as versions.csv labels them.' },
  { name: 'level', description: 'The quantification level of the converted result: requirements differ per level, since a protein row has no peptide sequence and a fragment row needs its fragment id.' },
  { name: 'verdict', description: 'fail: a required key is missing. warn: a recommended key is missing. pass: nothing required or recommended is missing; a missing optional key is still listed.' },
  { name: 'missing', description: 'Each key the result lacks, as <requirement> <key> in <slot>: recommended peptidoform_fragment in var means no var column holds the fragment id, and the set wants one. Meanings names the column of every key the result has.' }
]

/** One row per set, software version and level the set judges: its verdict and missing fields. */
export function coverage (rows: Row[]): Table {
  const groups = new Map<string, { row: Row; missing: string[] }>()
  for (const row of rows) {
    if (row.verdict === null || row.verdict === undefined) continue
    const key = keyOf(row, ['set', 'software', 'software_version_pattern', 'level'])
    const group = groups.get(key) ?? {
      row: { set: row.set ?? null, software: row.software ?? null, version: row.version ?? null, level: row.level ?? null, verdict: row.verdict },
      missing: []
    }
    if (row.name === null && row.requirement !== null && row.requirement !== undefined) group.missing.push(missingText(row))
    groups.set(key, group)
  }
  return {
    columns: ['set', 'software', 'version', 'level', 'verdict', 'missing'],
    rows: [...groups.values()].map(({ row, missing }) => ({ ...row, missing }))
  }
}
