// Plain values as apb2's rules bundle holds them. Projections and the shell take these
// types and never fetch, so their tests run on inline rows.

export type Value = null | boolean | number | string | Value[] | { [key: string]: Value }
export type Row = Record<string, Value>

/** A table as projected: its columns in order and its rows. */
export interface Table { columns: string[]; rows: Row[] }

/** One column of a projected table and what it holds. */
export interface Field { name: string; description: string }

export interface Column { field: string; title: string; tooltip: string; filter: 'list' | 'input' }

/** One table to show: a heading, the columns with their header tooltips, the rows, and what
 * each column holds. */
export interface TableView { key: string; title: string; description: string; columns: Column[]; rows: Row[]; legend: Field[] }

/** One JSON value to show as a tree under a heading. */
export interface JsonView { key: string; title: string; description: string; data: Value }

/** `manifest.json` of the bundle. */
export interface Manifest { bundle_format: number; apb2_version: string; apb2_commit: string | null; files: string[] }

/** One physical input of a rules.json and the levels it holds. */
export interface RuleTable { levels: string[]; input: Record<string, Value>; preparation: string | null }

/** One packaged rules.json, as `rules.json` of the bundle lists it. */
export interface RuleDocument {
  rule: string
  software_name: string
  software_version_pattern: string
  schema_version: string
  file_version: string
  hierarchy: string
  parameter_file: string
  categories: string[]
  levels: string[]
  tables: RuleTable[]
}

/** Search-parameter values a conversion may have. */
export interface Evidence { acquisition_method: string; combine_charge_states: boolean | null }

/** One effective declaration of a level, as conversion stores it, and the evidence that selects it. */
export interface Declaration { selected_by: Evidence[]; declaration: Record<string, Value> }

/** One level of one rule, as `levels.json` of the bundle lists it. */
export interface RuleLevel { rule: string; level: string; declarations: Declaration[] }

export type TabId = 'rules' | 'rule' | 'levels' | 'layers' | 'columns'

/** One tab, and whether it shows the level picker. */
export interface Tab { id: TabId; label: string; description: string; levels: boolean }
