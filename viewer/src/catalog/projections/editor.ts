// The catalog editor, a demo: the stored tables held as editable rows of text, checked against the
// keys and constraints datapackage.json declares, and written back as CSV files in a zip. Pure: no DOM.

import type { TableState } from '../types.js'
import { keyMarks } from './tables.js'

export type Cells = Record<string, string>

/** One row being edited; `id` stays the same while its cells change. */
export interface DraftRow { id: number; cells: Cells }

/** A foreign key: the row's `fields` must name a row of `resource` with those `reference` values. */
export interface ForeignKey { fields: string[]; resource: string; reference: string[] }

/** One stored table's shape, as datapackage.json declares it. */
export interface Schema {
  name: string
  path: string
  columns: string[]
  primaryKey: string[]
  foreignKeys: ForeignKey[]
  /** Columns of type boolean, edited as true or false. */
  booleans: string[]
  /** Columns with a pattern constraint, which every value must match. */
  patterns: Record<string, string>
  /** Columns datapackage.json marks required: a row must fill them. */
  required: string[]
  /** Columns datapackage.json marks unique: no two rows share a value. */
  unique: string[]
  /** Columns of the primary key or a foreign key. */
  keys: string[]
  /** Each key column's mark, as the stored tables show it: `[PK]`, `[K]`, `[FK]`. */
  marks: Record<string, string>
  /** What each column holds. */
  descriptions: Record<string, string>
}

/** Something a cell lacks or breaks. `broken`: a repeated primary key, a foreign key no row
 * answers, a broken pattern, or an empty required key or patterned cell; the tables would not
 * load. `incomplete`: an empty required cell that describes; they load, but say too little.
 * `resolvable`: a foreign key whose missing row the editor can add. */
export interface Problem { table: string; id: number; column: string; message: string; level: 'broken' | 'incomplete'; resolvable: boolean }

/** A file of a saved zip. */
export interface DraftFile { name: string; text: string }

/** The tables written from APB2's rules, shown but never edited. */
export const READ_ONLY = ['versions']

/** Columns each table fills itself: a catalog.csv row repeats its term's kind, PSI-MS terms and
 * whether the term fixes the row's qualifier value, so the editor takes them from terms.csv. */
export const DERIVED: Record<string, string[]> = { catalog: ['kind', 'fixed', 'psi_ms'] }

/** The columns one APB2 rule level writes, from the rules bundle's levels.json, and for each
 * name, as `<key>/<column>`, the vendor column it is read from and the rule's note on it. */
export interface RuleColumns {
  software: string
  pattern: string
  level: string
  layers: string[]
  obs: string[]
  var: string[]
  details: Record<string, { source: string; note: string }>
}

/** Every rule level's columns: its layers, and its obs and var columns with their key columns. */
export function parseRuleLevels (bundle: unknown): RuleColumns[] {
  const levels = isRecord(bundle) && Array.isArray(bundle.levels) ? bundle.levels : []
  const named = (list: unknown): string[] => (Array.isArray(list) ? list : []).filter(isRecord).map(item => String(item.name))
  return levels.filter(isRecord).flatMap(level => (Array.isArray(level.declarations) ? level.declarations : []).filter(isRecord).map(entry => {
    const declared = isRecord(entry.declaration) ? entry.declaration : {}
    const columns = isRecord(declared.columns) ? declared.columns : {}
    const axis = isRecord(declared.axis) ? declared.axis : {}
    const measurements = isRecord(declared.measurements) ? declared.measurements : {}
    const details: Record<string, { source: string; note: string }> = {}
    const described = (list: unknown, name: (column: string) => string): void => {
      for (const item of (Array.isArray(list) ? list : []).filter(isRecord)) {
        details[name(String(item.name))] = {
          source: typeof item.source === 'string' ? item.source : '',
          note: typeof item.note === 'string' ? item.note : ''
        }
      }
    }
    described(measurements.layers, layer => `${layer}/-`)
    described(columns.obs, column => `-/${column}`)
    described(columns.var, column => `-/${column}`)
    return {
      software: String(declared.software_name),
      pattern: String(declared.software_version_pattern),
      level: String(declared.quantification_level),
      layers: named(measurements.layers),
      obs: [...names(axis.obs_keys), ...named(columns.obs)],
      var: [...names(axis.var_keys), ...named(columns.var)],
      details
    }
  }))
}

/** The start of a basis for a field read from a vendor column: the column and the rule's note,
 * ending in `:`, where the reviewer adds what the value means; empty for a column read by a
 * pattern, as wide tables' per-run columns are, with no note either. */
