import { LitElement, html } from '../vendor/lit.js'

// The chrome: masthead, tabs and one host per panel. A humble view that only
// emits intent; app.js decides what each host shows.

const TABS = [
  ['catalog', 'Submissions'],
  ['overview', 'Counts'],
  ['resources', 'Resources'],
  ['storage', 'Storage']
]

class FixtureApp extends LitElement {
  static properties = {
    tab: { type: String },
    status: { type: String },
    error: { type: String },
    groups: { type: Array },
    group: { type: String }
  }

  /** Create the shell with empty state. */
  constructor () {
    super()
    this.tab = 'catalog'
    this.status = 'loading…'
    this.error = ''
    this.groups = []
    this.group = ''
  }

  /** @returns {HTMLElement} This light-DOM element, so Tabulator's CSS applies. */
  createRenderRoot () { return this }

  /**
   * Find the host element a panel renders into.
   *
   * @param {string} id Panel identity.
   * @returns {HTMLElement|null} Its host, or null before first render.
   */
  hostFor (id) {
    return this.querySelector(`[data-views="${id}"]`)
  }

  /** @param {string} tab The tab to activate. */
  select (tab) {
    this.tab = tab
    this.dispatchEvent(new CustomEvent('tab-change', { detail: { tab }, bubbles: true }))
  }

  /** @param {string} group The column to group the counts by. */
  regroup (group) {
    this.group = group
    this.dispatchEvent(new CustomEvent('group-change', { detail: { group }, bubbles: true }))
  }

  /** @returns {import('../vendor/lit.js').TemplateResult} The shell. */
  render () {
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
          <select @change=${(event) => this.regroup(event.target.value)}>
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
