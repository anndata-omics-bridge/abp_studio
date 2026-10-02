import { datasetArtifacts, formatBytes, workflowFields } from '../model.js'
import { fileUrl, sourceUrl } from '../lib/fetch.js'
import {
  artifactAttemptStorePath,
  artifactStorePath,
  loadRepresentationArtifacts,
  preferredLoadedRepresentation,
  representationArtifacts,
  representationViews
} from '../representation.js'
import { columnTitle, jsonTree, node } from '../render/dom.js'
import { fileLink } from '../render/links.js'
import { renderAnnDataStructure } from '../render/anndata-structure.js'
import {
  renderAnnData,
  renderAnnotationAnnData,
  renderApbMetadata,
  renderRepresentationJson,
  resizeDetailCharts
} from '../render/scientific.js'

// Dataset table presentation and one selected dataset's lazy detail navigation.

function fileCell (path, basename, parent, size, href = '', options = {}) {
  if (!path) return '—'
  const host = document.createElement('div')
  host.title = path
  const name = document.createElement('strong')
  if (href) {
    name.append(fileLink(href, basename, options))
  } else {
    name.textContent = basename
  }
  const context = document.createElement('div')
  const metadata = document.createElement('small')
  metadata.textContent = [parent, formatBytes(size)].filter(Boolean).join(' · ')
  context.append(metadata)
  host.append(name, context)
  return host
}

function renderDatasetFiles (host, row, run) {
  host.replaceChildren()
  const artifacts = datasetArtifacts(row)
  for (const artifact of artifacts) {
    const group = document.createElement('div')
    const term = document.createElement('dt')
    const value = document.createElement('dd')
    const name = document.createElement('strong')
    const code = document.createElement('code')
    const metadata = document.createElement('small')
    const size = artifact.size_bytes ?? (
      artifact.role === 'vendor_table' ? row.input_file_size_bytes : null
    )
    term.textContent = `${artifact.step} · ${artifact.direction}`
    const basename = artifact.path?.split('/').at(-1) ?? '—'
    const source = row[{
      vendor_table: 'input_file',
      vendor_parameter_file: 'vendor_parameter_file',
      fasta: 'fasta'
    }[artifact.role]]
    const href = artifact.direction === 'Input' && source
      ? sourceUrl(run, source)
      : artifact.size_bytes != null && artifacts.some(candidate =>
        candidate.direction === 'Output' && candidate.path === artifact.path)
        ? fileUrl(artifactStorePath(run, row.output_dir, artifact.path))
        : ''
    if (href) {
      name.append(fileLink(href, basename, { directory: artifact.format === 'parquet' }))
    } else {
      name.textContent = basename
    }
    code.textContent = artifact.path ?? '—'
    const formattedSize = formatBytes(size)
    const exactSize = size == null || size === ''
      ? ''
      : `${Number(size).toLocaleString()} bytes`
    metadata.textContent = [
      artifact.role,
      artifact.format,
      formattedSize || 'size unavailable',
      exactSize
    ].filter(Boolean).join(' · ')
    value.append(name, document.createElement('br'), code, document.createElement('br'), metadata)
    group.append(term, value)
    host.append(group)
  }
  host.hidden = artifacts.length === 0
}

/**
 * Create the selected-dataset controller.
 *
 * @param {HTMLElement} app Lit shell exposing hostFor/select and detail properties.
 * @param {(path: string) => Promise<object|null>} readRepresentation Read one APB sidecar.
 * @param {() => string} runPath Current store-relative run directory.
 * @returns {object} Detail navigation and dataset-column adapter.
 */
