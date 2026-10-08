import type { AnnDataDiagram, AnnDataStructure, ApbMetadata, DatasetReport, DatasetRow, FastaCheck, Layer, Level, LoadedRepresentation, NamedTable, Representation, RepresentationView, StepArtifact, StructureView } from './types.js'

// Pure projections of the versioned APB scientific representation.
export const REPRESENTATION_FORMAT = 'apb2-result-representation'
export const REPRESENTATION_VERSION = '5'
const EMBEDDED_JSON_FIELDS = new Set([
  'rule_json', 'plan_json', 'search_parameters'
])

/** Pair each recorded level check with the source provenance on its owning result. */
export function fastaChecks (representation: Representation): FastaCheck[] {
  const provenance = representation.root?.apb?.fasta?.provenance?.peptide_verification
  return representation.levels.flatMap(level => {
    const verification = level.apb?.fasta?.result?.peptide_verification
    if (!verification) return []
    return [{ level: level.name, ...verification, ...provenance }]
  })
}

function hierarchyOrder (representation: Representation | null | undefined): string[] {
  const hierarchy = representation?.root?.apb?.hierarchy ?? representation?.levels?.[0]?.apb?.hierarchy
  return (hierarchy?.identities ?? []).map(([name]) => name)
}

export function expandEmbeddedJsonForDisplay (value: unknown): unknown {
  return expandValue(value, '')
}

