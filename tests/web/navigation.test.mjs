import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { runInNewContext } from 'node:vm'
import { isolatedSource } from './source.mjs'
import {
  emptyRunFilters, emptyDatasetFilters, filterRuns, filterDatasets, runFacets, datasetFacets
} from '../../viewer/src/corpus/filters.ts'

const SHELL = fileURLToPath(new URL('../../viewer/src/corpus/shell/corpus-app.ts', import.meta.url))

// Execute the shell's navigation without importing the browser Lit module.
// Templates retain their values, so checks exercise the shell's rendered state.
class HTMLElement {
  constructor (properties = {}) { Object.assign(this, properties) }
}
class HTMLInputElement extends HTMLElement {}
class HTMLSelectElement extends HTMLElement {}

function createShell () {
  let App
  class LitElement extends HTMLElement {
    constructor () { super(); this.events = [] }
    dispatchEvent (event) { this.events.push(event) }
  }
  class CustomEvent {
    constructor (type, options) { this.type = type; Object.assign(this, options) }
  }
  runInNewContext(isolatedSource(SHELL), {
    LitElement,
    HTMLElement,
    HTMLInputElement,
    HTMLSelectElement,
    CustomEvent,
    emptyRunFilters, emptyDatasetFilters, filterRuns, filterDatasets, runFacets, datasetFacets,
    html: (strings, ...values) => ({ strings, values }),
    customElements: { define: (name, component) => { App = component } }
  }, { filename: SHELL })
  return new App()
}

function markup (value) {
  if (Array.isArray(value)) return value.map(markup).join('')
  if (value?.strings) {
    return value.strings.reduce((result, string, index) => result + string + markup(value.values[index]), '')
  }
  if (value == null || typeof value === 'function') return ''
  return String(value)
}

function tabButtons (app, attribute) {
  return [...markup(app.render()).matchAll(/<button\b[\s\S]*?<\/button>/g)]
    .map(match => match[0])
    .filter(button => button.includes(`${attribute}=`))
}

function ids (buttons, attribute) {
  return buttons.map(button => button.match(new RegExp(`${attribute}=["']?([^\\s"'>]+)`))[1])
}

function templates (value) {
  if (Array.isArray(value)) return value.flatMap(templates)
  if (!value?.strings) return []
  return [value, ...value.values.flatMap(templates)]
}

function keyboard (app, attribute) {
  const tabs = templates(app.render()).filter(template => template.strings.join('').includes(`${attribute}=`))
  const button = tabs[0]
  const handler = button.values[button.strings.findIndex(string => string.endsWith('@keydown='))]
  let focused
  return key => {
    let prevented = false
    handler({
      key,
      currentTarget: new HTMLElement({
        parentElement: {
          querySelectorAll: () => tabs.map((_tab, index) => ({ focus: () => { focused = index } }))
        }
      }),
      preventDefault: () => { prevented = true }
    })
    return { focused, prevented }
  }
}

test('the workspace opens on run combinations and keeps per-file navigation available', () => {
  const app = createShell()
  assert.equal(app.tab, 'runs')
  assert.equal(app.insightTab, 'results')
  const main = tabButtons(app, 'data-main-tab')
  assert.deepEqual(ids(main, 'data-main-tab'), ['runs', 'insights', 'files'])
  assert.equal(main.filter(button => button.includes('aria-selected=true')).length, 1)
  assert.match(main[0], /aria-selected=true/)
  assert.doesNotMatch(main[2], /\?disabled=true/)
  const rendered = markup(app.render())
  assert.match(rendered, /id="runs"[^>]*\?hidden=false/)
  assert.match(rendered, /id="insights"[^>]*\?hidden=true/)
  assert.match(rendered, /id="files"[^>]*\?hidden=true/)
  assert.ok(rendered.indexOf('id="files"') < rendered.indexOf('id="file-list"'))
  assert.ok(rendered.indexOf('id="file-list"') < rendered.indexOf('id="show-more"'))
})

test('choosing another run opens its dataset insights and emits the selected combination', () => {
  const app = createShell()
  app.tab = 'files'
  app.insightTab = 'log'
  app.selectRun('corpus/routine/convert/hdf5/run.json')
  assert.equal(app.tab, 'insights')
  assert.equal(app.insightTab, 'results')
  const event = app.events.find(event => event.type === 'run-change')
  assert.equal(event.detail.value, 'corpus/routine/convert/hdf5/run.json')
  assert.equal(event.bubbles, true)
})

