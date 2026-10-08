import type { Layout } from '../../shared/plotly.js'
import type { PlotTrace } from './scale.js'
import type { ScorePoint } from '../scores.js'

export const SCORE_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
  '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#393b79', '#637939', '#8c6d31', '#843c39'
]

export type ScorePlotMode = 'scatter' | 'ma'

function paddedRange (values: number[]): number[] {
  if (!values.length) return [0, 1]
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const padding = maximum === minimum ? Math.max(Math.abs(maximum) * 0.05, 0.05) : (maximum - minimum) * 0.05
  return [minimum - padding, maximum + padding]
}

/** Raw agreement or arithmetic difference versus mean, with a matching reference line. */
export function scoreFacetFigure (points: ScorePoint[], software: string[], mode: ScorePlotMode = 'scatter'): { traces: PlotTrace[]; layout: Partial<Layout> } {
  const mean = (point: ScorePoint) => point.reference / 2 + point.apb / 2
  const xLimits = paddedRange(mode === 'ma' ? points.map(mean) : points.flatMap(point => [point.reference, point.apb]))
  const differenceLimit = Math.max(...points.map(point => Math.abs(point.delta)), 0) * 1.05 || 0.05
  const yLimits = mode === 'ma' ? [-differenceLimit, differenceLimit] : xLimits
  const traces: PlotTrace[] = [{
    type: 'scatter', mode: 'lines', name: mode === 'ma' ? 'Δ = 0' : 'y = x', showlegend: false,
    x: xLimits, y: mode === 'ma' ? [0, 0] : xLimits,
    line: { color: '#687482', width: 1.5, dash: 'dash' },
    hoverinfo: 'skip'
  }]
  for (const [index, name] of software.entries()) {
    const selected = points.filter(point => point.software === name)
    if (!selected.length) continue
    traces.push({
      type: 'scatter', mode: 'markers', name, showlegend: false,
      x: selected.map(point => mode === 'ma' ? mean(point) : point.reference),
      y: selected.map(point => mode === 'ma' ? point.delta : point.apb),
      marker: { size: 7, opacity: 0.75, color: SCORE_COLORS[index % SCORE_COLORS.length] },
      text: selected.map(point => point.submission || point.input),
      customdata: selected.map(point => [point.module, point.quantity, point.sliceLabel, point.delta, point.input, point.level, point.reference, point.apb, mean(point)]),
      hovertemplate: '<b>%{text}</b><br>software=%{fullData.name}<br>module=%{customdata[0]}' +
        '<br>level=%{customdata[5]} · quantity=%{customdata[1]}<br>%{customdata[2]}' +
        '<br>ProteoBench=%{customdata[6]:.7g}<br>APB=%{customdata[7]:.7g}' +
        (mode === 'ma' ? '<br>Mean=%{customdata[8]:.7g}' : '') +
        '<br>Δ (APB − ProteoBench)=%{customdata[3]:.7g}' +
        '<br>%{customdata[4]}<extra></extra>'
    })
  }
  return {
    traces,
    layout: {
      height: 300, margin: { l: 65, r: 15, t: 8, b: 55 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 },
      xaxis: { title: { text: mode === 'ma' ? 'Mean score' : 'ProteoBench' }, range: xLimits, zeroline: false, automargin: true },
      yaxis: { title: { text: mode === 'ma' ? 'APB − ProteoBench' : 'APB' }, range: yLimits, zeroline: false, automargin: true }
    }
  }
}
