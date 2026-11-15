import type { AnnDataDiagram, AnnDataStructure, ApbMetadata, FeatureRelation, Layer, MuDataStructure, NamedTable, Representation, ResultStructure, TableDescription } from '../types.js'
import { alignedSummary, matrixSummary, structureLayout, structureViews } from '../representation.js'
import { dataTable, jsonTree, node } from './dom.js'
import { renderTabs } from './tabs.js'

function count (value: unknown): string {
  return Number(value ?? 0).toLocaleString()
}

function number (value: number | null | undefined): string {
  if (value == null) return '—'
  const absolute = Math.abs(value)
  if ((absolute >= 1_000_000 || (absolute > 0 && absolute < 0.001))) {
    return value.toExponential(3)
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function countedFraction (value: number | null | undefined, total: number | null | undefined): string {
  if (value == null) return '—'
  if (!total) return count(value)
  return `${count(value)} · ${(100 * value / total).toFixed(1)}%`
}

function list (items: string[], emptyText = 'Empty'): HTMLElement {
  if (!items.length) return node('p', emptyText, 'structure-empty')
  const result = document.createElement('ul')
  result.className = 'structure-list'
  for (const item of items) result.append(node('li', item))
  return result
}

function slot (name: string, title: string, summary: string, content: Node): HTMLElement {
  const section = document.createElement('section')
  section.className = 'structure-slot'
  section.dataset.slot = name
  section.setAttribute('aria-label', title)
  const heading = document.createElement('header')
  heading.append(node('h5', title), node('span', summary, 'structure-summary'))
  section.append(heading, content)
  return section
}

function columns (description: Pick<TableDescription, 'columns'> | null | undefined): HTMLElement {
  return list((description?.columns ?? []).map(column => {
    const nulls = column.null_count ? ` · ${count(column.null_count)} null` : ''
    return `${column.name} · ${column.dtype}${nulls}`
  }), 'No columns')
}

/** An AnnData axis names its index ``obs_names``/``var_names``; a DuckDB or Parquet level has key columns. */
function axisSlot (name: string, title: string, description: TableDescription | null | undefined, annData: boolean): HTMLElement {
  const keys = (description?.key_columns ?? []).join(', ') || 'none'
  const content = document.createElement('div')
  content.append(
    node('p', annData ? `${name}_names ← ${keys}` : `key columns: ${keys}`, 'structure-index'),
    columns(description)
  )
  return slot(
    name,
    title,
    `${count(description?.row_count)} rows · ${count(description?.columns?.length)} columns`,
    content
  )
}

function matrixCard (layer: Layer, primary = false): HTMLElement {
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

function layerSlot (diagram: AnnDataDiagram, annotation: boolean): HTMLElement {
  const primary = diagram.x
  return slot(
    'x',
    'X',
    primary ? primary.name : annotation ? 'None · annotation modality' : 'Missing primary layer',
    primary ? matrixCard(primary, true) : node('p', annotation ? 'X = None; features are described in var.' : 'No primary matrix', 'structure-empty')
  )
}

function layersSlot (diagram: AnnDataDiagram): HTMLElement {
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

function alignedSlot (name: string, values: NamedTable[]): HTMLElement {
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

interface UnsPart { uns: ApbMetadata; unsKey: string; hasStorage: boolean }

function unsGroups (part: UnsPart, objectPath: string | null): HTMLElement {
  const content = document.createElement('div')
  const groups = document.createElement('div')
  groups.className = 'structure-uns-groups'
  content.append(groups)
  for (const [tool, value] of Object.entries(part.uns)) {
    const group = document.createElement('section')
    group.append(
      node('h6', tool),
      node('code', `${objectPath ? `${objectPath}.` : ''}${part.unsKey}[${JSON.stringify(tool)}]`, 'structure-path'),
      jsonTree(value)
    )
    groups.append(group)
  }
  if (part.hasStorage) {
    content.append(node('p', `Also stored: ${part.unsKey}["storage"], the physical reconstruction descriptor. Its contents are not included in the representation.`, 'structure-scope-description'))
  }
  return content
}

/** One slot holding every APB part of an object: a standalone H5AD has a root and a level part. */
function unsSlot (parts: UnsPart[], objectPath: string | null, emptyText = 'Empty'): HTMLElement {
  const content = document.createElement('div')
  content.append(...parts.map(part => unsGroups(part, objectPath)))
  const children = parts.reduce((total, part) => total + Object.keys(part.uns).length, 0)
  const stored = parts.some(part => part.hasStorage)
  if (!children && !stored) content.append(node('p', emptyText, 'structure-empty'))
  const title = parts.filter(part => Object.keys(part.uns).length).map(part => part.unsKey).join(' · ')
  return slot(
    'uns',
    title || (objectPath == null ? 'apb' : 'uns'),
    children || stored
      ? `${count(children)} direct ${children === 1 ? 'child' : 'children'}${stored ? ' · storage omitted' : ''}`
      : 'Empty',
    content
  )
}

function relationsSlot (title: string, relations: FeatureRelation[], emptyText: string): HTMLElement {
  return slot('varp', title, `${count(relations.length)} relations`,
    relations.length
      ? dataTable(['Relation', 'From', 'To', 'Links'], relations.flatMap(relation =>
          relation.blocks.map(block => [relation.name, block.source, block.target, count(block.links)])
        ))
      : node('p', emptyText, 'structure-empty'))
}

function diagramNode (view: AnnDataStructure): HTMLElement {
  const { diagram } = view
  const result = document.createElement('div')
  result.className = 'anndata-diagram'
  result.setAttribute('role', 'group')
  const annData = view.objectPath != null
  result.setAttribute('aria-label', `${diagram.name} structure`)
  result.append(
    axisSlot('var', 'var', diagram.var, annData),
    alignedSlot('obsp', diagram.aligned.obsp),
    layerSlot(diagram, view.annotation),
    axisSlot('obs', 'obs', diagram.obs, annData),
    alignedSlot('obsm', diagram.aligned.obsm),
    layersSlot(diagram),
    unsSlot([
      ...(view.rootUns ? [{ uns: view.rootUns, unsKey: 'uns["apb"]', hasStorage: true }] : []),
      { uns: diagram.uns, unsKey: view.unsKey, hasStorage: view.hasStorage }
    ], view.objectPath, view.annotation
      ? 'Empty; this annotation AnnData has no APB metadata. Annotation provenance belongs to the MuData container.'
      : 'Empty'),
    alignedSlot('varm', diagram.aligned.varm),
    alignedSlot('varp', diagram.aligned.varp)
  )
  return result
}

function annDataSection (host: HTMLElement, view: AnnDataStructure): void {
  const section = document.createElement('section')
  section.className = 'structure-level'
  section.append(
    node('h4', `${view.label} · ${count(view.diagram.dimensions.observations)} observations × ${count(view.diagram.dimensions.variables)} variables`),
    ...(view.objectPath ? [node('code', view.objectPath, 'structure-path')] : []),
    diagramNode(view)
  )
  host.append(section)
}

function muDataSection (host: HTMLElement, view: MuDataStructure): void {
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
    unsSlot([{ uns: view.uns, unsKey: 'uns["apb"]', hasStorage: view.hasStorage }], view.objectPath),
    relationsSlot('varp · feature relations', view.relations, 'No cross-modality feature relations.'),
    node('p', 'The representation describes modality axes. MuData’s merged root axes and alignment maps are not included.', 'structure-intro')
  )
  host.append(section)
}

function resultSection (host: HTMLElement, view: ResultStructure): void {
  const section = document.createElement('section')
  section.className = 'structure-container'
  section.append(
    node('h4', view.label),
    node('p', 'Root metadata, annotation tables and feature relations belong here. Open a level subtab to inspect its X, layers, axes and aligned slots.', 'structure-intro'),
    node('h5', 'Levels'),
    dataTable(['Level', 'Observations', 'Variables'], view.levels.map(level => [
      level.name, count(level.dimensions.observations), count(level.dimensions.variables)
    ])),
    node('h5', 'Annotation tables'),
    view.annotationTables.length
      ? dataTable(['Table', 'Rows', 'Columns', 'Keys'], view.annotationTables.map(table => [
          table.name, count(table.row_count), count(table.columns?.length), (table.key_columns ?? []).join(', ') || 'none'
        ]))
      : node('p', 'No annotation tables.', 'structure-empty'),
    unsSlot([{ uns: view.uns, unsKey: 'apb', hasStorage: false }], null),
    relationsSlot('Feature relations', view.relations, 'No feature relations.')
  )
  host.append(section)
}

const TABLE_FORMATS: Record<string, string> = { duckdb: 'DuckDB', parquet: 'Parquet' }

/** Render the slots described by one APB result representation: AnnData objects in h5, levels otherwise. */
export async function renderAnnDataStructure (host: HTMLElement, representation: Representation): Promise<void> {
  const layout = structureLayout(representation)
  const format = representation.artifact?.physical_format ?? ''
  const tables = TABLE_FORMATS[format]
  const article = document.createElement('article')
  article.className = 'representation'
  article.append(
    node('h3', layout === 'mudata'
      ? 'MuData container and embedded AnnData structures'
      : layout === 'anndata' ? 'AnnData structure · H5AD' : `Result structure · ${tables ?? (format || 'unknown format')}`),
    node(
      'p',
      layout === 'mudata'
        ? 'One subtab per object: the MuData container, then each embedded AnnData. Each diagram shows only the slots owned by that AnnData.'
        : layout === 'anndata'
          ? 'One AnnData object with two APB parts, never merged: the root part in uns["apb"] and the level part in uns[level]["apb"]. Each groups provenance and results by tool.'
          : 'One subtab per object: the result root, then each level. Each diagram shows only the slots owned by that level.',
      'structure-intro'
    )
  )
  if (tables) {
    article.append(node(
      'p',
      `${tables} stores the result as generated tables plus an APB2 manifest; physical table names are not in the representation.`,
      'structure-intro'
    ))
  }
  const views = structureViews(representation)
  host.append(article)
  if (!views.length) {
    article.append(node('p', 'No levels.', 'empty-note'))
  } else if (layout === 'anndata') {
    for (const view of views) if (view.kind === 'anndata') annDataSection(article, view)
  } else {
    await renderTabs(article, layout === 'mudata' ? 'MuData and AnnData structures' : 'Result root and levels', views.map(view => ({
      label: view.label,
      render: panel => view.kind === 'mudata'
        ? muDataSection(panel, view)
        : view.kind === 'result' ? resultSection(panel, view) : annDataSection(panel, view)
    })))
  }
}