function expandValue (value: unknown, field: string): unknown {
  if (EMBEDDED_JSON_FIELDS.has(field) && typeof value === 'string') {
    try {
      const parsed: unknown = JSON.parse(value)
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

export function validatedRepresentation (document: unknown): Representation {
  const header = document && typeof document === 'object' ? document as Record<string, unknown> : {}
  if (header.format !== REPRESENTATION_FORMAT) {
    throw new Error(`Unsupported APB representation format: ${header.format ?? 'missing'}`)
  }
  if (header.format_version !== REPRESENTATION_VERSION) {
    throw new Error(`Unsupported APB representation version: ${header.format_version ?? 'missing'}`)
  }
  // The version identifies the tool-owned scientific schema; only known embedded JSON is expanded.
  return expandEmbeddedJsonForDisplay(header) as Representation
}

/** Read the ion AnnData var dimension without expanding the metadata tree. */
export function representationIonVariables (document: unknown): number | null {
  const header = document && typeof document === 'object' ? document as Record<string, unknown> : {}
  if (header.format !== REPRESENTATION_FORMAT ||
      header.format_version !== REPRESENTATION_VERSION) {
    throw new Error('Unsupported APB representation format or version')
  }
  const levels = Array.isArray(header.levels) ? header.levels as Level[] : []
  const count = levels.find(level => level?.name === 'ion')?.dimensions?.variables
  return typeof count === 'number' && Number.isSafeInteger(count) && count >= 0 ? count : null
}

export function representationArtifacts (record: DatasetReport | null | undefined): StepArtifact[] {
  return (record?.steps ?? []).flatMap(step => (step.outputs ?? [])
    .filter(artifact => artifact.role === 'representation')
    .map(artifact => ({ ...artifact, step: step.name })))
}

export async function loadRepresentationArtifacts (artifacts: StepArtifact[], load: (artifact: StepArtifact) => Promise<Representation | null>, isCurrent: () => boolean): Promise<{ loaded: LoadedRepresentation[]; problems: string[] } | null> {
  const loaded: LoadedRepresentation[] = []
  const problems: string[] = []
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

export function artifactStorePath (run: string, outputDirectory: string, artifactPath: string): string {
  const normalized = String(artifactPath ?? '').replaceAll('\\', '/')
  const marker = String(outputDirectory ?? '').replace(/^\/+|\/+$/g, '')
  const offset = normalized.indexOf(marker)
  if (!marker || offset < 0) throw new Error(`File is outside run artifacts: ${artifactPath}`)
  return `${run}/${normalized.slice(offset)}`
}

export function artifactAttemptStorePath (run: string, outputDirectory: string, artifactPath: string): string {
  const artifact = artifactStorePath(run, outputDirectory, artifactPath)
  const root = `${run}/${String(outputDirectory).replace(/^\/+|\/+$/g, '')}`
  const attempt = artifact.slice(root.length).replace(/^\/+/, '').split('/')[0]
  return attempt ? `${root}/${attempt}` : root
}

export function representationViews (representation: Representation): RepresentationView[] {
  const physicalFormat = representation?.artifact?.physical_format
  const isAnnDataFormat = physicalFormat === 'h5ad' || physicalFormat === 'h5mu'
  const metadata: RepresentationView = {
    key: 'apb-metadata',
    kind: 'apb-metadata',
    label: 'APB metadata',
    representation
  }
  const order = hierarchyOrder(representation)
  const sourceLevels = [...(representation?.levels ?? [])]
  if (isAnnDataFormat) {
    sourceLevels.sort((left, right) => order.indexOf(left.name) - order.indexOf(right.name))
  }
  const levels: Extract<RepresentationView, { kind: 'level' }>[] = sourceLevels.map((level, index) => ({
    key: `level-${index}`,
    kind: 'level',
    label: `${isAnnDataFormat ? 'AnnData' : 'Level'} · ${level.name}`,
    representation,
    level
  }))
  const annotations: RepresentationView[] = physicalFormat === 'h5mu'
    ? (representation?.annotation_tables ?? []).map((annotationTable, index) => ({
        key: `annotation-${index}`,
        kind: 'annotation',
        label: `AnnData · annotation/${annotationTable.name}`,
        representation,
        annotationTable,
        referenceLevel: levels[0]?.level
      }))
    : []
  const raw: RepresentationView = {
    key: 'representation-json',
    kind: 'representation-json',
    label: 'Representation JSON',
    representation
  }
  const structure: RepresentationView[] = isAnnDataFormat
    ? [{
        key: 'anndata-structure',
        kind: 'anndata-structure',
        label: 'Structure',
        representation
      }]
    : []
  return [metadata, ...levels, ...annotations, ...structure, raw]
}

export function annDataDiagram (level: Partial<Level> | null | undefined): AnnDataDiagram {
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
    aligned: { obsm: aligned.obsm ?? [], varm: aligned.varm ?? [], obsp: aligned.obsp ?? [], varp: aligned.varp ?? [] },
    uns: level?.apb ?? {}
  }
}

/** Project each physical AnnData separately from its MuData container. */
export function structureViews (representation: Representation): StructureView[] {
  const format = representation.artifact?.physical_format
  const order = hierarchyOrder(representation)
  const levels = [...(representation.levels ?? [])]
    .sort((left, right) => order.indexOf(left.name) - order.indexOf(right.name))
  const embedded = format === 'h5mu'
  const modalities: AnnDataStructure[] = levels.map(level => ({
    kind: 'anndata',
    label: `AnnData · ${level.name}`,
    objectPath: embedded ? `mdata.mod[${JSON.stringify(level.name)}]` : 'adata',
    // A standalone H5AD keeps the level part under uns[level] and its root part in uns["apb"].
    unsKey: embedded ? 'uns["apb"]' : `uns[${JSON.stringify(level.name)}]["apb"]`,
    ...(embedded ? {} : { rootUns: representation.root?.apb ?? {} }),
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
      unsKey: 'uns["apb"]',
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

export function matrixSummary (layer: Partial<Layer> = {}) {
  const statistics = layer.statistics ?? {}
  const number = (value: unknown): number | null => Number.isFinite(Number(value)) ? Number(value) : null
  const sum = (...values: (number | null | undefined)[]): number | null => values.some(value => number(value) != null)
    ? values.reduce<number>((total, value) => total + (number(value) ?? 0), 0)
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

export function alignedSummary (value: Partial<NamedTable> = {}) {
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

export function apbMetadataScopes (representation: Representation) {
  const physicalFormat = representation?.artifact?.physical_format
  const levels = representation?.levels ?? []
  const rootLabel = physicalFormat === 'h5mu'
    ? 'MuData'
    : physicalFormat === 'h5ad' ? 'AnnData root' : 'Result · root APB metadata'
  return [
    {
      label: rootLabel,
      value: apbNamespace(representation.root?.apb)
    },
    ...levels.map(level => ({
      label: physicalFormat === 'h5mu' || physicalFormat === 'h5ad'
        ? level.name
        : `Level "${level.name}" · APB metadata`,
      value: apbNamespace(level.apb)
    }))
  ]
}

function apbNamespace (value: ApbMetadata = {}) {
  return {
    uns: {
      apb: value
    }
  }
}

export function preferredLoadedRepresentation (row: DatasetRow | null | undefined, loadedRepresentations: LoadedRepresentation[]): (LoadedRepresentation & { representation: Representation }) | null {
  const readable = loadedRepresentations.filter((candidate): candidate is LoadedRepresentation & { representation: Representation } => candidate.representation != null)
  const outputPath = row?.output_file
  if (outputPath) {
    const expectedSidecar = `${outputPath}.apb.json`
    const matching = readable.find(candidate => candidate.artifact?.path === expectedSidecar)
    if (matching) return matching
  }
  return readable.at(-1) ?? null
}

export function layerChart (level: Level, layer: Layer) {
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
      type: 'box' as const,
      name: layer.name,
      x: summaries.map(summary =>
        observations.get(summary.observation_index)?.label ??
          `Observation ${summary.observation_index}`),
      q1: summaries.map(summary => summary.statistics.first_quartile ?? null),
      median: summaries.map(summary => summary.statistics.median ?? null),
      q3: summaries.map(summary => summary.statistics.third_quartile ?? null),
      lowerfence: summaries.map(summary => summary.statistics.minimum ?? null),
      upperfence: summaries.map(summary => summary.statistics.maximum ?? null),
      mean: summaries.map(summary => summary.statistics.mean ?? null),
      boxpoints: false as const,
      marker: { color: '#138c75' },
      hovertemplate: '<b>%{x}</b><br>minimum=%{lowerfence}<br>Q1=%{q1}<br>median=%{median}<br>Q3=%{q3}<br>maximum=%{upperfence}<extra></extra>'
    }
  }
}
