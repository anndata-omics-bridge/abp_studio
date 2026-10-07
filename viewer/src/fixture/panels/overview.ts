import type { ChartView, Count, Group, GroupField, Submission } from '../types.js'

// How the store's submissions divide up, grouped by whichever column the reader picks.
// Pure: rows and a field in, one view descriptor out.

const DOWNLOADED = '#1f4f82'
const PENDING = '#c3ccd6'

// What a reader can group by: the catalogue's categorical columns, nothing computed.
export const GROUPS: Group[] = [
  { field: 'software_name', label: 'Software' },
  { field: 'module', label: 'Module' },
  { field: 'software_version', label: 'Version' },
  { field: 'format', label: 'Format' },
  { field: 'status', label: 'Status' },
  { field: 'downloaded_on', label: 'Download date' }
]

export const DEFAULT_GROUP = GROUPS[0].field

export function groupFor (field: string | undefined): Group {
  return GROUPS.find((group) => group.field === field) ?? GROUPS[0]
}

export function countsBy (rows: Array<Partial<Submission>>, field: GroupField): Count[] {
  const counts = new Map<string, Count>()
  for (const row of rows) {
    const label = String(row[field] ?? '') || 'unknown'
    const entry = counts.get(label) ?? { label, total: 0, downloaded: 0 }
    entry.total += 1
    if (row.status === 'ok') entry.downloaded += 1
    counts.set(label, entry)
  }
  const counted = [...counts.values()]
  // Plotly puts the first entry at the bottom of a horizontal chart, so dates ascend:
  // oldest at the bottom, newest at the top, the way a timeline reads.
  return field.startsWith('downloaded')
    ? counted.sort((a, b) => a.label.localeCompare(b.label))
    : counted.sort((a, b) => a.total - b.total || a.label.localeCompare(b.label))
}

export function overviewViews (rows: Array<Partial<Submission>>, field: string = DEFAULT_GROUP): ChartView[] {
  const group = groupFor(field)
  const counts = countsBy(rows, group.field)
  const labels = counts.map((count) => count.label)
  return [{
    key: 'counts',
    backend: 'chart',
    title: `Submissions per ${group.label.toLowerCase()} (${counts.length})`,
    height: Math.max(180, 22 * counts.length + 78),
    traces: [
      {
        type: 'bar',
        orientation: 'h',
        name: 'on disk',
        x: counts.map((count) => count.downloaded),
        y: labels,
        marker: { color: DOWNLOADED },
        hovertemplate: '%{y}: %{x} on disk<extra></extra>'
      },
      {
        type: 'bar',
        orientation: 'h',
        name: 'not downloaded',
        x: counts.map((count) => count.total - count.downloaded),
        y: labels,
        marker: { color: PENDING },
        hovertemplate: '%{y}: %{x} not downloaded<extra></extra>'
      }
    ],
    layout: {
      barmode: 'stack',
      showlegend: true,
      // Above the plot, in margin of its own: at a smaller top margin the legend is
      // drawn over the longest bar.
      legend: { orientation: 'h', x: 0, y: 1, yanchor: 'bottom' },
      margin: { l: 8, r: 16, t: 44, b: 34 },
      xaxis: { title: { text: 'submissions', standoff: 6 }, zeroline: false },
      yaxis: { automargin: true, type: 'category' }
    }
  }]
}
