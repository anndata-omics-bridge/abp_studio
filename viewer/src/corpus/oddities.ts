import type { DatasetOddities, DatasetRow, OddityKind, RunOddities } from './types.js'

export const ODDITY_LABELS: Record<OddityKind, string> = {
  unknown_modification: 'Unknown modifications',
  unmatched_peptides: 'Unmatched peptides',
  unreadable_numeric: 'Unreadable numbers',
  effectively_empty: 'Empty layers',
  annotation_only: 'Annotation rows absent from quantification',
  quantification_only: 'Samples without annotation',
  annotation_corrections: 'Fuzzy annotation corrections'
}

/** The summary owns diagnostics; the browser only validates its envelope. */
export function validatedOddities (document: unknown, runId: string): RunOddities {
  const header = document && typeof document === 'object' ? document as Record<string, unknown> : {}
  if (header.format !== 'apb-studio-oddities' || header.format_version !== 1 || header.run_id !== runId ||
      !Array.isArray(header.datasets) || !Array.isArray(header.software)) {
    throw new Error('Unsupported or mismatched oddities summary')
  }
  return header as unknown as RunOddities
}

export function oddityState (report: DatasetOddities | null | undefined): string {
  if (!report) return 'Not summarized'
  if (!report.available) return 'Unavailable'
  if (report.findings.length) return 'Needs attention'
  if (!report.coverage.length || report.coverage.some(level => level.numeric !== 'recorded')) return 'Partial coverage'
  return 'No recorded findings'
}

export function withOddities (rows: DatasetRow[], summary: RunOddities | null): DatasetRow[] {
  const datasets = new Map(summary?.datasets.map(dataset => [dataset.input_file, dataset]) ?? [])
  return rows.map(row => {
    const oddities = datasets.get(row.input_file) ?? null
    return {
      ...row, oddities, oddity_state: oddityState(oddities),
      oddity_count: oddities?.available ? oddities.findings.length : null
    }
  })
}

export function oddityCountLabel (row: DatasetRow): string {
  if (row.oddity_count == null) return row.oddity_state ?? 'Not summarized'
  const suffix = row.oddities?.coverage.some(level => level.numeric !== 'recorded') ? ' · partial' : ''
  return `${row.oddity_count}${suffix}`
}
