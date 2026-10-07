import type { ChartView, DatasetPoint, XAxis } from '../types.js'
// The ion var dimension comes from persisted APB representations.

export function xValue (point: DatasetPoint, axis: XAxis): number | null {
  return axis === 'input_size_mib'
    ? point.input_size_mib
    : point.ion_variables ?? null
}

export function xLabel (axis: XAxis): string {
  if (axis === 'input_size_mib') return 'Vendor input size (MiB)'
  return 'Ion variables'
}

export function xAxisChoices (views: ChartView[]): { value: XAxis; label: string }[] {
  const points = views.flatMap(view => [
    ...(view.steps ?? []), ...(view.outputs ?? []),
    ...(view.timingViews ?? []).flatMap(timing => timing.points)
  ])
  return [
    { value: 'input_size_mib' as const, label: xLabel('input_size_mib') },
    ...(points.some(point => point.ion_variables != null)
      ? [{ value: 'ion_variables' as const, label: xLabel('ion_variables') }]
      : [])
  ]
}
