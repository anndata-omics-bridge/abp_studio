import assert from 'node:assert/strict'
import { test } from 'node:test'
import { workflowFlow } from '../../viewer/src/corpus/workflow-flow.ts'

test('exact paths connect non-adjacent consumers without confusing identical basenames or mutating reports', () => {
  const steps = [
    { name: 'convert', status: 'succeeded', outputs: [{ path: '/attempt/a/converted.h5mu', role: 'converted', size_bytes: 0 }] },
    { name: 'inspect', status: 'succeeded', inputs: [{ path: '/attempt/b/converted.h5mu', role: 'external' }], outputs: [] },
    { name: 'aggregate', status: 'failed', inputs: [{ path: '/attempt/a/converted.h5mu', role: 'converted' }], outputs: [{ path: '/attempt/a/result.h5mu', role: 'result', size_bytes: null }] }
  ]
  const before = JSON.stringify(steps)
  const flow = workflowFlow(steps)
  assert.equal(flow[1].inputs[0].producer, null)
  assert.equal(flow[2].inputs[0].producer, 0)
  assert.equal(flow[2].inputs[0].size, 0)
  assert.deepEqual(flow[0].outputs[0].consumers, [2])
  assert.equal(flow[2].outputs[0].size, null)
  assert.equal(flow[2].report.status, 'failed')
  assert.equal(JSON.stringify(steps), before)
})

test('a later producer of the same path owns subsequent handoffs and repeated inputs add one consumer', () => {
  const input = { path: '/result.h5mu', role: 'converted' }
  const flow = workflowFlow([
    { name: 'first', status: 'succeeded', outputs: [input] },
    { name: 'rewrite', status: 'succeeded', inputs: [input], outputs: [input] },
    { name: 'last', status: 'skipped', inputs: [input, input] }
  ])
  assert.deepEqual(flow[0].outputs[0].consumers, [1])
  assert.deepEqual(flow[1].outputs[0].consumers, [2])
  assert.equal(flow[2].inputs[0].producer, 1)
  assert.deepEqual(workflowFlow([]), [])
})
