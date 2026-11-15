import test from 'node:test'
import assert from 'node:assert/strict'
import { compareScores, completenessCutoffs, ionScorePoints, orderedScores, referenceScores, representationScores, scoreGroups } from '../../viewer/src/corpus/scores.ts'
import { ionScoreFigure, scoreFacetFigure } from '../../viewer/src/corpus/render/score-facets.ts'
import { runInNewContext } from 'node:vm'
import { isolatedSource } from './source.mjs'

function representation (proteobench) {
  return { levels: [{ name: 'peptidoform_ion', apb: { proteobench: { result: proteobench } } }] }
}

function row (input = 'submissions/repo/a/input.csv', status = 'succeeded') {
  return {
    input_file: input, software_name: 'DIA-NN', module: 'dia_astral', status,
    record: { steps: [
      { status: 'succeeded', outputs: [{ role: 'representation', path: 'converted.json', size_bytes: 100 }] },
      { status, outputs: [{ role: 'representation', path: `${input}.apb.json`, size_bytes: status === 'succeeded' ? 100 : null }] }
    ] }
  }
}

function scores (results, quantity = 'Intensity') {
  return representationScores(representation({ scoring: { [quantity]: { scores: { results } } } }))
}

test('pairing uses exact input, metric and completeness cutoff without coercing missing values', () => {
  const a = row()
  const b = row('submissions/other/a/input.csv')
  const apb = new Map([[`${a.input_file}.apb.json`, { scores: scores({
    1: { error: 0.2, nr_feature: 10, CV: null, flag: true, invalid: Infinity, extra: 9 },
    2: { error: 0.3 }, 3: { error: 0.4 }
  }) }]])
  const references = new Map([[a.input_file, referenceScores({ id: 'original', results: {
    1: { error: 0.1, nr_feature: 0, CV: 0.2, flag: 1, invalid: 0 }, 2: { error: 0.25 }, 4: { error: 0.5 }
  } })]])
  const comparison = compareScores([a, b], apb, references)
  assert.equal(comparison.matchedInputs, 1)
  assert.deepEqual(comparison.points.map(point => [point.metric, point.slice, point.reference, point.apb]), [
    ['error', '1', 0.1, 0.2], ['nr_feature', '1', 0, 10], ['error', '2', 0.25, 0.3]
  ])
  assert.equal(comparison.points[0].delta, 0.1)
  assert.equal(comparison.points[0].submission, 'original')
  assert.equal(comparison.unmatched[0].input, b.input_file)
  assert.equal(compareScores([a], apb, references, 'q_value', '2').points.length, 1)
  assert.equal(referenceScores({ results: { 1: { missing: null, nonfinite: NaN } } }), null)
})

test('ProteoBench plasma names pair with apb-proteobench\'s generic names; its duplicates pair with nothing', () => {
  const a = row()
  const apb = new Map([[`${a.input_file}.apb.json`, { scores: scores({ 1: {
    median_abs_epsilon_changed_global: 0.61, nr_quantified_changed: 30,
    dynamic_range_HUMAN_A: 3.1, dynamic_range_HUMAN: 2.1, median_abs_epsilon_HUMAN: 0.31
  } }) }]])
  const references = new Map([[a.input_file, referenceScores({ results: { 1: {
    median_abs_log2_fc_error_spike_ins_global: 0.6, median_abs_log2_fc_error_spike_ins: 0.6,
    nr_quantified_spike_ins: 29, dynamic_range_human_plasma_A: 3.2, dynamic_range_human_plasma_mean: 2.0,
    median_abs_epsilon_human_plasma: 0.3, median_abs_epsilon_HUMAN: 0.3
  } } })]])
  const comparison = compareScores([a], apb, references)
  assert.deepEqual(comparison.points.map(point => [point.metric, point.reference, point.apb]), [
    ['median_abs_epsilon_changed_global', 0.6, 0.61], ['nr_quantified_changed', 29, 30],
    ['dynamic_range_HUMAN_A', 3.2, 3.1], ['dynamic_range_HUMAN', 2.0, 2.1], ['median_abs_epsilon_HUMAN', 0.3, 0.31]
  ])
})

