// Pure projections of the versioned APB scientific representation.
export const REPRESENTATION_FORMAT = 'apb2-result-representation'
export const REPRESENTATION_VERSION = '4'
const EMBEDDED_JSON_FIELDS = new Set([
  'rule_json', 'plan_json', 'search_parameters'
])
const LEVEL_ORDER = ['ion', 'peptidoform', 'peptide', 'protein', 'fragment']

export function expandEmbeddedJsonForDisplay (value) {
  return expandValue(value, '')
}

function expandValue (value, field) {
  if (EMBEDDED_JSON_FIELDS.has(field) && typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      if (parsed !== null && typeof parsed === 'object') value = parsed
      else return value
    } catch {
      return value
    }
  }
  if (Array.isArray(value)) return value.map(item => expandValue(item, ''))
  if (value === null || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.entries(value).map(([name, item]) => [name, expandValue(item, name)])
  )
}

export function validatedRepresentation (document) {
  if (document?.format !== REPRESENTATION_FORMAT) {
    throw new Error(`Unsupported APB representation format: ${document?.format ?? 'missing'}`)
  }
  if (document.format_version !== REPRESENTATION_VERSION) {
    throw new Error(`Unsupported APB representation version: ${document.format_version ?? 'missing'}`)
  }
  return expandEmbeddedJsonForDisplay(document)
}

/** Read the ion AnnData var dimension without expanding the metadata tree. */
export function representationIonVariables (document) {
  if (document?.format !== REPRESENTATION_FORMAT ||
      document.format_version !== REPRESENTATION_VERSION) {
    throw new Error('Unsupported APB representation format or version')
  }
  const count = document.levels?.find(level => level?.name === 'ion')?.dimensions?.variables
  return Number.isSafeInteger(count) && count >= 0 ? count : null
}

export function representationArtifacts (record) {
  return (record?.steps ?? []).flatMap(step => (step.outputs ?? [])
    .filter(artifact => artifact.role === 'representation')
    .map(artifact => ({ ...artifact, step: step.name })))
}

export async function loadRepresentationArtifacts (artifacts, load, isCurrent) {
  const loaded = []
  const problems = []
  for (const artifact of artifacts) {
    try {
      const representation = await load(artifact)
      if (!isCurrent()) return null
      loaded.push({ artifact, representation })
      if (!representation) problems.push(`Missing representation: ${artifact.path}`)
    } catch (error) {
      if (!isCurrent()) return null
      loaded.push({ artifact, representation: null })
      problems.push(String(error))
    }
  }
  return { loaded, problems }
}

export function artifactStorePath (run, outputDirectory, artifactPath) {
  const normalized = String(artifactPath ?? '').replaceAll('\\', '/')
  const marker = String(outputDirectory ?? '').replace(/^\/+|\/+$/g, '')
  const offset = normalized.indexOf(marker)
  if (!marker || offset < 0) throw new Error(`File is outside run artifacts: ${artifactPath}`)
  return `${run}/${normalized.slice(offset)}`
}

export function artifactAttemptStorePath (run, outputDirectory, artifactPath) {
  const artifact = artifactStorePath(run, outputDirectory, artifactPath)
  const root = `${run}/${String(outputDirectory).replace(/^\/+|\/+$/g, '')}`
  const attempt = artifact.slice(root.length).replace(/^\/+/, '').split('/')[0]
  return attempt ? `${root}/${attempt}` : root
}

