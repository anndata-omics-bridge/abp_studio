import { node } from './dom.js'

export interface TabSection { label: string; render: (panel: HTMLElement) => unknown | Promise<unknown> }

let serial = 0

/** Mount accessible, lazy tabs; notify the caller after a panel becomes visible. */
export async function renderTabs (host: HTMLElement, label: string, sections: TabSection[], onActivate: (panel: HTMLElement) => void = () => {}): Promise<void> {
  if (!sections.length) return
  const id = ++serial
  const tabs = document.createElement('div')
  tabs.className = 'tabs representation-tabs'
  tabs.setAttribute('role', 'tablist')
  tabs.setAttribute('aria-label', label)
  const panels = document.createElement('div')
  const rendered = new Set()

  const activate = async (index: number): Promise<void> => {
    const buttons = [...tabs.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
    const tabPanels = [...panels.children] as HTMLElement[]
    for (const [position, button] of buttons.entries()) {
      const selected = position === index
      button.setAttribute('aria-selected', String(selected))
      button.tabIndex = selected ? 0 : -1
      tabPanels[position].hidden = !selected
    }
    const panel = tabPanels[index]
    if (!rendered.has(index)) {
      rendered.add(index)
      panel.setAttribute('aria-busy', 'true')
      try {
        await sections[index].render(panel)
      } catch (error) {
        panel.replaceChildren(node('p', error, 'representation-error'))
      } finally {
        panel.removeAttribute('aria-busy')
      }
    }
    onActivate(panel)
  }

  for (const [index, section] of sections.entries()) {
    const tab = document.createElement('button')
    const panel = document.createElement('section')
    const tabId = `representation-tab-${id}-${index}`
    const panelId = `representation-panel-${id}-${index}`
    tab.type = 'button'
    tab.id = tabId
    tab.textContent = section.label
    tab.setAttribute('role', 'tab')
    tab.setAttribute('aria-controls', panelId)
    tab.setAttribute('aria-selected', 'false')
    tab.tabIndex = -1
    tab.addEventListener('click', () => { void activate(index) })
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
      const target = event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? sections.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + sections.length) % sections.length
      event.preventDefault()
      const next = tabs.children[target] as HTMLButtonElement | undefined
      next?.focus()
      void activate(target)
    })
    panel.id = panelId
    panel.className = 'representation-tab-panel'
    panel.setAttribute('role', 'tabpanel')
    panel.setAttribute('aria-labelledby', tabId)
    panel.hidden = true
    tabs.append(tab)
    panels.append(panel)
  }
  host.append(tabs, panels)
  await activate(0)
}