export function createDetailPanel (app, readRepresentation, runPath) {
  let selected = ''
  let selectedRecord = null
  let generation = 0
  const element = id => app.hostFor(id)

  function activateTab (key) {
    const showMore = element('show-more')
    for (const button of showMore.querySelectorAll('[data-detail-tab]')) {
      const active = button.dataset.detailTab === key
      button.setAttribute('aria-selected', String(active))
      button.tabIndex = active ? 0 : -1
    }
    for (const panel of showMore.querySelectorAll('[data-detail-panel]')) {
      panel.hidden = panel.dataset.detailPanel !== key
      if (!panel.hidden) resizeDetailCharts(panel)
    }
  }

  function tabKeydown (event) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const tabs = [...element('detail-tabs').querySelectorAll('[data-detail-tab]')]
    const current = tabs.indexOf(event.currentTarget)
    const target = event.key === 'Home'
      ? tabs[0]
      : event.key === 'End'
        ? tabs.at(-1)
        : tabs[(current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]
    event.preventDefault()
    target?.focus()
    target?.click()
  }

  function registerTab (key, label, panel, render = null) {
    const tabs = element('detail-tabs')
    const button = document.createElement('button')
    const tabId = `detail-tab-${key}`
    const panelId = panel.id || `detail-panel-${key}`
    button.type = 'button'
    button.id = tabId
    button.dataset.detailTab = key
    button.setAttribute('role', 'tab')
    button.setAttribute('aria-controls', panelId)
    button.setAttribute('aria-selected', 'false')
    button.tabIndex = -1
    button.textContent = label
    panel.id = panelId
    panel.dataset.detailPanel = key
    panel.setAttribute('role', 'tabpanel')
    panel.setAttribute('aria-labelledby', tabId)
    let rendered = render === null
    button.addEventListener('keydown', tabKeydown)
    button.addEventListener('click', () => {
      activateTab(key)
      if (rendered || render === null) return
      rendered = true
      panel.setAttribute('aria-busy', 'true')
      panel.replaceChildren(node('p', 'Loading view…', 'empty-note'))
      Promise.resolve(render(panel))
        .catch(error => panel.replaceChildren(node('p', error, 'representation-error')))
        .finally(() => {
          panel.removeAttribute('aria-busy')
          if (!panel.hidden) resizeDetailCharts(panel)
        })
    })
    tabs.append(button)
    return button
  }

  function reset () {
    generation += 1
    selected = ''
    selectedRecord = null
    element('detail-tabs').replaceChildren()
    element('detail-tabs').hidden = true
    element('detail').replaceChildren()
    element('detail-files').replaceChildren()
    element('detail-files').hidden = true
    element('detail-notices').replaceChildren()
    element('detail-diagnostics').replaceChildren()
    const io = element('detail-io')
    io.hidden = true
    io.removeAttribute('aria-labelledby')
    app.showMoreDisabled = true
    app.showMoreStatus = ''
    return generation
  }

  async function show (row, navigate = false) {
    const changed = selected !== row.input_file || selectedRecord !== row.record
    selected = row.input_file
    selectedRecord = row.record
    element('detail-title').textContent = `${row.software_name} · ${row.module}`
    app.showMoreDisabled = !row.record
    app.showMoreStatus = row.status
    if (navigate && row.record) app.select('show-more')
    if (!changed) return
    const activeGeneration = reset()
    selected = row.input_file
    selectedRecord = row.record
    app.showMoreDisabled = !row.record
    app.showMoreStatus = row.status
    renderDatasetFiles(element('detail-files'), row, runPath())
    const tabs = element('detail-tabs')
    const ioPanel = element('detail-io')
    const notices = element('detail-notices')
    registerTab('io', 'Inputs & outputs', ioPanel)
    tabs.hidden = false
    activateTab('io')
    notices.replaceChildren(node('p', 'Loading scientific representation…', 'empty-note'))
    const result = await loadRepresentationArtifacts(
      representationArtifacts(row.record),
      artifact => readRepresentation(
        artifactStorePath(runPath(), row.output_dir, artifact.path)
      ),
      () => activeGeneration === generation
    )
    if (!result) return
    const { loaded, problems } = result
    notices.replaceChildren(...problems.map(problem => node('p', problem, 'representation-error')))
    const preferred = preferredLoadedRepresentation(row, loaded)
    if (!preferred) {
      notices.append(
        node('p', 'No scientific representation was produced for this dataset.', 'empty-note')
      )
    } else {
      for (const view of representationViews(preferred.representation)) {
        const panel = document.createElement('section')
        panel.className = 'detail-panel'
        panel.hidden = true
        element('detail').append(panel)
        registerTab(`scientific-${view.key}`, view.label, panel, async host => {
          host.replaceChildren()
          if (view.kind === 'apb-metadata') {
            await renderApbMetadata(host, view.representation, preferred.artifact.step)
          } else if (view.kind === 'anndata-structure') {
            await renderAnnDataStructure(host, view.representation)
          } else if (view.kind === 'representation-json') {
            renderRepresentationJson(host, view.representation)
          } else if (view.kind === 'annotation') {
            await renderAnnotationAnnData(
              host,
              view.representation,
              view.annotationTable,
              view.referenceLevel
            )
          } else {
            await renderAnnData(host, view.level)
          }
        })
      }
    }
    const diagnostics = document.createElement('details')
    diagnostics.className = 'execution-diagnostics'
    diagnostics.append(node('summary', 'Complete execution report'), jsonTree(row.record ?? {}))
    element('detail-diagnostics').replaceChildren(diagnostics)
  }

  function showMoreButton (cell) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'show-more-button'
    button.dataset.status = cell.getRow().getData().status
    button.textContent = 'Show more'
    button.addEventListener('click', event => {
      event.stopPropagation()
      void show(cell.getRow().getData(), true)
    })
    return button
  }

  return {
    reset,
    show,

    /** @param {object[]} workflowRows Frozen workflow join rows. @returns {object[]} Columns. */
    columns (workflowRows) {
      return [
        { title: 'Result', field: 'status', width: 110 },
        { title: 'Module', field: 'module', minWidth: 120 },
        { title: 'Software', field: 'software_name', minWidth: 120 },
        {
          title: 'Input file',
          field: 'input_file_name',
          formatter: cell => {
            const row = cell.getRow().getData()
            return fileCell(
              row.input_file,
              row.input_file_name,
              row.input_file_parent,
              row.input_file_size_bytes,
              sourceUrl(runPath(), row.input_file)
            )
          },
          minWidth: 240
        },
        {
          title: 'Output',
          field: 'output_file_name',
          formatter: cell => {
            const row = cell.getRow().getData()
            return fileCell(
              row.output_file,
              row.output_file_name,
              row.output_file_parent,
              row.output_file_size_bytes,
              row.output_file
                ? fileUrl(artifactAttemptStorePath(runPath(), row.output_dir, row.output_file))
                : '',
              { directory: true }
            )
          },
          minWidth: 240
        },
        ...workflowFields(workflowRows).map(field => ({
          title: field === 'software' ? 'Rule hint' : columnTitle(field),
          field,
          ...(field === 'fasta'
            ? { formatter: cell => cell.getValue()
                ? fileLink(sourceUrl(runPath(), cell.getValue()), cell.getValue().split('/').at(-1))
                : '—' }
            : {}),
          minWidth: 100
        })),
        {
          title: 'Ion vars',
          field: 'ion_variables',
          formatter: cell => cell.getValue()?.toLocaleString() ?? '—',
          width: 110
        },
        {
          title: 'Seconds',
          field: 'runtime_seconds',
          formatter: cell => cell.getValue()?.toFixed(2) ?? '—',
          width: 85
        },
        {
          title: '',
          formatter: showMoreButton,
          headerSort: false,
          headerFilter: false,
          width: 105,
          cellClick: (_event, cell) => { void show(cell.getRow().getData(), true) }
        }
      ]
    },

    /** Refresh the selected row after polling replaces table data. */
    async refresh (rows) {
      const row = rows.find(candidate => candidate.input_file === selected)
      if (row) await show(row)
    }
  }
}
