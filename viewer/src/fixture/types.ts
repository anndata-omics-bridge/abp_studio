import type { ColumnDefinition, Options, RowComponent } from '../shared/tabulator.js'
import type { Data, Layout } from '../shared/plotly.js'

export type CsvRow = Record<string, string | undefined>

export interface StoreIndex {
  root?: string
  submissionSummary?: string
  fasta?: string[]
  bytes?: { metadata?: number; fasta?: number }
  tables?: Array<{ name: string; sizeBytes: number }>
}

export interface SubmissionSummary {
  input_file?: string
  size_bytes?: number
  format?: string
  delimiter?: string
  rows?: number | null
  columns?: number | null
  column_names?: string
  parameter_file?: string
  downloaded_at?: string
}

export interface Submission {
  module: string
  repo_name: string
  intermediate_hash: string
  software_name: string
  software_version: string
  nr_feature: number | null
  is_temporary: boolean
  old_new: string
  smallest_per_software_version: boolean
  smallest_per_software: boolean
  smallest_per_module: boolean
  status: string
  input_file: string
  size_mb: number | null
  format: string
  delimiter: string
  rows: number | null
  columns: number | null
  column_names: string
  parameter_file: string
  downloaded_at: string
  downloaded_on: string
}

export type GroupField = 'software_name' | 'module' | 'software_version' | 'format' | 'status' | 'downloaded_on'
export interface Group { field: GroupField; label: string }
export interface Count { label: string; total: number; downloaded: number }
export interface Fact { key: string; value: string | number | boolean }

export interface ViewSection { key: string; title: string }
export interface TableEvents { rowClick?: (event: UIEvent, row: RowComponent) => void }
export interface TableView extends ViewSection {
  backend: 'table'
  rows: object[]
  columns: ColumnDefinition[]
  options?: Options
  events?: TableEvents
}
export interface NoteView extends ViewSection { backend: 'note'; text: string }
export interface ChartView extends ViewSection {
  backend: 'chart'
  height?: number
  traces: Data[]
  layout?: Partial<Layout>
}
export type View = TableView | NoteView | ChartView

export interface Renderer<V extends View, H> {
  name: V['backend']
  mount(host: HTMLElement, view: V): Promise<H>
  resize(handle: H): void
  destroy(handle: H): void
}
export interface MountedView { resize(): void; destroy(): void }
