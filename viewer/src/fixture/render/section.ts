import type { ViewSection } from '../types.js'

export function sectionFor (host: HTMLElement, view: ViewSection): { section: HTMLElement; body: HTMLElement } {
  const section = document.createElement('section')
  section.className = 'view'
  section.dataset.key = view.key
  const heading = document.createElement('h3')
  heading.textContent = view.title
  const body = document.createElement('div')
  body.className = 'body'
  section.append(heading, body)
  host.append(section)
  return { section, body }
}

export function removeSection (body: HTMLElement): void {
  body.parentElement?.remove()
}
