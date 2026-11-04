import { LitElement, html } from '../../shared/lit.js'
import type { TemplateResult } from '../../shared/lit.js'
import type { Tab, TabId } from '../types.js'

/** The Document view of the Rule tab, beside its levels. */
export const DOCUMENT = 'document'

/** One entry of the rule picker. */
export interface RuleOption { rule: string; label: string; levels: string[] }

// The light-DOM shell emits intent. Composition supplies the tabs, the rules and their contents.
export class RulesApp extends LitElement {
  static properties = {
    tab: { type: String },
    status: { type: String },
    error: { type: String },
    tabs: { type: Array },
    rules: { type: Array },
    rule: { type: String },
    view: { type: String },
    levels: { type: Array },
    level: { type: String }
  }

  tab: TabId = 'rules'
  status = 'loading…'
  error = ''
  tabs: Tab[] = []
  rules: RuleOption[] = []
  /** The rule the Rule tab shows. */
  rule = ''
  /** The Rule tab's view: one of the rule's levels, or the document. */
  view = ''
  /** Every level of the bundle, for the level picker. */
  levels: string[] = []
  /** The level picked for the tabs across rules; empty for every level. */
  level = ''

  createRenderRoot (): this { return this }

  hostFor (id: string): HTMLElement {
    const host = this.querySelector<HTMLElement>(`[data-views="${id}"]`)
    if (!host) throw new Error(`Rules panel "${id}" has not rendered`)
    return host
  }

  get chosen (): RuleOption | undefined {
    return this.rules.find(({ rule }) => rule === this.rule)
  }

  select (tab: TabId): void {
    this.tab = tab
    this.dispatchEvent(new CustomEvent('tab-change', { detail: { tab }, bubbles: true }))
  }

  /** Show one rule on the Rule tab, at `view`, or at its first level. */
  open (rule: string, view?: string): void {
    this.rule = rule
    this.view = view ?? this.chosen?.levels[0] ?? DOCUMENT
    this.select('rule')
  }

  show (view: string): void {
    this.view = view
    this.dispatchEvent(new CustomEvent('rule-view-change', { detail: { view }, bubbles: true }))
  }

  choose (level: string): void {
    this.level = level
    this.dispatchEvent(new CustomEvent('level-change', { detail: { level }, bubbles: true }))
  }

  picker (): TemplateResult {
    return html`
      <label class="picker">
        Level
        <select @change=${(event: Event) => { this.choose((event.currentTarget as HTMLSelectElement).value) }}>
          <option value="" ?selected=${this.level === ''}>every level</option>
          ${this.levels.map(level => html`<option value=${level} ?selected=${level === this.level}>${level}</option>`)}
        </select>
      </label>
    `
  }

  ruleControls (): TemplateResult {
    const views = [...(this.chosen?.levels ?? []), DOCUMENT]
    return html`
      <label class="picker">
        Rule
        <select @change=${(event: Event) => { this.open((event.currentTarget as HTMLSelectElement).value) }}>
          ${this.rules.map(({ rule, label }) => html`<option value=${rule} ?selected=${rule === this.rule}>${label}</option>`)}
        </select>
      </label>
      <nav class="tabs levels" role="tablist" aria-label="Levels of the rule">
        ${views.map(view => html`
          <button role="tab" aria-selected=${String(this.view === view)} @click=${() => this.show(view)}>${view === DOCUMENT ? 'rules.json' : view}</button>
        `)}
      </nav>
    `
  }

  render (): TemplateResult {
    const open = this.tabs.find(({ id }) => id === this.tab)
    return html`
      <header class="masthead">
        <h1>APB Parsing Rules</h1>
        <span class="status ${this.error ? 'error' : ''}">${this.error || this.status}</span>
      </header>
      <nav class="tabs" role="tablist" aria-label="Views">
        ${this.tabs.map(({ id, label }) => html`
          <button role="tab" aria-selected=${String(this.tab === id)} @click=${() => this.select(id)}>${label}</button>
        `)}
      </nav>
      <p class="group-description">${open?.description ?? ''}</p>
      ${this.tabs.map(tab => html`
        <div ?hidden=${this.tab !== tab.id}>
          ${tab.levels ? this.picker() : ''}
          ${tab.id === 'rule' ? this.ruleControls() : ''}
          <div data-views=${tab.id}></div>
        </div>
      `)}
    `
  }
}

customElements.define('rules-app', RulesApp)

declare global {
  interface HTMLElementTagNameMap { 'rules-app': RulesApp }
  interface HTMLElementEventMap {
    'rule-view-change': CustomEvent<{ view: string }>
    'level-change': CustomEvent<{ level: string }>
  }
}
