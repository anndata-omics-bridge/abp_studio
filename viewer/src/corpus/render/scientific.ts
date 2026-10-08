import type { AlignedTables, Layer, Level, NamedTable, Representation, Statistics, TableDescription } from '../types.js'
import type { Layout } from '../../shared/plotly.js'
import type { TabSection } from './tabs.js'
import { formatBytes } from '../model.js'
import { apbMetadataScopes, fastaChecks, layerChart } from '../representation.js'
import { dataTable, jsonTree, metadataCards, node } from './dom.js'
import { renderScalePlot, resizeScalePlot } from './plotly.js'
import { renderTabs } from './tabs.js'

// Scientific representation rendering is isolated from run loading and navigation.
// It receives already-validated APB representation objects and mounts only view state.

/** Show reference identity beside each persisted peptide-verification result. */
export function renderFastaChecks (host: HTMLElement, representation: Representation): void {
  const checks = fastaChecks(representation)
  if (!checks.length) return
  const card = document.createElement('article')
  card.className = 'scientific-card fasta-checks'
  card.append(
    node('h3', 'FASTA peptide checks'),
    node('p', 'Peptide matching against the workflow reference. I/L-only matched features occur only as another I/L spelling. An unmatched peptide can reflect a different search database or sequence variant.', 'structure-intro'),
    dataTable(
      ['Level', 'Reference FASTA used', 'Matched features', 'Unmatched features', 'I/L-only matched'],
      checks.map(check => [
        check.level,
        Object.values(check.sources ?? {}).map(source => source.path).filter(Boolean).join(', ') || 'Not recorded',
        check.matched_feature_count?.toLocaleString(),
        check.unmatched_feature_count?.toLocaleString(),
        check.il_only_matched_feature_count?.toLocaleString() ?? 'Not recorded'
      ])
    )
  )
  host.append(card)
}