test('insight subtabs stay separate from workspace navigation and retain their selection', () => {
  const app = createShell()
  assert.deepEqual(ids(tabButtons(app, 'data-insight-tab'), 'data-insight-tab'), [
    'results', 'visualizations', 'settings', 'log'
  ])
  app.select('insights')
  app.selectInsight('visualizations')
  assert.equal(app.tab, 'insights')
  assert.equal(app.insightTab, 'visualizations')
  assert.equal(app.events.at(-1).type, 'insight-tab-change')
  assert.equal(app.events.at(-1).detail.tab, 'visualizations')
  app.select('files')
  app.select('insights')
  assert.equal(app.insightTab, 'visualizations')
  const selected = tabButtons(app, 'data-insight-tab').filter(button => button.includes('aria-selected=true'))
  assert.deepEqual(ids(selected, 'data-insight-tab'), ['visualizations'])
})

test('file details can open before a dataset is selected and settings retain their own subtab', () => {
  const app = createShell()
  app.select('files')
  assert.equal(app.tab, 'files')
  assert.equal(app.events.at(-1).detail.tab, 'files')
  app.selectSettings('workflow-source')
  app.select('insights')
  app.selectInsight('settings')
  assert.equal(app.settingsTab, 'workflow-source')
  assert.equal(app.insightTab, 'settings')
})

test('workspace and insight tabs support wrapping arrows, Home and End with matching focus', () => {
  const app = createShell()
  const mainKey = keyboard(app, 'data-main-tab')
  assert.deepEqual(mainKey('ArrowLeft'), { focused: 2, prevented: true })
  assert.equal(app.tab, 'files')
  assert.deepEqual(mainKey('ArrowRight'), { focused: 0, prevented: true })
  assert.equal(app.tab, 'runs')
  assert.deepEqual(mainKey('End'), { focused: 2, prevented: true })
  assert.equal(app.tab, 'files')
  assert.deepEqual(mainKey('Home'), { focused: 0, prevented: true })
  assert.equal(app.tab, 'runs')
  assert.equal(mainKey('Escape').prevented, false)

  app.select('insights')
  const insightKey = keyboard(app, 'data-insight-tab')
  assert.deepEqual(insightKey('End'), { focused: 3, prevented: true })
  assert.equal(app.insightTab, 'log')
  assert.deepEqual(insightKey('ArrowRight'), { focused: 0, prevented: true })
  assert.equal(app.insightTab, 'results')
  assert.equal(app.tab, 'insights')
})


function run (corpus, workflow, format, datasets = 1) {
  return {
    path: `${corpus}/${workflow}/${format}/run.json`,
    label: `${corpus} · ${workflow} · ${format}`,
    manifest: { corpus_name: corpus, workflow, format, reports: Array.from({ length: datasets }, () => ({})) }
  }
}

function inputHandler (app, label) {
  const input = templates(app.render()).find(template => template.strings.join('').includes(`aria-label="${label}"`))
  assert.ok(input, `Missing input ${label}`)
  return input.values[input.strings.findIndex(string => string.endsWith('@input='))]
}

function facetHandler (app, value) {
  const checkbox = templates(app.render()).find(template =>
    template.strings.join('').includes('class="facet-choice"') && template.values.includes(value)
  )
  assert.ok(checkbox, `Missing facet checkbox ${value}`)
  return checkbox.values[checkbox.strings.findIndex(string => string.endsWith('@change='))]
}

test('the global selector stays above every workspace and run search narrows table and choices together', () => {
  const app = createShell()
  app.runs = [run('routine', 'convert', 'hdf5'), run('routine', 'convert', 'duckdb'), run('entrapment', 'proteobench_entrapment', 'hdf5')]
  app.runValue = app.runs[0].path
  app.runDisabled = false
  for (const tab of ['runs', 'insights', 'files']) {
    app.select(tab)
    const rendered = markup(app.render())
    assert.ok(rendered.indexOf('id="run-selector"') < rendered.indexOf('id="runs"'))
    assert.match(rendered, /aria-label="Find run"/)
  }
  inputHandler(app, 'Find run')({ currentTarget: new HTMLInputElement({ value: 'entrapment' }) })
  assert.equal(app.runFilters.search, 'entrapment')
  assert.deepEqual([...app.filteredRunChoices].map(item => item.label), ['entrapment · proteobench_entrapment · hdf5'])
  assert.equal(app.runValue, app.runs[0].path)
  assert.equal(app.tab, 'files')
  assert.ok(app.runOptions.some(([value, label]) => value === app.runValue && label.includes('outside filters')))
  assert.ok(app.runOptions.some(([value]) => value === app.runs[2].path))
  assert.ok(!app.runOptions.some(([value]) => value === app.runs[1].path))
  assert.ok(!app.events.some(event => event.type === 'run-change'))
  assert.match(markup(app.render()), /1 of 3 runs/)
  inputHandler(app, 'Search runs')({ currentTarget: new HTMLInputElement({ value: 'routine duckdb' }) })
  assert.equal(app.runFilters.search, 'routine duckdb')
  assert.deepEqual([...app.filteredRunChoices].map(item => item.path), [app.runs[1].path])
})

