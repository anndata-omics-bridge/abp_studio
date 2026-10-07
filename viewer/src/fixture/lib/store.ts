import type { CsvRow, Fact, StoreIndex, Submission, SubmissionSummary } from '../types.js'

// JSON contracts are checked once where files enter the viewer. Panels receive
// concrete store data, while arbitrary submission metadata remains unknown.
function record (value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(`${label}: expected an object`)
  }
  return value as Record<string, unknown>
}

function optionalString (value: unknown, field: string): string | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'string') throw new TypeError(`${field}: expected a string`)
  return value
}

function optionalNumber (value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new TypeError(`${field}: expected a finite number`)
  return value
}

export function parseStoreIndex (value: unknown): StoreIndex | null {
  if (value === null) return null
  const data = record(value, 'index.json')
  const index: StoreIndex = {
    root: optionalString(data.root, 'root'),
    submissionSummary: optionalString(data.submissionSummary, 'submissionSummary')
  }
  if (data.bytes !== undefined) {
    const bytes = record(data.bytes, 'bytes')
    index.bytes = {
      metadata: optionalNumber(bytes.metadata, 'bytes.metadata'),
      fasta: optionalNumber(bytes.fasta, 'bytes.fasta')
    }
  }
  if (data.fasta !== undefined) {
    if (!Array.isArray(data.fasta) || !data.fasta.every((name: unknown): name is string => typeof name === 'string')) {
      throw new TypeError('fasta: expected an array of file names')
    }
    index.fasta = data.fasta
  }
  if (data.tables !== undefined) {
    if (!Array.isArray(data.tables)) throw new TypeError('tables: expected an array')
    index.tables = data.tables.map((value: unknown) => {
      const table = record(value, 'table')
      const name = optionalString(table.name, 'table.name')
      const sizeBytes = optionalNumber(table.sizeBytes, 'table.sizeBytes')
      if (name === undefined || sizeBytes === undefined) throw new TypeError('table: name and sizeBytes are required')
      return { name, sizeBytes }
    })
  }
  return index
}

export function parseSummary (value: unknown): SubmissionSummary | null {
  if (value === null) return null
  const data = record(value, 'submission summary')
  return {
    input_file: optionalString(data.input_file, 'input_file'),
    size_bytes: optionalNumber(data.size_bytes, 'size_bytes'),
    format: optionalString(data.format, 'format'),
    delimiter: optionalString(data.delimiter, 'delimiter'),
    rows: data.rows === null ? null : optionalNumber(data.rows, 'rows'),
    columns: data.columns === null ? null : optionalNumber(data.columns, 'columns'),
    column_names: optionalString(data.column_names, 'column_names'),
    parameter_file: optionalString(data.parameter_file, 'parameter_file'),
    downloaded_at: optionalString(data.downloaded_at, 'downloaded_at')
  }
}

function flag (value: string | undefined): boolean {
  return value === 'True' || value === 'true'
}

function number (value: string | undefined): number | null {
  return value === undefined || value === '' ? null : Number(value)
}

export function summaryPath (pattern: string, row: CsvRow): string {
  return pattern.replace('{repo_name}', row.repo_name ?? '').replace('{intermediate_hash}', row.intermediate_hash ?? '')
}

// A persisted per-submission summary says the files have landed. downloads.csv
// supplies a refusal reason only when no summary exists.
export function joinSubmissions (
  catalog: CsvRow[], downloads: CsvRow[], summaries: ReadonlyMap<string, SubmissionSummary | null>
): Submission[] {
  const downloaded = new Map(downloads.map((row) => [row.intermediate_hash, row]))
  return catalog.map((row) => {
    const download = downloaded.get(row.intermediate_hash)
    const summary = summaries.get(row.intermediate_hash ?? '')
    const refused = download && download.status !== 'ok' ? download.status ?? 'not downloaded' : 'not downloaded'
    return {
      module: row.module ?? '',
      repo_name: row.repo_name ?? '',
      intermediate_hash: row.intermediate_hash ?? '',
      software_name: row.software_name ?? '',
      software_version: row.software_version ?? '',
      nr_feature: number(row.nr_feature),
      is_temporary: flag(row.is_temporary),
      old_new: row.old_new ?? '',
      smallest_per_software_version: flag(row.smallest_per_software_version),
      smallest_per_software: flag(row.smallest_per_software),
      smallest_per_module: flag(row.smallest_per_module),
      status: summary ? 'ok' : refused,
      input_file: summary?.input_file ?? '',
      size_mb: summary?.size_bytes === undefined ? null : summary.size_bytes / 1e6,
      format: summary?.format ?? '',
      delimiter: summary?.delimiter ?? '',
      rows: summary?.rows ?? null,
      columns: summary?.columns ?? null,
      column_names: summary?.column_names ?? '',
      parameter_file: summary?.parameter_file ?? '',
      downloaded_at: summary?.downloaded_at ?? '',
      downloaded_on: (summary?.downloaded_at ?? '').slice(0, 10)
    }
  })
}

export function storageRows (index: StoreIndex | null, downloaded: SubmissionSummary[] = []): Fact[] {
  if (!index) return [{ key: 'Store', value: 'index.json not available' }]
  const gb = (bytes: number): string => `${(bytes / 1e9).toFixed(2)} GB`
  const bytes = downloaded.reduce((total, summary) => total + (summary.size_bytes ?? 0), 0)
  return [
    { key: 'Store root', value: index.root ?? '' },
    { key: 'Submissions on disk', value: String(downloaded.length) },
    { key: 'Vendor tables size', value: gb(bytes) },
    { key: 'Metadata size', value: gb(index.bytes?.metadata ?? 0) },
    { key: 'FASTA files', value: (index.fasta ?? []).join(', ') || 'none' },
    { key: 'FASTA size', value: gb(index.bytes?.fasta ?? 0) },
    ...(index.tables ?? []).map((table) => ({ key: table.name, value: `${(table.sizeBytes / 1e3).toFixed(1)} kB` }))
  ]
}

// ProteoBench's metadata permits bare NaN/Infinity; the catalogue reader also
// treats these missing numeric values as null.
export function parseSubmissionJson (text: string): unknown {
  if (!text.trim()) return null
  return JSON.parse(text.replace(/:\s*(NaN|-?Infinity)\s*(?=[,}\]])/g, ': null')) as unknown
}
