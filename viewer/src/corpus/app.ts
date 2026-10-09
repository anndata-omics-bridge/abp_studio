import { emptyCsv, readCatalog, readInputKinds, readProteobenchReferences, readStore, readStoreJson } from './lib/fetch.js'
import { emptyDatasetFilters, filterDatasets } from './filters.js'
import {
  chartViews,
  counts,
  datasetRows,
  runChoices,
  scientificOutputExtensions,
  statusFractions,
  workflowSteps
} from './model.js'
import { createDetailPanel } from './panels/detail.js'
import { createScoresPanel } from './panels/scores.js'
import { representationScores } from './scores.js'
import { validatedOddities, withOddities } from './oddities.js'
import { renderOdditiesSummary } from './render/oddities.js'
import type { RepresentationSummary } from './scores.js'
import { createSettingsPanel } from './panels/settings.js'
import { createVisualizationPanel } from './panels/visualizations.js'
import { artifactStorePath, representationIonVariables, validatedRepresentation } from './representation.js'
import { mountTable } from './render/tabulator.js'
import { validatedToolTimings } from './tool-timings.js'
import type { CorpusApp } from './shell/corpus-app.js'
import './shell/corpus-app.js'
import './app.css'
import './representation.css'
import './json-viewer.css'
import type { ColumnDefinition, Tabulator } from '../shared/tabulator.js'
import type { Artifact, CatalogRun, CsvRows, DatasetReport, DatasetRow, InputKind, Operation, RunChoice, RunManifest, RunOddities, ToolTimings } from './types.js'
import type { ExecutionSettings } from './panels/settings.js'

type DetailPanel = ReturnType<typeof createDetailPanel>
type SettingsPanel = ReturnType<typeof createSettingsPanel>
type VisualizationPanel = ReturnType<typeof createVisualizationPanel>
type ScoresPanel = ReturnType<typeof createScoresPanel>
interface ViewerState {
  run: string
  requested: string
  manifestStamp: string
  operationStamp: string
  storeRoot: string
  manifest: RunManifest | null
  corpus: CsvRows
  inputMetadata: CsvRows
  inputKinds: Record<string, InputKind>
  workflowRows: CsvRows
  rows: DatasetRow[]
  reports: Map<string, DatasetReport>
  timingFiles: Map<string, ToolTimings | null>
  representationFiles: Map<string, RepresentationSummary | null>
  oddities: RunOddities | null
  odditiesStamp: string
  table: Tabulator | null
}
interface ArtifactEntry { row: DatasetRow; artifact: Artifact }

// Composition root. Server files enter through lib/fetch.js, pure model projections
// become views, and panel adapters own DOM-heavy rendering.

const state: ViewerState = {
  run: '',
  requested: '',
  manifestStamp: '',
  operationStamp: '',
  storeRoot: '',
  manifest: null,
  corpus: emptyCsv(),
  inputMetadata: emptyCsv(),
  inputKinds: {},
  workflowRows: emptyCsv(),
  rows: [],
  reports: new Map(),
  timingFiles: new Map(),
  representationFiles: new Map(),
  oddities: null,
  odditiesStamp: '',
  table: null
}

let selectionRender = Promise.resolve()
let refreshing = false
let refreshPending = false
let refreshTimer: number | undefined

function host (app: CorpusApp, id: string) { return app.hostFor(id) }

function ionDimensions (): Map<string, number | null> {
  return new Map([...state.representationFiles].map(([path, summary]) => [path, summary?.ionVariables ?? null]))
}

async function readRepresentation (path: string) {
  const document = await readStoreJson(path)
  return document ? validatedRepresentation(document) : null
}

async function table (target: HTMLElement, rows: DatasetRow[], columns: ColumnDefinition[]) {
  return mountTable(target, rows, columns.map(column => column.field
    ? { headerFilter: 'input', ...column }
    : column), {
    height: '55vh',
    placeholder: 'No records',
    columnDefaults: { formatter: 'plaintext' }
  })
}

function destroyTables () {
  if (state.table) state.table.destroy()
  state.table = null
}

