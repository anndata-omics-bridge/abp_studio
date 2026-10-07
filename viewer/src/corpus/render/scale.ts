import type { Datum, Layout, LayoutAxis, PlotData } from '../../shared/plotly.js'

/** Precomputed box summaries are supported by Plotly but absent from its typings. */
export type PlotTrace = Partial<PlotData> & {
  q1?: Datum[]
  median?: Datum[]
  q3?: Datum[]
  lowerfence?: Datum[]
  upperfence?: Datum[]
  mean?: Datum[]
}
export type ValueScale = 'linear' | 'log'
const BOX_ARRAY_FIELDS = ['x', 'q1', 'median', 'q3', 'lowerfence', 'upperfence', 'mean', 'text', 'customdata'] as const

function positive (value: unknown): boolean {
  const number = Number(value)
  return Number.isFinite(number) && number > 0
}

function logarithmicBoxTrace (trace: PlotTrace): PlotTrace {
  const { q1, median, q3 } = trace
  if (!Array.isArray(q1) || !Array.isArray(median) || !Array.isArray(q3)) return trace
  const indices = q1.map((_, index) => index)
    .filter(index => positive(q1[index]) && positive(median[index]) && positive(q3[index]))
  const projected: PlotTrace = { ...trace }
  // Each field retains its original element type; projection only selects matching rows.
  for (const field of BOX_ARRAY_FIELDS) {
    const values = trace[field]
    if (Array.isArray(values)) Object.assign(projected, { [field]: indices.map(index => values[index]) })
  }
  projected.lowerfence = indices.map(index => positive(trace.lowerfence?.[index]) ? trace.lowerfence![index] : q1[index])
  projected.upperfence = indices.map(index => positive(trace.upperfence?.[index]) ? trace.upperfence![index] : q3[index])
  if (Array.isArray(trace.mean)) {
    projected.mean = indices.map(index => positive(trace.mean![index]) ? trace.mean![index] : median[index])
  }
  if (typeof trace.hovertemplate === 'string') {
    projected.hovertemplate = trace.hovertemplate.replace('minimum=', 'visible lower bound=')
  }
  return projected
}

/** Prepare precomputed box summaries for a valid logarithmic axis. */
export function tracesForScale (traces: PlotTrace[], scale: ValueScale): PlotTrace[] {
  if (scale !== 'log') return traces
  return traces.map(trace => trace.type === 'box' ? logarithmicBoxTrace(trace) : trace)
}

/** Apply one selected scale to every y-axis, including timing facets. */
export function yAxesForScale (layout: Partial<Layout>, scale: ValueScale): Partial<Layout> {
  return Object.fromEntries(Object.entries(layout)
    .filter(([key]) => /^yaxis\d*$/.test(key))
    .map(([key, axis]) => {
      const scaled: Partial<LayoutAxis> = { ...axis as Partial<LayoutAxis>, type: scale, autorange: true }
      if (scale === 'log') delete scaled.rangemode
      return [key, scaled]
    }))
}
