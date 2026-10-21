import type { RunSearchSettings } from '../types.js'
import { searchSettingsRows } from '../search-settings.js'
import { dataTable, node } from './dom.js'

/** Settings recovered per software, as in the article's Figure S1, then the datasets left out. */
export function renderSearchSettings (host: HTMLElement, summary: RunSearchSettings | null): void {
  host.replaceChildren(node('h2', 'Search settings recovered'))
  if (!summary) {
    host.append(node('p', 'Search settings have not been summarized for this run. A completed run produces the summary.', 'empty-note'))
    return
  }
  const rows = searchSettingsRows(summary)
  if (!rows.length) {
    host.append(node('p', 'No result in this run records a parameter file.', 'empty-note'))
  } else {
    host.append(node('p', 'All datasets in the selected run whose result records a parameter file; n per software. Each cell is the percentage of them where APB recovered the setting, printed below 100.', 'empty-note'))
    const table = document.createElement('table')
    table.className = 'search-settings-heatmap'
    const head = document.createElement('tr')
    head.append(node('th', ''), ...summary.settings.map(setting => node('th', setting.label)))
    table.append(head)
    for (const row of rows) {
      const line = document.createElement('tr')
      line.append(node('th', row.label))
      for (const [index, cell] of row.cells.entries()) {
        const value = node('td', cell.text, cell.inverse ? 'inverse' : '')
        value.style.backgroundColor = cell.colour
        value.title = `${summary.settings[index]?.label}: ${cell.percent.toFixed(1)}%`
        line.append(value)
      }
      table.append(line)
    }
    host.append(table)
  }
  const missing = summary.datasets.filter(dataset => !dataset.parameters)
  if (!missing.length) return
  const details = document.createElement('details')
  details.append(node('summary', `Datasets not counted (${missing.length})`), dataTable(
    ['Software', 'Input', 'Result', 'Reason'],
    missing.map(dataset => [dataset.software_name, dataset.input_file, dataset.status, dataset.notes.join(' ')])
  ))
  host.append(details)
}
