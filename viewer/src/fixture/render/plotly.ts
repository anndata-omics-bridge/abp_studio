import { Plotly } from '../../shared/plotly.js'
import type { Config, Layout } from '../../shared/plotly.js'
import type { ChartView, Renderer } from '../types.js'
import { removeSection, sectionFor } from './section.js'

interface ChartHandle { body: HTMLElement; figure: HTMLDivElement }

const FONT = { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 }
const CONFIG: Partial<Config> = { displayModeBar: false, responsive: true }

function layoutFor (view: ChartView): Partial<Layout> {
  return {
    margin: { l: 150, r: 16, t: 8, b: 28 },
    height: view.height ?? 220,
    font: FONT,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    showlegend: false,
    bargap: 0.25,
    ...view.layout
  }
}

export const chartRenderer: Renderer<ChartView, ChartHandle> = {
  name: 'chart',
  async mount (host, view) {
    const { body } = sectionFor(host, view)
    const figure = document.createElement('div')
    body.append(figure)
    await Plotly.newPlot(figure, view.traces, layoutFor(view), CONFIG)
    return { body, figure }
  },
  resize (handle) {
    void Plotly.Plots.resize(handle.figure)
  },
  destroy (handle) {
    Plotly.purge(handle.figure)
    removeSection(handle.body)
  }
}
