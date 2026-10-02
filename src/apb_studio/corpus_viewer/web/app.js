import { readCatalog, readStore, readStoreJson } from './lib/fetch.js'
import {
  chartViews,
  counts,
  datasetRows,
  runChoices,
  statusFractions,
  workflowSteps
} from './model.js'
import { createDetailPanel } from './panels/detail.js'
import { createSettingsPanel } from './panels/settings.js'
import { createVisualizationPanel } from './panels/visualizations.js'
import { artifactStorePath, representationIonVariables, validatedRepresentation } from './representation.js'
import { mountTable } from './render/tabulator.js'
import { validatedToolTimings } from './tool-timings.js'
import './shell/corpus-app.js'

// Composition root. Server files enter through lib/fetch.js, pure model projections
// become views, and panel adapters own DOM-heavy rendering.

const state = {
  run: '',
  requested: '',
  manifestStamp: '',
  operationStamp: '',
  storeRoot: '',
  manifest: null,
  corpus: [],
  inputMetadata: [],
  workflowRows: [],
  reports: new Map(),
  timingFiles: new Map(),
  representationFiles: new Map(),
  table: null
}

function host (app, id) { return app.hostFor(id) }

async function readRepresentation (path) {
  const document = await readStoreJson(path)
  return document ? validatedRepresentation(document) : null
}

async function table (target, rows, columns) {
  return mountTable(target, rows, columns, {
    height: '55vh',
    placeholder: 'No records',
    columnDefaults: { formatter: 'plaintext', headerFilter: 'input' }
  })
}

function destroyTables () {
  if (state.table) state.table.destroy()
  state.table = null
}

function updateSummary (app, status, rows, summary, steps) {
  app.status = status
  app.counts = `${rows} datasets · ${Object.entries(summary)
    .map(([name, count]) => `${count} ${name}`)
    .join(' · ')}`
  app.steps = `Steps: ${steps.join(' → ') || 'none recorded'}`
  app.fractions = statusFractions(summary, rows)
}

async function loadRun (app, detail, settings, visualizations, choice) {
  detail.reset()
  destroyTables()
  state.manifest = null
  host(app, 'datasets').replaceChildren()
  app.select('results')
  state.run = choice.path.slice(0, -'/run.json'.length)
  state.manifest = choice.manifest
  state.manifestStamp = JSON.stringify(choice.manifest)
  state.reports.clear()
  state.timingFiles.clear()
  state.representationFiles.clear()
  state.operationStamp = ''
  const manifest = state.manifest
  state.corpus = await readStore(`${state.run}/${manifest.corpus}`, 'csv')
  state.inputMetadata = manifest.input_metadata
    ? await readStore(`${state.run}/${manifest.input_metadata}`, 'csv')
    : []
  state.workflowRows = manifest.workflow_table
    ? await readStore(
      `${state.run}/${manifest.workflow_table}`,
      manifest.workflow_table.endsWith('.tsv') ? 'tsv' : 'csv'
    )
    : []
  const config = await readStore(`${state.run}/${manifest.execution_settings}`)
  await settings.renderRun({
    directory: state.run,
    storeRoot: state.storeRoot,
    manifest,
    config,
    corpus: state.corpus,
    inputMetadata: state.inputMetadata,
    workflowRows: state.workflowRows
  })
  await refreshRun(app, detail, visualizations)
}

