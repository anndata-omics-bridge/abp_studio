import type { Field, Row, RuleDocument, RuleLevel, Table, Value } from '../types.js'
import { COLUMN_COLUMNS, COLUMN_FIELDS, columnRows, evidenceLabel, LAYER_COLUMNS, LAYER_FIELDS, layerRows } from './level.js'
import { tableOf } from './tables.js'

// The tabs across rules: every rule level, every layer, every column, optionally of one level.
// A level with several declarations gives one row per declaration, named in selected_by.

const LEVEL_ORDER = ['peptidoform_fragment', 'peptidoform_ion', 'peptidoform', 'peptide', 'protein']

const WHERE = ['software', 'versions', 'rule', 'level', 'selected_by']

export const WHERE_FIELDS: Field[] = [
  { name: 'software', description: 'The quantification tool.' },
  { name: 'versions', description: 'The rule\'s software_version_pattern.' },
  { name: 'rule', description: 'The rules.json.' },
  { name: 'level', description: 'The level, one feature type.' },
  { name: 'selected_by', description: 'Only for a level with several declarations: the search parameters that select this one.' }
]

export const LEVEL_FIELDS: Field[] = [
  ...WHERE_FIELDS,
  { name: 'obs_keys', description: 'The sample-table columns that identify a sample.' },
  { name: 'var_keys', description: 'The feature-table columns that identify a feature.' },
  { name: 'primary_layer', description: 'The primary abundance, X.' },
  { name: 'abundance_layers', description: 'Every layer with the abundance role.' },
  { name: 'protein_assignment', description: 'The column with the protein_assignment role: the protein group.' },
  { name: 'fasta_accessions', description: 'The column with the fasta_accessions role: the accessions apb-fasta looks up.' },
  { name: 'layers', description: 'How many quantity layers the level declares.' },
  { name: 'var_columns', description: 'How many feature-table columns the level declares.' },
  { name: 'repeated_cells', description: 'How rows that repeat one sample and feature become one cell: error, same, sum or keep_best.' },
  { name: 'forbidden_columns', description: 'Header columns that mean a table reports another level: the level skips a table carrying one.' }
]

/** Levels fine to coarse, as apb2 orders them; any other after them. */
export function orderedLevels (levels: RuleLevel[]): string[] {
  const present = [...new Set(levels.map(level => level.level))]
  return [...LEVEL_ORDER.filter(level => present.includes(level)), ...present.filter(level => !LEVEL_ORDER.includes(level))]
}

/** The rule levels of one level, or all of them for `''`. */
export function ofLevel (levels: RuleLevel[], level: string): RuleLevel[] {
  return level === '' ? levels : levels.filter(item => item.level === level)
}

function record (value: Value | undefined): Record<string, Value> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value : {}
}

function hasRole (row: Row, role: string): boolean {
  return Array.isArray(row.roles) && row.roles.includes(role)
}

// One row per declaration of each level, each with where it comes from.
function eachDeclaration (rules: RuleDocument[], levels: RuleLevel[], rows: (declaration: Record<string, Value>) => Row[]): Row[] {
  const documents = new Map(rules.map(rule => [rule.rule, rule]))
  return levels.flatMap(level => level.declarations.flatMap(item => {
    const document = documents.get(level.rule)
    const where: Row = {
      software: document?.software_name ?? '',
      versions: document?.software_version_pattern ?? '',
      rule: level.rule,
      level: level.level,
      selected_by: level.declarations.length > 1 ? evidenceLabel(item.selected_by) : null
    }
    return rows(item.declaration).map(row => ({ ...where, ...row }))
  }))
}

/** One row per rule level: its keys, primary layer, abundance layers and role columns. */
export function levelRows (rules: RuleDocument[], levels: RuleLevel[]): Table {
  const rows = eachDeclaration(rules, levels, declaration => {
    const axis = record(declaration.axis)
    const measurements = record(declaration.measurements)
    const layers = layerRows(declaration)
    const columns = columnRows(declaration, 'var')
    return [{
      obs_keys: axis.obs_keys ?? null,
      var_keys: axis.var_keys ?? null,
      primary_layer: measurements.primary_layer ?? null,
      abundance_layers: layers.filter(layer => hasRole(layer, 'abundance')).map(layer => layer.name ?? null),
      protein_assignment: columns.filter(column => hasRole(column, 'protein_assignment')).map(column => column.name ?? null),
      fasta_accessions: columns.filter(column => hasRole(column, 'fasta_accessions')).map(column => column.name ?? null),
      layers: layers.length,
      var_columns: columns.length,
      repeated_cells: record(measurements.repeated_cells).mode ?? null,
      forbidden_columns: declaration.forbidden_columns ?? null
    }]
  })
  return tableOf(rows, LEVEL_FIELDS.map(field => field.name))
}

/** Every quantity layer of every rule level. */
export function allLayers (rules: RuleDocument[], levels: RuleLevel[]): Table {
  return tableOf(eachDeclaration(rules, levels, layerRows), [...WHERE, ...LAYER_COLUMNS])
}

/** Every feature-table and sample-table column of every rule level, `table` naming which. */
export function allColumns (rules: RuleDocument[], levels: RuleLevel[]): Table {
  const rows = eachDeclaration(rules, levels, declaration => [
    ...columnRows(declaration, 'var').map(column => ({ table: 'var', ...column })),
    ...columnRows(declaration, 'obs').map(column => ({ table: 'obs', ...column }))
  ])
  return tableOf(rows, [...WHERE, 'table', ...COLUMN_COLUMNS])
}

export const ACROSS_LAYER_FIELDS: Field[] = [...WHERE_FIELDS, ...LAYER_FIELDS]
export const ACROSS_COLUMN_FIELDS: Field[] = [...WHERE_FIELDS, { name: 'table', description: 'var: the feature table; obs: the sample table.' }, ...COLUMN_FIELDS]