test('failed scoring never reuses declared outputs or scores from converted intermediates', () => {
  const failed = row('failed', 'failed')
  const reference = referenceScores({ results: { 1: { error: 0.1 } } })
  const cache = new Map([['failed.apb.json', { scores: scores({ 1: { error: 0.2 } }) }]])
  const result = compareScores([failed], cache, new Map([['failed', reference]]))
  assert.equal(result.points.length, 0)
  assert.match(result.unmatched[0].reason, /No successful APB scores \(failed\)/)
})

test('entrapment selects one explicit confidence kind and compares scalar scores only', () => {
  const a = row()
  const quantities = representationScores(representation({ entrapment: {
    q_value: { combined_FDP: 0.01, nr_id_features: 5, category_combined: 'valid', fdp_curve: { '0.001': { combined_FDP: 0.02 } } },
    library_q_value: { combined_FDP: 0.03, nr_id_features: 6 }
  } }))
  const references = new Map([[a.input_file, referenceScores({ results: {
    combined_FDP: 0.015, nr_id_features: 7, category_combined: 'valid', fdp_curve: { '0.001': { combined_FDP: 0.04 } }
  } })]])
  const cache = new Map([[`${a.input_file}.apb.json`, { scores: quantities }]])
  const normal = compareScores([a], cache, references)
  assert.deepEqual(normal.points.map(point => point.quantity), ['q_value', 'q_value'])
  assert.equal(normal.points[0].reference, 0.015)
  assert.equal(normal.points[0].apb, 0.01)
  const library = compareScores([a], cache, references, 'library_q_value')
  assert.equal(library.points[0].apb, 0.03)
  assert.equal(library.points.length, 2)
})

test('each facet has an identity line covering both series, common X/Y limits and delta hover', () => {
  const points = [{ reference: -2, apb: 3, software: 'DIA-NN', delta: 5, quantity: 'Intensity', metric: 'error', sliceLabel: 'cutoff 1' }]
  const figure = scoreFacetFigure(points, ['MaxQuant', 'DIA-NN'])
  const [line, scatter] = figure.traces
  assert.equal(line.mode, 'lines')
  assert.deepEqual(line.x, line.y)
  assert.ok(line.x[0] < -2 && line.x[1] > 3)
  assert.deepEqual(figure.layout.xaxis.range, figure.layout.yaxis.range)
  assert.deepEqual(scatter.x, [-2])
  assert.deepEqual(scatter.y, [3])
  assert.match(scatter.hovertemplate, /APB − ProteoBench/)
  assert.equal(scatter.customdata[0][3], 5)
  const unchanged = scoreFacetFigure([{ ...points[0], apb: -2 }], ['DIA-NN'])
  assert.ok(unchanged.layout.xaxis.range[1] > unchanged.layout.xaxis.range[0])
})

