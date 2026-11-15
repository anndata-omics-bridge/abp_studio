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

/**
 * ProteoBench plasma score names and the generic names apb-proteobench stores them under; its
 * docs/compatibility.md lists them. ProteoBench's duplicates (`*_abs_log2_fc_error_spike_ins`,
 * `*_abs_epsilon_human_plasma`) are left out, so they pair with nothing.
 */
const PROTEOBENCH_SCORE_NAMES: Record<string, string> = {
  median_abs_log2_fc_error_spike_ins_global: 'median_abs_epsilon_changed_global',
  mean_abs_log2_fc_error_spike_ins_global: 'mean_abs_epsilon_changed_global',
  median_abs_log2_fc_error_spike_ins_eq_species: 'median_abs_epsilon_changed_eq_species',
  mean_abs_log2_fc_error_spike_ins_eq_species: 'mean_abs_epsilon_changed_eq_species',
  nr_quantified_spike_ins: 'nr_quantified_changed',
  dynamic_range_human_plasma_A: 'dynamic_range_HUMAN_A',
  dynamic_range_human_plasma_B: 'dynamic_range_HUMAN_B',
  dynamic_range_human_plasma_mean: 'dynamic_range_HUMAN'
}

/** A downloaded ProteoBench datapoint, its scores under the names APB stores them by. */
export function referenceScores (document: unknown): ReferenceScores | null {
  const value = object(document)
  const slices = scoreSlices(value.results).map(slice => ({
    ...slice,
    values: Object.fromEntries(Object.entries(slice.values).map(([name, score]) => [PROTEOBENCH_SCORE_NAMES[name] ?? name, score]))
  }))
  return slices.length ? { id: typeof value.id === 'string' ? value.id : '', slices } : null
}

/** Read v5 metadata from its owning AnnData, including each entrapment confidence kind. */
export function representationScores (representation: Representation): ScoreQuantity[] {
  return representation.levels.flatMap(level => {
    const proteobench = object(object(level.apb?.proteobench).result)
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

/** One APB score of one dataset, beside the features ProteoBench scored at that completeness cutoff. */
export interface IonScorePoint {
  input: string; software: string; module: string; level: string; quantity: string
  slice: string; sliceLabel: string; metric: string; features: number; score: number; artifact: string
}

/** ProteoBench's count of the features passing a completeness cutoff; the y of every ion-score facet. */
export const FEATURE_COUNT = 'nr_feature'

/** The scores ProteoBench's quantification main plot offers on X, in its menu order. */
export const MAIN_PLOT_SCORES = [
  'median_abs_epsilon_global', 'mean_abs_epsilon_global',
  'median_abs_epsilon_eq_species', 'mean_abs_epsilon_eq_species', 'roc_auc'
]

/** Main-plot scores first, in ProteoBench's order; every other score after them, alphabetically. */
export function orderedScores (metrics: string[]): string[] {
  const rank = (metric: string) => {
    const index = MAIN_PLOT_SCORES.indexOf(metric)
    return index < 0 ? MAIN_PLOT_SCORES.length : index
  }
  return [...new Set(metrics)].sort((first, second) => rank(first) - rank(second) || first.localeCompare(second))
}

/**
 * APB's own quantification scores at one completeness cutoff, each against that cutoff's
 * ``nr_feature``. Entrapment scores and cutoffs without ``nr_feature`` are left out.
 */
export function ionScorePoints (
  rows: DatasetRow[], summaries: Map<string, RepresentationSummary | null>, sliceKey: string
): IonScorePoint[] {
  return rows.flatMap(row => {
    const { artifact, quantities } = scoresForRow(row, summaries)
    return quantities.filter(quantity => quantity.kind === 'quantification').flatMap(quantity =>
      quantity.slices.filter(slice => slice.key === sliceKey && slice.values[FEATURE_COUNT] != null).flatMap(slice =>
        Object.entries(slice.values).filter(([metric]) => metric !== FEATURE_COUNT).map(([metric, score]) => ({
          input: row.input_file, software: row.software_name, module: row.module,
          level: quantity.level, quantity: quantity.quantity, slice: slice.key, sliceLabel: slice.label,
          metric, features: slice.values[FEATURE_COUNT], score, artifact
        }))))
  })
}

/** The completeness cutoffs any dataset's quantification scores carry, in numeric order. */
export function completenessCutoffs (rows: DatasetRow[], summaries: Map<string, RepresentationSummary | null>): { key: string; label: string }[] {
  const cutoffs = new Map(scoreQuantities(rows, summaries)
    .filter(quantity => quantity.kind === 'quantification')
    .flatMap(quantity => quantity.slices.map(slice => [slice.key, { key: slice.key, label: slice.label }] as const)))
  return [...cutoffs.values()].sort((first, second) => Number(first.key) - Number(second.key))
}

export type ScoreGroup = 'main' | 'other'

/** ProteoBench's main-plot scores and every other score, each in display order; an empty group is left out. */
export function scoreGroups (metrics: string[]): { kind: ScoreGroup; metrics: string[] }[] {
  const ordered = orderedScores(metrics)
  const groups: { kind: ScoreGroup; metrics: string[] }[] = [
    { kind: 'main', metrics: ordered.filter(metric => MAIN_PLOT_SCORES.includes(metric)) },
    { kind: 'other', metrics: ordered.filter(metric => !MAIN_PLOT_SCORES.includes(metric)) }
  ]
  return groups.filter(group => group.metrics.length)
}
