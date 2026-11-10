import type { Declaration, Evidence, Field, JsonView, Row, RuleLevel, Section, TableView, Value } from '../types.js'
import { cellText, isEmpty, tableOf, tableView } from './tables.js'

// One level of one rule, from its effective declarations: apb2 composed each table's base with
// the level and applied the search-parameter overrides, so nothing here merges.

const ACQUISITIONS = ['DDA', 'DIA', 'unknown']
const COMBINE_CHARGE_STATES = [true, false, null]

// Shown in their own tables, or by the rule list and level buttons, not as settings.
const OWN_TABLES = new Set(['columns', 'modification_map', 'measurements.layers', 'schema_version', 'file_version', 'software_name', 'software_version_pattern', 'quantification_level'])

export const LAYER_COLUMNS = ['name', 'primary', 'source', 'version', 'roles', 'type', 'encoding_mode', 'required', 'missing_values', 'missing_tokens', 'categories', 'value_pattern', 'note']
export const COLUMN_COLUMNS = ['name', 'source', 'version', 'inputs', 'how', 'type', 'required', 'roles', 'per_feature', 'separator', 'missing_tokens', 'note']

export const LAYER_FIELDS: Field[] = [
  { name: 'name', description: 'The layer\'s name in the APB result.' },
  { name: 'primary', description: 'primary: the level\'s primary abundance, X; sample: the layer that decides which samples a feature was seen in.' },
  { name: 'source', description: 'The column the layer reads; in a wide table, a pattern whose sample group names the sample of each column.' },
  { name: 'version', description: 'The software versions whose reports carry the source, a pattern; layers of one name read one column the tool spells differently by version.' },
  { name: 'roles', description: 'Roles the rule declares: abundance marks a layer a consumer may use as abundance.' },
  { name: 'type', description: 'The value type: number, integer, string or boolean.' },
  { name: 'encoding_mode', description: 'numeric: values as read; factor: text categories stored as integer codes.' },
  { name: 'required', description: 'true: a report without the source column is refused.' },
  { name: 'missing_values', description: 'Missing-value policy: values that become missing, such as <=0.' },
  { name: 'missing_tokens', description: 'Texts that become missing, such as NA or -.' },
  { name: 'categories', description: 'For a factor layer, each category and its integer code.' },
  { name: 'value_pattern', description: 'A pattern that extracts the value from each cell.' },
  { name: 'note', description: 'Why the rule declares the entry as it does.' }
]

export const COLUMN_FIELDS: Field[] = [
  { name: 'name', description: 'The column\'s name in the APB result.' },
  { name: 'source', description: 'The report column it reads.' },
  { name: 'version', description: 'The software versions whose reports carry the source, a pattern; columns of one name read one column the tool spells differently by version.' },
  { name: 'inputs', description: 'For a computed column, the columns it is computed from.' },
  { name: 'how', description: 'For a computed column, the computation, such as proforma_sequence.' },
  { name: 'type', description: 'The value type: string, number, integer or boolean.' },
  { name: 'required', description: 'true: a report without the source column is refused.' },
  { name: 'roles', description: 'Roles the rule declares: protein_assignment names the protein group, fasta_accessions the accessions apb-fasta looks up, gene_assignment the gene group.' },
  { name: 'per_feature', description: 'How a feature\'s repeated rows become one value: first keeps the first nonblank value, min or max the smallest or largest number, best_row the row the level\'s rank_rows keeps.' },
  { name: 'separator', description: 'The separator that splits a list column.' },
  { name: 'missing_tokens', description: 'Text the tool writes for a missing value, such as NaN, read as missing.' },
  { name: 'note', description: 'Why the rule declares the entry as it does.' }
]

const SUMMARY_FIELDS: Field[] = [
  { name: 'setting', description: 'A declaration key; a dotted name is one key inside another, such as axis.var_keys.' },
  { name: 'value', description: 'Its value; lists are joined by ;, objects listed as key=value.' }
]

function isRecord (value: Value | undefined): value is Record<string, Value> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function records (value: Value | undefined): Record<string, Value>[] {
  return Array.isArray(value) ? value.filter(isRecord) : []
}

/** Which search parameters select a declaration, in words: an acquisition method alone when
 * every charge-state setting selects it, every value when all do. */
export function evidenceLabel (evidences: Evidence[]): string {
  const methods = ACQUISITIONS.filter(method => evidences.some(evidence => evidence.acquisition_method === method))
  const every = (method: string): boolean => COMBINE_CHARGE_STATES.every(combine =>
    evidences.some(evidence => evidence.acquisition_method === method && evidence.combine_charge_states === combine))
  if (methods.length === ACQUISITIONS.length && methods.every(every)) return 'any search parameters'
  return methods.map(method => {
    if (every(method)) return method
    const combines = evidences.filter(evidence => evidence.acquisition_method === method).map(evidence => String(evidence.combine_charge_states))
    return `${method} with combine_charge_states ${combines.join(' or ')}`
  }).join(', ')
}

/** The declaration's settings, one row each: objects one key deep, empty values left out. */
export function summaryRows (declaration: Record<string, Value>): Row[] {
  const rows: Row[] = []
  for (const [key, value] of Object.entries(declaration)) {
    if (OWN_TABLES.has(key)) continue
    if (isRecord(value)) {
      for (const [inner, item] of Object.entries(value)) {
        if (!OWN_TABLES.has(`${key}.${inner}`) && !isEmpty(item)) rows.push({ setting: `${key}.${inner}`, value: cellText(item) })
      }
    } else if (!isEmpty(value)) {
      rows.push({ setting: key, value: cellText(value) })
    }
  }
  return rows
}

