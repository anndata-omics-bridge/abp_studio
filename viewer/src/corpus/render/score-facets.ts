import type { Layout } from '../../shared/plotly.js'
import type { PlotTrace } from './scale.js'
import type { ScorePoint } from '../scores.js'

export const SCORE_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
  '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#393b79', '#637939', '#8c6d31', '#843c39'
]

/** Independent facet scales, with identical X/Y limits and intercept 0, slope 1. */
export function scoreFacetFigure (points: ScorePoint[], software: string[]): { traces: PlotTrace[]; layout: Partial<Layout> } {
  const values = points.flatMap(point => [point.reference, point.apb])
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const padding = maximum === minimum ? Math.max(Math.abs(maximum) * 0.05, 0.05) : (maximum - minimum) * 0.05
  const limits = values.length ? [minimum - padding, maximum + padding] : [0, 1]
  const traces: PlotTrace[] = [{
    type: 'scatter', mode: 'lines', name: 'y = x', showlegend: false,
    x: limits, y: limits, line: { color: '#687482', width: 1.5, dash: 'dash' },
    hoverinfo: 'skip'
  }]
  for (const [index, name] of software.entries()) {
    const selected = points.filter(point => point.software === name)
    if (!selected.length) continue
    traces.push({
      type: 'scatter', mode: 'markers', name, showlegend: false,
      x: selected.map(point => point.reference), y: selected.map(point => point.apb),
      marker: { size: 7, opacity: 0.75, color: SCORE_COLORS[index % SCORE_COLORS.length] },
      text: selected.map(point => point.submission || point.input),
      customdata: selected.map(point => [point.module, point.quantity, point.sliceLabel, point.delta, point.input, point.level]),
      hovertemplate: '<b>%{text}</b><br>software=%{fullData.name}<br>module=%{customdata[0]}' +
        '<br>level=%{customdata[5]} · quantity=%{customdata[1]}<br>%{customdata[2]}' +
        '<br>ProteoBench=%{x:.7g}<br>APB=%{y:.7g}<br>Δ (APB − ProteoBench)=%{customdata[3]:.7g}' +
        '<br>%{customdata[4]}<extra></extra>'
    })
  }
  return {
    traces,
    layout: {
      height: 300, margin: { l: 65, r: 15, t: 8, b: 55 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 },
      xaxis: { title: { text: 'ProteoBench' }, range: limits, zeroline: false, automargin: true },
      yaxis: { title: { text: 'APB' }, range: limits, zeroline: false, automargin: true }
    }
  }
}
