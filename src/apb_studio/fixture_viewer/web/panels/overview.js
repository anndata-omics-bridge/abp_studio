// How the store's submissions divide up, grouped by whichever column the reader picks.
// Pure: rows and a field in, one view descriptor out.

const DOWNLOADED = '#1f4f82'
const PENDING = '#c3ccd6'

// What a reader can group by: the catalogue's categorical columns, nothing computed.
export const GROUPS = [
  { field: 'software_name', label: 'Software' },
  { field: 'module', label: 'Module' },
  { field: 'software_version', label: 'Version' },
  { field: 'format', label: 'Format' },
  { field: 'status', label: 'Status' }
]

export const DEFAULT_GROUP = GROUPS[0].field

/**
 * Resolve a grouping field, falling back when it is not one we offer.
 *
 * @param {string} field A field name, possibly unknown.
 * @returns {{field: string, label: string}} The group to draw.
 */
export function groupFor (field) {
  return GROUPS.find((group) => group.field === field) ?? GROUPS[0]
}

/**
 * Count submissions and downloads per value of one field.
 *
 * @param {object[]} rows Joined submission rows.
 * @param {string} field The field to group by.
 * @returns {Array<{label: string, total: number, downloaded: number}>} Counts, smallest first.
 */
export function countsBy (rows, field) {
  const counts = new Map()
  for (const row of rows) {
    const label = String(row[field] ?? '') || 'unknown'
    const entry = counts.get(label) ?? { label, total: 0, downloaded: 0 }
    entry.total += 1
    if (row.status === 'ok') entry.downloaded += 1
    counts.set(label, entry)
  }
  return [...counts.values()].sort((a, b) => a.total - b.total || a.label.localeCompare(b.label))
}

/**
 * Describe the counts chart for one grouping.
 *
 * Horizontal bars because the labels are software names and module keys, which do not fit
 * under a vertical bar. Downloaded and pending are stacked, so a bar's length stays the
 * catalogue's count however much of it is on disk.
 *
 * @param {object[]} rows Joined submission rows.
 * @param {string} field The field to group by.
 * @returns {object[]} One chart view.
 */
export function overviewViews (rows, field = DEFAULT_GROUP) {
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
