import type { NoteView, Renderer } from '../types.js'
import { removeSection, sectionFor } from './section.js'

interface NoteHandle { body: HTMLElement }

export const noteRenderer: Renderer<NoteView, NoteHandle> = {
  name: 'note',
  async mount (host, view) {
    const { body } = sectionFor(host, view)
    const pre = document.createElement('pre')
    pre.textContent = view.text
    body.append(pre)
    return { body }
  },
  resize () {},
  destroy (handle) {
    removeSection(handle.body)
  }
}
