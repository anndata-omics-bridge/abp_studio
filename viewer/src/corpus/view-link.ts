// A shared view travels in the URL fragment, which a static file server never receives:
// the run directory, its tabs, and in File details one dataset and its first-level tab.

export interface ViewLink {
  run: string
  tab: string
  insight: string
  settings: string
  dataset: string
  detail: string
}

/** The page address with only the fields the shared tab uses. */
export function viewLinkUrl (page: string, view: ViewLink): string {
  const used: [string, string][] = [['run', view.run], ['tab', view.tab]]
  if (view.tab === 'insights') used.push(['insight', view.insight])
  if (view.tab === 'insights' && view.insight === 'settings') used.push(['settings', view.settings])
  if (view.tab === 'files') used.push(['dataset', view.dataset], ['detail', view.detail])
  return `${page.split('#')[0]}#${new URLSearchParams(used.filter(([, value]) => value))}`
}

/** The view a fragment names, or null when it names no run. */
export function parsedViewLink (hash: string): ViewLink | null {
  const fields = new URLSearchParams(hash.replace(/^#/, ''))
  const field = (key: keyof ViewLink) => fields.get(key) ?? ''
  const run = field('run')
  if (!run) return null
  return {
    run,
    tab: field('tab'),
    insight: field('insight'),
    settings: field('settings'),
    dataset: field('dataset'),
    detail: field('detail')
  }
}
