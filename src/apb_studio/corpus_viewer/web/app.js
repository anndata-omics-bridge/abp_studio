import { TabulatorFull } from './vendor/tabulator.js'
import { csvParse } from './vendor/d3-dsv.js'
import { Plotly } from './vendor/plotly.js'
import './vendor/json-viewer.js'
import { chartPoints, counts, datasetArtifacts, datasetRows, executionGroups, formatBytes, statusFractions, workflowFields, workflowSteps } from './model.js'
import { apbMetadataScopes, layerChart, loadRepresentationArtifacts, preferredLoadedRepresentation, representationArtifacts, representationStorePath, representationViews, validatedRepresentation } from './representation.js'

const element = id => document.getElementById(id)
const state = { run: '', requested: '', execution: '', requestedExecution: '', preview: '', manifests: new Map(), settings: new Map(), settingsPaths: new Map(), operationStamp: '', manifest: null, corpus: [], inputMetadata: [], workflowRows: [], reports: new Map(), selected: '', selectedRecord: null, detailGeneration: 0, table: null, tables: [] }
const url = path => new URL(`data/${path}`, document.baseURI).href
const chartIds = ['runtime-chart', 'memory-chart', 'output-chart']
const plotConfig = { displayModeBar: false, responsive: true }

async function read (path, kind = 'json') {
  const response = await fetch(url(path), { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  if (kind === 'json') {
    const document = await response.json()
    if (document.schema_version !== 1) throw new Error(`Unsupported schema: ${path}`)
    return document
  }
  const text = await response.text()
  return kind === 'csv' ? csvParse(text) : text
}

async function table (host, rows, columns) {
  const result = new TabulatorFull(host, {
    data: rows, columns, layout: 'fitDataStretch', height: 390,
    placeholder: 'No records', columnDefaults: { formatter: 'plaintext', headerFilter: 'input' }
  })
  await new Promise(resolve => result.on('tableBuilt', resolve))
  return result
}

function columnTitle (field) {
  const words = field.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function jsonTree (data, expandedPaths = []) {
  const container = document.createElement('div')
  container.className = 'json-tree'
  const controls = document.createElement('div')
  controls.className = 'json-controls'
  controls.setAttribute('aria-label', 'JSON tree controls')
  const viewer = document.createElement('json-viewer')
  viewer.data = data
  for (const [label, action] of [
    ['Expand all', () => viewer.expandAll()],
    ['Collapse all', () => viewer.collapseAll()]
  ]) {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = label
    button.addEventListener('click', action)
    controls.append(button)
  }
  container.append(controls, viewer)
  if (expandedPaths.length) {
    Promise.resolve(viewer.updateComplete).then(() => {
      for (const path of expandedPaths) viewer.expand(path)
    })
  }
  return container
}

function renderJson (host, data) {
  host.replaceChildren(jsonTree(data))
}

async function readRepresentation (path) {
  const response = await fetch(url(path), { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return validatedRepresentation(await response.json())
}

function node (tag, text, className = '') {
  const result = document.createElement(tag)
  result.textContent = text
  if (className) result.className = className
  return result
}

function dataTable (headings, rows) {
  const result = document.createElement('table')
  result.className = 'scientific-table'
  const head = document.createElement('thead')
  const headerRow = document.createElement('tr')
  headerRow.append(...headings.map(heading => node('th', heading)))
  head.append(headerRow)
  const body = document.createElement('tbody')
  for (const row of rows) {
    const tableRow = document.createElement('tr')
    tableRow.append(...row.map(value => node('td', value == null ? '—' : String(value))))
    body.append(tableRow)
  }
  result.append(head, body)
  return result
}

function metadataCards (entries) {
  const cards = document.createElement('dl')
  cards.className = 'metadata-cards'
  for (const [label, value] of entries) {
    const card = document.createElement('div')
    card.append(node('dt', label), node('dd', value == null || value === '' ? '—' : String(value)))
    cards.append(card)
  }
  return cards
}

function tableDescription (title, description) {
  const card = document.createElement('article')
  card.className = 'scientific-card'
  card.append(
    node('h4', title),
    metadataCards([
      ['Rows', description.row_count],
      ['Keys', (description.key_columns ?? []).join(', ') || 'none']
    ]),
    dataTable(
      ['Column', 'Logical dtype', 'Nulls'],
      (description.columns ?? []).map(column => [column.name, column.dtype, column.null_count])
    )
  )
  return card
}

function statisticsTable (statistics) {
  const labels = {
    total_count: 'Cells', finite_count: 'Finite', null_count: 'Null', nan_count: 'NaN',
    positive_infinity_count: '+Infinity', negative_infinity_count: '−Infinity', zero_count: 'Zero',
    mean: 'Mean', standard_deviation: 'Standard deviation', minimum: 'Minimum',
    first_quartile: 'First quartile', median: 'Median', third_quartile: 'Third quartile', maximum: 'Maximum',
    quartile_method: 'Quartile method', quartile_sample_count: 'Quartile sample cells',
    quartile_sample_limit: 'Quartile sample limit'
  }
  return dataTable(
    ['Statistic', 'Value'],
    Object.entries(labels).map(([field, label]) => [label, statistics?.[field]])
  )
}

function categoricalCountsTable (counts) {
  const labels = {
    total_count: 'Cells', known_count: 'Known-category cells',
    missing_or_unknown_count: 'Missing or unknown'
  }
  return dataTable(
    ['Count', 'Value'],
    Object.entries(labels).map(([field, label]) => [label, counts?.[field]])
  )
}

function observationIdentities (level) {
  const observations = level.observations ?? { total_count: 0, emitted_count: 0, truncated: false, items: [] }
  const keys = level.obs?.key_columns ?? []
  const details = document.createElement('details')
  const qualifier = observations.truncated ? ', truncated' : ''
  details.append(
    node('summary', `Observation identities · ${observations.emitted_count} of ${observations.total_count}${qualifier}`),
    dataTable(
      ['Index', ...keys, 'Label'],
      (observations.items ?? []).map(observation => [
        observation.index,
        ...keys.map(key => observation.key?.[key]),
        observation.label
      ])
    )
  )
  return details
}

function namedStructureTable (aligned) {
  const rows = []
  for (const slot of ['obsm', 'varm', 'obsp', 'varp']) {
    for (const value of aligned?.[slot] ?? []) {
      rows.push([slot, value.name, value.row_count, (value.columns ?? []).map(column => `${column.name}: ${column.dtype}`).join(', ')])
    }
  }
  return rows.length
    ? dataTable(['Slot', 'Name', 'Rows', 'Columns'], rows)
    : node('p', 'No aligned or pairwise slots.', 'empty-note')
}

async function renderLayer (host, level, layer) {
  const card = document.createElement('article')
  card.className = 'layer-card'
  const heading = document.createElement('div')
  heading.className = 'layer-heading'
  heading.append(node('h4', layer.name))
  if (layer.primary) heading.append(node('span', 'Primary', 'badge'))
  const metadata = [
    ['Role', layer.role],
    ['Shape', `${layer.shape.observations} × ${layer.shape.variables}`],
    ['Value kind', layer.value_kind],
    ['Dtype', layer.dtype]
  ]
  if (layer.value_kind === 'categorical') {
    metadata.push(['Categories', layer.category_count])
  } else {
    const summaries = layer.observation_summaries
    metadata.push(
      ['Unit', layer.unit],
      ['Scale', layer.scale],
      ['Plotted observations', summaries
        ? `${summaries.emitted_count} of ${summaries.total_count}${summaries.truncated ? ' (truncated)' : ''}`
        : null]
    )
  }
  card.append(
    heading,
    metadataCards(metadata)
  )
  if (layer.value_kind === 'categorical') {
    card.append(node('h5', 'Category encoding'), categoricalCountsTable(layer.counts))
    host.append(card)
    return
  }
  const content = document.createElement('div')
  content.className = 'layer-content'
  const statistics = document.createElement('div')
  statistics.append(node('h5', 'Whole layer'), statisticsTable(layer.statistics))
  const chartHost = document.createElement('div')
  chartHost.className = 'layer-chart'
  content.append(statistics, chartHost)
  card.append(content)
  host.append(card)
  const chart = layerChart(level, layer)
  if (!chart) return
  await Plotly.react(
    chartHost,
    chart.trace.x.length ? [chart.trace] : [],
    { ...chartLayout(chart.xTitle, chart.yTitle, Boolean(chart.trace.x.length)), height: 360, margin: { l: 85, r: 15, t: 15, b: 100 }, showlegend: false },
    plotConfig
  )
}

async function renderApbMetadata (host, representation, step) {
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', 'APB provenance and extension metadata'),
    metadataCards([
      ['Workflow step', step],
      ['Source artifact', representation.artifact.name],
      ['Physical format', representation.artifact.physical_format],
      ['Artifact size', formatBytes(representation.artifact.size_bytes)]
    ])
  )
  host.append(article)
  await renderNestedTabs(
    article,
    'APB metadata scopes',
    apbMetadataScopes(representation).map(scope => ({
      label: scope.label,
      render: panel => panel.append(
        jsonTree(scope.value, ['uns', 'uns.apb', 'uns.apb.parse'])
      )
    }))
  )
}

function renderRepresentationJson (host, representation) {
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', 'Complete APB result representation'),
    jsonTree(representation)
  )
  host.append(article)
}

let nestedTabsSerial = 0

async function renderNestedTabs (host, label, sections) {
  const serial = ++nestedTabsSerial
  const tabs = document.createElement('div')
  tabs.className = 'representation-tabs'
  tabs.setAttribute('role', 'tablist')
  tabs.setAttribute('aria-label', label)
  const panels = document.createElement('div')
  panels.className = 'representation-tab-panels'
  const rendered = new Set()

  const activate = async index => {
    const buttons = [...tabs.querySelectorAll('[role="tab"]')]
    const tabPanels = [...panels.querySelectorAll('[role="tabpanel"]')]
    for (const [position, button] of buttons.entries()) {
      const selected = position === index
      button.setAttribute('aria-selected', String(selected))
      button.tabIndex = selected ? 0 : -1
      tabPanels[position].hidden = !selected
    }
    const panel = tabPanels[index]
    if (!rendered.has(index)) {
      rendered.add(index)
      panel.setAttribute('aria-busy', 'true')
      try {
        await sections[index].render(panel)
      } catch (error) {
        panel.replaceChildren(node('p', String(error), 'representation-error'))
      } finally {
        panel.removeAttribute('aria-busy')
      }
    }
    resizeDetailCharts(panel)
  }

  for (const [index, section] of sections.entries()) {
    const tab = document.createElement('button')
    const panel = document.createElement('section')
    const tabId = `representation-tab-${serial}-${index}`
    const panelId = `representation-panel-${serial}-${index}`
    tab.type = 'button'
    tab.id = tabId
    tab.textContent = section.label
    tab.setAttribute('role', 'tab')
    tab.setAttribute('aria-controls', panelId)
    tab.setAttribute('aria-selected', 'false')
    tab.tabIndex = -1
    tab.addEventListener('click', () => { void activate(index) })
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
      const target = event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? sections.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + sections.length) % sections.length
      event.preventDefault()
      tabs.children[target]?.focus()
      void activate(target)
    })
    panel.id = panelId
    panel.className = 'representation-tab-panel'
    panel.setAttribute('role', 'tabpanel')
    panel.setAttribute('aria-labelledby', tabId)
    panel.hidden = true
    tabs.append(tab)
    panels.append(panel)
  }
  host.append(tabs, panels)
  await activate(0)
}

