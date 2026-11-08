import { LitElement, html, nothing } from '../../shared/lit.js'
import type { TemplateResult } from '../../shared/lit.js'
import type { Filter, Tab, TabGroup } from '../types.js'

// The groups of tabs, each with what it holds: the catalog's tables first, then the views
// computed from them, then the editor demo.
const GROUPS: Array<{ group: TabGroup; label: string; description: string }> = [
  {
    group: 'tables',
    label: 'Catalog',
    description: 'The catalog as the bundle stores it: one CSV table per tab, each column described in datapackage.json; ' +
      '[PK] marks a primary key, [K] part of one, [FK] part of a foreign key. The views are computed from these tables.'
  },
  {
    group: 'views',
    label: 'Catalog Views',
    description: 'Computed from the catalog tables, one question each. Overview: which catalogue sets are there? ' +
      'Meanings: what does each software version call each key? Coverage: what does a converted result lack? ' +
      'Long table: which entries apply to which software version? Software: which versions does APB2 convert, and which catalogued columns does each write?'
  },
  {
    group: 'editor',
    label: 'Editor (demo)',
    description: 'A demo, not for production: edit the catalog tables in this browser. Start with sets, name your catalog, then add its terms, ' +
      'kinds and qualifiers, and map the terms in catalog. Foreign-key cells offer the values the referenced tables hold; red cells break a key. ' +
      'Edits stay in this page until you save every set, or the chosen set, as a zip of CSV tables; one set\'s zip is a plugin package\'s folder.'
  },
  {
    group: 'console',
    label: 'API console (demo)',
    description: 'A demo: run JavaScript against apb-catalog-ts, the TypeScript API, on the loaded bundle. ' +
      'Pick an example or write your own; rows come back as a table, anything else as JSON. The editor\'s tables are there as editor.'
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
    levels: { type: Array },
    locations: { type: Array },
    set: { type: String },
    level: { type: String },
    location: { type: String }
  }

  tab = 'overview'
  status = 'loading…'
  error = ''
  tabs: Tab[] = []
  sets: string[] = []
  levels: string[] = []
  locations: string[] = []
  set = ''
  level = ''
  location = ''

  createRenderRoot (): this { return this }

  // The tab last shown in each group, so returning to a group returns to it.
  #last = new Map<TabGroup, string>()

  hostFor (id: string): HTMLElement {
    const host = this.querySelector<HTMLElement>(`[data-views="${id}"]`)
    if (!host) throw new Error(`Catalog panel "${id}" has not rendered`)
    return host
  }

  get group (): TabGroup {
    return this.tabs.find(({ id }) => id === this.tab)?.group ?? 'tables'
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

  choose (change: Partial<Filter>): void {
    this.set = change.set ?? this.set
    this.level = change.level ?? this.level
    this.location = change.location ?? this.location
    this.dispatchEvent(new CustomEvent('filter-change', { detail: change, bubbles: true }))
  }

  /** The set a tab shows: none, the chosen one, or for a one-set tab the first when every set is chosen. */
  setFor (tab: Tab): string {
    if (tab.sets === 'none') return ''
    return tab.sets === 'one' && this.set === '' ? this.sets[0] ?? '' : this.set
  }

  /** What a tab shows: the chosen set, level and location where it takes them, every one elsewhere. */
  filterFor (tab: Tab): Filter {
    return { set: this.setFor(tab), level: tab.levels ? this.level : '', location: tab.locations ? this.location : '' }
  }

  /** One picker as tabs down the left: every value first where the tab takes every one. */
  picker (label: string, every: string | null, values: string[], chosen: string, pick: (value: string) => void): TemplateResult {
    const choices = [...(every === null ? [] : [{ value: '', text: every }]), ...values.map(value => ({ value, text: value }))]
    return html`
      <h2>${label}</h2>
      <nav class="tabs" role="tablist" aria-orientation="vertical" aria-label=${label}>
        ${choices.map(({ value, text }) => html`
          <button role="tab" aria-selected=${String(value === chosen)} @click=${() => { pick(value) }}>${text}</button>
        `)}
      </nav>
    `
  }

  /** The pickers a tab takes: catalogue set, level and location. */
  filters (tab: Tab): TemplateResult {
    const shown = this.filterFor(tab)
    return html`
      <aside class="filters">
        ${tab.sets === 'none' ? '' : this.picker('Catalogue set', tab.sets === 'any' ? 'every set' : null, this.sets, shown.set, set => { this.choose({ set }) })}
        ${tab.levels ? this.picker('Level', 'every level', this.levels, shown.level, level => { this.choose({ level }) }) : ''}
        ${tab.locations ? this.picker('Location', 'every location', this.locations, shown.location, location => { this.choose({ location }) }) : ''}
      </aside>
    `
  }

  render (): TemplateResult {
    const current = this.tabs.find(({ id }) => id === this.tab)
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
        ${this.tabs.filter(tab => tab.group === this.group).map(({ id, label, state }) => html`
          <button role="tab" aria-selected=${String(this.tab === id)} data-state=${state ?? nothing} title=${state ?? nothing} @click=${() => this.select(id)}>${label}</button>
        `)}
      </nav>
      <div class="workspace">
        ${current === undefined || (current.sets === 'none' && !current.levels && !current.locations) ? '' : this.filters(current)}
        <div class="panels">
          ${this.tabs.map(tab => html`
            <div ?hidden=${this.tab !== tab.id}>
              ${tab.id === 'software'
                ? html`<div class="split"><div data-views=${tab.id}></div><div data-views="software-detail" class="detail"></div></div>`
                : html`<div data-views=${tab.id}></div>`}
            </div>
          `)}
        </div>
      </div>
    `
  }
}

customElements.define('catalog-app', CatalogApp)

declare global {
  interface HTMLElementTagNameMap { 'catalog-app': CatalogApp }
  interface HTMLElementEventMap { 'filter-change': CustomEvent<Partial<Filter>> }
}