/** The quantity layers, the primary and sample layers marked. */
export function layerRows (declaration: Record<string, Value>): Row[] {
  const measurements = isRecord(declaration.measurements) ? declaration.measurements : {}
  return records(measurements.layers).map(layer => ({
    ...layer,
    primary: layer.name === measurements.primary_layer ? 'primary' : layer.name === measurements.sample_layer ? 'sample' : null
  }))
}

/** The `var` or `obs` columns the declaration selects or computes. */
export function columnRows (declaration: Record<string, Value>, group: 'var' | 'obs'): Row[] {
  return isRecord(declaration.columns) ? records(declaration.columns[group]) : []
}

/** The level's modification map, one row per token and the Unimod accession it maps to. */
export function modificationRows (declaration: Record<string, Value>): Row[] {
  const tokens = isRecord(declaration.modification_map) ? declaration.modification_map : {}
  return Object.entries(tokens).map(([token, accession]): Row => ({ token, accession }))
}

// Every leaf of a value by path; list items with a name are keyed by it, and by their version where
// entries of one name read one column per version, so a layer keeps its path.
function leaves (value: Value, path: string, out: Map<string, string>): void {
  if (Array.isArray(value) && value.length > 0 && value.every(item => isRecord(item) && typeof item.name === 'string')) {
    for (const item of value) leaves(item, `${path}[${itemKey(item as Record<string, Value>)}]`, out)
  } else if (isRecord(value) && Object.keys(value).length > 0) {
    for (const [key, item] of Object.entries(value)) leaves(item, path === '' ? key : `${path}.${key}`, out)
  } else {
    out.set(path, cellText(value))
  }
}

function itemKey (item: Record<string, Value>): string {
  return typeof item.version === 'string' ? `${String(item.name)} ${item.version}` : String(item.name)
}

/** The settings in which a level's declarations differ, one column per declaration named by the
 * search parameters that select it. */
export function variantRows (declarations: Declaration[]): { columns: string[]; rows: Row[] } {
  const labels = declarations.map(declaration => evidenceLabel(declaration.selected_by))
  const flat = declarations.map(declaration => {
    const out = new Map<string, string>()
    leaves(declaration.declaration, '', out)
    return out
  })
  const paths = [...new Set(flat.flatMap(map => [...map.keys()]))]
  const rows = paths.filter(path => new Set(flat.map(map => map.get(path) ?? '')).size > 1)
    .map(path => Object.fromEntries([['setting', path], ...labels.map((label, index) => [label, flat[index]?.get(path) ?? ''])]) as Row)
  return { columns: ['setting', ...labels], rows }
}

/** What the Rule tab shows for one level, one tab each: settings, the differences between its
 * declarations, layers, columns, modification map, and each declaration as stored. */
export function levelPage (level: RuleLevel): Section[] {
  const [first] = level.declarations
  if (!first) return []
  const declaration = first.declaration
  const several = level.declarations.length > 1
  const key = `${level.rule}:${level.level}`
  const sections: Section[] = []
  const add = (id: string, view: TableView): void => { sections.push({ id, label: view.title, tables: [view], json: [] }) }
  const settings = summaryRows(declaration)
  settings.splice(0, 0, { setting: 'selected by', value: several ? level.declarations.map(item => evidenceLabel(item.selected_by)).join(' / ') : evidenceLabel(first.selected_by) })
  add('settings', tableView(`${key}:settings`, 'Settings', several ? `This level has ${level.declarations.length} declarations; the settings are those of the first, ${evidenceLabel(first.selected_by)}, and Variants lists where the others differ.` : 'Axis keys, primary layer, duplicate policy, sequence syntax and search-parameter conditions, as conversion stores them.', tableOf(settings, ['setting', 'value']), SUMMARY_FIELDS))
  if (several) {
    add('variants', tableView(`${key}:variants`, 'Variants', 'Where the declarations differ, one column per declaration, named by the search parameters that select it.', variantRows(level.declarations)))
  }
  add('layers', tableView(`${key}:layers`, 'Quantity layers', 'One matrix of samples by features each, in the order the rule declares them.', tableOf(layerRows(declaration), LAYER_COLUMNS), LAYER_FIELDS))
  // A wide table names its samples in the layer patterns, so its sample table may declare no column.
  const groups = [
    ['var', 'Feature table (var)', 'One value per feature: identifiers, experiment-wide values and computed columns such as the ProForma identifiers.'],
    ['obs', 'Sample table (obs)', 'One value per sample.']
  ] as const
  for (const [group, title, description] of groups) {
    const rows = columnRows(declaration, group)
    if (rows.length > 0) add(group, tableView(`${key}:${group}`, title, description, tableOf(rows, COLUMN_COLUMNS), COLUMN_FIELDS))
  }
  const modifications = modificationRows(declaration)
  if (modifications.length > 0) add('modifications', tableView(`${key}:modifications`, 'Modification map', 'Each modification token the tool writes and the Unimod accession it maps to.', tableOf(modifications, ['token', 'accession'])))
  const json = level.declarations.map((item, index): JsonView => ({
    key: `${key}:json:${index}`,
    title: several ? `Declaration ${index + 1} as stored: ${evidenceLabel(item.selected_by)}` : 'Declaration as stored',
    description: 'The exact rule_json conversion stores for this level, every default filled in.',
    data: item.declaration
  }))
  sections.push({ id: 'stored', label: 'As stored', tables: [], json })
  return sections
}
