import { Plotly } from '../vendor/plotly.js'
import { removeSection, sectionFor, updateSection } from './section.js'

// The one chart renderer. Panels describe traces and a layout; nothing here knows
// what a submission is.

const FONT = { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 }
const CONFIG = { displayModeBar: false, responsive: true }

/**
 * Merge a view's layout with the house style.
 *
 * @param {object} view The view, with `traces` and optional `layout`.
 * @returns {object} The layout handed to Plotly.
 */
function layoutFor (view) {
  return {
    margin: { l: 150, r: 16, t: 8, b: 28 },
    height: view.height ?? 220,
    font: FONT,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    showlegend: false,
    bargap: 0.25,
    ...(view.layout ?? {})
  }
}

export const chartRenderer = {
  name: 'chart',

  /**
   * Draw a chart into a new section of the host.
   *
   * @param {HTMLElement} host The panel host.
   * @param {object} view The view, with `traces`.
   * @returns {Promise<object>} The handle for later calls.
   */
  async mount (host, view) {
    const { section, body } = sectionFor(host, view)
    const figure = document.createElement('div')
    body.append(figure)
    await Plotly.newPlot(figure, view.traces, layoutFor(view), CONFIG)
    return { section, body, figure, view }
  },

  /**
   * Redraw with new data.
   *
   * @param {object} handle The handle from `mount`.
   * @param {object} view The new view.
   */
  async update (handle, view) {
    handle.view = view
    updateSection(handle.body, view)
    await Plotly.react(handle.figure, view.traces, layoutFor(view), CONFIG)
  },

  /**
   * Re-measure a chart that was drawn while its tab was hidden.
   *
   * @param {object} handle The handle from `mount`.
   */
  resize (handle) {
    Plotly.Plots.resize(handle.figure)
  },

  /**
   * Remove the chart and its listeners.
   *
   * @param {object} handle The handle from `mount`.
   */
  destroy (handle) {
    Plotly.purge(handle.figure)
    removeSection(handle.body)
  }
}