async function renderAnnData (host, level) {
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', `AnnData · ${level.name}`),
    metadataCards([
      ['Shape', `${level.dimensions.observations} observations × ${level.dimensions.variables} variables`],
      ['Primary layer', level.primary_layer],
      ['Layers', level.layers.length]
    ])
  )
  host.append(article)
  await renderNestedTabs(article, `${level.name} AnnData sections`, [
    {
      label: 'Axes',
      render: panel => {
        const axes = document.createElement('div')
        axes.className = 'scientific-grid'
        axes.append(tableDescription('Observations', level.obs), tableDescription('Variables', level.var))
        panel.append(axes, observationIdentities(level))
      }
    },
    ...level.layers.map(layer => ({
      label: layer.name,
      render: panel => renderLayer(panel, level, layer)
    })),
    {
      label: 'Aligned structures',
      render: panel => panel.append(namedStructureTable(level.aligned))
    }
  ])
}

async function renderAnnotationAnnData (host, representation, annotationTable, reference) {
  const observationCount = reference?.dimensions?.observations ?? reference?.obs?.row_count ?? 0
  const observations = reference?.obs ?? { row_count: observationCount, key_columns: [], columns: [] }
  const variables = {
    row_count: annotationTable.row_count,
    key_columns: annotationTable.key_columns ?? [],
    columns: annotationTable.columns ?? []
  }
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', `AnnData · annotation/${annotationTable.name}`),
    metadataCards([
      ['Modality role', 'annotation table'],
      ['Shape', `${observationCount} observations × ${annotationTable.row_count} variables`]
    ])
  )
  const relations = (representation.feature_relations ?? [])
    .filter(relation => relation.annotation_table === annotationTable.name)
  host.append(article)
  await renderNestedTabs(article, `${annotationTable.name} annotation AnnData sections`, [
    {
      label: 'Axes',
      render: panel => {
        const axes = document.createElement('div')
        axes.className = 'scientific-grid'
        axes.append(tableDescription('Observations', observations), tableDescription('Variables', variables))
        panel.append(axes)
        if (reference) panel.append(observationIdentities(reference))
      }
    },
    {
      label: 'Feature relations',
      render: panel => {
        if (relations.length) {
          panel.append(dataTable(
            ['Name', 'Target level', 'Coordinates'],
            relations.map(relation => [relation.name, relation.target_level, relation.coordinates.row_count])
          ))
        } else panel.append(node('p', 'No feature relations originate from this annotation table.', 'empty-note'))
      }
    }
  ])
}

