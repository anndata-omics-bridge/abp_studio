import type { Row, Table } from '../types.js'
import { cellText } from './tables.js'

// The software versions APB2 supports: each row of versions.csv with every level the
// catalogue_table rows name for it, as the catalog derives them, joined with the rows that
// name the same software, pattern and level.

// What the chosen software version and level already say about each of its entries.
const CHOSEN = ['source', 'software_version_pattern', 'level']

function names (entry: Row, level: Row): boolean {
  return entry.source === level.software &&
    entry.software_version_pattern === level.software_version_pattern &&
    entry.level === level.level
}

/** Each software version's levels, as every set's entries name them, with the number of
 * the chosen entries naming each. */
export function softwareList (versions: Table, every: Row[], chosen: Row[]): Table {
  const rows: Row[] = []
  for (const version of versions.rows) {
    const named = every.filter(entry => entry.source === version.software && entry.software_version_pattern === version.software_version_pattern)
    for (const level of new Set(named.map(entry => entry.level))) {
      const row = { ...version, level }
      rows.push({ ...row, entries: chosen.filter(entry => names(entry, row)).length })
    }
  }
  return { columns: [...versions.columns, 'level', 'entries'], rows }
}

/** The entries one software version and level counts, one row each, without the columns
 * the version and level fix or none of them fills. */
export function versionEntries (entries: Table, level: Row): Table {
  const rows = entries.rows.filter(entry => names(entry, level))
  const columns = entries.columns.filter(column => !CHOSEN.includes(column) && rows.some(row => cellText(row[column]) !== ''))
  return { columns, rows }
}
