import { LitElement, html } from '../../shared/lit.js'
import type { TemplateResult } from '../../shared/lit.js'
import type { DatasetRow, RunChoice } from '../types.js'
import {
  emptyRunFilters, emptyDatasetFilters, filterRuns, filterDatasets, runFacets, datasetFacets
} from '../filters.js'
import type { RunFilters, DatasetFilters } from '../filters.js'

export type MainTab = 'runs' | 'insights' | 'files'
export type InsightTab = 'results' | 'visualizations' | 'scores' | 'settings' | 'log'
export type SettingsTab = 'execution-settings' | 'saved-run' | 'corpus-input' | 'input-metadata' | 'workflow-input' | 'workflow-source'

// Global selectors, faceted sidebars, tabs and one light-DOM host per panel.
// It owns navigation state and emits user intent; app.ts owns loading and composition.

const MAIN_TABS = [
  ['runs', 'Runs'],
  ['insights', 'Run overview'],
  ['files', 'File details']
] as const

const RUN_COLUMNS = [
  ['corpus_name', 'Corpus'], ['workflow', 'Workflow'], ['format', 'Format'], ['output', 'Output'], ['datasets', 'Datasets']
] as const

type RunSort = typeof RUN_COLUMNS[number][0]

const INSIGHT_TABS = [
  ['results', 'Datasets'],
  ['visualizations', 'Visualizations'],
  ['scores', 'Score comparison'],
  ['settings', 'Settings & inputs'],
  ['log', 'Scheduler log']
] as const

const SETTINGS_TABS = [
  ['execution-settings', 'Execution settings'],
  ['saved-run', 'Run manifest'],
  ['corpus-input', 'Corpus'],
  ['input-metadata', 'Input sizes'],
  ['workflow-input', 'Workflow table'],
  ['workflow-source', 'Workflow script']
] as const

export class CorpusApp extends LitElement {
  static properties = {
    tab: { type: String },
    insightTab: { type: String },
    runs: { type: Array },
    datasets: { type: Array },
    outputExtensions: { attribute: false },
    runFilters: { attribute: false },
    runSort: { state: true },
    datasetFilters: { attribute: false },
    settingsTab: { type: String },
    error: { type: String },
    status: { type: String },
    counts: { type: String },
    steps: { type: String },
    fractions: { type: Object },
    runValue: { type: String },
    runDisabled: { type: Boolean },
    hasProteobench: { type: Boolean }
  }

  tab: MainTab = 'runs'
  insightTab: InsightTab = 'results'
  runs: RunChoice[] = []
  datasets: DatasetRow[] = []
  outputExtensions: string[] | null = null
  runFilters: RunFilters = emptyRunFilters()
  runSort: { key: RunSort; descending: boolean } = { key: 'corpus_name', descending: false }
  datasetFilters: DatasetFilters = emptyDatasetFilters()
  settingsTab: SettingsTab = 'execution-settings'
  error = ''
  status = 'Waiting for a run'
  counts = 'No saved run selected'
  steps = 'Steps: none recorded'
  fractions: Record<string, number> = {}
  runValue = ''
  runDisabled = true
  hasProteobench = false
  private headerObserver: ResizeObserver | null = null

  /** Use light DOM so the shared table styles apply to each panel. */
  createRenderRoot (): HTMLElement { return this }

  connectedCallback () {
    super.connectedCallback()
    const header = this.querySelector<HTMLElement>('.bar')
    if (header) this.headerObserver?.observe(header)
  }

  firstUpdated () {
    const header = this.querySelector<HTMLElement>('.bar')
    if (!header) return
    this.headerObserver = new ResizeObserver(() => {
      this.style.setProperty('--corpus-bar-height', `${header.offsetHeight}px`)
    })
    this.headerObserver.observe(header)
  }

  disconnectedCallback () {
    this.headerObserver?.disconnect()
    super.disconnectedCallback()
  }

  /** Restore the active choice after Lit replaces the filtered native options. */
  updated () {
    const selector = this.querySelector<HTMLSelectElement>('#run-selector')
    if (selector && selector.value !== this.runValue) selector.value = this.runValue
  }

  /** Shell hosts exist after updateComplete; a missing host is a wiring error. */
  hostFor (id: string): HTMLElement {
    const host = this.querySelector<HTMLElement>(`#${id}`)
    if (!host) throw new Error(`Missing corpus panel host: ${id}`)
    return host
  }

  /** Activate a workspace without resetting its nested view. */
  select (tab: MainTab) {
    this.tab = tab
    this.dispatchEvent(new CustomEvent('tab-change', { detail: { tab }, bubbles: true }))
  }