function resizeDetailCharts (panel) {
  window.requestAnimationFrame(() => {
    for (const chart of panel.querySelectorAll('.layer-chart')) {
      if (chart.data) Plotly.Plots.resize(chart)
    }
  })
}

function activateDetailTab (key) {
  const showMore = element('show-more')
  for (const button of showMore.querySelectorAll('[data-detail-tab]')) {
    const selected = button.dataset.detailTab === key
    button.setAttribute('aria-selected', String(selected))
    button.tabIndex = selected ? 0 : -1
  }
  for (const panel of showMore.querySelectorAll('[data-detail-panel]')) {
    panel.hidden = panel.dataset.detailPanel !== key
    if (!panel.hidden) resizeDetailCharts(panel)
  }
}

function detailTabKeydown (event) {
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

function registerDetailTab (key, label, panel, render = null) {
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
  button.addEventListener('keydown', detailTabKeydown)
  button.addEventListener('click', () => {
    activateDetailTab(key)
    if (rendered || render === null) return
    rendered = true
    panel.setAttribute('aria-busy', 'true')
    panel.replaceChildren(node('p', 'Loading view…', 'empty-note'))
    Promise.resolve(render(panel))
      .catch(error => panel.replaceChildren(node('p', String(error), 'representation-error')))
      .finally(() => {
        panel.removeAttribute('aria-busy')
        if (!panel.hidden) resizeDetailCharts(panel)
      })
  })
  tabs.append(button)
  return button
}

function resetDetailTabs () {
  const generation = ++state.detailGeneration
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

function chartLayout (xTitle, yTitle, hasData) {
  return {
    height: 430,
    margin: { l: 90, r: 20, t: 20, b: 130 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'system-ui, -apple-system, sans-serif', size: 11, color: '#395951' },
    legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.38 },
    xaxis: { title: { text: xTitle, standoff: 14 }, automargin: true, gridcolor: '#e7eeeb', zeroline: false },
    yaxis: { title: { text: yTitle, standoff: 12 }, automargin: true, gridcolor: '#e7eeeb', zeroline: false },
    annotations: hasData ? [] : [{ text: 'No persisted measurements are available for this chart.', showarrow: false, x: 0.5, y: 0.5, xref: 'paper', yref: 'paper' }]
  }
}

function tracesFor (points, yField, yLabel, artifact = false) {
  const software = [...new Set(points.map(point => point.software_name))].sort()
  return software.map(name => {
    const selected = points.filter(point => point.software_name === name && point.input_size_mib != null && point[yField] != null)
    return {
      type: 'scatter', mode: 'markers', name,
      x: selected.map(point => point.input_size_mib),
      y: selected.map(point => point[yField]),
      text: selected.map(point => point.input_file),
      customdata: selected.map(point => [point.module, point.step, point.status, artifact ? point.output_role : '', artifact ? point.output_path : '']),
      marker: { size: 10, opacity: 0.78 },
      hovertemplate: `<b>%{text}</b><br>module=%{customdata[0]}<br>step=%{customdata[1]}<br>status=%{customdata[2]}${artifact ? '<br>output role=%{customdata[3]}<br>output=%{customdata[4]}' : ''}<br>input=%{x:.2f} MiB<br>${yLabel}=%{y:.2f}<extra>%{fullData.name}</extra>`
    }
  }).filter(trace => trace.x.length)
}

async function renderCharts (points) {
  const charts = [
    { id: 'runtime-chart', points: points.steps, field: 'runtime_seconds', x: 'Vendor input size (MiB)', y: 'Runtime (seconds)', label: 'runtime' },
    { id: 'memory-chart', points: points.steps, field: 'peak_memory_mib', x: 'Vendor input size (MiB)', y: 'Peak process-tree RSS (MiB)', label: 'peak RSS' },
    { id: 'output-chart', points: points.outputs, field: 'output_size_mib', x: 'Vendor input size (MiB)', y: 'Generated artifact size (MiB)', label: 'output size', artifact: true }
  ]
  await Promise.all(charts.map(chart => {
    const traces = tracesFor(chart.points, chart.field, chart.label, chart.artifact)
    return Plotly.react(element(chart.id), traces, chartLayout(chart.x, chart.y, Boolean(traces.length)), plotConfig)
  }))
}

function resizeCharts () {
  for (const id of chartIds) {
    const host = element(id)
    if (host.data) Plotly.Plots.resize(host)
  }
}

async function detail (row, navigate = false) {
  const changed = state.selected !== row.input_file || state.selectedRecord !== row.record
  state.selected = row.input_file
  state.selectedRecord = row.record
  element('detail-title').textContent = `${row.software_name} · ${row.module}`
  const showMoreTab = element('show-more-tab')
  showMoreTab.disabled = !row.record
  showMoreTab.dataset.status = row.status
  if (navigate && row.record) element('show-more-tab').click()
  if (changed) {
    const generation = resetDetailTabs()
    const detailRun = state.run
    renderDatasetFiles(row)
    const tabs = element('detail-tabs')
    const ioPanel = element('detail-io')
    const notices = element('detail-notices')
    registerDetailTab('io', 'Inputs & outputs', ioPanel)
    tabs.hidden = false
    activateDetailTab('io')
    notices.replaceChildren(node('p', 'Loading scientific representation…', 'empty-note'))
    const artifacts = representationArtifacts(row.record)
    const result = await loadRepresentationArtifacts(
      artifacts,
      async artifact => {
        const path = representationStorePath(detailRun, row.output_dir, artifact.path)
        return await readRepresentation(path)
      },
      () => generation === state.detailGeneration
    )
    if (!result) return
    const { loaded, problems } = result
    notices.replaceChildren(...problems.map(problem => node('p', problem, 'representation-error')))
    const selected = preferredLoadedRepresentation(row, loaded)
    if (!selected) {
      notices.append(node('p', 'No scientific representation was produced for this dataset.', 'empty-note'))
    } else {
      const views = representationViews(selected.representation)
      for (const view of views) {
        const panel = document.createElement('section')
        panel.className = 'detail-panel'
        panel.hidden = true
        element('detail').append(panel)
        registerDetailTab(`scientific-${view.key}`, view.label, panel, async host => {
          host.replaceChildren()
          if (view.kind === 'apb-metadata') {
            await renderApbMetadata(host, view.representation, selected.artifact.step)
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
            await renderAnnData(
              host,
              view.level
            )
          }
        })
      }
    }
    const diagnostics = document.createElement('details')
    diagnostics.className = 'execution-diagnostics'
    diagnostics.append(node('summary', 'Complete execution report'), jsonTree(row.record ?? {}))
    element('detail-diagnostics').replaceChildren(diagnostics)
  } else renderDatasetFiles(row)
}

function showMoreButton (cell) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'show-more-button'
  button.dataset.status = cell.getRow().getData().status
  button.textContent = 'Show more'
  button.addEventListener('click', event => {
    event.stopPropagation()
    void detail(cell.getRow().getData(), true)
  })
  return button
}

