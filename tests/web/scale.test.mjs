import assert from 'node:assert/strict'
import { test } from 'node:test'
import { tracesForScale } from '../../viewer/src/corpus/render/scale.ts'

test('linear box traces preserve their complete five-number summaries', () => {
  const traces = [{
    type: 'box', x: ['sample'], q1: [0.1], median: [0.2], q3: [0.3],
    lowerfence: [0], upperfence: [0.5]
  }]

  assert.equal(tracesForScale(traces, 'linear'), traces)
})

test('log box traces hide invalid summaries and replace non-positive whiskers', () => {
  const traces = [{
    type: 'box',
    x: ['PEP with zeros', 'all zero'],
    q1: [0.00004, 0],
    median: [0.001, 0],
    q3: [0.01, 0],
    lowerfence: [0, 0],
    upperfence: [0.7, 0],
    mean: [0.009, 0],
    customdata: [['kept'], ['removed']],
    hovertemplate: 'minimum=%{lowerfence}'
  }]

  assert.deepEqual(tracesForScale(traces, 'log'), [{
    ...traces[0],
    x: ['PEP with zeros'],
    q1: [0.00004],
    median: [0.001],
    q3: [0.01],
    lowerfence: [0.00004],
    upperfence: [0.7],
    mean: [0.009],
    customdata: [['kept']],
    hovertemplate: 'visible lower bound=%{lowerfence}'
  }])
})
