import type { Field, Row, Table } from '../types.js'
import { cellText } from './tables.js'

// rule_coverage rows, one per catalogued or required field of each software version
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

/** What one key stands for: its kind, the qualifier values it fixes, and where it lives. */
function keyMeaning (row: Row): string {
  const qualifiers = cellText(row.qualifiers).replaceAll(';', ', ')
  const location = cellText(row.location)
  return [cellText(row.kind), qualifiers, location === '' ? '' : `in ${location}`].filter(part => part !== '').join(', ')
}

/** One set's keys as columns: one row per software version and level, each cell the column
 * holding that key, or `missing MUST` (SHOULD, MAY) for a required key the version lacks.
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
    const cell = row.column === null ? `missing ${cellText(row.requirement)}` : cellText(row.column)
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
  const columns = ['producer', 'key', 'location', 'table', 'column', 'needs']
  const lines = new Map<string, { row: Row; levels: string[] }>()
  for (const row of rows.filter(written)) {
    const key = keyOf(row, columns)
    const line = lines.get(key) ?? { row: Object.fromEntries(columns.map(column => [column, row[column] ?? null])), levels: [] }
    if (!line.levels.includes(cellText(row.level))) line.levels.push(cellText(row.level))
    lines.set(key, line)
  }
  return {
    columns: ['producer', 'key', 'levels', 'location', 'table', 'column', 'needs'],
    rows: [...lines.values()].map(({ row, levels }) => ({ ...row, levels: levels.join(', ') }))
  }
}

function missingText (row: Row): string {
  return `${cellText(row.requirement)} ${cellText(row.key)} in ${cellText(row.location)}`
}

/** What each coverage column holds, for its header tooltip and legend. */
export const COVERAGE_FIELDS: Field[] = [
  { name: 'set', description: 'The catalogue set whose requirements.csv rows judge the result.' },
  { name: 'software', description: 'The conversion software.' },
  { name: 'version', description: 'The software versions one APB2 rule converts, as versions.csv labels them.' },
  { name: 'level', description: 'The quantification level of the converted result: requirements differ per level, since a protein row has no peptide sequence and a fragment row needs its fragment id.' },
  { name: 'verdict', description: 'fail: a MUST key is missing. warn: only SHOULD or MAY keys are missing. pass: nothing the set requires is missing.' },
  { name: 'missing', description: 'Each key the result lacks, as <requirement> <key> in <slot>: SHOULD peptidoform_fragment in var means no var column holds the fragment id, and the set wants one. Meanings names the column of every key the result has.' }
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
    if (row.column === null && row.requirement !== null && row.requirement !== undefined) group.missing.push(missingText(row))
    groups.set(key, group)
  }
  return {
    columns: ['set', 'software', 'version', 'level', 'verdict', 'missing'],
    rows: [...groups.values()].map(({ row, missing }) => ({ ...row, missing }))
  }
}