function tableDescription (title: string, description: TableDescription): HTMLElement {
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

function statisticsTable (statistics: Statistics | undefined): HTMLTableElement {
  const labels = {
    total_count: 'Cells',
    finite_count: 'Finite',
    null_count: 'Null',
    nan_count: 'NaN',
    positive_infinity_count: '+Infinity',
    negative_infinity_count: '−Infinity',
    zero_count: 'Zero',
    mean: 'Mean',
    standard_deviation: 'Standard deviation',
    minimum: 'Minimum',
    first_quartile: 'First quartile',
    median: 'Median',
    third_quartile: 'Third quartile',
    maximum: 'Maximum',
    quartile_method: 'Quartile method',
    quartile_sample_count: 'Quartile sample cells',
    quartile_sample_limit: 'Quartile sample limit'
  }
  return dataTable(
    ['Statistic', 'Value'],
    Object.entries(labels).map(([field, label]) => [label, statistics?.[field]])
  )
}

function categoricalCountsTable (counts: Record<string, number> | undefined): HTMLTableElement {
  const labels = {
    total_count: 'Cells',
    known_count: 'Known-category cells',
    missing_or_unknown_count: 'Missing or unknown'
  }
  return dataTable(
    ['Count', 'Value'],
    Object.entries(labels).map(([field, label]) => [label, counts?.[field]])
  )
}

function observationIdentities (level: Level): HTMLElement {
  const observations = level.observations ?? {
    total_count: 0,
    emitted_count: 0,
    truncated: false,
    items: []
  }
  const keys = level.obs?.key_columns ?? []
  const details = document.createElement('details')
  const qualifier = observations.truncated ? ', truncated' : ''
  details.append(
    node(
      'summary',
      `Observation identities · ${observations.emitted_count} of ${observations.total_count}${qualifier}`
    ),
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

function namedStructureTable (aligned: AlignedTables | undefined): HTMLElement {
  const rows = []
  for (const slot of ['obsm', 'varm', 'obsp', 'varp'] as const) {
    for (const value of aligned?.[slot] ?? []) {
      rows.push([
        slot,
        value.name,
        value.row_count,
        (value.columns ?? []).map(column => `${column.name}: ${column.dtype}`).join(', ')
      ])
    }
  }
  return rows.length
    ? dataTable(['Slot', 'Name', 'Rows', 'Columns'], rows)
    : node('p', 'No aligned or pairwise slots.', 'empty-note')
}

function layerLayout (xTitle: string, yTitle: string, hasData: boolean): Partial<Layout> {
  return {
    height: 360,
    margin: { l: 85, r: 15, t: 15, b: 100 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 },
    showlegend: false,
    xaxis: { title: { text: xTitle }, automargin: true, zeroline: false },
    yaxis: { title: { text: yTitle }, automargin: true, zeroline: false },
    annotations: hasData
      ? []
      : [{
          text: 'No persisted measurements are available for this layer.',
          showarrow: false,
          x: 0.5,
          y: 0.5,
          xref: 'paper',
          yref: 'paper'
        }]
  }
}

async function renderLayer (host: HTMLElement, level: Level, layer: Layer): Promise<void> {
  const card = document.createElement('article')
  card.className = 'layer-card'
  const heading = document.createElement('div')
  heading.className = 'layer-heading'
  heading.append(node('h4', layer.name))
  if (layer.primary) heading.append(node('span', 'Primary', 'badge'))
  const metadata: [string, unknown][] = [
    ['Role', layer.role],
    ['Shape', `${layer.shape.observations} × ${layer.shape.variables}`],
    ['Value kind', layer.value_kind]
  ]
  if (layer.value_kind === 'categorical') {
    metadata.push(['Dtype', layer.dtype])
    metadata.push(['Categories', layer.category_count])
  } else {
    const summaries = layer.observation_summaries
    metadata.push(
      ['Logical type', layer.type ?? 'number'],
      ['Matrix dtype', layer.dtype],
      ['Unit', layer.unit],
      ['Scale', layer.scale],
      [
        'Plotted observations',
        summaries
          ? `${summaries.emitted_count} of ${summaries.total_count}${summaries.truncated ? ' (truncated)' : ''}`
          : null
      ]
    )
  }
  card.append(heading, metadataCards(metadata))
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
  await renderScalePlot(
    chartHost,
    chart.trace.x.length ? [chart.trace] : [],
    layerLayout(chart.xTitle, chart.yTitle, Boolean(chart.trace.x.length))
  )
}

/** @param {HTMLElement} panel Visible panel. */
export function resizeDetailCharts (panel: HTMLElement): void {
  window.requestAnimationFrame(() => {
    for (const chart of panel.querySelectorAll<HTMLElement>('.layer-chart')) {
      resizeScalePlot(chart)
    }
  })
}

async function renderNestedTabs (host: HTMLElement, label: string, sections: TabSection[]): Promise<void> {
  await renderTabs(host, label, sections, resizeDetailCharts)
}

/** Render the APB metadata scopes for one result. */
export async function renderApbMetadata (host: HTMLElement, representation: Representation, step: string): Promise<void> {
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', 'APB provenance and extension metadata'),
    node('p', 'Metadata is grouped by tool in a root part and one part per level, never merged: a MuData\'s uns["apb"] and each modality\'s, or a standalone AnnData\'s uns["apb"] and uns[level]["apb"]. The storage reconstruction descriptor is omitted.', 'structure-intro'),
    metadataCards([
      ['Workflow step', step],
      ['Source artifact', representation.artifact?.name],
      ['Physical format', representation.artifact?.physical_format],
      ['Artifact size', formatBytes(representation.artifact?.size_bytes)]
    ])
  )
  host.append(article)
  await renderNestedTabs(
    article,
    'APB metadata scopes',
    apbMetadataScopes(representation).map(scope => ({
      label: scope.label,
      render: panel => panel.append(jsonTree(scope.value, ['uns', 'uns.apb']))
    }))
  )
}

/** Render the complete representation JSON. */
export function renderRepresentationJson (host: HTMLElement, representation: Representation): void {
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(node('h3', 'Complete APB result representation'), jsonTree(representation))
  host.append(article)
}

/** Render one quantitative AnnData level. */
export async function renderAnnData (host: HTMLElement, level: Level): Promise<void> {
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
        axes.append(
          tableDescription('Observations', level.obs),
          tableDescription('Variables', level.var)
        )
        panel.append(axes, observationIdentities(level))
      }
    },
    ...level.layers.map(layer => ({
      label: layer.name,
      render: (panel: HTMLElement) => renderLayer(panel, level, layer)
    })),
    {
      label: 'Aligned structures',
      render: panel => panel.append(namedStructureTable(level.aligned))
    }
  ])
}

/** Render one annotation table as its AnnData projection. */
export async function renderAnnotationAnnData (
  host: HTMLElement,
  representation: Representation,
  annotationTable: NamedTable,
  reference: Level | undefined
) {
  const observationCount = reference?.dimensions?.observations ?? reference?.obs?.row_count ?? 0
  const observations = reference?.obs ?? {
    row_count: observationCount,
    key_columns: [],
    columns: []
  }
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
        axes.append(
          tableDescription('Observations', observations),
          tableDescription('Variables', variables)
        )
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
            relations.map(relation => [
              relation.name,
              relation.target_level,
              relation.coordinates.row_count
            ])
          ))
        } else {
          panel.append(
            node('p', 'No feature relations originate from this annotation table.', 'empty-note')
          )
        }
      }
    }
  ])
}
