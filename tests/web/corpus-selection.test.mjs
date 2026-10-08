import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'
import { isolatedSource } from './source.mjs'
import * as model from '../../viewer/src/corpus/model.ts'
import * as filters from '../../viewer/src/corpus/filters.ts'
import * as representation from '../../viewer/src/corpus/representation.ts'
import { representationScores } from '../../viewer/src/corpus/scores.ts'
import * as oddities from '../../viewer/src/corpus/oddities.ts'

function deferred () {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

function dataset (software, status = 'succeeded') {
  return {
    input_file: `inputs/${software}.tsv`, input_file_name: `${software}.tsv`,
    input_file_parent: 'inputs', input_file_size_bytes: 1024,
    module: 'dda', software_name: software, status,
    dataset: software, output_dir: `artifacts/${software}`, path: `${software}.json`,
    progress: `${software}.progress.json`, output_file: '', output_file_name: '',
    output_file_parent: '', output_file_size_bytes: null, output_file_format: null,
    runtime_seconds: 2, peak_memory_bytes: 1024, ion_variables: null,
    record: { status, steps: [{ name: 'convert', status, runtime_seconds: 2, outputs: [] }] }
  }
}

function manifest (corpus = 'routine', rows = []) {
  return {
    schema_version: 2, run_id: corpus, created_at: '2026-10-06T12:00:00Z',
    corpus_name: corpus, workflow: 'convert', format: 'hdf5', data_root: '/fixtures',
    cores: 1, corpus: 'corpus.csv', source_corpus: 'corpus.csv',
    workflow_source: 'workflow.py', execution_settings: 'settings.json',
    reports: rows.map(row => ({
      input_file: row.input_file, dataset: row.dataset, path: row.path,
      progress: row.progress, output_dir: row.output_dir
    }))
  }
}

function controller (options = {}) {
  const mounts = []
  const replacements = []
  const details = []
  const charts = []
  const comparisons = []
  const settingsRuns = []
  let settingsDirectory = ''
  let detailResets = 0
  const timers = new Map()
  const hosts = new Map()
  let timerId = 0
  let activeMounts = 0
  let maxActiveMounts = 0
  const app = {
    datasetFilters: filters.emptyDatasetFilters(), datasets: [], runs: [],
    tab: 'insights', insightTab: 'results', updateComplete: Promise.resolve(),
    hostFor (id) {
      if (!hosts.has(id)) hosts.set(id, { replaceChildren () {}, textContent: '' })
      return hosts.get(id)
    }
  }
  const detail = {
    columns: () => [], reset () { detailResets += 1 },
    async refresh (all, visible = all) { details.push({ all, visible }) }
  }
  const visualizations = { async render (views) { charts.push(views) }, resize () {} }
  const scores = { async render (run, rows, summaries, names) { comparisons.push({ run, rows, summaries, names }) } }
  const settings = {
    async renderRun (run) { settingsRuns.push(run.directory); settingsDirectory = run.directory },
    clear () { settingsDirectory = '' }, redraw () {}
  }
  const context = {
    ...model, ...filters, ...representation, ...oddities, representationScores,
    renderOdditiesSummary: () => {},
    emptyCsv: () => [],
    readCatalog: options.readCatalog ?? (async () => ({ runs: [] })),
    readInputKinds: options.readInputKinds ?? (async () => ({})),
    readStore: options.readStore ?? (async () => null),
    readStoreJson: options.readStoreJson ?? (async () => null),
    validatedToolTimings: () => null,
    async mountTable (_target, rows) {
      mounts.push(rows)
      activeMounts += 1
      maxActiveMounts = Math.max(maxActiveMounts, activeMounts)
      await options.mountReady
      activeMounts -= 1
      return {
        async replaceData (next) { replacements.push(next) },
        destroy () {}, redraw () {}
      }
    },
    window: {
      setTimeout (callback) { timers.set(++timerId, callback); return timerId },
      clearTimeout (id) { timers.delete(id) },
      requestAnimationFrame (callback) { callback() }, scrollTo () {}
    },
    console,
    app, detail, settings, visualizations, scores
  }
  const source = isolatedSource('viewer/src/corpus/app.ts').replace(/void main\(\);?\s*$/, '')
  const api = runInNewContext(`${source}\n({ state, renderSelection, refresh, refreshRun, loadRun })`, context)
  api.state.manifest = manifest()
  return {
    ...api, app, detail, visualizations, settings, mounts, replacements, details, charts, timers, settingsRuns, scores, comparisons,
    maxActiveMounts: () => maxActiveMounts,
    detailResets: () => detailResets,
    settingsDirectory: () => settingsDirectory
  }
}

const inputFiles = rows => Array.from(rows, row => row.input_file)
const chartSnapshot = views => JSON.parse(JSON.stringify(views))
const settle = async () => { for (let index = 0; index < 12; index += 1) await Promise.resolve() }

function savedRows (viewer, rows) {
  viewer.state.run = 'corpus/routine/convert/hdf5'
  viewer.state.manifest = manifest('routine', rows)
  viewer.state.corpus = rows.map(row => ({
    input_file: row.input_file, software_name: row.software_name, module: row.module,
    input_file_size_bytes: String(row.input_file_size_bytes)
  }))
  viewer.state.reports = new Map(rows.map(row => [row.path, row.record]))
}

test('dataset filters project tables and charts while details retain the complete run', async () => {
  const viewer = controller()
  const rows = [dataset('MaxQuant'), dataset('Sage'), dataset('FragPipe', 'failed')]
  savedRows(viewer, rows)
  viewer.app.datasetFilters = { ...filters.emptyDatasetFilters(), software_name: ['MaxQuant'] }
  await viewer.refreshRun(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  assert.deepEqual(inputFiles(viewer.app.datasets), inputFiles(rows), 'facets retain the full inventory')
  assert.deepEqual(inputFiles(viewer.mounts[0]), [rows[0].input_file])
  assert.deepEqual(inputFiles(viewer.details.at(-1).all), inputFiles(rows))
  assert.deepEqual(inputFiles(viewer.details.at(-1).visible), [rows[0].input_file])
  assert.deepEqual(inputFiles(viewer.comparisons.at(-1).rows), [rows[0].input_file])
  assert.deepEqual(Array.from(viewer.comparisons.at(-1).names), ['FragPipe', 'MaxQuant', 'Sage'])
  assert.deepEqual(viewer.charts.at(-1), model.chartViews([rows[0]], new Map(), new Map()))

  viewer.app.datasetFilters = { ...filters.emptyDatasetFilters(), search: 'absent' }
  await viewer.renderSelection(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  assert.deepEqual(inputFiles(viewer.replacements.at(-1)), [])
  assert.deepEqual(inputFiles(viewer.details.at(-1).all), inputFiles(rows))
  assert.deepEqual(inputFiles(viewer.details.at(-1).visible), [])
  assert.deepEqual(viewer.charts.at(-1), model.chartViews([], new Map(), new Map()))
})

test('rapid filter changes share one table mount and settle on the newest selection', async () => {
  const mounting = deferred()
  const viewer = controller({ mountReady: mounting.promise })
  const rows = [dataset('MaxQuant'), dataset('Sage'), dataset('FragPipe', 'failed')]
  viewer.state.rows = rows
  viewer.app.datasetFilters = { ...filters.emptyDatasetFilters(), software_name: ['MaxQuant'] }
  const first = viewer.renderSelection(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  await settle()
  assert.equal(viewer.mounts.length, 1)
  viewer.app.datasetFilters = { ...filters.emptyDatasetFilters(), software_name: ['Sage'] }
  const second = viewer.renderSelection(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  viewer.app.datasetFilters = { ...filters.emptyDatasetFilters(), status: ['failed'] }
  const third = viewer.renderSelection(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  await settle()
  assert.equal(viewer.mounts.length, 1, 'filter events cannot mount a second table while the first is pending')
  mounting.resolve()
  await Promise.all([first, second, third])
  assert.equal(viewer.maxActiveMounts(), 1)
  assert.equal(viewer.mounts.length, 1)
  assert.deepEqual(inputFiles(viewer.replacements.at(-1)), [rows[2].input_file])
  assert.deepEqual(inputFiles(viewer.details.at(-1).all), inputFiles(rows))
  assert.deepEqual(inputFiles(viewer.details.at(-1).visible), [rows[2].input_file])
  assert.deepEqual(viewer.charts.at(-1), model.chartViews([rows[2]], new Map(), new Map()))
})

test('refresh requests wait for the current load and settle on the latest requested run', async () => {
  const loadingFirst = deferred()
  const releaseFirst = deferred()
  const paths = ['first', 'second', 'third'].map(name => `corpus/${name}/convert/hdf5/run.json`)
  const manifests = new Map(paths.map((path, index) => [path, manifest(['first', 'second', 'third'][index])]))
  let catalogReads = 0
  const viewer = controller({
    async readCatalog () {
      catalogReads += 1
      return { runs: paths, output_extensions: { [paths[0]]: ['.h5mu'], [paths[2]]: ['.h5ad'] } }
    },
    async readStore (path, kind) {
      if (manifests.has(path)) return manifests.get(path)
      if (kind === 'csv') return []
      if (path.endsWith('/settings.json')) {
        if (path.includes('/first/')) {
          loadingFirst.resolve()
          await releaseFirst.promise
        }
        return { sources: [] }
      }
      return null
    }
  })
  viewer.state.manifest = null
  viewer.state.requested = paths[0]
  const first = viewer.refresh(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores)
  await loadingFirst.promise
  viewer.state.requested = paths[1]
  await viewer.refresh(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores)
  viewer.state.requested = paths[2]
  await viewer.refresh(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores)
  assert.equal(catalogReads, 1, 'selection requests cannot overlap the current catalogue/run load')

  releaseFirst.resolve()
  await first
  for (let attempt = 0; attempt < 10 && !viewer.timers.size; attempt += 1) await settle()
  assert.equal(catalogReads, 2, 'queued requests coalesce into one follow-up refresh')
  assert.equal(viewer.state.run, paths[2].replace('/run.json', ''))
  assert.equal(viewer.app.runValue, paths[2])
  assert.deepEqual(Array.from(viewer.app.runs.find(run => run.path === paths[2]).outputExtensions), ['.h5ad'])
  assert.deepEqual(viewer.settingsRuns, [paths[0], paths[2]].map(path => path.replace('/run.json', '')))
  assert.equal(viewer.timers.size, 1, 'one polling timer resumes after the latest run settles')
  assert.equal(viewer.app.error, '')
})

test('run overview output extensions follow all current reports independently of row filters', async () => {
  const viewer = controller()
  const rows = [dataset('MaxQuant'), dataset('Sage')]
  rows[0].record.steps[0].outputs = [{ role: 'converted', path: '/results/artifacts/MaxQuant/full.h5mu', size_bytes: 100 }]
  rows[1].record.steps[0].outputs = [
    { role: 'result', path: '/results/artifacts/Sage/ions.h5ad', size_bytes: 100 },
    { role: 'representation', path: '/results/artifacts/Sage/ions.h5ad.apb.json', size_bytes: 200 }
  ]
  savedRows(viewer, rows)
  viewer.app.datasetFilters = { ...filters.emptyDatasetFilters(), software_name: ['MaxQuant'] }
  await viewer.refreshRun(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  assert.deepEqual(Array.from(viewer.app.outputExtensions), ['.h5ad', '.h5mu'])
  assert.deepEqual(inputFiles(viewer.mounts[0]), [rows[0].input_file])

  viewer.state.reports.set(rows[1].path, { status: 'running', steps: [] })
  await viewer.refreshRun(viewer.app, viewer.detail, viewer.visualizations, viewer.scores)
  assert.deepEqual(Array.from(viewer.app.outputExtensions), ['.h5mu'], 'polling removes obsolete observed outputs')
})

test('updated manifests preserve filters and file selection until the run path changes', async () => {
  const viewer = controller({
    async readStore (path, kind) {
      if (kind === 'csv') return []
      return path.endsWith('/settings.json') ? { sources: [] } : null
    }
  })
  const path = 'corpus/routine/convert/hdf5/run.json'
  viewer.state.run = path.replace('/run.json', '')
  const selectedFilters = { ...filters.emptyDatasetFilters(), software_name: ['Sage'] }
  viewer.app.datasetFilters = selectedFilters
  await viewer.loadRun(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores, {
    path, label: 'routine · convert · hdf5', manifest: manifest()
  })
  assert.equal(viewer.app.datasetFilters, selectedFilters)
  assert.equal(viewer.detailResets(), 0, 'a new snapshot of the same run preserves its opened detail')

  await viewer.loadRun(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores, {
    path: 'corpus/other/convert/hdf5/run.json', label: 'other · convert · hdf5', manifest: manifest('other')
  })
  assert.deepEqual(viewer.app.datasetFilters, filters.emptyDatasetFilters())
  assert.equal(viewer.detailResets(), 1)
})

test('a failed run load clears previous evidence and retries the new combination', async () => {
  const oldRow = dataset('MaxQuant')
  const newRow = dataset('Sage')
  const oldDirectory = 'corpus/routine/convert/hdf5'
  const newDirectory = 'corpus/other/convert/hdf5'
  const oldPath = `${oldDirectory}/run.json`
  const newPath = `${newDirectory}/run.json`
  const oldManifest = manifest('routine', [oldRow])
  const newManifest = manifest('other', [newRow])
  let settingsAvailable = false
  const viewer = controller({
    async readCatalog () { return { runs: [oldPath, newPath] } },
    async readStore (path, kind) {
      if (path === oldPath) return oldManifest
      if (path === newPath) return newManifest
      if (kind === 'csv') {
        const row = path.startsWith(oldDirectory) ? oldRow : newRow
        return [{ input_file: row.input_file, software_name: row.software_name, module: row.module,
          input_file_size_bytes: String(row.input_file_size_bytes) }]
      }
      if (path === `${newDirectory}/settings.json` && !settingsAvailable) {
        assert.equal(viewer.settingsDirectory(), '', 'old settings clear before new settings are read')
        assert.deepEqual(chartSnapshot(viewer.charts.at(-1)), model.chartViews([]))
        assert.equal(viewer.app.hostFor('scheduler-log').textContent, '')
        return null
      }
      if (path.endsWith('/settings.json')) return { sources: [] }
      if (path === `${oldDirectory}/${oldRow.path}`) return oldRow.record
      if (path === `${newDirectory}/${newRow.path}`) return newRow.record
      return null
    }
  })
  viewer.state.manifest = null
  viewer.state.requested = oldPath
  await viewer.refresh(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores)
  assert.equal(viewer.settingsDirectory(), oldDirectory)
  assert.deepEqual(viewer.charts.at(-1), model.chartViews([oldRow], new Map(), new Map()))
  viewer.app.hostFor('scheduler-log').textContent = 'Old run scheduler output'

  viewer.state.requested = newPath
  await viewer.refresh(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores)
  assert.match(viewer.app.error, /Run execution settings are missing/)
  assert.equal(viewer.app.runValue, newPath)
  assert.equal(viewer.state.run, newDirectory)
  assert.equal(viewer.state.manifest, null)
  assert.equal(viewer.state.manifestStamp, '')
  assert.deepEqual(inputFiles(viewer.app.datasets), [])
  assert.equal(viewer.settingsDirectory(), '')
  assert.deepEqual(chartSnapshot(viewer.charts.at(-1)), model.chartViews([]))
  assert.equal(viewer.comparisons.at(-1).run, newDirectory)
  assert.deepEqual(inputFiles(viewer.comparisons.at(-1).rows), [], 'failed loads cannot retain the previous run’s score comparison')
  assert.equal(viewer.app.hostFor('scheduler-log').textContent, '')

  settingsAvailable = true
  await viewer.refresh(viewer.app, viewer.detail, viewer.settings, viewer.visualizations, viewer.scores)
  assert.equal(viewer.app.error, '')
  assert.equal(viewer.app.runValue, newPath)
  assert.equal(viewer.state.manifest, newManifest)
  assert.equal(viewer.state.manifestStamp, JSON.stringify(newManifest))
  assert.equal(viewer.settingsDirectory(), newDirectory)
  assert.deepEqual(inputFiles(viewer.app.datasets), [newRow.input_file])
  assert.deepEqual(viewer.charts.at(-1), model.chartViews([newRow], new Map(), new Map()))
  assert.equal(viewer.timers.size, 1)
})
