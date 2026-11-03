// Plain values as apb-catalog-ts answers them. Projections and the shell take these
// types and never import apb-catalog-ts, so their tests run on inline rows.

export type Value = null | boolean | number | string | Value[] | { [key: string]: Value }
export type Row = Record<string, Value>

/** A table as stored or projected: its columns in order and its rows. */
export interface Table { columns: string[]; rows: Row[] }

/** One column of a stored table and what it holds, as datapackage.json describes it. */
export interface Field { name: string; description: string }

/** One stored table of the bundle, as datapackage.json declares it. */
export interface Resource { name: string; path: string; description: string; fields: Field[] }

export interface Column { field: string; title: string; tooltip: string; filter: 'list' | 'input' }

/** One table to show: a heading, the columns with their header tooltips, the rows, and for a
 * stored table what each column holds. */
export interface TableView { key: string; title: string; description: string; columns: Column[]; rows: Row[]; legend: Field[] }

export type TabGroup = 'views' | 'tables'
/** How a tab picks catalogue sets: not at all, one set, or one or every set. */
export type SetPicker = 'none' | 'one' | 'any'

/** One tab, and whether its rows belong to catalogue sets, so it shows the set picker. */
export interface Tab { id: string; label: string; group: TabGroup; sets: SetPicker }