function fileCell (path, basename, parent, size) {
  if (!path) return '—'
  const host = document.createElement('div')
  host.title = path
  const name = document.createElement('strong')
  name.textContent = basename
  const context = document.createElement('div')
  const metadata = document.createElement('small')
  metadata.textContent = [parent, formatBytes(size)].filter(Boolean).join(' · ')
  context.append(metadata)
  host.append(name, context)
  return host
}

function inputFileCell (cell) {
  const row = cell.getRow().getData()
  return fileCell(row.input_file, row.input_file_name, row.input_file_parent, row.input_file_size_bytes)
}

function outputFileCell (cell) {
  const row = cell.getRow().getData()
  return fileCell(row.output_file, row.output_file_name, row.output_file_parent, row.output_file_size_bytes)
}

function renderStatusBar (summary, total) {
  const bar = element('status-bar')
  const fractions = statusFractions(summary, total)
  for (const segment of bar.children) {
    const fraction = fractions[segment.dataset.status] ?? 0
    segment.style.width = `${fraction * 100}%`
    segment.hidden = fraction === 0
  }
  const result = Object.entries(summary).map(([status, count]) => `${count} ${status}`).join(', ')
  bar.setAttribute('aria-label', total ? `${total} datasets: ${result}` : 'No dataset results')
}