  /** Activate a run overview subtab. */
  selectInsight (tab: InsightTab) {
    this.insightTab = tab
    this.dispatchEvent(new CustomEvent('insight-tab-change', { detail: { tab }, bubbles: true }))
  }

  /** Arrow-key navigation follows the same selections as pointer navigation. */
  tabKeydown<T extends string> (event: KeyboardEvent, choices: readonly (readonly [T, string])[], selected: T, activate: (tab: T) => void) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const current = choices.findIndex(([id]) => id === selected)
    const index = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1
      : (current + (event.key === 'ArrowRight' ? 1 : -1) + choices.length) % choices.length
    event.preventDefault()
    activate(choices[index][0])
    const button = event.currentTarget
    if (button instanceof HTMLElement) {
      button.parentElement?.querySelectorAll<HTMLElement>('[role="tab"]')[index]?.focus()
    }
  }

  /** Activate a settings subtab. */
  selectSettings (tab: SettingsTab) {
    this.settingsTab = tab
    this.dispatchEvent(new CustomEvent('settings-tab-change', { detail: { tab }, bubbles: true }))
  }

  /** Opening a run enters its overview; filtering never changes this selection. */
  selectRun (value: string) {
    if (!value) return
    this.selectInsight('results')
    this.select('insights')
    this.dispatchEvent(new CustomEvent('run-change', { detail: { value }, bubbles: true }))
  }

  get filteredRunChoices (): RunChoice[] {
    return filterRuns(this.runs, this.runFilters)
  }

  get sortedRunChoices (): RunChoice[] {
    const { key, descending } = this.runSort
    return [...this.filteredRunChoices].sort((first, second) => {
      const comparison = key === 'datasets'
        ? (first.manifest.reports?.length ?? 0) - (second.manifest.reports?.length ?? 0)
        : key === 'output'
          ? (first.outputExtensions ?? []).join(',').localeCompare((second.outputExtensions ?? []).join(','))
          : first.manifest[key].localeCompare(second.manifest[key], undefined, { numeric: true })
      return comparison * (descending ? -1 : 1)
    })
  }

  get selectedOutputExtensions (): string[] {
    return this.outputExtensions ?? this.runs.find(run => run.path === this.runValue)?.outputExtensions ?? []
  }

  get selectedRun (): RunChoice | undefined {
    return this.runs.find(run => run.path === this.runValue)
  }

  get insightTabs () {
    return INSIGHT_TABS.filter(([id]) => id !== 'scores' || this.hasProteobench)
  }

  sortRuns (key: RunSort) {
    this.runSort = { key, descending: this.runSort.key === key && !this.runSort.descending }
  }

  get runOptions (): [string, string][] {
    const matches = this.sortedRunChoices
    const options: [string, string][] = [['', this.runs.length
      ? `Choose from ${matches.length} matching runs` : 'No corpus runs yet']]
    const selected = this.runs.find(run => run.path === this.runValue)
    if (selected && !matches.includes(selected)) {
      options.push([selected.path, `${selected.label} (selected; outside filters)`])
    }
    return [...options, ...matches.map((run): [string, string] => [run.path, run.label])]
  }

  setRunSearch (search: string) {
    this.runFilters = { ...this.runFilters, search }
  }

  toggleRunFacet (key: Exclude<keyof RunFilters, 'search'>, value: string, selected: boolean) {
    this.runFilters = { ...this.runFilters, [key]: this.toggledValues(this.runFilters[key], value, selected) }
  }

  clearRunFilters () { this.runFilters = emptyRunFilters() }

  setDatasetSearch (search: string) {
    this.setDatasetFilters({ ...this.datasetFilters, search })
  }

  toggleDatasetFacet (key: Exclude<keyof DatasetFilters, 'search'>, value: string, selected: boolean) {
    this.setDatasetFilters({ ...this.datasetFilters, [key]: this.toggledValues(this.datasetFilters[key], value, selected) })
  }

  clearDatasetFilters () { this.setDatasetFilters(emptyDatasetFilters()) }

  private setDatasetFilters (filters: DatasetFilters) {
    this.datasetFilters = filters
    this.dispatchEvent(new CustomEvent('dataset-filter-change', { detail: { filters }, bubbles: true }))
  }

  private toggledValues (values: readonly string[], value: string, selected: boolean): string[] {
    return selected ? [...new Set([...values, value])] : values.filter(item => item !== value)
  }

  /** Facets narrow rows; checkbox counts include the other active filters. */
  private renderFacet<Key extends string> (
    group: { key: Key; label: string; options: { value: string; count: number }[] },
    selected: readonly string[],
    toggle: (key: Key, value: string, selected: boolean) => void
  ): TemplateResult {
    return html`
      <fieldset class="facet">
        <legend>${group.label}</legend>
        ${group.options.map(option => html`
          <label class="facet-choice">
            <input type="checkbox" .checked=${selected.includes(option.value)}
              @change=${(event: Event) => {
                const input = event.currentTarget
                if (input instanceof HTMLInputElement) toggle(group.key, option.value, input.checked)
              }}>
            <span class="facet-value">${option.value || 'Unspecified'}</span>
            <span class="facet-count">${option.count}</span>
          </label>
        `)}
      </fieldset>
    `
  }

  private renderDatasetFilters (compact = false): TemplateResult {
    const matches = filterDatasets(this.datasets, this.datasetFilters)
    const facets = datasetFacets(this.datasets, this.datasetFilters).map(group => {
      const selected = this.datasetFilters[group.key]
      return html`
        <details class="facet-dropdown">
          <summary>
            <span>${group.label}</span>
            <span class="facet-selection" title=${selected.join(', ')}>${selected.join(', ') || 'All'}</span>
          </summary>
          ${this.renderFacet(group, selected, (key, value, checked) => this.toggleDatasetFacet(key, value, checked))}
        </details>
      `
    })
    return html`
      <label class="filter-label">Filter datasets
        <input type="search" aria-label="Filter datasets" placeholder="file, software, acquisition…"
          .value=${this.datasetFilters.search} @input=${(event: Event) => {
            const input = event.currentTarget
            if (input instanceof HTMLInputElement) this.setDatasetSearch(input.value)
          }}>
      </label>
      ${compact ? html`
        <details class="dataset-filter-options">
          <summary>Filter options</summary>
          ${facets}
        </details>
      ` : facets}
      <div class="sidebar-actions">
        <span class="selection-count">${matches.length} of ${this.datasets.length} datasets</span>
        <button type="button" @click=${() => this.clearDatasetFilters()}>Clear filters</button>
      </div>
    `
  }

  /** Keep the selected run explicit; changing it is a separate compact control. */
  private renderRunBanner (): TemplateResult {
    const selected = this.selectedRun
    return html`
      <section class="run-banner" aria-label="Selected run">
        <span class="run-banner-title">Selected run</span>
        ${selected ? html`
          <dl class="run-banner-identity">
            <div><dt>Corpus</dt><dd>${selected.manifest.corpus_name}</dd></div>
            <div><dt>Workflow</dt><dd>${selected.manifest.workflow}</dd></div>
            <div><dt>Format</dt><dd>${selected.manifest.format}</dd></div>
            <div><dt>Output</dt><dd>${this.selectedOutputExtensions.join(', ') || '—'}</dd></div>
          </dl>
          <span class="run-banner-counts">${this.counts}</span>
        ` : html`<strong>Choose a run from Runs</strong>`}
      </section>
    `
  }

  private renderRunSelector (): TemplateResult {
    return html`
      <details class="run-switcher">
        <summary>Change run</summary>
        <label class="run-select">Run
        <select id="run-selector" aria-label="Corpus workflow and format" .value=${this.runValue}
          ?disabled=${this.runDisabled} @change=${(event: Event) => {
            const select = event.currentTarget
            if (select instanceof HTMLSelectElement && select.value) {
              this.selectRun(select.value)
              select.closest('details')?.removeAttribute('open')
            }
          }}>
          ${this.runOptions.map(([value, label]) => html`<option value=${value} .selected=${value === this.runValue}>${label}</option>`)}
        </select>
        </label>
      </details>
    `
  }

  /** Persistent panel hosts keep tables and scientific renderers mounted while filters change. */
  render (): TemplateResult {
    const statuses = ['succeeded', 'failed', 'running', 'interrupted']
    const runs = this.sortedRunChoices
    return html`
      <header class="bar">
        <h1 class="brand">APB Studio</h1>
        ${this.tab === 'runs' ? html`<strong class="catalog-title">Saved runs</strong>` : html`
          ${this.renderRunBanner()}
          ${this.renderRunSelector()}
        `}
        ${this.error || this.tab !== 'runs' ? html`
          <span class="status ${this.error ? 'error' : ''}" role="status">${this.error || this.status}</span>
        ` : ''}
      </header>
      <nav class="tabs main-tabs" role="tablist" aria-label="Workspace views">
        ${MAIN_TABS.map(([id, label]) => html`
          <button type="button" role="tab" id=${`tab-${id}`} data-main-tab=${id}
            aria-controls=${id} aria-selected=${String(this.tab === id)} tabindex=${this.tab === id ? 0 : -1}
            @keydown=${(event: KeyboardEvent) => this.tabKeydown(event, MAIN_TABS, this.tab, tab => this.select(tab))}
            @click=${() => this.select(id)}>${label}</button>
        `)}
      </nav>
      <section id="runs" class="view workspace-panel" role="tabpanel" aria-labelledby="tab-runs" ?hidden=${this.tab !== 'runs'}>
        <aside class="workspace-sidebar" aria-labelledby="run-facets-title">
          <h2 id="run-facets-title">Narrow the list</h2>
          <label class="filter-label">Search
            <input type="search" aria-label="Search runs" placeholder="corpus, workflow, format…"
              .value=${this.runFilters.search} @input=${(event: Event) => {
                const input = event.currentTarget
                if (input instanceof HTMLInputElement) this.setRunSearch(input.value)
              }}>
          </label>
          ${runFacets(this.runs, this.runFilters).map(group => this.renderFacet(
            group, this.runFilters[group.key], (key, value, selected) => this.toggleRunFacet(key, value, selected)
          ))}
          <div class="sidebar-actions">
            <span class="selection-count">${runs.length} of ${this.runs.length} runs</span>
            <button type="button" @click=${() => this.clearRunFilters()}>Clear filters</button>
          </div>
        </aside>
        <section class="workspace-content run-index" aria-label="Run index">
          <p class="view-description">Saved corpus runs. Narrow the list, then open a combination to explore its datasets and files.</p>
          <h2>${runs.length} of ${this.runs.length} runs</h2>
        ${runs.length ? html`
          <div class="run-catalog-wrap">
            <table class="run-catalog">
              <thead><tr><th scope="col">Open</th>${RUN_COLUMNS.map(([key, label]) => html`
                <th scope="col" aria-sort=${this.runSort.key === key ? (this.runSort.descending ? 'descending' : 'ascending') : 'none'}>
                  <button type="button" class="sort-run" data-run-sort=${key} @click=${() => this.sortRuns(key)}>
                    ${label}<span aria-hidden="true">${this.runSort.key === key ? (this.runSort.descending ? '▾' : '▴') : '↕'}</span>
                  </button>
                </th>
              `)}</tr></thead>
              <tbody>${runs.map(run => html`
                <tr aria-current=${run.path === this.runValue ? 'true' : 'false'}>
                  <td><button type="button" class="open-run" aria-label=${`Open ${run.label}`} @click=${() => this.selectRun(run.path)}>Open</button></td>
                  <td>${run.manifest.corpus_name}</td><td>${run.manifest.workflow}</td><td>${run.manifest.format}</td>
                  <td class="run-output">${run.outputExtensions?.join(' · ') || '—'}</td>
                  <td>${run.manifest.reports?.length ?? 0}</td>
                </tr>
              `)}</tbody>
            </table>
          </div>
        ` : html`<p class="empty-note">${this.runs.length ? 'No runs match the current filters.' : 'No saved corpus runs yet.'}</p>`}
        </section>
      </section>
      <section id="insights" class="view workspace-panel" role="tabpanel" aria-labelledby="tab-insights" ?hidden=${this.tab !== 'insights'}>
        <aside class="workspace-sidebar" aria-labelledby="dataset-filters-title">
          <h2 id="dataset-filters-title">Datasets in run</h2>
          ${this.renderDatasetFilters()}
        </aside>
        <section class="workspace-content">
        <nav class="tabs subtabs insight-tabs" role="tablist" aria-label="Run insight views">
          ${this.insightTabs.map(([id, label]) => html`
            <button type="button" role="tab" id=${`insight-tab-${id}`} data-insight-tab=${id}
              aria-controls=${id} aria-selected=${String(this.insightTab === id)} tabindex=${this.insightTab === id ? 0 : -1}
              @keydown=${(event: KeyboardEvent) => this.tabKeydown(event, this.insightTabs, this.insightTab, tab => this.selectInsight(tab))}
              @click=${() => this.selectInsight(id)}>${label}</button>
          `)}
        </nav>
        <section class="run-summary" aria-label="Run summary">
          <span>${this.counts}</span><span>${this.steps}</span>
          <span class="run-output">Output: ${this.selectedOutputExtensions.join(' · ') || '—'}</span>
          <div class="status-bar" role="img" aria-label=${this.counts}>
            ${statuses.map(status => html`<span data-status=${status} style=${`width:${(this.fractions[status] ?? 0) * 100}%`}></span>`)}
          </div>
        </section>
      <section id="results" class="view insight-panel" role="tabpanel" aria-labelledby="insight-tab-results" ?hidden=${this.insightTab !== 'results'}><div id="datasets"></div></section>
      <section id="visualizations" class="view insight-panel" role="tabpanel" aria-labelledby="insight-tab-visualizations" ?hidden=${this.insightTab !== 'visualizations'}>
        <h2>Corpus resource profiles</h2>
        <label class="visualization-x-axis">X axis
          <select id="visualization-x-axis" aria-label="Resource profile x axis">
            <option value="input_size_mib">Vendor input size (MiB)</option>
          </select>
        </label>
        <nav id="visualization-tabs" class="tabs subtabs visualization-tabs" aria-label="Workflow visualization views" role="tablist"></nav>
        <section id="visualization-chart-panel" class="visualization-chart-panel" role="tabpanel"></section>
      </section>
      <section id="scores" class="view insight-panel" role="tabpanel" aria-labelledby="insight-tab-scores" ?hidden=${this.insightTab !== 'scores' || !this.hasProteobench}></section>
      <section id="settings" class="view insight-panel" role="tabpanel" aria-labelledby="insight-tab-settings" ?hidden=${this.insightTab !== 'settings'}>
        <nav class="tabs subtabs" aria-label="Settings and input views">
          ${SETTINGS_TABS.map(([id, label]) => html`
            <button role="tab" data-settings-tab=${id} aria-selected=${String(this.settingsTab === id)} @click=${() => this.selectSettings(id)}>${label}</button>
          `)}
        </nav>
        <section id="execution-settings" class="settings-panel" ?hidden=${this.settingsTab !== 'execution-settings'}><h2>Execution settings</h2><div id="execution-settings-links" class="settings-links"></div><div id="manifest"></div></section>
        <section id="saved-run" class="settings-panel" ?hidden=${this.settingsTab !== 'saved-run'}><h2>Run manifest</h2><div id="saved-run-links" class="settings-links"></div><div id="run-manifest"></div></section>
        <section id="corpus-input" class="settings-panel" ?hidden=${this.settingsTab !== 'corpus-input'}><h2 id="corpus-title">Corpus inventory</h2><div id="corpus-input-links" class="settings-links"></div><p id="corpus-description"></p><div id="corpus"></div></section>
        <section id="input-metadata" class="settings-panel" ?hidden=${this.settingsTab !== 'input-metadata'}><h2 id="input-metadata-title">Input-size metadata</h2><div id="input-metadata-links" class="settings-links"></div><div id="input-metadata-table"></div></section>
        <section id="workflow-input" class="settings-panel" ?hidden=${this.settingsTab !== 'workflow-input'}><h2 id="workflow-table-title">Workflow table</h2><div id="workflow-input-links" class="settings-links"></div><div id="workflow-table"></div></section>
        <section id="workflow-source" class="settings-panel" ?hidden=${this.settingsTab !== 'workflow-source'}><h2>Workflow script</h2><div id="workflow-source-links" class="settings-links"></div><pre id="source"></pre></section>
      </section>
      <section id="log" class="view insight-panel" role="tabpanel" aria-labelledby="insight-tab-log" ?hidden=${this.insightTab !== 'log'}><h2>Snakemake</h2><pre id="scheduler-log"></pre></section>
        </section>
      </section>
      <section id="files" class="view workspace-panel" role="tabpanel" aria-labelledby="tab-files" ?hidden=${this.tab !== 'files'}>
        <aside class="workspace-sidebar file-sidebar" aria-label="Dataset files">
          <h2>Choose a file</h2>
          ${this.renderDatasetFilters(true)}
          <nav id="file-list" aria-label="Choose a dataset file"></nav>
        </aside>
        <section id="show-more" class="workspace-content file-content">
        <h2 id="detail-title">Choose a file from the sidebar</h2>
        <nav id="detail-tabs" class="tabs subtabs detail-subtabs" aria-label="Dataset detail views" role="tablist" hidden></nav>
        <section id="detail-io" class="detail-panel" data-detail-panel="io" role="tabpanel" hidden>
          <h3>Workflow file flow</h3>
          <div id="detail-files" hidden></div>
          <div id="detail-notices"></div>
          <div id="detail-diagnostics"></div>
        </section>
        <div id="detail"></div>
      </section>
      </section>
      <footer>Reads persisted run files · refreshes every 2 seconds · APB failures remain inspectable</footer>
    `
  }
}

customElements.define('corpus-app', CorpusApp)


declare global {
  interface HTMLElementTagNameMap {
    'corpus-app': CorpusApp
  }
}
