// The ion var dimension comes from persisted APB representations.

export function xValue (point, axis) {
  return axis === 'input_size_mib'
    ? point.input_size_mib
    : point.ion_variables ?? null
}

export function xLabel (axis) {
  if (axis === 'input_size_mib') return 'Vendor input size (MiB)'
  return 'Ion variables'
}

export function xAxisChoices (views) {
  const points = views.flatMap(view => [
    ...(view.steps ?? []), ...(view.outputs ?? []),
    ...(view.timingViews ?? []).flatMap(timing => timing.points)
  ])
  return [
    { value: 'input_size_mib', label: xLabel('input_size_mib') },
    ...(points.some(point => point.ion_variables != null)
      ? [{ value: 'ion_variables', label: xLabel('ion_variables') }]
      : [])
  ]
}