function updateSummary (app: CorpusApp, status: string, rows: number, summary: Record<string, number>, steps: string[]) {
  app.status = status
  app.counts = `${rows} datasets · ${Object.entries(summary)
    .map(([name, count]) => `${count} ${name}`)
    .join(' · ')}`
  app.steps = `Steps: ${steps.join(' → ') || 'none recorded'}`
  app.fractions = statusFractions(summary, rows)
}

async function loadRun (app: CorpusApp, detail: DetailPanel, settings: SettingsPanel, visualizations: VisualizationPanel, scores: ScoresPanel, choice: RunChoice) {
  const directory = choice.path.slice(0, -'/run.json'.length)
  const runChanged = directory !== state.run
  state.manifest = null
  await selectionRender.catch(() => {})
  if (runChanged) {
    detail.reset()
    app.datasetFilters = emptyDatasetFilters()
  }
  destroyTables()
  host(app, 'datasets').replaceChildren()
  state.run = directory
  state.rows = []
  app.datasets = []
  app.outputExtensions = null
  state.manifestStamp = ''
  state.reports.clear()
  state.timingFiles.clear()
  state.representationFiles.clear()
  state.oddities = null
  state.odditiesStamp = ''
  state.operationStamp = ''
  const manifest = choice.manifest
  app.hasProteobench = Boolean(manifest.tools?.['apb-proteobench'])
  if (!app.hasProteobench && app.insightTab === 'scores') app.selectInsight('results')
  updateSummary(app, 'Loading run…', 0, {}, [])
  settings.clear()
  host(app, 'scheduler-log').textContent = ''
  await visualizations.render(chartViews([]))
  await scores.render(directory, [], new Map(), [])
  state.corpus = await readStore(`${state.run}/${manifest.corpus}`, 'csv') ?? emptyCsv()
  state.inputMetadata = manifest.input_metadata
    ? await readStore(`${state.run}/${manifest.input_metadata}`, 'csv') ?? emptyCsv()
    : emptyCsv()
  state.inputKinds = await readInputKinds(state.run)
  state.workflowRows = manifest.workflow_table
    ? await readStore(
      `${state.run}/${manifest.workflow_table}`,
      manifest.workflow_table.endsWith('.tsv') ? 'tsv' : 'csv'
    ) ?? emptyCsv()
    : emptyCsv()
  const config = await readStore<ExecutionSettings>(`${state.run}/${manifest.execution_settings}`)
  if (!config) throw new Error('Run execution settings are missing')
  await settings.renderRun({
    directory: state.run,
    storeRoot: state.storeRoot,
    manifest,
    config,
    corpus: state.corpus,
    inputMetadata: state.inputMetadata,
    workflowRows: state.workflowRows
  })
  state.manifest = manifest
  state.manifestStamp = JSON.stringify(manifest)
  await refreshRun(app, detail, visualizations, scores)
}

/** Serialize panel updates; each update projects the latest records and filters. */
function renderSelection (app: CorpusApp, detail: DetailPanel, visualizations: VisualizationPanel, scores: ScoresPanel): Promise<void> {
  selectionRender = selectionRender.catch(() => {}).then(async () => {
    if (!state.manifest) return
    const rows = filterDatasets(state.rows, app.datasetFilters)
    if (state.table) await state.table.replaceData(rows)
    else state.table = await table(host(app, 'datasets'), rows, detail.columns(state.workflowRows))
    await detail.refresh(state.rows, rows)
    await visualizations.render(chartViews(rows, state.timingFiles, ionDimensions()))
    await scores.render(state.run, rows, state.representationFiles, [...new Set(state.rows.map(row => row.software_name))].sort())
    renderOdditiesSummary(host(app, 'oddities'), state.oddities)
  })
  return selectionRender
}

async function renderSchedulerLog (app: CorpusApp) {
  if (!state.manifest) return
  const directory = state.run
  const log = await readStore(`${directory}/snakemake.log`, 'text')
  if (directory === state.run) host(app, 'scheduler-log').textContent = log ?? ''
}

