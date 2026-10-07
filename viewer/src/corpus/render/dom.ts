import '../../shared/json-viewer.js'

// Small DOM renderers shared by detail and settings panels.

export function node (tag: keyof HTMLElementTagNameMap, text: unknown, className = ''): HTMLElement {
  const result = document.createElement(tag)
  result.textContent = String(text)
  if (className) result.className = className
  return result
}

export function dataTable (headings: string[], rows: unknown[][]): HTMLTableElement {
  const result = document.createElement('table')
  result.className = 'scientific-table'
  const head = document.createElement('thead')
  const headerRow = document.createElement('tr')
  headerRow.append(...headings.map(heading => node('th', heading)))
  head.append(headerRow)
  const body = document.createElement('tbody')
  for (const row of rows) {
    const tableRow = document.createElement('tr')
    tableRow.append(...row.map(value => node('td', value == null ? '—' : value)))
    body.append(tableRow)
  }
  result.append(head, body)
  return result
}

export function metadataCards (entries: [string, unknown][]): HTMLElement {
  const cards = document.createElement('dl')
  cards.className = 'metadata-cards'
  for (const [label, value] of entries) {
    const card = document.createElement('div')
    card.append(node('dt', label), node('dd', value == null || value === '' ? '—' : value))
    cards.append(card)
  }
  return cards
}

export function jsonTree (data: unknown, expandedPaths: string[] = []): HTMLElement {
  const container = document.createElement('div')
  container.className = 'json-tree'
  const controls = document.createElement('div')
  controls.className = 'json-controls'
  controls.setAttribute('aria-label', 'JSON tree controls')
  const viewer = document.createElement('json-viewer')
  viewer.data = data as NonNullable<typeof viewer.data>
  const actions: [string, () => void][] = [
    ['Expand all', () => viewer.expandAll()],
    ['Collapse all', () => viewer.collapseAll()]
  ]
  for (const [label, action] of actions) {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = label
    button.addEventListener('click', action)
    controls.append(button)
  }
  container.append(controls, viewer)
  if (expandedPaths.length) {
    Promise.resolve(viewer.updateComplete).then(() => {
      for (const path of expandedPaths) viewer.expand(path)
    })
  }
  return container
}

export function renderJson (host: HTMLElement, data: unknown): void { host.replaceChildren(jsonTree(data)) }

export function columnTitle (field: string): string {
  const words = field.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}
