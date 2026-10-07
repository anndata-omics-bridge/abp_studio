import { Plotly } from '../../shared/plotly.js'
import type { PlotlyHTMLElement } from '../../shared/plotly.js'
import type { DatasetRow } from '../types.js'
import type { ReferenceScores, RepresentationSummary, ScoreComparison } from '../scores.js'
import { compareScores, referenceScores, scoreQuantities } from '../scores.js'
import { node } from '../render/dom.js'
import { PLOT_CONFIG } from '../render/plotly.js'
import { SCORE_COLORS, scoreFacetFigure } from '../render/score-facets.js'
import { artifactStorePath } from '../representation.js'
import { fileUrl, proteobenchReferenceUrl } from '../lib/fetch.js'

type ReadReference = (context: string, input: string) => Promise<unknown>

/** Lazy comparison panel: no extra fixture reads until its tab is opened. */
export function createScoresPanel (host: HTMLElement, readReference: ReadReference) {
  let directory = ''
  let rows: DatasetRow[] = []
  let summaries = new Map<string, RepresentationSummary | null>()
  let software: string[] = []
  const references = new Map<string, ReferenceScores | null>()
  const errors = new Map<string, string>()
  let loading: Promise<void> | null = null
  let confidence = 'q_value'
  let slice = ''
  let signature = ''
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting || !(entry.target instanceof HTMLElement)) continue
      observer.unobserve(entry.target)
      drawFacet(entry.target)
    }
  })
  const figures = new WeakMap<HTMLElement, ReturnType<typeof scoreFacetFigure>>()

  function visible () { return !host.hidden && !host.closest<HTMLElement>('#insights')?.hidden }

  function drawFacet (plot: HTMLElement) {
    const figure = figures.get(plot)
    if (figure && plot.isConnected && visible()) {
      void Plotly.react(plot, figure.traces, figure.layout, PLOT_CONFIG)
    }
  }

  function clearPlots () {
    observer.disconnect()
    for (const plot of host.querySelectorAll<HTMLElement>('.score-plot')) {
      if ((plot as PlotlyHTMLElement).data) Plotly.purge(plot)
    }
    host.replaceChildren()
    signature = ''
  }

  function selectControl (label: string, choices: { key: string; label: string }[], value: string, select: (value: string) => void) {
    const control = node('label', label, 'score-control')
    const dropdown = document.createElement('select')
    dropdown.setAttribute('aria-label', label)
    for (const choice of choices) {
      const option = document.createElement('option')
      option.value = choice.key
      option.textContent = choice.label
      dropdown.append(option)
    }
    dropdown.value = value
    dropdown.addEventListener('change', () => { select(dropdown.value); renderComparison() })
    control.append(dropdown)
    return control
  }

  function sourceList (comparison: ScoreComparison) {
    const details = document.createElement('details')
    details.className = 'score-sources'
    details.append(node('summary', `Score sources and unmatched datasets (${comparison.unmatched.length})`))
    const list = document.createElement('ul')
    for (const row of rows) {
      const item = document.createElement('li')
      const reason = comparison.unmatched.find(entry => entry.input === row.input_file)?.reason
      item.append(node('strong', `${row.software_name} · ${row.module}`), node('span', row.input_file))
      const original = document.createElement('a')
      original.href = proteobenchReferenceUrl(directory, row.input_file)
      original.target = '_blank'
      original.rel = 'noopener'
      original.textContent = 'Downloaded ProteoBench JSON'
      item.append(original)
      const paired = comparison.points.find(point => point.input === row.input_file)
      if (paired) {
        const apb = document.createElement('a')
        apb.href = fileUrl(artifactStorePath(directory, row.output_dir, paired.artifact))
        apb.target = '_blank'
        apb.rel = 'noopener'
        apb.textContent = 'APB score metadata'
        item.append(apb)
      }
      if (reason) item.append(node('span', errors.get(row.input_file) ?? reason, 'empty-note'))
      list.append(item)
    }
    details.append(list)
    return details
  }

  function renderComparison () {
    if (!visible()) return
    const quantities = scoreQuantities(rows, summaries)
    const confidenceKinds = [...new Set(quantities.filter(quantity => quantity.kind === 'entrapment').map(quantity => quantity.quantity))].sort()
    if (confidenceKinds.length && !confidenceKinds.includes(confidence)) confidence = confidenceKinds[0]
    const slices = [...new Map(quantities.flatMap(quantity => quantity.slices.map(item => [item.key, { key: item.key, label: item.label }] as const))).values()]
      .sort((first, second) => first.key.localeCompare(second.key, undefined, { numeric: true }))
    if (slices.length && (!slice || (slice !== 'all' && !slices.some(item => item.key === slice)))) {
      slice = slices.find(item => item.key === '1' || item.key === 'summary')?.key ?? slices[0]?.key ?? 'all'
    }
    const comparison = compareScores(rows, summaries, references, confidence, slice || 'all')
    const next = JSON.stringify([comparison, slices, confidenceKinds, confidence, slice, software, [...errors]])
    if (signature === next) return
    clearPlots()
    signature = next
    host.append(node('h2', 'ProteoBench score comparison'))
    host.append(node('p', 'Downloaded ProteoBench scores on X; APB scores on Y. Dashed line: y = x. Hover for values and Δ (APB − ProteoBench). Only matching score names and completeness cutoffs with finite values are plotted.', 'view-description'))
    const controls = node('div', '', 'score-controls')
    if (slices.some(item => item.key !== 'summary')) controls.append(selectControl('Completeness cutoff', [
      { key: 'all', label: 'All matching cutoffs' }, ...slices
    ], slice, value => { slice = value }))
    if (confidenceKinds.length) {
      controls.append(selectControl('APB confidence kind', confidenceKinds.map(key => ({ key, label: key })), confidence, value => { confidence = value }))
      host.append(node('p', 'The downloaded entrapment JSON has one reported-FDR score set. Compare it with the selected APB confidence kind; FDP curves are not mixed into these summary scores.', 'empty-note'))
    }
    host.append(controls, node('p', `${comparison.matchedInputs} of ${rows.length} datasets paired · ${comparison.points.length} score pairs · ${comparison.unmatched.length} unmatched`, 'score-counts'))
    const legend = node('div', '', 'score-legend')
    for (const [index, name] of software.entries()) {
      if (!comparison.points.some(point => point.software === name)) continue
      const entry = node('span', name)
      const swatch = node('i', '')
      swatch.style.backgroundColor = SCORE_COLORS[index % SCORE_COLORS.length]
      entry.prepend(swatch)
      legend.append(entry)
    }
    host.append(legend)
    const grid = node('div', '', 'score-facet-grid')
    const metrics = [...new Set(comparison.points.map(point => point.metric))].sort()
    for (const metric of metrics) {
      const points = comparison.points.filter(point => point.metric === metric)
      const card = node('section', '', 'score-facet')
      card.dataset.score = metric
      const title = node('h3', metric)
      const maxDelta = Math.max(...points.map(point => Math.abs(point.delta)))
      card.append(title, node('p', `${points.length} pairs · max |Δ| ${maxDelta.toPrecision(4)}`, 'score-delta'))
      const plot = node('div', '', 'score-plot')
      plot.setAttribute('aria-label', `${metric}: APB versus ProteoBench`)
      figures.set(plot, scoreFacetFigure(points, software))
      card.append(plot)
      grid.append(card)
      observer.observe(plot)
    }
    if (!metrics.length) grid.append(node('p', 'No comparable scores are available for the selected datasets and cutoff. Expand score sources below for the missing evidence.', 'empty-note'))
    host.append(grid, sourceList(comparison))
  }

  async function activate () {
    if (!visible() || !directory) return
    if (!loading) {
      const context = directory
      const pending = rows.filter(row => !references.has(row.input_file))
      if (pending.length) host.setAttribute('aria-busy', 'true')
      loading = (async () => {
        for (let start = 0; start < pending.length; start += 12) {
          if (context !== directory) return
          await Promise.all(pending.slice(start, start + 12).map(async row => {
            try {
              const document = await readReference(context, row.input_file)
              if (context === directory) references.set(row.input_file, referenceScores(document))
            } catch (error) {
              if (context === directory) {
                references.set(row.input_file, null)
                errors.set(row.input_file, String(error))
              }
            }
          }))
        }
      })().finally(() => { loading = null; host.removeAttribute('aria-busy') })
    }
    await loading
    renderComparison()
    for (const plot of host.querySelectorAll<HTMLElement>('.score-plot')) {
      if (!(plot as PlotlyHTMLElement).data) observer.observe(plot)
    }
  }

  function resize () {
    if (!visible()) return
    for (const plot of host.querySelectorAll<HTMLElement>('.score-plot')) {
      if ((plot as PlotlyHTMLElement).data) void Plotly.Plots.resize(plot)
    }
  }

  return {
    async render (context: string, selected: DatasetRow[], files: Map<string, RepresentationSummary | null>, names: string[]) {
      if (directory !== context) {
        directory = context
        references.clear()
        errors.clear()
        slice = ''
        confidence = 'q_value'
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