test('run facets toggle immutably, keep the active run pinned and clear without opening another run', () => {
  const app = createShell()
  app.runs = [run('routine', 'convert', 'hdf5'), run('routine', 'export_prolfqua', 'hdf5'), run('entrapment', 'proteobench_entrapment', 'hdf5')]
  app.runValue = app.runs[2].path
  const before = app.runFilters
  facetHandler(app, 'routine')({ currentTarget: new HTMLInputElement({ checked: true }) })
  assert.notEqual(app.runFilters, before)
  assert.equal(before.corpus.length, 0)
  assert.deepEqual([...app.filteredRunChoices].map(item => item.path), app.runs.slice(0, 2).map(item => item.path))
  assert.equal(app.runOptions.filter(([value]) => value === app.runValue).length, 1)
  app.toggleRunFacet('workflow', 'convert', true)
  assert.deepEqual([...app.filteredRunChoices].map(item => item.path), [app.runs[0].path])
  app.toggleRunFacet('workflow', 'convert', true)
  assert.equal(app.runFilters.workflow.length, 1)
  app.toggleRunFacet('workflow', 'convert', false)
  assert.equal(app.filteredRunChoices.length, 2)
  app.clearRunFilters()
  assert.equal(app.filteredRunChoices.length, 3)
  assert.equal(app.runValue, app.runs[2].path)
  assert.equal(app.events.length, 0)
})

test('dataset filter controls emit shared row filters without replacing selected panels', () => {
  const app = createShell()
  app.datasets = [
    { software_name: 'MaxQuant', module: 'dda', status: 'succeeded', input_file_name: 'peptides.txt' },
    { software_name: 'DIA-NN', module: 'dia', status: 'failed', input_file_name: 'report.tsv' }
  ]
  app.select('files')
  app.selectInsight('settings')
  inputHandler(app, 'Filter datasets')({ currentTarget: new HTMLInputElement({ value: 'peptides' }) })
  assert.equal(app.datasetFilters.search, 'peptides')
  assert.equal(app.events.at(-1).type, 'dataset-filter-change')
  assert.equal(app.events.at(-1).detail.filters, app.datasetFilters)
  assert.equal(app.events.at(-1).bubbles, true)
  facetHandler(app, 'MaxQuant')({ currentTarget: new HTMLInputElement({ checked: true }) })
  assert.deepEqual([...app.datasetFilters.software_name], ['MaxQuant'])
  assert.equal(app.tab, 'files')
  assert.equal(app.insightTab, 'settings')
  assert.match(markup(app.render()), /1 of 2 datasets/)
  app.clearDatasetFilters()
  assert.equal(app.events.at(-1).type, 'dataset-filter-change')
  assert.deepEqual(app.datasetFilters, emptyDatasetFilters())
  assert.equal(app.tab, 'files')
})

test('run headers sort actual workflow, format, corpus and numeric dataset counts', () => {
  const app = createShell()
  app.runs = [run('routine', 'export_prolfqua', 'hdf5', 11), run('entrapment', 'convert', 'parquet', 2), run('routine', 'aggregate', 'duckdb', 9)]
  assert.match(markup(app.render()), /<th scope="col">Open<\/th>/)
  assert.equal(tabButtons(app, 'data-run-sort').length, 5)
  app.sortRuns('datasets')
  assert.deepEqual([...app.sortedRunChoices].map(item => item.manifest.reports.length), [2, 9, 11])
  assert.match(markup(app.render()), /aria-sort=ascending/)
  app.sortRuns('datasets')
  assert.deepEqual([...app.sortedRunChoices].map(item => item.manifest.reports.length), [11, 9, 2])
  assert.match(markup(app.render()), /aria-sort=descending/)
  app.sortRuns('workflow')
  assert.deepEqual([...app.sortedRunChoices].map(item => item.manifest.workflow), ['aggregate', 'convert', 'export_prolfqua'])
  app.sortRuns('format')
  assert.deepEqual([...app.sortedRunChoices].map(item => item.manifest.format), ['duckdb', 'hdf5', 'parquet'])
  app.sortRuns('corpus_name')
  assert.deepEqual([...app.sortedRunChoices].map(item => item.manifest.corpus_name), ['entrapment', 'routine', 'routine'])
  assert.equal(app.events.length, 0)
})

test('the selector placeholder does not create an empty run selection', () => {
  const app = createShell()
  app.selectRun('')
  assert.equal(app.tab, 'runs')
  assert.equal(app.events.length, 0)
})

