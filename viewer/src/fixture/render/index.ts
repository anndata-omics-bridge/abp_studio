import type { MountedView, Renderer, View } from '../types.js'
import { noteRenderer } from './note.js'
import { chartRenderer } from './plotly.js'
import { tableRenderer } from './tabulator.js'

const RENDERERS = { table: tableRenderer, note: noteRenderer, chart: chartRenderer }

export function rendererFor<K extends keyof typeof RENDERERS> (backend: K): typeof RENDERERS[K] {
  return RENDERERS[backend]
}

async function mountWith<V extends View, H> (renderer: Renderer<V, H>, host: HTMLElement, view: V): Promise<MountedView> {
  const handle = await renderer.mount(host, view)
  return { resize: () => renderer.resize(handle), destroy: () => renderer.destroy(handle) }
}

// The backend-to-renderer boundary retains each view's matching handle type.
// Composition holds lifecycle closures, so it cannot pass a table handle to Plotly.
export function mountView (host: HTMLElement, view: View): Promise<MountedView> {
  switch (view.backend) {
    case 'table': return mountWith(rendererFor('table'), host, view)
    case 'note': return mountWith(rendererFor('note'), host, view)
    case 'chart': return mountWith(rendererFor('chart'), host, view)
  }
}
