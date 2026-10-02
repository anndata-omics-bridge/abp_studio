import { alignedSummary, matrixSummary, structureViews } from '../representation.js'
import { dataTable, jsonTree, node } from './dom.js'
import { renderTabs } from './tabs.js'

function count (value) {
  return Number(value ?? 0).toLocaleString()
}

function number (value) {
  if (value == null) return '—'
  const absolute = Math.abs(value)
  if ((absolute >= 1_000_000 || (absolute > 0 && absolute < 0.001))) {
    return value.toExponential(3)
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function countedFraction (value, total) {
  if (value == null) return '—'
  if (!total) return count(value)
  return `${count(value)} · ${(100 * value / total).toFixed(1)}%`
}

function list (items, emptyText = 'Empty') {
  if (!items.length) return node('p', emptyText, 'structure-empty')
  const result = document.createElement('ul')
  result.className = 'structure-list'
  for (const item of items) result.append(node('li', item))
  return result
}

function slot (name, title, summary, content) {
  const section = document.createElement('section')
  section.className = 'structure-slot'
  section.dataset.slot = name
  section.setAttribute('aria-label', title)
  const heading = document.createElement('header')
  heading.append(node('h5', title), node('span', summary, 'structure-summary'))
  section.append(heading, content)
  return section
}

function columns (description) {
  return list((description?.columns ?? []).map(column => {
    const nulls = column.null_count ? ` · ${count(column.null_count)} null` : ''
    return `${column.name} · ${column.dtype}${nulls}`
  }), 'No columns')
}

function axisSlot (name, title, description) {
  const keys = (description?.key_columns ?? []).join(', ') || 'none'
  const content = document.createElement('div')
  content.append(
    node('p', `${name}_names ← ${keys}`, 'structure-index'),
    columns(description)
  )
  return slot(
    name,
    title,
    `${count(description?.row_count)} rows · ${count(description?.columns?.length)} columns`,
    content
  )
}

function matrixCard (layer, primary = false) {
  const summary = matrixSummary(layer)
  const card = document.createElement('section')
  card.className = 'structure-matrix-card'
  const heading = document.createElement('header')
  heading.append(
    node('h6', primary ? `${summary.name} · X` : summary.name),
    node('span', primary ? 'primary' : summary.role, 'structure-matrix-role')
  )
  const facts = document.createElement('dl')
  facts.className = 'structure-matrix-facts'
  const kind = [summary.valueKind, summary.unit, summary.scale].filter(Boolean).join(' · ')
  const entries = [
    ['Shape', `${count(summary.shape.observations)} × ${count(summary.shape.variables)}`],
    ['Dtype', summary.dtype],
    ['Kind', kind],
    ['Finite', countedFraction(summary.finiteCount, summary.totalCount)],
    ['Missing', countedFraction(summary.missingCount, summary.totalCount)],
    ['Zeros', countedFraction(summary.zeroCount, summary.totalCount)],
    ['Mean', number(summary.mean)],
    ['Median', number(summary.median)],
    ['Range', summary.minimum == null && summary.maximum == null
      ? '—'
      : `${number(summary.minimum)} – ${number(summary.maximum)}`]
  ]
  if (summary.infiniteCount) {
    entries.splice(6, 0, ['Infinite', countedFraction(summary.infiniteCount, summary.totalCount)])
  }
  for (const [label, value] of entries) {
    const fact = document.createElement('div')
    fact.append(node('dt', label), node('dd', value || '—'))
    facts.append(fact)
  }
  card.append(heading, facts)
  return card
}

function layerSlot (diagram, annotation) {
  const primary = diagram.x
  return slot(
    'x',
    'X',
    primary ? primary.name : annotation ? 'None · annotation modality' : 'Missing primary layer',
    primary ? matrixCard(primary, true) : node('p', annotation ? 'X = None; features are described in var.' : 'No primary matrix', 'structure-empty')
  )
}

function layersSlot (diagram) {
  const content = document.createElement('div')
  content.className = 'structure-layers-grid'
  content.append(...diagram.layers.map(layer => matrixCard(layer)))
  return slot(
    'layers',
    'layers',
    `${count(diagram.layers.length)} matrices`,
    diagram.layers.length ? content : node('p', 'No layers', 'structure-empty')
  )
}

function alignedSlot (name, values) {
  const content = document.createElement('div')
  content.className = 'structure-aligned-grid'
  for (const value of values) {
    const summary = alignedSummary(value)
    const card = document.createElement('section')
    card.className = 'structure-aligned-card'
    const heading = document.createElement('header')
    heading.append(
      node('h6', summary.name),
      node('span', `${count(summary.rowCount)} × ${count(summary.columnCount)}`, 'structure-object-shape')
    )
    const facts = document.createElement('dl')
    facts.className = 'structure-matrix-facts'
    for (const [label, fact] of [
      ['Rows', count(summary.rowCount)],
      ['Columns', count(summary.columnCount)],
      ['Null cells', countedFraction(summary.nullCount, summary.cellCount)],
      ['Dtypes', summary.dtypes.join(', ') || '—'],
      ['Keys', summary.keyColumns.join(', ') || 'none']
    ]) {
      const item = document.createElement('div')
      item.append(node('dt', label), node('dd', fact))
      facts.append(item)
    }
    const columnList = columns(summary)
    columnList.classList.add('structure-aligned-columns')
    card.append(heading, facts, columnList)
    content.append(card)
  }
  return slot(
    name,
    name,
    `${count(values.length)} objects`,
    values.length ? content : node('p', 'Empty', 'structure-empty')
  )
}

function unsSlot (uns, objectPath, hasStorage) {
  const content = document.createElement('div')
  const groups = document.createElement('div')
  groups.className = 'structure-uns-groups'
  content.append(groups)
  for (const [tool, value] of Object.entries(uns)) {
    const group = document.createElement('section')
    group.append(
      node('h6', tool),
      node('code', `${objectPath}.uns["apb"][${JSON.stringify(tool)}]`, 'structure-path'),
      jsonTree(value)
    )
    groups.append(group)
  }
  if (hasStorage) {
    content.append(node('p', 'Also stored: uns["apb"]["storage"], the physical reconstruction descriptor. Its contents are not included in the representation.', 'structure-scope-description'))
  }
  if (!Object.keys(uns).length && !hasStorage) {
    content.append(node('p', 'Empty; this annotation AnnData has no APB metadata. Annotation provenance belongs to the MuData container.', 'structure-empty'))
  }
  return slot(
    'uns',
    Object.keys(uns).length ? 'uns["apb"]' : 'uns',
    hasStorage ? `${count(Object.keys(uns).length)} direct ${Object.keys(uns).length === 1 ? 'child' : 'children'} · storage omitted` : 'Empty',
    content
  )
}

function diagramNode (view) {
  const { diagram } = view
  const result = document.createElement('div')
  result.className = 'anndata-diagram'
  result.setAttribute('role', 'group')
  result.setAttribute('aria-label', `${diagram.name} AnnData structure`)
  result.append(
    axisSlot('var', 'var', diagram.var),
    alignedSlot('obsp', diagram.aligned.obsp),
    layerSlot(diagram, view.annotation),
    axisSlot('obs', 'obs', diagram.obs),
    alignedSlot('obsm', diagram.aligned.obsm),
    layersSlot(diagram),
    unsSlot(diagram.uns, view.objectPath, view.hasStorage),
    alignedSlot('varm', diagram.aligned.varm),
    alignedSlot('varp', diagram.aligned.varp)
  )
  return result
}

function annDataSection (host, view) {
  const section = document.createElement('section')
  section.className = 'structure-level'
  section.append(
    node('h4', `${view.label} · ${count(view.diagram.dimensions.observations)} observations × ${count(view.diagram.dimensions.variables)} variables`),
    node('code', view.objectPath, 'structure-path'),
    diagramNode(view)
  )
  host.append(section)
}

function muDataSection (host, view) {
  const section = document.createElement('section')
  section.className = 'structure-container'
  section.append(
    node('h4', 'MuData container'),
    node('code', view.objectPath, 'structure-path'),
    node('p', 'Root metadata and cross-modality relations belong here. Open an AnnData subtab to inspect that object’s X, layers, axes and aligned slots.', 'structure-intro'),
    node('h5', 'mod · embedded AnnData objects'),
    dataTable(['AnnData', 'Observations', 'Variables'], view.modalities.map(modality => [
      modality.name, count(modality.dimensions.observations), count(modality.dimensions.variables)
    ])),
    unsSlot(view.uns, view.objectPath, view.hasStorage),
    slot('varp', 'varp · feature relations', `${count(view.relations.length)} relations`,
      view.relations.length
        ? dataTable(['Relation', 'Annotation table', 'Target AnnData', 'Coordinates'], view.relations.map(relation => [
            relation.name, relation.annotation_table, relation.target_level, count(relation.coordinates?.row_count)
          ]))
        : node('p', 'No cross-modality feature relations.', 'structure-empty')),
    node('p', 'The representation describes modality axes. MuData’s merged root axes and alignment maps are not included.', 'structure-intro')
  )
  host.append(section)
}

/** Render the AnnData slots described by one APB result representation. */
export async function renderAnnDataStructure (host, representation) {
  const embedded = representation.artifact?.physical_format === 'h5mu'
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', embedded ? 'MuData container and embedded AnnData structures' : 'AnnData structure · H5AD'),
    node(
      'p',
      embedded
        ? 'One subtab per object: the MuData container, then each embedded AnnData. Each diagram shows only the slots owned by that AnnData.'
        : 'One AnnData object. Provenance, parsing evidence and results are grouped by tool directly in its uns["apb"].',
      'structure-intro'
    )
  )
  const views = structureViews(representation)
  host.append(article)
  if (!views.length) {
    article.append(node('p', 'No AnnData levels.', 'empty-note'))
  } else if (embedded) {
    await renderTabs(article, 'MuData and AnnData structures', views.map(view => ({
      label: view.label,
      render: panel => view.kind === 'mudata'
        ? muDataSection(panel, view)
        : annDataSection(panel, view)
    })))
  } else {
    for (const view of views) annDataSection(article, view)
  }
}