/** Cap concurrent file reads so large corpuses do not flood the server. */
async function inBatches<T> (items: T[], read: (item: T) => Promise<void>): Promise<void> {
  for (let start = 0; start < items.length; start += 12) {
    await Promise.all(items.slice(start, start + 12).map(read))
  }
}

function outputsWithRole (rows: DatasetRow[], role: string): ArtifactEntry[] {
  return rows.flatMap(row => (row.record?.steps ?? []).flatMap(step =>
    step.status === 'succeeded'
      ? (step.outputs ?? []).filter(artifact =>
          artifact.role === role && artifact.size_bytes != null)
        .map(artifact => ({ row, artifact }))
      : []))
}

async function readArtifactCache<T> (
  entries: ArtifactEntry[], cache: Map<string, T | null>, validate: (document: unknown) => T | null, label: string
): Promise<void> {
  await inBatches(entries.filter(({ artifact }) => !cache.has(artifact.path)), async ({ row, artifact }) => {
    try {
      const path = artifactStorePath(state.run, row.output_dir, artifact.path)
      const document = await readStoreJson(path)
      cache.set(artifact.path, document ? validate(document) : null)
    } catch (error) {
      cache.set(artifact.path, null)
      console.warn(`Cannot read ${label} ${artifact.path}: ${error}`)
    }
  })
}

async function refreshRun (app: CorpusApp, detail: DetailPanel, visualizations: VisualizationPanel, scores: ScoresPanel) {
  if (!state.manifest) return
  const operation = await readStore<Operation>(`${state.run}/operation.json`)
  const odditiesDocument = await readStoreJson(`${state.run}/oddities.json`)
  const odditiesStamp = JSON.stringify(odditiesDocument)
  if (odditiesStamp !== state.odditiesStamp) {
    state.oddities = odditiesDocument ? validatedOddities(odditiesDocument, state.manifest.run_id) : null
    state.odditiesStamp = odditiesStamp
  }
  if (state.operationStamp !== (operation?.updated_at ?? '')) {
    state.reports.clear()
    state.timingFiles.clear()
    state.representationFiles.clear()
    state.operationStamp = operation?.updated_at ?? ''
  }
  const progress = new Map<string, DatasetReport | null>()
  const pending = state.manifest.reports.filter(link => !state.reports.has(link.path))
  await inBatches(pending, async link => {
    const report = await readStore<DatasetReport>(`${state.run}/${link.path}`)
    if (report) state.reports.set(link.path, report)
    else progress.set(link.progress, await readStore<DatasetReport>(`${state.run}/${link.progress}`))
  })
  let rows = datasetRows(
    state.manifest,
    state.corpus,
    state.inputMetadata,
    state.reports,
    progress,
    operation,
    state.workflowRows
  )
  await readArtifactCache(
    outputsWithRole(rows, 'tool_timings'), state.timingFiles,
    validatedToolTimings, 'tool timings'
  )
  await readArtifactCache(
    outputsWithRole(rows, 'representation'), state.representationFiles,
    document => ({
      ionVariables: representationIonVariables(document),
      scores: representationScores(validatedRepresentation(document))
    }), 'representation scores and dimensions'
  )
  rows = datasetRows(
    state.manifest, state.corpus, state.inputMetadata, state.reports, progress,
    operation, state.workflowRows, ionDimensions()
  ).map(row => ({ ...row, input_file_kind: state.inputKinds[row.input_file] ?? null }))
  rows = withOddities(rows, state.oddities)
  state.rows = rows
  app.datasets = rows
  app.outputExtensions = scientificOutputExtensions(rows.map(row => row.record))
  const summary = counts(rows)
  updateSummary(
    app,
    operation?.status ?? 'prepared',
    rows.length,
    summary,
    workflowSteps(rows)
  )
  await renderSelection(app, detail, visualizations, scores)
  if (app.tab === 'insights' && app.insightTab === 'log') {
    await renderSchedulerLog(app)
  }
}

