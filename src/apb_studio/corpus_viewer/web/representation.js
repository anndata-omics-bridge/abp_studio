// Pure projections of the versioned APB scientific representation.
export const REPRESENTATION_FORMAT = 'apb2-result-representation'
export const REPRESENTATION_VERSION = '2'
const EMBEDDED_JSON_FIELDS = new Set([
  'rule_json', 'plan_json', 'search_parameters', 'aggregate'
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

export function representationStorePath (run, outputDirectory, artifactPath) {
  const normalized = String(artifactPath ?? '').replaceAll('\\', '/')
  const marker = String(outputDirectory ?? '').replace(/^\/+|\/+$/g, '')
  const offset = normalized.indexOf(marker)
  if (!marker || offset < 0) throw new Error(`Representation is outside run artifacts: ${artifactPath}`)
  return `${run}/${normalized.slice(offset)}`
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
  return [metadata, ...levels, ...annotations, raw]
}

export function apbMetadataScopes (representation) {
  const physicalFormat = representation?.artifact?.physical_format
  const shared = representation?.shared ?? { uns: {}, metadata: {} }
  const levels = representation?.levels ?? []
  if (physicalFormat === 'h5ad') {
    return levels.map(level => ({
      label: level.name,
      value: apbNamespace(level.uns, { ...shared.metadata, ...level.metadata })
    }))
  }
  const rootLabel = physicalFormat === 'h5mu'
    ? 'MuData'
    : 'Result · shared APB metadata'
  return [
    {
      label: rootLabel,
      value: apbNamespace(shared.uns, shared.metadata)
    },
    ...levels.map(level => ({
      label: physicalFormat === 'h5mu'
        ? level.name
        : `Level "${level.name}" · APB metadata`,
      value: apbNamespace(level.uns, { ...shared.metadata, ...level.metadata })
    }))
  ]
}

function apbNamespace (parse = {}, extensions = {}) {
  return {
    uns: {
      apb: {
        parse: parse ?? {},
        ...(extensions ?? {})
      }
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
