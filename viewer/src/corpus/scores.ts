import type { DatasetRow, Representation } from './types.js'

/** Scores are tool-owned observations; this module only matches and subtracts them. */
export interface ScoreSlice { key: string; label: string; values: Record<string, number> }
export interface ScoreQuantity {
  kind: 'quantification' | 'entrapment'
  level: string
  quantity: string
  slices: ScoreSlice[]
}
export interface RepresentationSummary { ionVariables: number | null; scores: ScoreQuantity[] }
export interface ReferenceScores { id: string; slices: ScoreSlice[] }
export interface ScorePoint {
  input: string; software: string; module: string; submission: string
  level: string; quantity: string; slice: string; sliceLabel: string
  metric: string; reference: number; apb: number; delta: number; artifact: string
}
export interface ScoreComparison {
  points: ScorePoint[]
  unmatched: { input: string; reason: string }[]
  matchedInputs: number
}

function object (value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {}
}

function numericScores (value: unknown): Record<string, number> {
  return Object.fromEntries(Object.entries(object(value)).filter(
    (entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1])
  ))
}

/** Quantification results are keyed by completeness cutoff; entrapment has scalar results. */
function scoreSlices (results: unknown): ScoreSlice[] {
  const values = object(results)
  const scalar = numericScores(values)
  if (Object.keys(scalar).length) {
    return [{ key: 'summary', label: 'Reported FDR', values: scalar }]
  }
  return Object.entries(values).filter(([key]) => /^\d+$/.test(key))
    .sort(([first], [second]) => Number(first) - Number(second))
    .map(([key, value]) => ({ key, label: `Completeness cutoff ${key}`, values: numericScores(value) }))
    .filter(slice => Object.keys(slice.values).length)
}

export function referenceScores (document: unknown): ReferenceScores | null {
  const value = object(document)
  const slices = scoreSlices(value.results)
  return slices.length ? { id: typeof value.id === 'string' ? value.id : '', slices } : null
}

/** Read v4 metadata from its owning AnnData, including each entrapment confidence kind. */
export function representationScores (representation: Representation): ScoreQuantity[] {
  return representation.levels.flatMap(level => {
    const proteobench = object(level.apb?.proteobench)
    const quantified = Object.entries(object(proteobench.scoring)).map(([quantity, value]) => ({
      kind: 'quantification' as const, level: level.name, quantity,
      slices: scoreSlices(object(object(value).scores).results)
    }))
    const entrapment = Object.entries(object(proteobench.entrapment)).map(([quantity, value]) => ({
      kind: 'entrapment' as const, level: level.name, quantity,
      slices: scoreSlices(value)
    }))
    return [...quantified, ...entrapment].filter(quantity => quantity.slices.length)
  })
}

export function scoreQuantities (rows: DatasetRow[], summaries: Map<string, RepresentationSummary | null>): ScoreQuantity[] {
  return rows.flatMap(row => scoresForRow(row, summaries).quantities)
}

function scoresForRow (row: DatasetRow, summaries: Map<string, RepresentationSummary | null>): { artifact: string; quantities: ScoreQuantity[] } {
  // Prefer the latest successfully observed scoring result; converted intermediates have none.
  for (const step of [...(row.record?.steps ?? [])].reverse()) {
    if (step.status !== 'succeeded') continue
    for (const artifact of [...(step.outputs ?? [])].reverse()) {
      if (artifact.role !== 'representation' || artifact.size_bytes == null) continue
      const quantities = summaries.get(artifact.path)?.scores ?? []
      if (quantities.length) return { artifact: artifact.path, quantities }
    }
  }
  return { artifact: '', quantities: [] }
}

/** Pair only the same input, score name and cutoff. Missing observations never become zero. */
export function compareScores (
  rows: DatasetRow[], summaries: Map<string, RepresentationSummary | null>,
  references: Map<string, ReferenceScores | null>, confidence: string = 'q_value', sliceKey: string = 'all'
): ScoreComparison {
  const points: ScorePoint[] = []
  const unmatched: ScoreComparison['unmatched'] = []
  const matched = new Set<string>()
  for (const row of rows) {
    const reference = references.get(row.input_file)
    const { artifact, quantities } = scoresForRow(row, summaries)
    const selected = quantities.filter(quantity => quantity.kind !== 'entrapment' || quantity.quantity === confidence)
    const start = points.length
    for (const quantity of selected) {
      for (const slice of quantity.slices) {
        if (sliceKey !== 'all' && slice.key !== sliceKey) continue
        const original = reference?.slices.find(candidate => candidate.key === slice.key)
        if (!original) continue
        for (const [metric, apb] of Object.entries(slice.values)) {
          const baseline = original.values[metric]
          if (baseline == null) continue
          points.push({
            input: row.input_file, software: row.software_name, module: row.module,
            submission: reference?.id ?? '', level: quantity.level, quantity: quantity.quantity,
            slice: slice.key, sliceLabel: slice.label, metric, reference: baseline, apb,
            delta: apb - baseline, artifact
          })
        }
      }
    }
    if (points.length > start) matched.add(row.input_file)
    else unmatched.push({
      input: row.input_file,
      reason: !quantities.length ? `No successful APB scores (${row.status})`
        : !reference ? 'Downloaded ProteoBench scores unavailable'
          : !selected.length ? `No APB ${confidence} scores`
            : 'No finite scores with matching names and completeness cutoff'
    })
  }
  return { points, unmatched, matchedInputs: matched.size }
}
