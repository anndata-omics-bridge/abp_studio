const BOX_ARRAY_FIELDS = [
  'x', 'q1', 'median', 'q3', 'lowerfence', 'upperfence', 'mean', 'text', 'customdata'
]

function positive (value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0
}

function logarithmicBoxTrace (trace) {
  if (!Array.isArray(trace.q1) || !Array.isArray(trace.median) || !Array.isArray(trace.q3)) {
    return trace
  }
  const indices = trace.q1
    .map((_, index) => index)
    .filter(index => positive(trace.q1[index]) &&
      positive(trace.median[index]) && positive(trace.q3[index]))
  const projected = { ...trace }
  for (const field of BOX_ARRAY_FIELDS) {
    if (Array.isArray(trace[field])) projected[field] = indices.map(index => trace[field][index])
  }
  projected.lowerfence = indices.map(index =>
    positive(trace.lowerfence?.[index]) ? trace.lowerfence[index] : trace.q1[index])
  projected.upperfence = indices.map(index =>
    positive(trace.upperfence?.[index]) ? trace.upperfence[index] : trace.q3[index])
  if (Array.isArray(trace.mean)) {
    projected.mean = indices.map(index =>
      positive(trace.mean[index]) ? trace.mean[index] : trace.median[index])
  }
  if (typeof trace.hovertemplate === 'string') {
    projected.hovertemplate = trace.hovertemplate.replace('minimum=', 'visible lower bound=')
  }
  return projected
}

/** Prepare precomputed box summaries for a valid logarithmic axis. */
export function tracesForScale (traces, scale) {
  if (scale !== 'log') return traces
  return traces.map(trace => trace.type === 'box' ? logarithmicBoxTrace(trace) : trace)
}

/** Apply one selected scale to every y-axis, including timing facets. */
export function yAxesForScale (layout, scale) {
  return Object.fromEntries(Object.entries(layout)
    .filter(([key]) => /^yaxis\d*$/.test(key))
    .map(([key, axis]) => {
      const scaled = { ...axis, type: scale, autorange: true }
      if (scale === 'log') delete scaled.rangemode
      return [key, scaled]
    }))
}