function renderDatasetFiles (row) {
  const files = element('detail-files')
  files.replaceChildren()
  const artifacts = datasetArtifacts(row)
  for (const artifact of artifacts) {
    const group = document.createElement('div')
    const term = document.createElement('dt')
    const value = document.createElement('dd')
    const name = document.createElement('strong')
    const code = document.createElement('code')
    const metadata = document.createElement('small')
    const size = artifact.size_bytes ?? (artifact.role === 'vendor_table' ? row.input_file_size_bytes : null)
    term.textContent = `${artifact.step} · ${artifact.direction}`
    name.textContent = artifact.path?.split('/').at(-1) ?? '—'
    code.textContent = artifact.path ?? '—'
    const formattedSize = formatBytes(size)
    const exactSize = size == null || size === '' ? '' : `${Number(size).toLocaleString()} bytes`
    metadata.textContent = [artifact.role, artifact.format, formattedSize || 'size unavailable', exactSize].filter(Boolean).join(' · ')
    value.append(name, document.createElement('br'), code, document.createElement('br'), metadata)
    group.append(term, value)
    files.append(group)
  }
  files.hidden = artifacts.length === 0
}

async function loadRun (path) {
  resetDetailTabs()
  state.preview = ''
  state.manifest = null
  state.selected = ''
  state.selectedRecord = null
  for (const mounted of [state.table, ...state.tables].filter(Boolean)) mounted.destroy()
  state.table = null
  state.tables = []
  element('datasets').replaceChildren()
  element('show-more-tab').disabled = true
  element('show-more-tab').removeAttribute('data-status')
  document.querySelector('[data-tab="results"]').click()
  state.run = path.replace(/\/run.json$/, '')
  state.manifest = await read(path)
  state.reports.clear()
  state.operationStamp = ''
  const manifest = state.manifest
  state.corpus = await read(`${state.run}/${manifest.corpus}`, 'csv')
  state.inputMetadata = manifest.input_metadata
    ? await read(`${state.run}/${manifest.input_metadata}`, 'csv')
    : []
  state.workflowRows = manifest.workflow_table
    ? await read(`${state.run}/${manifest.workflow_table}`, 'csv')
    : []
  const config = await read(`${state.run}/${manifest.execution_settings}`)
  renderJson(element('manifest'), config)
  renderJson(element('run-manifest'), {
    run_id: manifest.run_id, created_at: manifest.created_at, apb_version: manifest.apb_version,
    aggregate_executable: manifest.aggregate_executable ?? null,
    aggregate_version: manifest.aggregate_version ?? null,
    corpus_snapshot: `${state.run}/${manifest.source_corpus}`,
    selected_corpus_snapshot: `${state.run}/${manifest.corpus}`,
    workflow_table_snapshot: manifest.workflow_table ? `${state.run}/${manifest.workflow_table}` : null,
    input_metadata_snapshot: manifest.input_metadata ? `${state.run}/${manifest.input_metadata}` : null
  })
  const links = element('links')
  links.replaceChildren()
  for (const name of new Set(['run.json', manifest.execution_settings, manifest.source_corpus, manifest.corpus, manifest.input_metadata, manifest.workflow_table, manifest.workflow_source].filter(Boolean))) {
    const link = document.createElement('a')
    link.href = url(`${state.run}/${name}`)
    link.textContent = name
    link.target = '_blank'
    links.append(link)
  }
  const inventory = await read(`${state.run}/${manifest.source_corpus}`, 'csv')
  element('corpus-title').textContent = `Corpus: ${config.corpus.split('/').at(-1)}`
  element('corpus-description').textContent = `${inventory.length} inventory entries · ${state.corpus.length} selected for this run. Table below is the frozen snapshot, not a live view of the source file.`
  state.tables.push(await table(element('corpus'), inventory,
    inventory.columns.map(field => ({ title: field, field }))))
  element('input-metadata-table').replaceChildren()
  if (manifest.input_metadata) {
    element('input-metadata-title').textContent = `Input sizes: ${manifest.input_metadata}`
    state.tables.push(await table(element('input-metadata-table'), state.inputMetadata,
      state.inputMetadata.columns.map(field => ({ title: field, field }))))
  } else element('input-metadata-title').textContent = 'No input-size snapshot in this run'
  element('workflow-table').replaceChildren()
  if (manifest.workflow_table) {
    element('workflow-table-title').textContent = manifest.workflow_table
    state.tables.push(await table(element('workflow-table'), state.workflowRows,
      state.workflowRows.columns.map(field => ({ title: field, field }))))
  } else element('workflow-table-title').textContent = 'This workflow needs no resource table'
  element('source').textContent = await read(`${state.run}/${manifest.workflow_source}`, 'text')
  await refreshRun()
}

