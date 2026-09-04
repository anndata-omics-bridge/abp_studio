import { noteRenderer } from './note.js'
import { tableRenderer } from './tabulator.js'

// The one place a backend name is turned into behaviour. Panels name the backend
// they want; nothing else compares that name against anything.

const RENDERERS = new Map([
  [tableRenderer.name, tableRenderer],
  [noteRenderer.name, noteRenderer]
])

/**
 * Look up the renderer a view asks for.
 *
 * @param {string} backend The backend name from a view.
 * @returns {object} The renderer.
 * @throws {Error} No renderer is registered under that name.
 */
export function rendererFor (backend) {
  const renderer = RENDERERS.get(backend)
  if (!renderer) throw new Error(`No renderer registered for backend "${backend}"`)
  return renderer
}