async function refreshRun (app, detail, visualizations) {
  if (!state.manifest) return
  const operation = await readStore(`${state.run}/operation.json`)
  if (state.operationStamp !== operation?.updated_at) {
    state.reports.clear()
    state.timingFiles.clear()
    state.representationFiles.clear()
    state.operationStamp = operation?.updated_at
  }
  const progress = new Map()
  const pending = state.manifest.reports.filter(link => !state.reports.has(link.path))
  for (let start = 0; start < pending.length; start += 12) {
    await Promise.all(pending.slice(start, start + 12).map(async link => {
      const report = await readStore(`${state.run}/${link.path}`)
      if (report) state.reports.set(link.path, report)
      else progress.set(link.progress, await readStore(`${state.run}/${link.progress}`))
    }))
  }
  let rows = datasetRows(
    state.manifest,
    state.corpus,
    state.inputMetadata,
    state.reports,
    progress,
    operation,
    state.workflowRows
  )
  const timingArtifacts = rows.flatMap(row => (row.record?.steps ?? []).flatMap(step =>
    step.status === 'succeeded'
      ? (step.outputs ?? []).filter(artifact =>
          artifact.role === 'tool_timings' && artifact.size_bytes != null)
        .map(artifact => ({ row, artifact }))
      : []))
  const pendingTimings = timingArtifacts.filter(({ artifact }) =>
    !state.timingFiles.has(artifact.path))
  for (let start = 0; start < pendingTimings.length; start += 12) {
    await Promise.all(pendingTimings.slice(start, start + 12).map(async ({ row, artifact }) => {
      try {
        const path = artifactStorePath(state.run, row.output_dir, artifact.path)
        const document = await readStoreJson(path)
        state.timingFiles.set(artifact.path, document ? validatedToolTimings(document) : null)
      } catch (error) {
        state.timingFiles.set(artifact.path, null)
        console.warn(`Cannot read tool timings ${artifact.path}: ${error}`)
      }
    }))
  }
  const representations = rows.flatMap(row => (row.record?.steps ?? []).flatMap(step =>
    step.status === 'succeeded'
      ? (step.outputs ?? []).filter(artifact =>
          artifact.role === 'representation' && artifact.size_bytes != null)
        .map(artifact => ({ row, artifact }))
      : []))
  const pendingRepresentations = representations.filter(({ artifact }) =>
    !state.representationFiles.has(artifact.path))
  for (let start = 0; start < pendingRepresentations.length; start += 12) {
    await Promise.all(pendingRepresentations.slice(start, start + 12).map(async ({ row, artifact }) => {
      try {
        const path = artifactStorePath(state.run, row.output_dir, artifact.path)
        const document = await readStoreJson(path)
        state.representationFiles.set(
          artifact.path, document ? representationIonVariables(document) : null
        )
      } catch (error) {
        state.representationFiles.set(artifact.path, null)
        console.warn(`Cannot read representation dimensions ${artifact.path}: ${error}`)
      }
    }))
  }
  rows = datasetRows(
    state.manifest, state.corpus, state.inputMetadata, state.reports, progress,
    operation, state.workflowRows, state.representationFiles
  )
  const summary = counts(rows)
  updateSummary(
    app,
    `${state.manifest.workflow} / ${state.manifest.format} · ${operation?.status ?? 'prepared'}`,
    rows.length,
    summary,
    workflowSteps(rows)
  )
  if (state.table) await state.table.replaceData(rows)
  else state.table = await table(host(app, 'datasets'), rows, detail.columns(state.workflowRows))
  await detail.refresh(rows)
  await visualizations.render(chartViews(rows, state.timingFiles, state.representationFiles))
  if (app.tab === 'log') {
    host(app, 'scheduler-log').textContent =
      await readStore(`${state.run}/snakemake.log`, 'text') ?? ''
  }
}

async function refresh (app, detail, settings, visualizations) {
  try {
    const catalog = await readCatalog()
    state.storeRoot = catalog.store_root ?? ''
    const paths = catalog.runs ?? []
    const choices = runChoices(await Promise.all(paths.map(async path => ({
      path,
      manifest: await readStore(path)
    }))))
    const current = state.requested || `${state.run}/run.json`
    const choice = choices.find(candidate => candidate.path === current) ?? choices[0]
    state.requested = ''
    app.runOptions = choices.length
      ? choices.map(candidate => [candidate.path, candidate.label])
      : [['', 'No corpus runs yet']]
    app.runValue = choice?.path ?? ''
    app.runDisabled = !choice
    const manifestChanged = choice && state.manifestStamp !== JSON.stringify(choice.manifest)
    if (choice && (`${state.run}/run.json` !== choice.path || manifestChanged)) {
      await loadRun(app, detail, settings, visualizations, choice)
    } else if (choice) {
      await refreshRun(app, detail, visualizations)
    } else if (state.manifest) {
      state.run = ''
      state.manifest = null
      state.manifestStamp = ''
      state.reports.clear()
      state.timingFiles.clear()
      state.representationFiles.clear()
      destroyTables()
      detail.reset()
      settings.clear()
      host(app, 'datasets').replaceChildren()
      host(app, 'scheduler-log').textContent = ''
      updateSummary(app, 'Waiting for a run', 0, {}, [])
      await visualizations.render(chartViews([]))
    }
    app.error = ''
  } catch (error) {
    app.error = String(error)
  }
  window.setTimeout(() => { void refresh(app, detail, settings, visualizations) }, 2000)
}

async function main () {
  const app = document.querySelector('corpus-app')
  await app.updateComplete
  const visualizations = createVisualizationPanel(
    host(app, 'visualization-tabs'),
    host(app, 'visualization-chart-panel')
  )
  const detail = createDetailPanel(app, readRepresentation, () => state.run)
  const settings = createSettingsPanel(app)
  app.addEventListener('run-change', event => { state.requested = event.detail.value })
  app.addEventListener('tab-change', () => {
    window.requestAnimationFrame(() => {
      if (state.table) state.table.redraw(true)
      settings.redraw()
      if (app.tab === 'visualizations') visualizations.resize()
    })
  })
  app.addEventListener('settings-tab-change', () => {
    window.requestAnimationFrame(() => {
      settings.redraw()
    })
  })
  await refresh(app, detail, settings, visualizations)
}

void main()
