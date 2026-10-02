import { LitElement, html } from '../vendor/lit.js'

// The chrome: masthead, selectors, tabs and one light-DOM host per panel.
// It owns navigation state and emits user intent; app.js owns loading and composition.

const TABS = [
  ['results', 'Datasets'],
  ['show-more', 'Show more'],
  ['visualizations', 'Visualizations'],
  ['settings', 'Settings & inputs'],
  ['log', 'Scheduler log']
]

const SETTINGS_TABS = [
  ['execution-settings', 'Execution settings'],
  ['saved-run', 'Run manifest'],
  ['corpus-input', 'Corpus'],
  ['input-metadata', 'Input sizes'],
  ['workflow-input', 'Workflow table'],
  ['workflow-source', 'Workflow script']
]

class CorpusApp extends LitElement {
  static properties = {
    tab: { type: String },
    settingsTab: { type: String },
    error: { type: String },
    status: { type: String },
    counts: { type: String },
    steps: { type: String },
    fractions: { type: Object },
    runOptions: { type: Array },
    runValue: { type: String },
    runDisabled: { type: Boolean },
    showMoreDisabled: { type: Boolean },
    showMoreStatus: { type: String }
  }

  /** Create the shell with its explicit empty state. */
  constructor () {
    super()
    this.tab = 'results'
    this.settingsTab = 'execution-settings'
    this.error = ''
    this.status = 'Waiting for a run'
    this.counts = 'No saved run selected'
    this.steps = 'Steps: none recorded'
    this.fractions = {}
    this.runOptions = [['', 'No corpus runs yet']]
    this.runValue = ''
    this.runDisabled = true
    this.showMoreDisabled = true
    this.showMoreStatus = ''
  }

  /** @returns {HTMLElement} This light-DOM element, so Tabulator CSS applies. */
  createRenderRoot () { return this }

  /** @param {string} id Host identity. @returns {HTMLElement|null} Its element. */
  hostFor (id) { return this.querySelector(`#${id}`) }

  /** @param {string} tab Top-level tab to activate. */
  select (tab) {
    if (tab === 'show-more' && this.showMoreDisabled) return
    this.tab = tab
    this.dispatchEvent(new CustomEvent('tab-change', { detail: { tab }, bubbles: true }))
  }

  /** @param {string} tab Settings sub-tab to activate. */
  selectSettings (tab) {
    this.settingsTab = tab
    this.dispatchEvent(new CustomEvent('settings-tab-change', { detail: { tab }, bubbles: true }))
  }

  /** @param {string} value Selected run identity. */
  selectRun (value) {
    this.dispatchEvent(new CustomEvent('run-change', { detail: { value }, bubbles: true }))
  }

  /** @param {Array<[string, string]>} options Selector options. */
  options (options) {
    return options.map(([value, label]) => html`<option value=${value}>${label}</option>`)
  }

  /** @returns {import('../vendor/lit.js').TemplateResult} The application shell. */
  render () {
    const statuses = ['succeeded', 'failed', 'running', 'interrupted']
    return html`
      <header class="masthead">
        <h1>APB Studio — Corpus Runs</h1>
        <span class="status ${this.error ? 'error' : ''}">${this.error || this.status}</span>
      </header>
      <section class="run-controls" aria-label="Run selection">
        <label class="picker">Corpus · workflow · format
          <select .value=${this.runValue} ?disabled=${this.runDisabled} @change=${event => this.selectRun(event.target.value)}>
            ${this.options(this.runOptions)}
          </select>
        </label>
      </section>
      <section class="run-summary" aria-label="Run summary">
        <span>${this.counts}</span>
        <span>${this.steps}</span>
        <div class="status-bar" role="img" aria-label=${this.counts}>
          ${statuses.map(status => html`
            <span data-status=${status} style=${`width:${(this.fractions[status] ?? 0) * 100}%`}></span>
          `)}
        </div>
      </section>
      <nav class="tabs" role="tablist" aria-label="Run views">
        ${TABS.map(([id, label]) => html`
          <button
            role="tab"
            data-tab=${id}
            data-status=${id === 'show-more' ? this.showMoreStatus : ''}
            aria-selected=${String(this.tab === id)}
            ?disabled=${id === 'show-more' && this.showMoreDisabled}
            @click=${() => this.select(id)}
          >${label}</button>
        `)}
      </nav>
      <section id="results" class="view" ?hidden=${this.tab !== 'results'}><div id="datasets"></div></section>
      <section id="show-more" class="view" ?hidden=${this.tab !== 'show-more'}>
        <h2 id="detail-title">Select a dataset using its Show more button</h2>
        <nav id="detail-tabs" class="tabs subtabs detail-subtabs" aria-label="Dataset detail views" role="tablist" hidden></nav>
        <section id="detail-io" class="detail-panel" data-detail-panel="io" role="tabpanel" hidden>
          <h3>Inputs, outputs & intermediates</h3>
          <dl id="detail-files" class="dataset-files" hidden></dl>
          <div id="detail-notices"></div>
          <div id="detail-diagnostics"></div>
        </section>
        <div id="detail"></div>
      </section>
      <section id="visualizations" class="view" ?hidden=${this.tab !== 'visualizations'}>
        <h2>Corpus resource profiles</h2>
        <label class="visualization-x-axis">X axis
          <select id="visualization-x-axis" aria-label="Resource profile x axis">
            <option value="input_size_mib">Vendor input size (MiB)</option>
          </select>
        </label>
        <nav id="visualization-tabs" class="tabs subtabs visualization-tabs" aria-label="Workflow visualization views" role="tablist"></nav>
        <section id="visualization-chart-panel" class="visualization-chart-panel" role="tabpanel"></section>
      </section>
      <section id="settings" class="view" ?hidden=${this.tab !== 'settings'}>
        <div class="file-strip"><span>Files</span><div id="links"></div></div>
        <nav class="tabs subtabs" aria-label="Settings and input views">
          ${SETTINGS_TABS.map(([id, label]) => html`
            <button role="tab" data-settings-tab=${id} aria-selected=${String(this.settingsTab === id)} @click=${() => this.selectSettings(id)}>${label}</button>
          `)}
        </nav>
        <section id="execution-settings" class="settings-panel" ?hidden=${this.settingsTab !== 'execution-settings'}><h2>Execution settings</h2><div id="manifest"></div></section>
        <section id="saved-run" class="settings-panel" ?hidden=${this.settingsTab !== 'saved-run'}><h2>Run manifest</h2><div id="run-manifest"></div></section>
        <section id="corpus-input" class="settings-panel" ?hidden=${this.settingsTab !== 'corpus-input'}><h2 id="corpus-title">Corpus inventory</h2><p id="corpus-description"></p><div id="corpus"></div></section>
        <section id="input-metadata" class="settings-panel" ?hidden=${this.settingsTab !== 'input-metadata'}><h2 id="input-metadata-title">Input-size metadata</h2><div id="input-metadata-table"></div></section>
        <section id="workflow-input" class="settings-panel" ?hidden=${this.settingsTab !== 'workflow-input'}><h2 id="workflow-table-title">Workflow table</h2><div id="workflow-table"></div></section>
        <section id="workflow-source" class="settings-panel" ?hidden=${this.settingsTab !== 'workflow-source'}><h2>Workflow script</h2><pre id="source"></pre></section>
      </section>
      <section id="log" class="view" ?hidden=${this.tab !== 'log'}><h2>Snakemake</h2><pre id="scheduler-log"></pre></section>
      <footer>Reads persisted run files · refreshes every 2 seconds · APB failures remain inspectable</footer>
    `
  }
}

customElements.define('corpus-app', CorpusApp)
