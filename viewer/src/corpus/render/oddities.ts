import type { DatasetOddities, OddityMetric, RunOddities } from '../types.js'
import { dataTable, jsonTree, node } from './dom.js'

const STATUS_LABELS: Record<OddityMetric['status'], string> = {
  attention: 'Needs attention',
  not_checked: 'Not checked',
  ok: 'OK'
}
const STATUS_ORDER: OddityMetric['status'][] = ['attention', 'not_checked', 'ok']

function value (metric: OddityMetric): string {
  if (metric.value === null) return metric.status === 'not_checked' ? '—' : 'Undefined'
  const shown = typeof metric.value === 'number' ? metric.value.toLocaleString() : String(metric.value)
  return metric.unit ? `${shown} ${metric.unit}` : shown
}

/** Every recorded summary entry, attention first, each in its own unit. */
export function renderOdditiesDetail (host: HTMLElement, report: DatasetOddities | null | undefined): void {
  host.replaceChildren(node('h3', 'Oddities'))
  if (!report) {
    host.append(node('p', 'Oddities have not been summarized for this run.', 'empty-note'))
    return
  }
  host.append(...report.notes.map(note => node('p', note, 'representation-error')))
  if (!report.available) return
  const metrics = [...report.metrics].sort(
    (left, right) => STATUS_ORDER.indexOf(left.status) - STATUS_ORDER.indexOf(right.status)
  )
  const attention = metrics.filter(metric => metric.status === 'attention').length
  host.append(node('p', `Source: ${report.source_step} (${report.source_status}) · ${attention} metrics need attention`, 'empty-note'))
  if (!metrics.length) {
    host.append(node('p', 'The displayed result records no summary metrics.', 'empty-note'))
    return
  }
  host.append(dataTable(['Status', 'Metric', 'Value', 'Layer', 'Record', 'Scope'], metrics.map(metric => [
    STATUS_LABELS[metric.status], metric.label, value(metric), metric.layer || '—', metric.record, metric.scope
  ])))
  const full = document.createElement('details')
  full.append(node('summary', 'Complete oddities evidence'), jsonTree(report))
  host.append(full)
}

/** Datasets per software with each attention metric, counted once per dataset. */
export function renderOdditiesSummary (host: HTMLElement, summary: RunOddities | null): void {
  host.replaceChildren(node('h2', 'Corpus oddities'))
  if (!summary) {
    host.append(node('p', 'Oddities have not been summarized for this run. A completed run produces the summary.', 'empty-note'))
    return
  }
  host.append(node('p', 'All datasets in the selected run. Each metric column counts the datasets where that producer metric needs attention.', 'empty-note'))
  const columns = new Map<string, string>()
  for (const software of summary.software) {
    for (const item of software.affected) columns.set(`${item.record}/${item.name}`, `${item.label} (${item.record})`)
  }
  const keys = [...columns.keys()].sort()
  host.append(dataTable([
    'Software', 'Datasets', 'Summarized', 'Needs attention', ...keys.map(key => columns.get(key) ?? key)
  ], summary.software.map(software => {
    const counts = new Map(software.affected.map(item => [`${item.record}/${item.name}`, item.datasets]))
    return [
      software.software_name, software.dataset_count, software.summarized_count, software.attention_count,
      ...keys.map(key => counts.get(key) ?? 0)
    ]
  })))
}
