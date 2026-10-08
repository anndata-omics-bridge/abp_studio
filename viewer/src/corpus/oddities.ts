import type { DatasetOddities, DatasetRow, RunOddities } from './types.js'

/** The summary owns diagnostics; the browser only validates its envelope. */
export function validatedOddities (document: unknown, runId: string): RunOddities {
  const header = document && typeof document === 'object' ? document as Record<string, unknown> : {}
  if (header.format !== 'apb-studio-oddities' || header.format_version !== 2 || header.run_id !== runId ||
      !Array.isArray(header.datasets) || !Array.isArray(header.software)) {
    throw new Error('Unsupported or mismatched oddities summary')
  }
  return header as unknown as RunOddities
}

function attentionCount (report: DatasetOddities): number {
  return report.metrics.filter(metric => metric.status === 'attention').length
}

function partial (report: DatasetOddities | null | undefined): boolean {
  return report?.metrics.some(metric => metric.status === 'not_checked') ?? false
}

export function oddityState (report: DatasetOddities | null | undefined): string {
  if (!report) return 'Not summarized'
  if (!report.available) return 'Unavailable'
  if (attentionCount(report)) return 'Needs attention'
  if (!report.metrics.length || partial(report)) return 'Partial coverage'
  return 'No recorded findings'
}

export function withOddities (rows: DatasetRow[], summary: RunOddities | null): DatasetRow[] {
  const datasets = new Map(summary?.datasets.map(dataset => [dataset.input_file, dataset]) ?? [])
  return rows.map(row => {
    const oddities = datasets.get(row.input_file) ?? null
    return {
      ...row, oddities, oddity_state: oddityState(oddities),
      oddity_count: oddities?.available ? attentionCount(oddities) : null
    }
  })
}

export function oddityCountLabel (row: DatasetRow): string {
  if (row.oddity_count == null) return row.oddity_state ?? 'Not summarized'
  return `${row.oddity_count}${partial(row.oddities) ? ' · partial' : ''}`
}