async function refresh (app: CorpusApp, detail: DetailPanel, settings: SettingsPanel, visualizations: VisualizationPanel, scores: ScoresPanel) {
  if (refreshing) {
    refreshPending = true
    return
  }
  refreshing = true
  window.clearTimeout(refreshTimer)
  try {
    const catalog = await readCatalog()
    state.storeRoot = catalog.store_root ?? ''
    const paths = catalog.runs ?? []
    const candidates = await Promise.all(paths.map(async path => ({
      path, manifest: await readStore<RunManifest>(path),
      outputExtensions: catalog.output_extensions?.[path] ?? []
    })))
    const choices = runChoices(candidates.filter((candidate): candidate is CatalogRun & { outputExtensions: string[] } => candidate.manifest !== null))
    const current = state.requested || `${state.run}/run.json`
    const choice = choices.find(candidate => candidate.path === current) ?? choices[0]
    state.requested = ''
    app.runs = choices
    app.runValue = choice?.path ?? ''
    app.runDisabled = !choice
    const manifestChanged = choice && state.manifestStamp !== JSON.stringify(choice.manifest)
    if (choice && (`${state.run}/run.json` !== choice.path || manifestChanged)) {
      await loadRun(app, detail, settings, visualizations, scores, choice)
    } else if (choice) {
      await refreshRun(app, detail, visualizations, scores)
    } else if (state.run) {
      state.run = ''
      state.manifest = null
      await selectionRender.catch(() => {})
      state.rows = []
      app.datasets = []
      app.outputExtensions = null
      app.hasProteobench = false
      state.manifestStamp = ''
      state.reports.clear()
      state.timingFiles.clear()
      state.representationFiles.clear()
      state.oddities = null
      state.odditiesStamp = ''
      destroyTables()
      detail.reset()
      settings.clear()
      host(app, 'datasets').replaceChildren()
      host(app, 'scheduler-log').textContent = ''
      updateSummary(app, 'Waiting for a run', 0, {}, [])
      await visualizations.render(chartViews([]))
      await scores.render('', [], new Map(), [])
      renderOdditiesSummary(host(app, 'oddities'), null)
    }
    app.error = ''
  } catch (error) {
    app.error = String(error)
  } finally {
    refreshing = false
    if (refreshPending) {
      refreshPending = false
      void refresh(app, detail, settings, visualizations, scores)
    } else {
      refreshTimer = window.setTimeout(() => { void refresh(app, detail, settings, visualizations, scores) }, 2000)
    }
  }
}

async function main () {
  const app = document.querySelector('corpus-app')
  if (!app) throw new Error('Missing corpus application shell')
  await app.updateComplete
  const visualizations = createVisualizationPanel(
    host(app, 'visualization-tabs'),
    host(app, 'visualization-chart-panel')
  )
  const scores = createScoresPanel(host(app, 'scores'), readProteobenchReferences)
  const detail = createDetailPanel(app, readRepresentation, () => state.run)
  const settings = createSettingsPanel(app)
  app.addEventListener('run-change', event => {
    if (event instanceof CustomEvent && typeof event.detail?.value === 'string') {
      state.requested = event.detail.value
      void refresh(app, detail, settings, visualizations, scores)
    }
  })
  app.addEventListener('dataset-filter-change', () => {
    void renderSelection(app, detail, visualizations, scores).catch(error => { app.error = String(error) })
  })
  app.addEventListener('tab-change', async () => {
    await app.updateComplete
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0 })
      if (state.table) state.table.redraw(true)
      settings.redraw()
      if (app.tab === 'insights' && app.insightTab === 'visualizations') visualizations.resize()
      if (app.tab === 'insights' && app.insightTab === 'scores') void scores.activate()
    })
  })
  app.addEventListener('insight-tab-change', () => {
    if (app.insightTab === 'log') void renderSchedulerLog(app)
    window.requestAnimationFrame(() => {
      if (state.table) state.table.redraw(true)
      settings.redraw()
      if (app.insightTab === 'visualizations') visualizations.resize()
      if (app.insightTab === 'scores') void scores.activate()
    })
  })
  app.addEventListener('settings-tab-change', () => {
    window.requestAnimationFrame(() => {
      settings.redraw()
    })
  })
  await refresh(app, detail, settings, visualizations, scores)
}

void main()