export function representationViews (representation) {
  const physicalFormat = representation?.artifact?.physical_format
  const isAnnDataFormat = physicalFormat === 'h5ad' || physicalFormat === 'h5mu'
  const metadata = {
    key: 'apb-metadata',
    kind: 'apb-metadata',
    label: 'APB metadata',
    representation
  }
  const sourceLevels = [...(representation?.levels ?? [])]
  if (isAnnDataFormat) {
    sourceLevels.sort((left, right) => LEVEL_ORDER.indexOf(left.name) - LEVEL_ORDER.indexOf(right.name))
  }
  const levels = sourceLevels.map((level, index) => ({
    key: `level-${index}`,
    kind: 'level',
    label: `${isAnnDataFormat ? 'AnnData' : 'Level'} · ${level.name}`,
    representation,
    level
  }))
  const annotations = physicalFormat === 'h5mu'
    ? (representation?.annotation_tables ?? []).map((annotationTable, index) => ({
        key: `annotation-${index}`,
        kind: 'annotation',
        label: `AnnData · annotation/${annotationTable.name}`,
        representation,
        annotationTable,
        referenceLevel: levels[0]?.level
      }))
    : []
  const raw = {
    key: 'representation-json',
    kind: 'representation-json',
    label: 'Representation JSON',
    representation
  }
  const structure = isAnnDataFormat
    ? [{
        key: 'anndata-structure',
        kind: 'anndata-structure',
        label: 'Structure',
        representation
      }]
    : []
  return [metadata, ...levels, ...annotations, ...structure, raw]
}

export function annDataDiagram (level) {
  const logicalLayers = level?.layers ?? []
  const primary = logicalLayers.find(layer => layer.storage_slot === 'X') ??
    logicalLayers.find(layer => layer.primary) ?? null
  const layers = logicalLayers.filter(layer => layer.storage_slot !== 'X')
  const aligned = level?.aligned ?? {}
  return {
    name: level?.name ?? 'unnamed',
    dimensions: level?.dimensions ?? { observations: 0, variables: 0 },
    x: primary,
    layers,
    obs: level?.obs ?? { row_count: 0, key_columns: [], columns: [] },
    var: level?.var ?? { row_count: 0, key_columns: [], columns: [] },
    aligned: Object.fromEntries(
      ['obsm', 'varm', 'obsp', 'varp'].map(slot => [slot, aligned[slot] ?? []])
    ),
    uns: level?.apb ?? {}
  }
}

/** Project each physical AnnData separately from its MuData container. */
export function structureViews (representation) {
  const format = representation.artifact?.physical_format
  const levels = [...(representation.levels ?? [])]
    .sort((left, right) => LEVEL_ORDER.indexOf(left.name) - LEVEL_ORDER.indexOf(right.name))
  const embedded = format === 'h5mu'
  const modalities = levels.map(level => ({
    kind: 'anndata',
    label: `AnnData · ${level.name}`,
    objectPath: embedded ? `mdata.mod[${JSON.stringify(level.name)}]` : 'adata',
    diagram: annDataDiagram(level),
    hasStorage: true,
    annotation: false
  }))
  if (!embedded) return modalities

  for (const table of representation.annotation_tables ?? []) {
    // Annotation AnnData uses the first persisted level's obs and has no X or uns.
    const reference = levels[0]
    const description = `annotation/${table.name}`
    const diagram = annDataDiagram({
      name: description,
      dimensions: {
        observations: reference?.dimensions?.observations ?? 0,
        variables: table.row_count
      },
      obs: reference?.obs,
      var: table
    })
    diagram.uns = {}
    modalities.push({
      kind: 'anndata',
      label: `AnnData · ${description}`,
      // The sidecar records logical names, not encoded physical annotation keys.
      objectPath: `mdata.mod · annotation table ${JSON.stringify(table.name)}`,
      diagram,
      hasStorage: false,
      annotation: true
    })
  }
  return [{
    kind: 'mudata',
    label: 'MuData container',
    objectPath: 'mdata',
    uns: representation.root?.apb ?? {},
    hasStorage: true,
    modalities: modalities.map(view => ({
      name: view.diagram.name,
      objectPath: view.objectPath,
      dimensions: view.diagram.dimensions
    })),
    relations: representation.feature_relations ?? []
  }, ...modalities]
}

