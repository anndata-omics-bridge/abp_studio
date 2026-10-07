import type { ColumnDefinition } from '../../shared/tabulator.js'
import type { Submission, View } from '../types.js'

// One submission in depth: its facts, its columns, its metadata, its parameter file.
// Pure: data in, view descriptors out.

const FACTS: Array<[keyof Submission, string]> = [
  ['module', 'Module'],
  ['repo_name', 'Results repository'],
  ['intermediate_hash', 'Hash'],
  ['software_name', 'Software'],
  ['software_version', 'Version'],
  ['nr_feature', 'Features'],
  ['status', 'Download status'],
  ['downloaded_at', 'Downloaded'],
  ['input_file', 'Input file'],
  ['format', 'Format'],
  ['delimiter', 'Delimiter'],
  ['rows', 'Rows'],
  ['columns', 'Columns'],
  ['parameter_file', 'Parameter file']
]

const KEY_VALUE_COLUMNS: ColumnDefinition[] = [
  { title: '', field: 'key', width: 180 },
  { title: '', field: 'value' }
]

export function detailViews (row: Submission, metadata: unknown, parameterText: string): View[] {
  const facts = FACTS.map(([field, key]) => ({ key, value: row[field] ?? '' }))
  return [
    {
      key: 'detail-facts',
      backend: 'table',
      title: 'Submission',
      rows: facts,
      columns: KEY_VALUE_COLUMNS,
      options: { layout: 'fitColumns', headerVisible: false }
    },
    {
      key: 'detail-columns',
      backend: 'note',
      title: `Column names (${row.columns ?? 0})`,
      text: row.column_names ? row.column_names.split('|').join('\n') : 'not summarised yet'
    },
    {
      key: 'detail-metadata',
      backend: 'note',
      title: 'Submission JSON',
      text: metadata ? JSON.stringify(metadata, null, 2) : 'not catalogued yet'
    },
    {
      key: 'detail-parameters',
      backend: 'note',
      title: 'Parameter file',
      text: parameterText || 'not downloaded yet'
    }
  ]
}