test('Runs and run overview show observed scientific extensions separately from HDF5', () => {
  const app = createShell()
  app.runs = [
    { ...run('routine', 'convert', 'hdf5', 2), outputExtensions: ['.h5mu'] },
    { ...run('proteobench', 'proteobench_pmultiqc', 'hdf5', 1), outputExtensions: ['.h5ad'] },
    run('pending', 'convert', 'hdf5', 1)
  ]
  app.runValue = app.runs[1].path
  let rendered = markup(app.render())
  assert.match(rendered, /data-run-sort=output/)
  assert.match(rendered, /class="run-output">\.h5ad<\/td>/)
  assert.match(rendered, /class="run-output">\.h5mu<\/td>/)
  assert.match(rendered, /class="run-output">—<\/td>/)
  assert.match(rendered, /Output: \.h5ad/)
  app.sortRuns('output')
  assert.deepEqual([...app.sortedRunChoices].map(choice => choice.outputExtensions?.join(',')), [undefined, '.h5ad', '.h5mu'])
  assert.equal(app.runs[0].manifest.format, 'hdf5')

  app.outputExtensions = ['.h5mu']
  rendered = markup(app.render())
  assert.match(rendered, /Output: \.h5mu/, 'the overview follows the current dataset reports')
  app.outputExtensions = []
  assert.match(markup(app.render()), /Output: —/, 'pending current records do not borrow stale extensions')
})


test('file chooser keeps search and counts visible while only facets collapse', () => {
  const app = createShell()
  app.datasets = [{ software_name: 'MaxQuant', module: 'dda', status: 'succeeded', input_file_name: 'peptides.txt' }]
  const rendered = markup(app.render())
  const files = rendered.slice(rendered.indexOf('id="files"'))
  assert.match(files, /aria-label="Filter datasets"/)
  assert.match(files, /1 of 1 datasets/)
  assert.equal([...rendered.matchAll(/class="dataset-filter-options"/g)].length, 1)
  assert.match(files, /<details class="dataset-filter-options">\s*<summary>Filter options<\/summary>/)
  assert.doesNotMatch(files, /<details[^>]*\bopen[= >]/)
  assert.ok(files.indexOf('</details>') < files.indexOf('id="file-list"'))
  const collapsed = files.slice(files.indexOf('<details'), files.indexOf('</details>'))
  assert.match(collapsed, /<fieldset class="facet">/)
  assert.doesNotMatch(collapsed, /Filter datasets|selection-count|Clear filters/)
})

test('dataset facets are closed dropdowns that retain multiple selected values and their counts', () => {
  const app = createShell()
  app.datasets = [
    { software_name: 'MaxQuant', module: 'dda', status: 'succeeded' },
    { software_name: 'DIA-NN', module: 'dia', status: 'succeeded' },
    { software_name: 'Sage', module: 'dda', status: 'failed' }
  ]
  const rendered = markup(app.render())
  const overview = rendered.slice(rendered.indexOf('id="insights"'), rendered.indexOf('id="files"'))
  assert.equal([...overview.matchAll(/<details class="facet-dropdown">/g)].length, 3)
  assert.doesNotMatch(overview, /<details[^>]*\bopen[= >]/)
  assert.match(overview, /class="facet-selection"[^>]*>All<\/span>/)
  facetHandler(app, 'MaxQuant')({ currentTarget: new HTMLInputElement({ checked: true }) })
  facetHandler(app, 'DIA-NN')({ currentTarget: new HTMLInputElement({ checked: true }) })
  assert.deepEqual([...app.datasetFilters.software_name], ['MaxQuant', 'DIA-NN'])
  assert.match(markup(app.render()), /class="facet-selection"[^>]*>MaxQuant, DIA-NN<\/span>/)
  assert.match(markup(app.render()), /2 of 3 datasets/)
  app.clearDatasetFilters()
  assert.match(markup(app.render()), /3 of 3 datasets/)
})

test('option selection follows active run after catalogs or filters replace the choice list', () => {
  const app = createShell()
  app.runs = [run('routine', 'convert', 'hdf5'), run('routine', 'export_prolfqua', 'hdf5')]
  app.runValue = app.runs[1].path
  const selectedOptions = () => [...markup(app.render()).matchAll(/<option\b[^>]*\.selected=true[^>]*>[\s\S]*?<\/option>/g)]
    .map(match => match[0])
  assert.equal(selectedOptions().length, 1)
  assert.match(selectedOptions()[0], /routine\/export_prolfqua\/hdf5\/run.json/)
  app.setRunSearch('convert')
  assert.equal(selectedOptions().length, 1)
  assert.match(selectedOptions()[0], /outside filters/)
  app.runs = [run('routine', 'convert', 'hdf5'), run('routine', 'export_prolfqua', 'hdf5'), run('routine', 'aggregate', 'hdf5')]
  assert.equal(selectedOptions().length, 1)
  app.clearRunFilters()
  app.runValue = app.runs[2].path
  assert.equal(selectedOptions().length, 1)
  assert.match(selectedOptions()[0], /routine\/aggregate\/hdf5\/run.json/)
})
