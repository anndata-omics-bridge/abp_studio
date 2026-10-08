import type { CellComponent, ColumnDefinition } from '../../shared/tabulator.js'
import type { CsvRows, DatasetOddities, DatasetReport, DatasetRow, Representation, RepresentationView } from '../types.js'
import type { CorpusApp } from '../shell/corpus-app.js'

import { formatBytes, workflowFields } from '../model.js'
import { fileUrl, sourceUrl } from '../lib/fetch.js'
import {
  artifactAttemptStorePath,
  artifactStorePath,
  fastaChecks,
  loadRepresentationArtifacts,
  preferredLoadedRepresentation,
  representationArtifacts,
  representationViews
} from '../representation.js'
import { columnTitle, jsonTree, node } from '../render/dom.js'
import { fileLink } from '../render/links.js'
import { renderAnnDataStructure } from '../render/anndata-structure.js'
import { renderTabs } from '../render/tabs.js'
import { renderWorkflowFiles } from '../render/workflow-files.js'
import { renderOdditiesDetail } from '../render/oddities.js'
import { oddityCountLabel } from '../oddities.js'
import {
  renderAnnData,
  renderAnnotationAnnData,
  renderApbMetadata,
  renderFastaChecks,
  renderRepresentationJson,
  resizeDetailCharts
} from '../render/scientific.js'

