import { LitElement, html } from '../../shared/lit.js'
import type { TemplateResult } from '../../shared/lit.js'
import type { Group, GroupField } from '../types.js'

const TABS = [
  ['catalog', 'Submissions'],
  ['overview', 'Counts'],
  ['resources', 'Resources'],
  ['storage', 'Storage']
] as const

type Tab = typeof TABS[number][0]
export type Host = Tab | 'detail'

// The light-DOM shell emits intent. Composition supplies the panel contents.
export class FixtureApp extends LitElement {
  static properties = {
    tab: { type: String },
    status: { type: String },
    error: { type: String },
    groups: { type: Array },
    group: { type: String }
  }

  tab: Tab = 'catalog'
  status = 'loading…'
  error = ''
  groups: Group[] = []
  group: GroupField = 'software_name'

  createRenderRoot (): this { return this }

  hostFor (id: Host): HTMLElement {
    const host = this.querySelector<HTMLElement>(`[data-views="${id}"]`)
    if (!host) throw new Error(`Fixture panel "${id}" has not rendered`)
    return host
  }

  select (tab: Tab): void {
    this.tab = tab
    this.dispatchEvent(new CustomEvent('tab-change', { detail: { tab }, bubbles: true }))
  }

  regroup (group: GroupField): void {
    this.group = group
    this.dispatchEvent(new CustomEvent('group-change', { detail: { group }, bubbles: true }))
  }

  render (): TemplateResult {
    return html`
      <header class="masthead">
        <h1>APB Studio — Fixture Store</h1>
        <span class="status ${this.error ? 'error' : ''}">${this.error || this.status}</span>
      </header>
      <nav class="tabs" role="tablist">
        ${TABS.map(([id, label]) => html`
          <button role="tab" aria-selected=${String(this.tab === id)} @click=${() => this.select(id)}>
            ${label}
          </button>
        `)}
      </nav>
      <div ?hidden=${this.tab !== 'catalog'}>
        <div data-views="catalog"></div>
        <div data-views="detail" class="detail"></div>
      </div>
      <div ?hidden=${this.tab !== 'overview'}>
        <label class="picker">
          Group by
          <select @change=${(event: Event) => {
            const select = event.currentTarget as HTMLSelectElement
            const group = this.groups.find(({ field }) => field === select.value)
            if (group) this.regroup(group.field)
          }}>
            ${this.groups.map(({ field, label }) => html`
              <option value=${field} ?selected=${field === this.group}>${label}</option>
            `)}
          </select>
        </label>
        <div data-views="overview"></div>
      </div>
      <div ?hidden=${this.tab !== 'resources'}><div data-views="resources"></div></div>
      <div ?hidden=${this.tab !== 'storage'}><div data-views="storage"></div></div>
    `
  }
}

customElements.define('fixture-app', FixtureApp)

declare global {
  interface HTMLElementTagNameMap { 'fixture-app': FixtureApp }
  interface HTMLElementEventMap { 'group-change': CustomEvent<{ group: GroupField }> }
}
