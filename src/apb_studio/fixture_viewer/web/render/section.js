// One titled section per view inside a panel host.

/**
 * Create a section for a view.
 *
 * @param {HTMLElement} host The panel host.
 * @param {object} view The view.
 * @returns {{section: HTMLElement, body: HTMLElement}} The section and its body.
 */
export function sectionFor (host, view) {
  const section = document.createElement('section')
  section.className = 'view'
  section.dataset.key = view.key
  const heading = document.createElement('h3')
  heading.textContent = view.title ?? ''
  const body = document.createElement('div')
  body.className = 'body'
  section.append(heading, body)
  host.append(section)
  return { section, body }
}

/**
 * Refresh a section's title.
 *
 * @param {HTMLElement} body The section body.
 * @param {object} view The new view.
 */
export function updateSection (body, view) {
  const heading = body.parentElement?.querySelector('h3')
  if (heading) heading.textContent = view.title ?? ''
}

/**
 * Remove a section.
 *
 * @param {HTMLElement} body The section body.
 */
export function removeSection (body) {
  body.parentElement?.remove()
}
