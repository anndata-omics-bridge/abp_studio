import test from 'node:test'
import assert from 'node:assert/strict'
import { timingFacetFigure } from '../../src/apb_studio/corpus_viewer/web/render/timing-facets.js'
import { yAxesForScale } from '../../src/apb_studio/corpus_viewer/web/render/scale.js'
import { xAxisChoices } from '../../src/apb_studio/corpus_viewer/web/render/x-axis.js'

function point (phase, software, seconds) {
  return {
    phase, software_name: software, duration_seconds: seconds,
    input_size_mib: 100, ion_variables: 50000,
    input_file: `${software}.tsv`, module: 'dia_aif',
    step: 'convert', tool: 'apb2', status: 'succeeded', timing_path: '/run/timings.json'
  }
}

test('tool phases are faceted with one shared software legend and visible write panel', () => {
  const figure = timingFacetFigure([
    point('compile', 'DIA-NN', 1), point('compile', 'MaxQuant', 2),
    point('read', 'DIA-NN', 3), point('parse', 'MaxQuant', 4),
    point('write', 'DIA-NN', 5), point('write', 'MaxQuant', 6)
  ])

  assert.deepEqual(figure.phases, ['compile', 'read', 'parse', 'write'])
  assert.deepEqual(figure.layout.annotations.map(annotation => annotation.text), figure.phases)
  assert.deepEqual(figure.traces.filter(trace => trace.showlegend).map(trace => trace.name), [
    'DIA-NN', 'MaxQuant'
  ])
  assert.deepEqual(new Set(figure.traces.map(trace => trace.legendgroup)),
    new Set(['DIA-NN', 'MaxQuant']))
  assert.equal(figure.traces.find(trace => trace.yaxis === 'y4').y[0], 5)
  assert.equal(figure.traces.find(trace => trace.name === 'DIA-NN' && trace.yaxis === 'y').marker.color,
    figure.traces.find(trace => trace.name === 'DIA-NN' && trace.yaxis === 'y4').marker.color)
  assert.equal(figure.layout.xaxis.showticklabels, false)
  assert.equal(figure.layout.xaxis4.showticklabels, true)
  assert.equal(figure.layout.xaxis4.matches, 'x')
  assert.ok(figure.layout.yaxis.domain[0] > figure.layout.yaxis2.domain[1])
  assert.match(figure.traces[0].hovertemplate, /timing file=/)
})

test('timing facets can compare phases against persisted ion variable counts', () => {
  const points = [point('parse', 'DIA-NN', 8), point('write', 'DIA-NN', 12)]
  const choices = xAxisChoices([{ steps: [], outputs: [], timingViews: [{ points }] }])
  assert.deepEqual(choices.map(choice => choice.value), [
    'input_size_mib', 'ion_variables'
  ])
  const figure = timingFacetFigure(points, 'ion_variables')
  assert.deepEqual(figure.traces.map(trace => trace.x), [[50000], [50000]])
  assert.equal(figure.layout.xaxis2.title.text, 'Ion variables')
  assert.match(figure.traces[0].hovertemplate, /Ion variables=/)
  assert.equal(timingFacetFigure([{ ...points[0], ion_variables: null }], 'ion_variables').traces.length, 0)
  assert.deepEqual(xAxisChoices([{ steps: [{ ...points[0], ion_variables: null }] }]).map(choice => choice.value), ['input_size_mib'])
})

test('linear and log controls update every facet axis without invalid log-to-zero range', () => {
  const { layout } = timingFacetFigure([point('read', 'DIA-NN', 1), point('write', 'DIA-NN', 2)])
  const linear = yAxesForScale(layout, 'linear')
  const logarithmic = yAxesForScale(layout, 'log')

  assert.deepEqual(Object.keys(linear), ['yaxis', 'yaxis2'])
  assert.equal(linear.yaxis.type, 'linear')
  assert.equal(linear.yaxis2.rangemode, 'tozero')
  assert.equal(logarithmic.yaxis.type, 'log')
  assert.equal(logarithmic.yaxis2.type, 'log')
  assert.equal(logarithmic.yaxis2.rangemode, undefined)
  assert.equal(logarithmic.yaxis2.title.text, 'Seconds')
})