// Dataset table presentation and one selected dataset's lazy detail navigation.
function fileCell (path: string, basename: string, parent: string, size: string | number | null | undefined, href = '', options: { directory?: boolean } = {}) {
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

/** Own selection, lazy scientific views and the dataset-column adapter. */
export function createDetailPanel (app: CorpusApp, readRepresentation: (path: string) => Promise<Representation | null>, runPath: () => string) {
  let selected = ''
  let selectedRecord: DatasetReport | null | undefined = null
  let selectedOddities: DatasetOddities | null | undefined = null
  let selectedTab = ''
  let selectedObject = ''
  let defaultTab = 'io'
  let sidebarStamp = ''
  let currentRows = new Map<string, DatasetRow>()
  let generation = 0
  const element = (id: string) => app.hostFor(id)

  function activateTab (key: string) {
    selectedTab = key
    const showMore = element('show-more')
    for (const button of showMore.querySelectorAll<HTMLButtonElement>('[data-detail-tab]')) {
      const active = button.dataset.detailTab === key
      button.setAttribute('aria-selected', String(active))
      button.tabIndex = active ? 0 : -1
    }
    for (const panel of showMore.querySelectorAll<HTMLElement>('[data-detail-panel]')) {
      panel.hidden = panel.dataset.detailPanel !== key
      if (!panel.hidden) resizeDetailCharts(panel)
    }
  }

  function tabKeydown (event: KeyboardEvent) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const tabs = [...element('detail-tabs').querySelectorAll<HTMLButtonElement>('[data-detail-tab]')]
    const current = tabs.indexOf(event.currentTarget as HTMLButtonElement)
    const target = event.key === 'Home'
      ? tabs[0]
      : event.key === 'End'
        ? tabs.at(-1)
        : tabs[(current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]
    event.preventDefault()
    target?.focus()
    target?.click()
  }

  function registerTab (key: string, label: string, panel: HTMLElement, render: ((host: HTMLElement) => void | Promise<void>) | null = null) {
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

  function clearDetail () {
    generation += 1
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
    return generation
  }

  function reset () {
    clearDetail()
    selected = ''
    selectedRecord = null
    selectedOddities = null
    selectedTab = ''
    selectedObject = ''
    defaultTab = 'io'
    sidebarStamp = ''
    currentRows.clear()
    element('file-list').replaceChildren()
    element('detail-title').textContent = 'Select a file to inspect its results'
  }

  function openTab (key: string) {
    const button = [...element('detail-tabs').querySelectorAll<HTMLButtonElement>('[data-detail-tab]')]
      .find(candidate => candidate.dataset.detailTab === key)
    button?.click()
    return Boolean(button)
  }

  function updateSidebarSelection () {
    for (const button of element('file-list').querySelectorAll<HTMLButtonElement>('[data-input-file]')) {
      const active = button.dataset.inputFile === selected
      button.setAttribute('aria-current', String(active))
    }
  }

  async function renderScientificView (host: HTMLElement, view: RepresentationView, step: string) {
    host.replaceChildren()
    if (view.kind === 'apb-metadata') {
      await renderApbMetadata(host, view.representation, step)
    } else if (view.kind === 'anndata-structure') {
      await renderAnnDataStructure(host, view.representation)
    } else if (view.kind === 'representation-json') {
      renderRepresentationJson(host, view.representation)
    } else if (view.kind === 'annotation') {
      await renderAnnotationAnnData(
        host, view.representation, view.annotationTable, view.referenceLevel
      )
    } else if (view.kind === 'level') {
      await renderAnnData(host, view.level)
    }
  }

  async function show (row: DatasetRow, navigate = false) {
    const changed = selected !== row.input_file || selectedRecord !== row.record || selectedOddities !== row.oddities
    const sameFile = selected === row.input_file
    const retainedTab = sameFile && !navigate ? selectedTab : ''
    if (!sameFile) selectedObject = ''
    selected = row.input_file
    selectedRecord = row.record
    selectedOddities = row.oddities
    element('detail-title').textContent = `${row.software_name} · ${row.module} · ${row.input_file_name || row.input_file.split('/').at(-1)}`
    updateSidebarSelection()
    if (navigate) {
      app.select('files')
      if (!changed) openTab(defaultTab)
    }
    if (!changed) return
    const activeGeneration = clearDetail()
    const selectedRun = runPath()
    renderWorkflowFiles(element('detail-files'), row, runPath())
    const tabs = element('detail-tabs')
    const ioPanel = element('detail-io')
    const notices = element('detail-notices')
    registerTab('io', 'Inputs & outputs', ioPanel)
    const odditiesPanel = document.createElement('section')
    odditiesPanel.className = 'detail-panel'
    odditiesPanel.hidden = true
    element('detail').append(odditiesPanel)
    registerTab('oddities', 'Oddities', odditiesPanel, host => renderOdditiesDetail(host, row.oddities))
    tabs.hidden = false
    activateTab('io')
    const diagnostics = document.createElement('details')
    diagnostics.className = 'execution-diagnostics'
    diagnostics.append(node('summary', 'Complete execution report'), jsonTree(row.record ?? {}))
    element('detail-diagnostics').replaceChildren(diagnostics)
    notices.replaceChildren(node('p', 'Loading scientific representation…', 'empty-note'))
    const result = await loadRepresentationArtifacts(
      representationArtifacts(row.record),
      artifact => readRepresentation(
        artifactStorePath(selectedRun, row.output_dir, artifact.path)
      ),
      () => activeGeneration === generation
    )
    if (!result || activeGeneration !== generation) return
    const { loaded, problems } = result
    notices.replaceChildren(...problems.map(problem => node('p', problem, 'representation-error')))
    const preferred = preferredLoadedRepresentation(row, loaded)
    if (!preferred?.representation) {
      const message = row.status === 'failed'
        ? 'This file failed. Inspect its outputs and complete execution report below.'
        : !row.record || ['pending', 'running'].includes(row.status)
          ? `This file is ${row.status || 'pending'}. Scientific views appear when results are available.`
          : 'No scientific representation was produced for this dataset.'
      notices.append(node('p', message, 'empty-note'))
      defaultTab = 'io'
    } else {
      if (fastaChecks(preferred.representation).length) {
        const panel = document.createElement('section')
        panel.className = 'detail-panel'
        panel.hidden = true
        element('detail').append(panel)
        registerTab('fasta', 'FASTA check', panel,
          host => {
            host.replaceChildren()
            renderFastaChecks(host, preferred.representation)
          })
      }
      const views = representationViews(preferred.representation)
      const objects = views.filter(view => ['level', 'annotation'].includes(view.kind))
      if (objects.length) {
        const panel = document.createElement('section')
        panel.className = 'detail-panel'
        panel.hidden = true
        element('detail').append(panel)
        const format = preferred.representation.artifact?.physical_format
        const label = format === 'h5ad' || format === 'h5mu' ? 'AnnData' : 'Levels'
        registerTab('anndata', label, panel, async host => {
          host.replaceChildren()
          const rememberedObject = selectedObject
          await renderTabs(host, `${label} objects`, objects.map(view => ({
            label: view.label,
            render: (target: HTMLElement) => renderScientificView(target, view, preferred.artifact.step)
          })), (activePanel: HTMLElement) => {
            if (activeGeneration !== generation) return
            const button = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
              .find(candidate => candidate.getAttribute('aria-controls') === activePanel.id)
            const index = [...host.querySelectorAll<HTMLButtonElement>('.representation-tabs > [role="tab"]')]
              .indexOf(button as HTMLButtonElement)
            if (index >= 0) selectedObject = objects[index].key
            resizeDetailCharts(activePanel)
          })
          if (activeGeneration !== generation) return
          const index = objects.findIndex(view => view.key === rememberedObject)
          if (index > 0) host.querySelector('.representation-tabs')?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[index]?.click()
        })
      }
      for (const view of views.filter(view => !['level', 'annotation'].includes(view.kind))) {
        const panel = document.createElement('section')
        panel.className = 'detail-panel'
        panel.hidden = true
        element('detail').append(panel)
        registerTab(`scientific-${view.key}`, view.label, panel,
          host => renderScientificView(host, view, preferred.artifact.step))
      }
      defaultTab = objects.length ? 'anndata'
        : views.some(view => view.kind === 'anndata-structure') ? 'scientific-anndata-structure' : 'io'
    }
    const scientificTabs = ['anndata', 'scientific-anndata-structure'].map(key =>
      [...tabs.querySelectorAll<HTMLButtonElement>('[data-detail-tab]')].find(button => button.dataset.detailTab === key)
    ).filter((button): button is HTMLButtonElement => Boolean(button))
    tabs.prepend(...scientificTabs)
    if (!openTab(retainedTab)) openTab(defaultTab)
  }

  function rowForCell (cell: CellComponent): DatasetRow {
    // This table is constructed exclusively from the typed dataset projection.
    return cell.getRow().getData() as DatasetRow
  }

  function showMoreButton (cell: CellComponent) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'show-more-button'
    button.dataset.status = rowForCell(cell).status
    button.textContent = 'Show more'
    button.addEventListener('click', event => {
      event.stopPropagation()
      void show(rowForCell(cell), true)
    })
    return button
  }

  return {
    reset,
    show,

    /** Turn frozen workflow fields into dataset-table columns. */
    columns (workflowRows: CsvRows): ColumnDefinition[] {
      return [
        {
          title: 'Open',
          formatter: showMoreButton,
          headerSort: false,
          frozen: true,
          width: 110,
          cellClick: (_event, cell) => { void show(rowForCell(cell), true) }
        },
        { title: 'Result', field: 'status', width: 110 },
        {
          title: 'Oddities', field: 'oddity_count', sorter: 'number', width: 150,
          formatter: cell => oddityCountLabel(rowForCell(cell))
        },
        { title: 'Module', field: 'module', minWidth: 120 },
        { title: 'Software', field: 'software_name', minWidth: 120 },
        {
          title: 'Input file',
          field: 'input_file_name',
          formatter: cell => {
            const row = rowForCell(cell)
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
            const row = rowForCell(cell)
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
            ? { formatter: (cell: CellComponent) => {
                const path: unknown = cell.getValue()
                return typeof path === 'string' && path
                  ? fileLink(sourceUrl(runPath(), path), path.split('/').at(-1) ?? path)
                  : '—'
              } }
            : {}),
          minWidth: 100
        })),
        {
          title: 'Ion vars',
          field: 'ion_variables',
          formatter: (cell: CellComponent) => rowForCell(cell).ion_variables?.toLocaleString() ?? '—',
          width: 110
        },
        {
          title: 'Seconds',
          field: 'runtime_seconds',
          formatter: (cell: CellComponent) => rowForCell(cell).runtime_seconds?.toFixed(2) ?? '—',
          width: 85
        }
      ]
    },

    /** Refresh reports without changing the opened file when its chooser entry is filtered out. */
    async refresh (rows: DatasetRow[], sidebarRows: DatasetRow[] = rows) {
      currentRows = new Map(rows.map(row => [row.input_file, row]))
      const softwareCounts = new Map<string, number>()
      for (const row of rows) softwareCounts.set(row.software_name, (softwareCounts.get(row.software_name) ?? 0) + 1)
      const stamp = JSON.stringify({
        emptyRun: rows.length === 0,
        repeatedSoftware: [...softwareCounts].filter(([, count]) => count > 1).map(([software]) => software),
        files: sidebarRows.map(row => [
          row.input_file, row.input_file_kind, row.input_file_size_bytes,
          row.software_name, row.module, row.status
        ])
      })
      if (stamp !== sidebarStamp) {
        sidebarStamp = stamp
        const buttons = sidebarRows.map(row => {
          const button = document.createElement('button')
          button.type = 'button'
          button.className = 'file-list-item'
          button.dataset.inputFile = row.input_file
          button.dataset.status = row.status
          button.title = `${row.input_file}\n${row.module} · ${row.status}`
          const kind = row.input_file_kind
          const type = kind === 'folder' ? 'Folder' : kind === 'file' ? 'File' : 'Input'
          const size = formatBytes(row.input_file_size_bytes) || 'Size unavailable'
          const heading = node('span', '', 'file-list-heading')
          const icon = node('span', kind === 'folder' ? '📁' : kind === 'file' ? '📄' : '', 'file-list-icon')
          icon.setAttribute('aria-hidden', 'true')
          heading.append(icon, node('strong', row.software_name, 'file-list-name'))
          const module = (softwareCounts.get(row.software_name) ?? 0) > 1 ? row.module : ''
          if (module) heading.append(node('span', `· ${module}`, 'file-list-module'))
          button.append(
            heading,
            node('span', `${type} · ${size}`, 'file-list-context')
          )
          button.setAttribute('aria-label', [row.software_name, module, type.toLowerCase(), size, row.status].filter(Boolean).join(', '))
          button.addEventListener('click', () => {
            const current = currentRows.get(row.input_file)
            if (current) void show(current)
          })
          return button
        })
        element('file-list').replaceChildren(...(buttons.length ? buttons
          : [node('p', rows.length ? 'No files match the filters.' : 'No files in this run.', 'empty-note')]))
      }
      const row = rows.find(candidate => candidate.input_file === selected) ??
        rows.find(candidate => representationArtifacts(candidate.record).length) ??
        rows.find(candidate => candidate.record) ?? rows[0]
      if (row) await show(row)
    }
  }
}
