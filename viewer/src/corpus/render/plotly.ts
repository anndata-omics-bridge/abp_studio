import type { Layout, PlotlyHTMLElement } from '../../shared/plotly.js'
import type { PlotTrace, ValueScale } from './scale.js'
import { Plotly } from '../../shared/plotly.js'
import { tracesForScale, yAxesForScale } from './scale.js'

export const PLOT_CONFIG = { displayModeBar: false, responsive: true }
const plotStates = new WeakMap<HTMLElement, { plot: HTMLElement; traces: PlotTrace[]; layout: Partial<Layout> }>()

function updateControls (host: HTMLElement, scale: ValueScale): void {
  host.dataset.yScale = scale
  for (const button of host.querySelectorAll<HTMLButtonElement>('[data-y-scale]')) {
    button.setAttribute('aria-pressed', String(button.dataset.yScale === scale))
  }
  const note = host.querySelector<HTMLElement>('.scale-note')
  if (note) note.hidden = scale !== 'log'
}

async function draw (host: HTMLElement, scale: ValueScale): Promise<void> {
  const state = plotStates.get(host)
  if (!state) return
  await Plotly.react(
    state.plot,
    tracesForScale(state.traces, scale),
    {
      ...state.layout,
      ...yAxesForScale(state.layout, scale)
    },
    PLOT_CONFIG
  )
}

/** Render a Plotly chart with an accessible linear/logarithmic value-axis control. */
export async function renderScalePlot (host: HTMLElement, traces: PlotTrace[], layout: Partial<Layout>): Promise<void> {
  let plot = host.querySelector<HTMLElement>(':scope > .plotly-chart')
  if (!plot) {
    const controls = document.createElement('div')
    const label = document.createElement('span')
    const note = document.createElement('span')
    controls.className = 'scale-controls'
    controls.setAttribute('aria-label', 'Value axis scale')
    label.textContent = 'Y scale'
    note.className = 'scale-note'
    note.textContent = 'Non-positive values hidden; affected whiskers start at Q1.'
    note.hidden = true
    controls.append(label)
    for (const [scale, text] of [['linear', 'Linear'], ['log', 'Log']] as const) {
      const button = document.createElement('button')
      button.type = 'button'
      button.dataset.yScale = scale
      button.textContent = text
      button.addEventListener('click', () => {
        updateControls(host, scale)
        void draw(host, scale)
      })
      controls.append(button)
    }
    controls.append(note)
    plot = document.createElement('div')
    plot.className = 'plotly-chart'
    host.append(controls, plot)
  }
  const scale = host.dataset.yScale === 'log' ? 'log' : 'linear'
  const hasData = traces.length > 0
  plotStates.set(host, { plot, traces, layout })
  updateControls(host, scale)
  for (const button of host.querySelectorAll<HTMLButtonElement>('[data-y-scale]')) button.disabled = !hasData
  await draw(host, scale)
}

/** Resize a chart rendered by renderScalePlot. */
export function resizeScalePlot (host: HTMLElement): void {
  const plot = host.querySelector<HTMLElement>(':scope > .plotly-chart')
  if ((plot as PlotlyHTMLElement | null)?.data) void Plotly.Plots.resize(plot!)
}