async function loadConfiguration (group) {
  const config = group.settings
  const path = state.settingsPaths.get(group.id)
  const directory = path.replace(/\/execution_settings.json$/, '')
  state.run = ''
  state.manifest = null
  state.inputMetadata = []
  state.workflowRows = []
  state.reports.clear()
  state.selected = ''
  state.selectedRecord = null
  for (const mounted of [state.table, ...state.tables].filter(Boolean)) mounted.destroy()
  state.table = null
  state.tables = []
  resetDetailTabs()
  element('show-more-tab').disabled = true
  element('show-more-tab').removeAttribute('data-status')
  element('detail-title').textContent = 'No saved runs for these execution settings'
  renderJson(element('manifest'), config)
  element('run-manifest').textContent = 'No saved runs. Execution has not been started.'
  element('status').textContent = `${config.workflow} / ${config.format} · configured`
  const inventory = await read(`${directory}/corpus.csv`, 'csv')
  element('counts').textContent = `${inventory.length} inventory entries · no saved runs`
  renderStatusBar({}, inventory.length)
  element('workflow-steps').textContent = 'Steps: available after the first run'
  element('corpus-title').textContent = `Corpus: ${config.corpus.split('/').at(-1)}`
  element('corpus-description').textContent = `${inventory.length} entries. Preview captured when these execution settings were saved.`
  state.tables.push(await table(element('corpus'), inventory, inventory.columns.map(field => ({ title: field, field }))))
  element('input-metadata-table').replaceChildren()
  if (config.downloads) {
    const metadata = await read(`${directory}/input_metadata.csv`, 'csv')
    element('input-metadata-title').textContent = 'Input sizes: input_metadata.csv'
    state.tables.push(await table(element('input-metadata-table'), metadata,
      metadata.columns.map(field => ({ title: field, field }))))
  } else element('input-metadata-title').textContent = 'No downloads metadata configured'
  const workflowFile = config.workflow_table?.split('/').at(-1)
  element('workflow-table').replaceChildren()
  if (workflowFile) {
    const rows = await read(`${directory}/${workflowFile}`, 'csv')
    element('workflow-table-title').textContent = workflowFile
    state.tables.push(await table(element('workflow-table'), rows, rows.columns.map(field => ({ title: field, field }))))
  } else element('workflow-table-title').textContent = 'This workflow needs no resource table'
  element('links').replaceChildren(...['execution_settings.json', 'corpus.csv', config.downloads ? 'input_metadata.csv' : null, workflowFile].filter(Boolean).map(name => {
    const link = document.createElement('a')
    link.href = url(`${directory}/${name}`)
    link.textContent = name
    link.target = '_blank'
    return link
  }))
  element('source').textContent = 'Workflow source is captured when a run is prepared.'
  element('scheduler-log').textContent = ''
  await renderCharts({ steps: [], outputs: [] })
  state.preview = group.id
  document.querySelector('[data-tab="settings"]').click()
}

