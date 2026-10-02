import '../vendor/json-viewer.js'

// Small DOM renderers shared by detail and settings panels.

/** @param {string} tag Tag name. @param {unknown} text Text. @param {string} className Class. @returns {HTMLElement} */
export function node (tag, text, className = '') {
  const result = document.createElement(tag)
  result.textContent = String(text)
  if (className) result.className = className
  return result
}

/** @param {string[]} headings Headers. @param {unknown[][]} rows Values. @returns {HTMLTableElement} */
export function dataTable (headings, rows) {
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

/** @param {Array<[string, unknown]>} entries Label/value pairs. @returns {HTMLElement} */
export function metadataCards (entries) {
  const cards = document.createElement('dl')
  cards.className = 'metadata-cards'
  for (const [label, value] of entries) {
    const card = document.createElement('div')
    card.append(node('dt', label), node('dd', value == null || value === '' ? '—' : value))
    cards.append(card)
  }
  return cards
}

/** @param {object} data JSON data. @param {string[]} expandedPaths Initial paths. @returns {HTMLElement} */
export function jsonTree (data, expandedPaths = []) {
  const container = document.createElement('div')
  container.className = 'json-tree'
  const controls = document.createElement('div')
  controls.className = 'json-controls'
  controls.setAttribute('aria-label', 'JSON tree controls')
  const viewer = document.createElement('json-viewer')
  viewer.data = data
  for (const [label, action] of [
    ['Expand all', () => viewer.expandAll()],
    ['Collapse all', () => viewer.collapseAll()]
  ]) {
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

/** @param {HTMLElement} host Destination. @param {object} data JSON data. */
export function renderJson (host, data) { host.replaceChildren(jsonTree(data)) }

/** @param {string} field Machine field. @returns {string} Human title. */
export function columnTitle (field) {
  const words = field.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}