export function matrixSummary (layer = {}) {
  const statistics = layer.statistics ?? {}
  const number = value => Number.isFinite(Number(value)) ? Number(value) : null
  const sum = (...values) => values.some(value => number(value) != null)
    ? values.reduce((total, value) => total + (number(value) ?? 0), 0)
    : null
  return {
    name: layer.name ?? 'unnamed',
    role: layer.role ?? 'measurement',
    shape: layer.shape ?? { observations: 0, variables: 0 },
    dtype: layer.dtype ?? layer.type ?? 'unknown',
    valueKind: layer.value_kind ?? 'unknown',
    unit: layer.unit ?? null,
    scale: layer.scale ?? null,
    totalCount: number(statistics.total_count),
    finiteCount: number(statistics.finite_count),
    missingCount: sum(statistics.null_count, statistics.nan_count),
    infiniteCount: sum(
      statistics.positive_infinity_count,
      statistics.negative_infinity_count
    ),
    zeroCount: number(statistics.zero_count),
    mean: number(statistics.mean),
    median: number(statistics.median),
    minimum: number(statistics.minimum),
    maximum: number(statistics.maximum)
  }
}

export function alignedSummary (value = {}) {
  const columns = value.columns ?? []
  const rowCount = Number(value.row_count ?? 0)
  const cellCount = rowCount * columns.length
  return {
    name: value.name ?? 'unnamed',
    rowCount,
    columnCount: columns.length,
    cellCount,
    nullCount: columns.reduce((total, column) => total + Number(column.null_count ?? 0), 0),
    keyColumns: value.key_columns ?? [],
    dtypes: [...new Set(columns.map(column => column.dtype).filter(Boolean))],
    columns
  }
}

export function apbMetadataScopes (representation) {
  const physicalFormat = representation?.artifact?.physical_format
  const levels = representation?.levels ?? []
  if (physicalFormat === 'h5ad') {
    return levels.map(level => ({
      label: level.name,
      value: apbNamespace(level.apb)
    }))
  }
  const rootLabel = physicalFormat === 'h5mu'
    ? 'MuData'
    : 'Result · root APB metadata'
  return [
    {
      label: rootLabel,
      value: apbNamespace(representation.root?.apb)
    },
    ...levels.map(level => ({
      label: physicalFormat === 'h5mu'
        ? level.name
        : `Level "${level.name}" · APB metadata`,
      value: apbNamespace(level.apb)
    }))
  ]
}

function apbNamespace (value = {}) {
  return {
    uns: {
      apb: value
    }
  }
}

export function preferredLoadedRepresentation (row, loadedRepresentations) {
  const readable = loadedRepresentations.filter(candidate => candidate?.representation != null)
  const outputPath = row?.output_file
  if (outputPath) {
    const expectedSidecar = `${outputPath}.apb.json`
    const matching = readable.find(candidate => candidate.artifact?.path === expectedSidecar)
    if (matching) return matching
  }
  return readable.at(-1) ?? null
}

export function layerChart (level, layer) {
  if (layer.value_kind !== 'quantitative') return null
  const observations = new Map(
    (level.observations?.items ?? []).map(observation => [observation.index, observation])
  )
  const summaries = (layer.observation_summaries?.items ?? [])
    .filter(summary => summary.statistics?.first_quartile != null)
  const unit = layer.unit || 'encoded value'
  return {
    title: `${level.name} · ${layer.name}`,
    xTitle: (level.obs?.key_columns ?? []).join(' · ') || 'Observation',
    yTitle: `${layer.name} (${unit})`,
    trace: {
      type: 'box',
      name: layer.name,
      x: summaries.map(summary =>
        observations.get(summary.observation_index)?.label ??
          `Observation ${summary.observation_index}`),
      q1: summaries.map(summary => summary.statistics.first_quartile),
      median: summaries.map(summary => summary.statistics.median),
      q3: summaries.map(summary => summary.statistics.third_quartile),
      lowerfence: summaries.map(summary => summary.statistics.minimum),
      upperfence: summaries.map(summary => summary.statistics.maximum),
      mean: summaries.map(summary => summary.statistics.mean),
      boxpoints: false,
      marker: { color: '#138c75' },
      hovertemplate: '<b>%{x}</b><br>minimum=%{lowerfence}<br>Q1=%{q1}<br>median=%{median}<br>Q3=%{q3}<br>maximum=%{upperfence}<extra></extra>'
    }
  }
}
