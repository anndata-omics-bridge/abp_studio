import { Plotly } from '../../shared/plotly.js'
import type { PlotlyHTMLElement } from '../../shared/plotly.js'
import type { DatasetRow } from '../types.js'
import type { IonScorePoint, RepresentationSummary, ScoreGroup } from '../scores.js'
import { completenessCutoffs, ionScorePoints, scoreGroups } from '../scores.js'
import { node } from '../render/dom.js'
import { PLOT_CONFIG } from '../render/plotly.js'
import { renderTabs } from '../render/tabs.js'
import { SCORE_COLORS, ionScoreFigure } from '../render/score-facets.js'

const GROUP_LABELS: Record<ScoreGroup, string> = { main: 'Main scores', other: 'Other scores' }

/**
 * APB's ProteoBench scores against the ions scored at one completeness cutoff, in two tabs:
 * ProteoBench's main-plot scores and every other score, each one score at a time. Reads no extra files.
 */
export function createProteobenchScoresPanel (host: HTMLElement) {
  let directory = ''
  let rows: DatasetRow[] = []
  let summaries = new Map<string, RepresentationSummary | null>()
  let software: string[] = []
  let slice = ''
  let group: ScoreGroup = 'main'
  const chosen: Record<ScoreGroup, string> = { main: '', other: '' }
  let signature = ''

  function visible () { return !host.hidden && !host.closest<HTMLElement>('#insights')?.hidden }

  function plots () { return [...host.querySelectorAll<HTMLElement>('.score-plot')] }

  function clearPlots () {
    for (const plot of plots()) {
      if ((plot as PlotlyHTMLElement).data) Plotly.purge(plot)
    }
    host.replaceChildren()
    signature = ''
  }

  function dropdown (label: string, choices: { key: string; label: string }[], value: string, select: (value: string) => void) {
    const control = node('label', label, 'score-control')
    const element = document.createElement('select')
    element.setAttribute('aria-label', label)
    for (const choice of choices) {
      const option = document.createElement('option')
      option.value = choice.key
      option.textContent = choice.label
      element.append(option)
    }
    element.value = value
    element.addEventListener('change', () => { select(element.value) })
    control.append(element)
    return control
  }

  /** One tab: a score dropdown over one plot, redrawn in place when another score is chosen. */
  function scoreTab (kind: ScoreGroup, metrics: string[], points: IonScorePoint[]) {
    return {
      label: GROUP_LABELS[kind],
      render: (panel: HTMLElement) => {
        if (!metrics.includes(chosen[kind])) chosen[kind] = metrics[0]
        const count = node('p', '', 'score-delta')
        const plot = node('div', '', 'score-plot score-plot-single')
        const draw = () => {
          const selected = points.filter(point => point.metric === chosen[kind])
          count.textContent = `${selected.length} datasets`
          plot.dataset.score = chosen[kind]
          plot.setAttribute('aria-label', `Ions scored versus ${chosen[kind]}`)
          const figure = ionScoreFigure(selected, software)
          void Plotly.react(plot, figure.traces, { ...figure.layout, height: 480 }, PLOT_CONFIG)
        }
        const controls = node('div', '', 'score-controls')
        controls.append(dropdown('Score', metrics.map(metric => ({ key: metric, label: metric })), chosen[kind], value => {
          chosen[kind] = value
          draw()
        }))
        panel.append(controls, count, plot)
        draw()
      }
    }
  }

  async function renderScores () {
    if (!visible()) return
    const cutoffs = completenessCutoffs(rows, summaries)
    if (!cutoffs.some(cutoff => cutoff.key === slice)) slice = cutoffs.find(cutoff => cutoff.key === '1')?.key ?? cutoffs[0]?.key ?? ''
    const points = ionScorePoints(rows, summaries, slice)
    const next = JSON.stringify([points, cutoffs, slice, software])
    if (signature === next) return
    clearPlots()
    signature = next
    host.append(
      node('h2', 'ProteoBench scores'),
      node('p', 'APB\'s own ProteoBench scores for each dataset on X; on Y, the ions that pass the selected completeness cutoff (nr_feature). Main scores are those ProteoBench\'s main plot offers; Other scores holds the rest. Hover for the dataset and values.', 'view-description')
    )
    const controls = node('div', '', 'score-controls')
    if (cutoffs.length) {
      controls.append(dropdown('Completeness cutoff', cutoffs, slice, value => {
        slice = value
        void renderScores()
      }))
    }
    const groups = scoreGroups(points.map(point => point.metric))
    const scored = new Set(points.map(point => point.input)).size
    const total = groups.reduce((sum, item) => sum + item.metrics.length, 0)
    host.append(controls, node('p', `${scored} of ${rows.length} datasets scored · ${total} scores`, 'score-counts'))
    const legend = node('div', '', 'score-legend')
    for (const [index, name] of software.entries()) {
      if (!points.some(point => point.software === name)) continue
      const entry = node('span', name)
      const swatch = node('i', '')
      swatch.style.backgroundColor = SCORE_COLORS[index % SCORE_COLORS.length]
      entry.prepend(swatch)
      legend.append(entry)
    }
    host.append(legend)
    if (!groups.length) {
      host.append(node('p', 'No APB ProteoBench scores with nr_feature are available for the selected datasets and cutoff.', 'empty-note'))
      return
    }
    const tabs = node('div', '', 'proteobench-score-tabs')
    host.append(tabs)
    const remembered = group
    await renderTabs(tabs, 'ProteoBench score groups', groups.map(item => scoreTab(item.kind, item.metrics, points)), panel => {
      const index = [...(panel.parentElement?.children ?? [])].indexOf(panel)
      if (groups[index]) group = groups[index].kind
      for (const plot of panel.querySelectorAll<HTMLElement>('.score-plot')) {
        if ((plot as PlotlyHTMLElement).data) void Plotly.Plots.resize(plot)
      }
    })
    const index = groups.findIndex(item => item.kind === remembered)
    if (index > 0) tabs.querySelectorAll<HTMLButtonElement>('[role="tab"]')[index]?.click()
  }

  async function activate () {
    if (!visible() || !directory) return
    await renderScores()
  }

  function resize () {
    if (!visible()) return
    for (const plot of plots()) {
      if ((plot as PlotlyHTMLElement).data && plot.offsetParent !== null) void Plotly.Plots.resize(plot)
    }
  }

  return {
    async render (context: string, selected: DatasetRow[], files: Map<string, RepresentationSummary | null>, names: string[]) {
      if (directory !== context) {
        directory = context
        slice = ''
        group = 'main'
        chosen.main = ''
        chosen.other = ''
        clearPlots()
      }
      rows = selected
      summaries = files
      software = names
      await activate()
    },
    activate,
    resize
  }
}