export function basisStart (detail: { source: string; note: string }): string {
  const source = detail.source.startsWith('^') ? '' : detail.source
  const text = [source, detail.note === '' ? '' : `(${detail.note})`].filter(part => part !== '').join(' ')
  return text === '' ? '' : `${text}:`
}

/** A row every row of one table needs in another, as apb-catalog's loader requires: the target
 * row shares the `columns`, holds `match`, and is added with `fill`. */
interface Needed { table: string; target: string; columns: string[]; match: Cells; fill: Cells; message: string }

const UNKNOWN_DEFINITION = 'The reviewer could not establish this.'

// A qualifier with values defines the value `unknown`, which a reviewer gives where the evidence
// does not establish one; a qualifier declared alone is being planned and needs none. Kinds have
// no `unknown`: a field whose meaning is not established is not catalogued.
const NEEDED: Needed[] = [
  { table: 'qualifiers', target: 'qualifier_values', columns: ['set', 'qualifier'], match: { value: 'unknown' }, fill: { definition: UNKNOWN_DEFINITION }, message: 'this qualifier has values, none of them unknown; a qualifier with values defines it' }
]

// A location is `<level>/<attribute>`; `*` is every level, which app and annotation entries use.
const LEVELS = ['protein', 'peptide', 'peptidoform', 'peptidoform_ion', 'peptidoform_fragment', '*']
const ATTRIBUTES = ['layers', 'var', 'obs', 'varm']