async function refreshRun () {
  if (!state.manifest) return
  const operation = await read(`${state.run}/operation.json`)
  if (state.operationStamp !== operation?.updated_at) {
    state.reports.clear()
    state.operationStamp = operation?.updated_at
  }
  const progress = new Map()
  const pending = state.manifest.reports.filter(link => !state.reports.has(link.path))
  for (let start = 0; start < pending.length; start += 12) {
    await Promise.all(pending.slice(start, start + 12).map(async link => {
      const report = await read(`${state.run}/${link.path}`)
      if (report) state.reports.set(link.path, report)
      else progress.set(link.progress, await read(`${state.run}/${link.progress}`))
    }))
  }
  const rows = datasetRows(state.manifest, state.corpus, state.inputMetadata, state.reports, progress, operation, state.workflowRows)
  const summary = counts(rows)
  element('status').textContent = `${state.manifest.workflow} / ${state.manifest.format} · ${operation?.status ?? 'prepared'}`
  element('counts').textContent = `${rows.length} datasets · ` + Object.entries(summary).map(([name, count]) => `${count} ${name}`).join(' · ')
  renderStatusBar(summary, rows.length)
  element('workflow-steps').textContent = `Steps: ${workflowSteps(rows).join(' → ') || 'none recorded'}`
  if (state.table) await state.table.replaceData(rows)
  else {
    state.table = await table(element('datasets'), rows, [
      { title: 'Result', field: 'status', width: 125 }, { title: 'Module', field: 'module', width: 140 },
      { title: 'Software', field: 'software_name', width: 145 },
      { title: 'Input file', field: 'input_file_name', formatter: inputFileCell, minWidth: 260 },
      { title: 'Output', field: 'output_file_name', formatter: outputFileCell, minWidth: 260 },
      ...workflowFields(state.workflowRows).map(field => ({ title: columnTitle(field), field, width: 120 })),
      { title: 'Seconds', field: 'runtime_seconds', formatter: cell => cell.getValue()?.toFixed(2) ?? '—', width: 95 },
      { title: '', formatter: showMoreButton, headerSort: false, headerFilter: false, width: 120,
        cellClick: (_event, cell) => { void detail(cell.getRow().getData(), true) } }
    ])
  }
  const selected = rows.find(row => row.input_file === state.selected)
  if (selected) await detail(selected)
  await renderCharts(chartPoints(rows))
  if (!element('log').hidden) element('scheduler-log').textContent = await read(`${state.run}/snakemake.log`, 'text') ?? ''
}

