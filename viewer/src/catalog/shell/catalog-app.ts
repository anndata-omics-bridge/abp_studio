import { LitElement, html } from '../../shared/lit.js'
import type { TemplateResult } from '../../shared/lit.js'
import type { Tab, TabGroup } from '../types.js'

// The two groups of tabs, each with what it holds.
const GROUPS: Array<{ group: TabGroup; label: string; description: string }> = [
  {
    group: 'views',
    label: 'Views',
    description: 'Computed from the stored tables, one question each. Overview: which catalogue sets are there? ' +
      'Meanings: what does each software version call each key? Coverage: what does a converted result lack? ' +
      'Long table: which entries apply to which software version? Software: which versions does APB2 convert, and which catalogued columns does each write?'
  },
  {
    group: 'tables',
    label: 'Stored tables',
    description: 'The catalogue as the bundle stores it: one CSV table per tab, each column described in datapackage.json. The views are computed from these.'
  }
]

// The light-DOM shell emits intent. Composition supplies the tabs and their contents.
export class CatalogApp extends LitElement {
  static properties = {
    tab: { type: String },
    status: { type: String },
    error: { type: String },
    tabs: { type: Array },
    sets: { type: Array },
    set: { type: String }
  }

  tab = 'overview'
  status = 'loading…'
  error = ''
  tabs: Tab[] = []
  sets: string[] = []
  set = ''

  createRenderRoot (): this { return this }

  // The tab last shown in each group, so returning to a group returns to it.
  #last = new Map<TabGroup, string>()

  hostFor (id: string): HTMLElement {
    const host = this.querySelector<HTMLElement>(`[data-views="${id}"]`)
    if (!host) throw new Error(`Catalog panel "${id}" has not rendered`)
    return host
  }

  get group (): TabGroup {
    return this.tabs.find(({ id }) => id === this.tab)?.group ?? 'views'
  }

  select (tab: string): void {
    this.tab = tab
    this.#last.set(this.group, tab)
    this.dispatchEvent(new CustomEvent('tab-change', { detail: { tab }, bubbles: true }))
  }

  open (group: TabGroup): void {
    const tab = this.#last.get(group) ?? this.tabs.find(tab => tab.group === group)?.id
    if (tab !== undefined) this.select(tab)
  }

  choose (set: string): void {
    this.set = set
    this.dispatchEvent(new CustomEvent('set-change', { detail: { set }, bubbles: true }))
  }

  /** The set a tab shows: none, the chosen one, or for a one-set tab the first when every set is chosen. */
  setFor (tab: Tab): string {
    if (tab.sets === 'none') return ''
    return tab.sets === 'one' && this.set === '' ? this.sets[0] ?? '' : this.set
  }

  picker (tab: Tab): TemplateResult {
    const chosen = this.setFor(tab)
    return html`
      <label class="picker">
        Catalogue set
        <select @change=${(event: Event) => { this.choose((event.currentTarget as HTMLSelectElement).value) }}>
          ${tab.sets === 'any' ? html`<option value="" ?selected=${chosen === ''}>every set</option>` : ''}
          ${this.sets.map(set => html`<option value=${set} ?selected=${set === chosen}>${set}</option>`)}
        </select>
      </label>
    `
  }

  render (): TemplateResult {
    return html`
      <header class="masthead">
        <h1>APB Catalog</h1>
        <span class="status ${this.error ? 'error' : ''}">${this.error || this.status}</span>
      </header>
      <nav class="tabs groups" role="tablist" aria-label="Views">
        ${GROUPS.map(({ group, label }) => html`
          <button role="tab" aria-selected=${String(this.group === group)} @click=${() => this.open(group)}>${label}</button>
        `)}
      </nav>
      <p class="group-description">${GROUPS.find(({ group }) => group === this.group)?.description ?? ''}</p>
      <nav class="tabs" role="tablist" aria-label=${GROUPS.find(({ group }) => group === this.group)?.label ?? ''}>
        ${this.tabs.filter(tab => tab.group === this.group).map(({ id, label }) => html`
          <button role="tab" aria-selected=${String(this.tab === id)} @click=${() => this.select(id)}>${label}</button>
        `)}
      </nav>
      ${this.tabs.map(tab => html`
        <div ?hidden=${this.tab !== tab.id}>
          ${tab.sets === 'none' ? '' : this.picker(tab)}
          ${tab.id === 'software'
            ? html`<div class="split"><div data-views=${tab.id}></div><div data-views="software-detail" class="detail"></div></div>`
            : html`<div data-views=${tab.id}></div>`}
        </div>
      `)}
    `
  }
}

customElements.define('catalog-app', CatalogApp)

declare global {
  interface HTMLElementTagNameMap { 'catalog-app': CatalogApp }
  interface HTMLElementEventMap { 'set-change': CustomEvent<{ set: string }> }
}