function isRecord (value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function names (value: unknown): string[] {
  if (typeof value === 'string') return [value]
  return Array.isArray(value) ? value.filter((name): name is string => typeof name === 'string') : []
}

/** Every stored table's shape. A table with a `set` column also refers to `sets.csv` by it, which
 * every table assumes and only some declare. */
export function parseSchemas (datapackage: unknown): Schema[] {
  const resources = isRecord(datapackage) && Array.isArray(datapackage.resources) ? datapackage.resources : []
  return resources.filter(isRecord).map((resource) => {
    const schema = isRecord(resource.schema) ? resource.schema : {}
    const fields = (Array.isArray(schema.fields) ? schema.fields : []).filter(isRecord)
    const name = String(resource.name)
    const columns = fields.map(field => String(field.name))
    const foreignKeys: ForeignKey[] = (Array.isArray(schema.foreignKeys) ? schema.foreignKeys : [])
      .filter(isRecord)
      .map(key => {
        const reference = isRecord(key.reference) ? key.reference : {}
        return { fields: names(key.fields), resource: String(reference.resource), reference: names(reference.fields) }
      })
    const setsTable = resources.some(other => isRecord(other) && other.name === 'sets')
    if (setsTable && name !== 'sets' && columns.includes('set') && !foreignKeys.some(key => key.resource === 'sets')) {
      foreignKeys.push({ fields: ['set'], resource: 'sets', reference: ['set'] })
    }
    const patterns: Record<string, string> = {}
    const required: string[] = []
    const unique: string[] = []
    for (const field of fields) {
      const constraints = isRecord(field.constraints) ? field.constraints : {}
      if (typeof constraints.pattern === 'string') patterns[String(field.name)] = constraints.pattern
      if (constraints.required === true) required.push(String(field.name))
      if (constraints.unique === true) unique.push(String(field.name))
    }
    const primaryKey = names(schema.primaryKey)
    return {
      name,
      path: String(resource.path),
      columns,
      primaryKey,
      foreignKeys,
      booleans: fields.filter(field => field.type === 'boolean').map(field => String(field.name)),
      patterns,
      required,
      unique,
      keys: [...new Set([...primaryKey, ...foreignKeys.flatMap(key => key.fields)])],
      marks: Object.fromEntries(keyMarks(schema)),
      descriptions: Object.fromEntries(fields.map(field => [String(field.name), typeof field.description === 'string' ? field.description : '']))
    }
  })
}

/** The values a pattern such as `^(required|recommended|optional)?$` lists; null for any other.
 * An empty cell, which `?` admits, is cleared rather than chosen. */
function patternChoices (pattern: string): string[] | null {
  const match = /^\^\(([\w|]+)\)(\?)?\$$/.exec(pattern)
  if (!match) return null
  return (match[1] ?? '').split('|')
}

const sortText = (values: Iterable<string>): string[] => [...new Set(values)].sort((one, other) => one.localeCompare(other))

/** The catalog's tables as rows being edited: added, changed and removed in memory, until saved. */
export class CatalogDraft {
  readonly schemas: Schema[]
  readonly #rows = new Map<string, DraftRow[]>()
  #next = 0
  /** Whether anything changed since the tables were loaded. */
  edited = false
  /** The columns APB2's rules write, for the names a catalog row may map; none until loaded. */
  rules: RuleColumns[] = []

  constructor (schemas: Schema[], tables: Map<string, Cells[]>) {
    this.schemas = schemas
    for (const schema of schemas) {
      this.#rows.set(schema.name, (tables.get(schema.name) ?? []).map(cells => this.#row(schema, cells)))
    }
  }

  #row (schema: Schema, cells: Cells): DraftRow {
    this.#next += 1
    return { id: this.#next, cells: Object.fromEntries(schema.columns.map(column => [column, cells[column] ?? ''])) }
  }

  schema (table: string): Schema {
    const found = this.schemas.find(schema => schema.name === table)
    if (!found) throw new Error(`No catalog table ${table}`)
    return found
  }

  /** A table's rows, of one set when it has a `set` column and a set is given. */
  rows (table: string, set = ''): DraftRow[] {
    const rows = this.#rows.get(table) ?? []
    return set === '' || !this.schema(table).columns.includes('set') ? rows : rows.filter(row => row.cells.set === set)
  }

  /** The sets `sets.csv` names now. */
  sets (): string[] {
    return this.rows('sets').map(row => row.cells.set ?? '').filter(set => set !== '')
  }

  /** A new empty row, in the set given where the table has a `set` column. */
  add (table: string, set = ''): DraftRow {
    const schema = this.schema(table)
    const row = this.#row(schema, {
      ...(schema.columns.includes('set') ? { set } : {}),
      ...(schema.columns.includes('fixed') ? { fixed: 'false' } : {})
    })
    this.#rows.get(table)?.push(row)
    this.edited = true
    return row
  }

  /** One row, by its id. */
  row (table: string, id: number): DraftRow {
    const row = this.rows(table).find(found => found.id === id)
    if (!row) throw new Error(`No row ${id} in ${table}`)
    return row
  }

  /** Change one cell; the columns the table fills itself follow, and a catalog.csv row naming a
   * field with an empty basis gets the start of one from the rule. */
  update (table: string, id: number, column: string, value: string): void {
    const row = this.row(table, id)
    row.cells[column] = value
    this.#derive(table, row)
    if (table === 'catalog' && column === 'name' && (row.cells.basis ?? '') === '') {
      const detail = this.#declared(row.cells).map(rule => rule.details[value]).find(found => found !== undefined)
      if (detail !== undefined) row.cells.basis = basisStart(detail)
    }
    this.edited = true
  }

  /** The rule levels a catalog.csv row's software, version and level name; `*` names every one. */
  #declared (cells: Cells): RuleColumns[] {
    const [software = '', version = ''] = (cells.software ?? '').split('/')
    const level = (cells.location ?? '').split('/')[0] ?? ''
    const patterns = new Set(this.rows('versions')
      .filter(row => row.cells.software === software && (version === '*' || row.cells.version === version))
      .map(row => row.cells.software_version_pattern ?? ''))
    return this.rules.filter(rule => rule.software === software && patterns.has(rule.pattern) && (level === '*' || rule.level === level))
  }

  /** The term rows a catalog.csv row maps: its set's key at its location. */
  #term (cells: Cells): DraftRow[] {
    return this.rows('terms').filter(term => term.cells.set === cells.set && term.cells.key === cells.key && term.cells.location === cells.location)
  }

  /** Fill a catalog.csv row's kind and PSI-MS terms from its term, and `fixed` true where the term
   * fixes the row's qualifier at the row's value. A row naming no term yet keeps its cells. */
  #derive (table: string, row: DraftRow): void {
    if (DERIVED[table] === undefined) return
    const term = this.#term(row.cells)
    const first = term[0]
    if (first === undefined) return
    row.cells.kind = first.cells.kind ?? ''
    row.cells.psi_ms = first.cells.psi_ms ?? ''
    const fixes = term.some(found => (found.cells.qualifier ?? '') !== '' && found.cells.qualifier === row.cells.qualifier && found.cells.value === row.cells.value)
    row.cells.fixed = fixes ? 'true' : 'false'
  }

  remove (table: string, id: number): void {
    this.#rows.set(table, this.rows(table).filter(row => row.id !== id))
    this.edited = true
  }

  /** Every editable table emptied, to start a catalog from nothing. */
  clear (): void {
    for (const schema of this.schemas) if (!READ_ONLY.includes(schema.name)) this.#rows.set(schema.name, [])
    this.edited = true
  }

  /** What a cell may hold, for a dropdown: true or false for a boolean; the values a pattern
   * lists; or, for a column of foreign keys, the values the referenced tables hold for the row's
   * other key fields filled so far. A `software` column also offers each `versions.csv` label and
   * `*`. Null for free text. */
  choices (table: string, cells: Cells, column: string): string[] | null {
    const schema = this.schema(table)
    if (column === 'set' && table !== 'sets') return this.sets()
    if (table === 'catalog' && column === 'name') return this.#names(cells)
    if (table === 'catalog' && column === 'evidence_url') {
      const source = (cells.software ?? '').split('/')[0] ?? ''
      return sortText(this.rows('catalog')
        .filter(row => source === '' || (row.cells.software ?? '').split('/')[0] === source)
        .map(row => row.cells.evidence_url ?? '')
        .filter(url => url !== ''))
    }
    if (schema.booleans.includes(column)) return ['true', 'false']
    const pattern = schema.patterns[column]
    const listed = pattern === undefined ? null : patternChoices(pattern)
    if (listed !== null) return listed
    const answers: Set<string>[] = []
    for (const key of schema.foreignKeys) {
      const at = key.fields.indexOf(column)
      const target = key.reference[at]
      if (at < 0 || target === undefined) continue
      const matches = this.rows(key.resource).filter(row => key.fields.every((field, index) => {
        const value = cells[field] ?? ''
        const reference = key.reference[index] ?? ''
        return field === column || value === '' || row.cells[reference] === value
      }))
      answers.push(new Set(matches.map(row => row.cells[target] ?? '').filter(value => value !== '')))
    }
    const [first, ...others] = answers
    const found = first === undefined ? null : [...first].filter(value => others.every(other => other.has(value)))
    if (column === 'software' && table !== 'versions') {
      const labels = this.rows('versions').flatMap(row => [`${row.cells.software ?? ''}/${row.cells.version ?? ''}`, `${row.cells.software ?? ''}/*`])
      const apps = this.rows('producers').map(row => `${row.cells.producer ?? ''}/*`)
      return sortText([...labels, ...apps, ...this.rows(table).map(row => row.cells.software ?? '')].filter(label => label !== ''))
    }
    if (column === 'location' && found === null) {
      return LEVELS.flatMap(level => ATTRIBUTES.map(attribute => `${level}/${attribute}`))
    }
    return found === null ? null : sortText(found)
  }

  /** The names a catalog.csv row may map, as `<key>/<column>`: the layers, or the obs or var
   * columns, APB2's rules write for the row's software, version and level (`*` every version or
   * level), and the names other rows already map there. */
  #names (cells: Cells): string[] {
    const attribute = (cells.location ?? '').split('/')[1] ?? ''
    const declared = this.#declared(cells)
    const written = attribute === 'layers'
      ? declared.flatMap(rule => rule.layers.map(layer => `${layer}/-`))
      : attribute === 'var' || attribute === 'obs' ? declared.flatMap(rule => rule[attribute].map(column => `-/${column}`)) : []
    const mapped = this.rows('catalog').filter(row => row.cells.software === cells.software && row.cells.location === cells.location).map(row => row.cells.name ?? '')
    return sortText([...written, ...mapped].filter(name => name !== ''))
  }

  /** Whether a row of the key's table holds these values in the key's reference columns. */
  #answers (key: ForeignKey, values: string[]): boolean {
    return this.rows(key.resource).some(target => key.reference.every((column, index) => target.cells[column] === values[index]))
  }

  /** The rows of other tables a row lacks: the cells each needs, those it is matched by first.
   * A row needs one only once the target holds rows of it, as a set needs `unknown` once it has
   * kinds. */
  #lacks (table: string, row: DraftRow): Array<{ needed: Needed; cells: Cells }> {
    return NEEDED
      .filter(needed => needed.table === table && this.schemas.some(schema => schema.name === needed.target))
      .filter(needed => needed.columns.every(column => (row.cells[column] ?? '') !== ''))
      .filter(needed => this.rows(needed.target).some(target => needed.columns.every(column => target.cells[column] === row.cells[column])))
      .map(needed => ({ needed, cells: { ...Object.fromEntries(needed.columns.map(column => [column, row.cells[column] ?? ''])), ...needed.match } }))
      .filter(({ needed, cells }) => !this.rows(needed.target).some(target => Object.entries(cells).every(([column, value]) => target.cells[column] === value)))
  }

  /** What every row lacks or breaks; see {@link Problem}. A foreign key with an empty field is not
   * checked, as a key the row leaves open, and an empty cell is checked only if required. */
  problems (): Problem[] {
    const problems: Problem[] = []
    for (const schema of this.schemas) {
      const seen = new Set<string>()
      const taken = new Map(schema.unique.map(column => [column, new Set<string>()]))
      for (const row of this.rows(schema.name)) {
        const found = (column: string, message: string, level: Problem['level'] = 'broken', resolvable = false): void => {
          problems.push({ table: schema.name, id: row.id, column, message, level, resolvable })
        }
        const key = JSON.stringify(schema.primaryKey.map(column => row.cells[column] ?? ''))
        if (schema.primaryKey.length > 0 && seen.has(key)) found(schema.primaryKey[0] ?? '', `repeats the primary key ${schema.primaryKey.join(', ')} of another row`)
        seen.add(key)
        for (const [column, values] of taken) {
          const value = row.cells[column] ?? ''
          if (value !== '' && values.has(value)) found(column, `'${value}' is already the ${column} of another row; ${column} is unique`)
          values.add(value)
        }
        if (schema.name === 'catalog' && (row.cells.basis ?? '').trim().endsWith(':')) {
          found('basis', 'basis says where the value is read from; add what it means after the colon', 'incomplete')
        }
        for (const column of schema.required) {
          if ((row.cells[column] ?? '') !== '') continue
          const shapes = schema.keys.includes(column) || column in schema.patterns
          found(column, shapes ? `${column} is empty; a key or patterned column needs a value` : `${column} is empty; datapackage.json requires it`, shapes ? 'broken' : 'incomplete')
        }
        for (const [column, pattern] of Object.entries(schema.patterns)) {
          const value = row.cells[column] ?? ''
          if (value !== '' && !new RegExp(pattern).test(value)) found(column, `'${value}' does not match ${pattern}`)
        }
        for (const foreign of schema.foreignKeys) {
          const values = foreign.fields.map(field => row.cells[field] ?? '')
          if (values.some(value => value === '') || this.#answers(foreign, values)) continue
          const column = foreign.fields.find(field => field !== 'set') ?? foreign.fields[0] ?? ''
          found(column, `${foreign.fields.join(', ')} = ${values.join(', ')} names no row of ${foreign.resource}`, 'broken', !READ_ONLY.includes(foreign.resource))
        }
        for (const { needed } of this.#lacks(schema.name, row)) found(needed.columns.at(-1) ?? '', needed.message, 'broken', true)
        if (DERIVED[schema.name] !== undefined) {
          const pinned = this.#term(row.cells).find(term => (term.cells.qualifier ?? '') !== '' && term.cells.qualifier === row.cells.qualifier)
          if (pinned !== undefined && pinned.cells.value !== row.cells.value) {
            found('value', `the term ${row.cells.key ?? ''} fixes ${pinned.cells.qualifier ?? ''} = ${pinned.cells.value ?? ''}`)
          }
        }
      }
    }
    return problems
  }

  /** Each table's state: `broken` if a row breaks something, `incomplete` if a row only lacks a
   * required description, else `complete`. */
  states (): Record<string, TableState> {
    const problems = this.problems()
    return Object.fromEntries(this.schemas.map(({ name }) => {
      const levels = new Set(problems.filter(problem => problem.table === name).map(problem => problem.level))
      return [name, levels.has('broken') ? 'broken' : levels.has('incomplete') ? 'incomplete' : 'complete']
    }))
  }

  /** Add the row each unanswered foreign key needs, its key columns filled and the rest empty,
   * and the `unknown` value each qualifier with values needs, until nothing
   * resolvable is left; a row added may need rows of its own, as a qualifier value needs its
   * qualifier. Returns how many rows each table gained. */
  resolve (): Record<string, number> {
    const added: Record<string, number> = {}
    for (let pass = 0; pass < this.schemas.length; pass += 1) {
      let grew = false
      for (const schema of this.schemas) {
        for (const row of [...this.rows(schema.name)]) {
          for (const foreign of schema.foreignKeys) {
            const values = foreign.fields.map(field => row.cells[field] ?? '')
            if (READ_ONLY.includes(foreign.resource) || values.some(value => value === '') || this.#answers(foreign, values)) continue
            const target = this.schema(foreign.resource)
            this.#rows.get(target.name)?.push(this.#row(target, Object.fromEntries(foreign.reference.map((column, index) => [column, values[index] ?? '']))))
            added[target.name] = (added[target.name] ?? 0) + 1
            grew = true
          }
          for (const { needed, cells } of this.#lacks(schema.name, row)) {
            const target = this.schema(needed.target)
            this.#rows.get(target.name)?.push(this.#row(target, { ...cells, ...needed.fill }))
            added[target.name] = (added[target.name] ?? 0) + 1
            grew = true
          }
        }
      }
      if (!grew) break
    }
    if (Object.keys(added).length > 0) this.edited = true
    return added
  }

  /** The tables as CSV files: every table for every set, or for one set only the tables with a
   * `set` column, holding its rows, as a plugin package's folder holds them. */
  files (set = ''): DraftFile[] {
    return this.schemas
      .filter(schema => set === '' || schema.columns.includes('set'))
      .map(schema => ({ name: schema.path, text: csvText(schema.columns, this.rows(schema.name, set).map(row => row.cells)) }))
  }
}

/** One CSV cell, quoted as Python's csv module quotes: where it holds a comma, a quote or a line break. */
function csvCell (value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value
}

/** A table as CSV text, header first, each line ending in `\n`. */
export function csvText (columns: string[], rows: Cells[]): string {
  return [columns, ...rows.map(cells => columns.map(column => cells[column] ?? ''))]
    .map(line => `${line.map(csvCell).join(',')}\n`).join('')
}

const CRC_TABLE = Uint32Array.from({ length: 256 }, (_, index) => {
  let crc = index
  for (let bit = 0; bit < 8; bit += 1) crc = crc & 1 ? 0xEDB88320 ^ (crc >>> 1) : crc >>> 1
  return crc >>> 0
})

function crc32 (bytes: Uint8Array): number {
  let crc = 0xFFFFFFFF
  for (const byte of bytes) crc = (CRC_TABLE[(crc ^ byte) & 0xFF] ?? 0) ^ (crc >>> 8)
  return (crc ^ 0xFFFFFFFF) >>> 0
}

// DOS date of 1980-01-01 at 00:00, the earliest a zip records; saved files carry no time.
const DOS_DATE = (1 << 5) | 1

/** Files as one zip archive, stored uncompressed, names in UTF-8. */
export function zipFiles (files: DraftFile[]): Uint8Array<ArrayBuffer> {
  const encoder = new TextEncoder()
  const local: Uint8Array[] = []
  const central: Uint8Array[] = []
  let offset = 0
  for (const file of files) {
    const name = encoder.encode(file.name)
    const data = encoder.encode(file.text)
    const crc = crc32(data)
    const head = new DataView(new ArrayBuffer(30))
    head.setUint32(0, 0x04034B50, true)
    head.setUint16(4, 20, true)
    head.setUint16(6, 0x0800, true)
    head.setUint16(12, DOS_DATE, true)
    head.setUint32(14, crc, true)
    head.setUint32(18, data.length, true)
    head.setUint32(22, data.length, true)
    head.setUint16(26, name.length, true)
    local.push(new Uint8Array(head.buffer), name, data)
    const entry = new DataView(new ArrayBuffer(46))
    entry.setUint32(0, 0x02014B50, true)
    entry.setUint16(4, 20, true)
    entry.setUint16(6, 20, true)
    entry.setUint16(8, 0x0800, true)
    entry.setUint16(14, DOS_DATE, true)
    entry.setUint32(16, crc, true)
    entry.setUint32(20, data.length, true)
    entry.setUint32(24, data.length, true)
    entry.setUint16(28, name.length, true)
    entry.setUint32(42, offset, true)
    central.push(new Uint8Array(entry.buffer), name)
    offset += 30 + name.length + data.length
  }
  const size = central.reduce((total, part) => total + part.length, 0)
  const end = new DataView(new ArrayBuffer(22))
  end.setUint32(0, 0x06054B50, true)
  end.setUint16(8, files.length, true)
  end.setUint16(10, files.length, true)
  end.setUint32(12, size, true)
  end.setUint32(16, offset, true)
  const parts = [...local, ...central, new Uint8Array(end.buffer)]
  const zip = new Uint8Array(parts.reduce((total, part) => total + part.length, 0))
  let at = 0
  for (const part of parts) {
    zip.set(part, at)
    at += part.length
  }
  return zip
}
