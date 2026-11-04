import '../../shared/json-viewer.js'
import type { JsonView } from '../types.js'

// One JSON value as a collapsible tree under a heading, as the corpus viewer shows JSON.

/** Append `view` to `host` as a titled section with Expand all and Collapse all. */
export function mountJson (host: HTMLElement, view: JsonView): void {
  const section = document.createElement('section')
  section.className = 'view'
  const heading = document.createElement('h3')
  heading.textContent = view.title
  section.append(heading)
  if (view.description) {
    const description = document.createElement('p')
    description.textContent = view.description
    section.append(description)
  }
  const container = document.createElement('div')
  container.className = 'json-tree'
  const controls = document.createElement('div')
  controls.className = 'json-controls'
  controls.setAttribute('aria-label', 'JSON tree controls')
  const viewer = document.createElement('json-viewer')
  viewer.data = view.data as NonNullable<typeof viewer.data>
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
  section.append(container)
  host.append(section)
}