test('MA facets plot signed differences against arithmetic means and keep original values on hover', () => {
  const points = [
    { reference: 10, apb: 12, delta: 2, software: 'DIA-NN' },
    { reference: 8, apb: 6, delta: -2, software: 'DIA-NN' },
    { reference: -4, apb: -4, delta: 0, software: 'DIA-NN' }
  ]
  const figure = scoreFacetFigure(points, ['DIA-NN'], 'ma')
  const [line, scatter] = figure.traces
  assert.deepEqual(line.y, [0, 0])
  assert.deepEqual(line.x, figure.layout.xaxis.range)
  assert.deepEqual(scatter.x, [11, 7, -4])
  assert.deepEqual(scatter.y, [2, -2, 0])
  assert.equal(figure.layout.yaxis.range[0], -figure.layout.yaxis.range[1])
  assert.ok(figure.layout.yaxis.range[1] > 2)
  assert.equal(figure.layout.xaxis.title.text, 'Mean score')
  assert.equal(figure.layout.yaxis.title.text, 'APB − ProteoBench')
  assert.deepEqual(scatter.customdata[0].slice(6), [10, 12, 11])
  assert.match(scatter.hovertemplate, /ProteoBench=%\{customdata\[6\]/)
  assert.match(scatter.hovertemplate, /APB=%\{customdata\[7\]/)
  const unchanged = scoreFacetFigure([points[2]], ['DIA-NN'], 'ma')
  assert.ok(unchanged.layout.xaxis.range[0] < -4 && unchanged.layout.xaxis.range[1] > -4)
  assert.ok(unchanged.layout.yaxis.range[0] < 0 && unchanged.layout.yaxis.range[1] > 0)
})

test('score panel reads references lazily, defaults to cutoff 1 after an empty load and caches per run', async () => {
  class Element extends EventTarget {
    children = []
    hidden = false
    style = {}
    dataset = {}
    className = ''
    textContent = ''
    attributes = new Map()
    constructor (tag = 'section') { super(); this.tag = tag }
    append (...children) { this.children.push(...children) }
    prepend (...children) { this.children.unshift(...children) }
    replaceChildren (...children) { this.children = children }
    closest () { return null }
    focus () { context.document.activeElement = this }
    querySelector (selector) { return this.querySelectorAll(selector)[0] ?? null }
    setAttribute (name, value) { this.attributes.set(name, value) }
    removeAttribute (name) { this.attributes.delete(name) }
    querySelectorAll (selector) {
      return this.children.flatMap(child => [
        ...(selector.startsWith('.') ? child.className === selector.slice(1) : child.tag === selector) ? [child] : [],
        ...child.querySelectorAll(selector)
      ])
    }
  }
  const reads = []
  const host = new Element()
  host.hidden = true
  const context = {
    HTMLElement: Element, document: { createElement: tag => new Element(tag) },
    IntersectionObserver: class { observe () {} unobserve () {} disconnect () {} },
    Plotly: { purge () {}, react () {}, Plots: { resize () {} } }, PLOT_CONFIG: {},
    compareScores, referenceScores, scoreQuantities: (_rows, files) => [...files.values()].flatMap(file => file?.scores ?? []),
    SCORE_COLORS: ['blue'], scoreFacetFigure,
    node (tag, text, className = '') { const element = new Element(tag); element.textContent = text; element.className = className; return element },
    artifactStorePath: (_directory, _output, path) => path, fileUrl: path => path,
    sourceUrl: path => `fixtures/${path}`,
    host,
    readReferences: async directory => {
      reads.push(directory)
      return new Map([[a.input_file, { path: 'metadata/repo/hash.json', document: { results: { 1: { error: 0.1 }, 2: { error: 0.15 } } } }]])
    }
  }
  const a = row()
  const panel = runInNewContext(`${isolatedSource('viewer/src/corpus/panels/scores.ts')}\ncreateScoresPanel(host, readReferences)`, context)
  const cache = new Map([[`${a.input_file}.apb.json`, { scores: scores({ 1: { error: 0.2 }, 2: { error: 0.3 } }) }]])
  await panel.render('first', [a], cache, ['DIA-NN'])
  assert.equal(reads.length, 0, 'hidden comparisons must not read fixture metadata')
  host.hidden = false
  await panel.render('first', [], new Map(), [])
  await panel.render('first', [a], cache, ['DIA-NN'])
  const cutoff = host.querySelectorAll('select')[0]
  assert.equal(cutoff.value, '1', 'the loading projection must not choose all cutoffs')
  assert.match(host.querySelectorAll('.score-counts')[0].textContent, /1 score pairs/)
  const toggle = host.querySelectorAll('input')[0]
  assert.equal(toggle.checked, false)
  toggle.focus()
  toggle.checked = true
  toggle.dispatchEvent(new Event('change'))
  assert.equal(context.document.activeElement, host.querySelectorAll('input')[0], 'keyboard focus follows the replacement checkbox')
  assert.match(host.querySelectorAll('.view-description')[0].textContent, /Mean of APB and ProteoBench/)
  assert.match(host.querySelectorAll('.score-plot')[0].attributes.get('aria-label'), /versus mean score/)
  assert.match(host.querySelectorAll('.score-counts')[0].textContent, /1 score pairs/)
  await panel.render('first', [a], cache, ['DIA-NN'])
  assert.equal(host.querySelectorAll('input')[0].checked, true, 'polling preserves MA mode')
  assert.equal(reads.length, 1, 'switching plots must not reload score evidence')
  const scatterToggle = host.querySelectorAll('input')[0]
  scatterToggle.checked = false
  scatterToggle.dispatchEvent(new Event('change'))
  assert.match(host.querySelectorAll('.view-description')[0].textContent, /Dashed line: y = x/)
  assert.match(host.querySelectorAll('.score-plot')[0].attributes.get('aria-label'), /APB versus ProteoBench/)
  const allCutoffs = host.querySelectorAll('select')[0]
  allCutoffs.value = 'all'
  allCutoffs.dispatchEvent(new Event('change'))
  assert.match(host.querySelectorAll('.score-counts')[0].textContent, /2 score pairs/)
  await panel.render('first', [a], cache, ['DIA-NN'])
  assert.equal(host.querySelectorAll('select')[0].value, 'all', 'polling preserves the chosen cutoff')
  assert.equal(reads.length, 1, 'polling reuses reference reads')
  await panel.render('second', [a], cache, ['DIA-NN'])
  assert.equal(reads.length, 2, 'a new run reloads its own references')
  assert.equal(host.querySelectorAll('select')[0].value, '1')
})

test('ion scores plot each APB score of one cutoff against that cutoff\'s nr_feature, never a reference', () => {
  const a = row()
  const b = row('submissions/other/a/input.csv')
  const c = row('submissions/third/a/input.csv')
  const entrapment = representationScores(representation({ entrapment: { q_value: { combined_FDP: 0.01 } } }))
  const cache = new Map([
    [`${a.input_file}.apb.json`, { scores: [...scores({ 1: { CV_median: 0.2, nr_feature: 900 }, 2: { CV_median: 0.15, nr_feature: 700 } }), ...entrapment] }],
    [`${b.input_file}.apb.json`, { scores: scores({ 1: { CV_median: 0.3 } }) }],
    [`${c.input_file}.apb.json`, { scores: scores({ 1: { CV_median: 0.25, roc_auc: 0.9, nr_feature: 1200 } }) }]
  ])
  const points = ionScorePoints([a, b, c], cache, '1')
  assert.deepEqual(points.map(point => [point.input, point.metric, point.features, point.score]), [
    [a.input_file, 'CV_median', 900, 0.2],
    [c.input_file, 'CV_median', 1200, 0.25],
    [c.input_file, 'roc_auc', 1200, 0.9]
  ], 'a cutoff without nr_feature, nr_feature itself and entrapment scores are not plotted')
  assert.deepEqual(ionScorePoints([a], cache, '2').map(point => point.features), [700])
  assert.deepEqual(completenessCutoffs([a, b, c], cache).map(cutoff => cutoff.key), ['1', '2'])

  const figure = ionScoreFigure(points.filter(point => point.metric === 'CV_median'), ['DIA-NN'])
  assert.equal(figure.traces.length, 1, 'no identity or reference line')
  assert.deepEqual(Array.from(figure.traces[0].x), [0.2, 0.25], 'the score is on X')
  assert.deepEqual(Array.from(figure.traces[0].y), [900, 1200], 'the ions scored are on Y')
  assert.equal(figure.layout.yaxis.title.text, 'Ions scored (nr_feature)')
})

test('ProteoBench main-plot scores lead the ion-score facets in its menu order; the rest follow alphabetically', () => {
  assert.deepEqual(orderedScores([
    'CV_median', 'roc_auc', 'mean_abs_epsilon_global', 'nr_quantified_HUMAN',
    'median_abs_epsilon_eq_species', 'median_abs_epsilon_global', 'CV_median'
  ]), [
    'median_abs_epsilon_global', 'mean_abs_epsilon_global', 'median_abs_epsilon_eq_species', 'roc_auc',
    'CV_median', 'nr_quantified_HUMAN'
  ])
})

test('ion scores split into ProteoBench main-plot scores and the rest; an empty group is left out', () => {
  assert.deepEqual(scoreGroups(['CV_median', 'roc_auc', 'median_abs_epsilon_global', 'nr_quantified_HUMAN']), [
    { kind: 'main', metrics: ['median_abs_epsilon_global', 'roc_auc'] },
    { kind: 'other', metrics: ['CV_median', 'nr_quantified_HUMAN'] }
  ])
  assert.deepEqual(scoreGroups(['CV_median']), [{ kind: 'other', metrics: ['CV_median'] }])
  assert.deepEqual(scoreGroups([]), [])
})