function populate (picker, options, value) {
  const signature = JSON.stringify(options)
  if (picker.dataset.options !== signature) {
    picker.dataset.options = signature
    picker.replaceChildren(...options.map(([value, label]) => {
      const option = document.createElement('option')
      option.value = value
      option.textContent = label
      return option
    }))
  }
  picker.value = value
}

async function refresh () {
  try {
    const catalog = await read('index.json')
    const paths = catalog?.runs ?? []
    for (const path of catalog?.settings ?? []) {
      const id = path.split('/').at(-2)
      state.settingsPaths.set(id, path)
      if (!state.settings.has(id)) state.settings.set(id, await read(path))
    }
    for (const path of paths) {
      if (!state.manifests.has(path)) state.manifests.set(path, await read(path))
    }
    const groups = executionGroups(paths.map(path => ({ path, manifest: state.manifests.get(path) })), state.settings)
    const choice = state.requestedExecution || state.execution
    const group = groups.find(group => group.id === choice) ?? groups[0]
    state.requestedExecution = ''
    if (group) {
      if (state.execution !== group.id) {
        state.execution = group.id
        state.requested = group.runs[0]?.path ?? ''
      }
      populate(element('execution'), groups.map(group => [group.id, group.label]), group.id)
      element('run').disabled = !group.runs.length
      if (group.runs.length) {
        const current = state.requested || `${state.run}/run.json`
        const run = group.runs.find(run => run.path === current) ?? group.runs[0]
        state.requested = ''
        populate(element('run'), group.runs.map(run => [run.path, `${run.manifest.created_at} · ${run.manifest.run_id}`]), run.path)
        if (`${state.run}/run.json` !== run.path) await loadRun(run.path)
        else await refreshRun()
      } else {
        populate(element('run'), [['', 'No saved runs']], '')
        if (state.preview !== group.id) await loadConfiguration(group)
      }
    }
    element('error').hidden = true
  } catch (error) {
    element('error').textContent = String(error)
    element('error').hidden = false
  }
  window.setTimeout(refresh, 2000)
}

element('run').addEventListener('change', event => {
  state.requested = event.target.value
})
element('execution').addEventListener('change', event => {
  state.requestedExecution = event.target.value
})
for (const button of document.querySelectorAll('[data-tab]')) {
  button.addEventListener('click', () => {
    for (const panel of document.querySelectorAll('.panel')) panel.hidden = panel.id !== button.dataset.tab
    for (const item of document.querySelectorAll('[data-tab]')) item.setAttribute('aria-selected', String(item === button))
    for (const mounted of [state.table, ...state.tables].filter(Boolean)) mounted.redraw(true)
    if (button.dataset.tab === 'visualizations') resizeCharts()
  })
}
for (const button of document.querySelectorAll('[data-settings-tab]')) {
  button.addEventListener('click', () => {
    const selected = button.dataset.settingsTab
    for (const panel of document.querySelectorAll('.settings-panel')) panel.hidden = panel.id !== selected
    for (const item of document.querySelectorAll('[data-settings-tab]')) item.setAttribute('aria-selected', String(item === button))
    for (const mounted of state.tables) mounted.redraw(true)
  })
}
refresh()
