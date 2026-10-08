import type { DatasetOddities, OddityFinding, OddityKind, RunOddities } from '../types.js'
import { ODDITY_LABELS } from '../oddities.js'
import { dataTable, jsonTree, node } from './dom.js'

function count (value: unknown): string {
  return typeof value === 'number' ? value.toLocaleString() : 'Not recorded'
}

const DESCRIPTIONS: Record<OddityKind, (details: Record<string, unknown>) => string> = {
  unknown_modification: d => `${count(d.token_count)} distinct tokens`,
  unmatched_peptides: d => `${count(d.unmatched_feature_count)} unmatched of ${count(d.feature_count)} features`,
  unreadable_numeric: d => `${count(d.cell_count)} cells · ${count(d.distinct_token_count)} distinct tokens`,
  effectively_empty: d => `${typeof d.occupancy === 'number' ? (d.occupancy * 100).toPrecision(3) : 'Unknown'}% occupied · threshold ${typeof d.empty_ratio === 'number' ? d.empty_ratio * 100 : 'unknown'}%`,
  annotation_only: d => `${count(d.count)} annotation rows`,
  quantification_only: d => `${count(d.count)} samples`,
  annotation_corrections: d => `${count(d.count)} accepted corrections`
}

function examples (finding: OddityFinding): string {
  const details = finding.details
  if (Array.isArray(details.examples)) return details.examples.slice(0, 5).map(String).join(' · ')
  if (Array.isArray(details.reference_layers)) return `Populated: ${details.reference_layers.join(' · ')}`
  if (details.corrections && typeof details.corrections === 'object') {
    return Object.values(details.corrections).slice(0, 5).map(value => {
      const correction = value as Record<string, unknown>
      return `${correction.observed} → ${correction.expected}`
    }).join(' · ')
  }
  return 'Not recorded'
}

export function renderOdditiesDetail (host: HTMLElement, report: DatasetOddities | null | undefined): void {
  host.replaceChildren(node('h3', 'Oddities'))
  if (!report) {
    host.append(node('p', 'Oddities have not been summarized for this run.', 'empty-note'))
    return
  }
  host.append(...report.notes.map(note => node('p', note, 'representation-error')))
  if (!report.available) return
  host.append(node('p', `Source: ${report.source_step} (${report.source_status}) · ${report.findings.length} recorded findings`, 'empty-note'))
  if (report.findings.length) {
    host.append(dataTable(['Level', 'Finding', 'Layer / convention', 'Affected values', 'Examples'], report.findings.map(finding => [
      finding.level, ODDITY_LABELS[finding.kind], finding.layer || finding.convention || '—',
      DESCRIPTIONS[finding.kind](finding.details), examples(finding)
    ])))
  } else {
    host.append(node('p', 'No findings in the recorded checks. Coverage is listed below.', 'empty-note'))
  }
  host.append(node('h4', 'Check coverage'), dataTable(['Level', 'Numeric diagnostics', 'FASTA', 'Annotation'], report.coverage.map(level => [
    level.level, level.numeric === 'recorded' ? 'Recorded' : 'Not recorded',
    level.fasta === 'checked' ? 'Checked' : 'Not checked',
    level.annotation_conventions.join(' · ') || 'Not checked'
  ])))
  const full = document.createElement('details')
  full.append(node('summary', 'Complete oddities evidence'), jsonTree(report))
  host.append(full)
}

export function renderOdditiesSummary (host: HTMLElement, summary: RunOddities | null): void {
  host.replaceChildren(node('h2', 'Corpus oddities'))
  if (!summary) {
    host.append(node('p', 'Oddities have not been summarized for this run. A completed run produces the summary.', 'empty-note'))
    return
  }
  host.append(node('p', 'All datasets in the selected run. Each finding column counts affected datasets once; checks not performed are shown in coverage columns.', 'empty-note'))
  const kinds = Object.keys(ODDITY_LABELS) as OddityKind[]
  host.append(dataTable([
    'Software', 'Datasets', 'Summarized', 'Numeric recorded', 'FASTA checked', 'Annotation checked',
    ...kinds.map(kind => ODDITY_LABELS[kind])
  ], summary.software.map(software => [
    software.software_name, software.dataset_count, software.summarized_count,
    software.numeric_recorded_count, software.fasta_checked_count, software.annotation_checked_count,
    ...kinds.map(kind => software.affected_datasets[kind] ?? 0)
  ])))
}
