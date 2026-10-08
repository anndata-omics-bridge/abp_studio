import assert from 'node:assert/strict'
import { test } from 'node:test'
import { oddityCountLabel, oddityState, validatedOddities, withOddities } from '../../viewer/src/corpus/oddities.ts'
import { emptyDatasetFilters, filterDatasets } from '../../viewer/src/corpus/filters.ts'

const metric = (status, value = 0) => ({
  scope: 'ion', record: 'parse', name: `m_${status}`, label: status, value, unit: 'cells', status, layer: ''
})
const clean = { input_file: 'clean.tsv', available: true, metrics: [metric('ok')] }
const old = { ...clean, input_file: 'old.tsv', metrics: [metric('ok'), metric('not_checked', null)] }
const attention = { ...clean, input_file: 'attention.tsv', metrics: [metric('ok'), metric('attention', 3)] }
const failed = { ...clean, input_file: 'failed.tsv', available: false, metrics: [] }
const summary = { format: 'apb-studio-oddities', format_version: 2, run_id: 'routine', datasets: [clean, old, attention, failed], software: [] }

test('recorded zero, partial coverage, unavailable and missing summaries remain distinct', () => {
  assert.equal(oddityState(clean), 'No recorded findings')
  assert.equal(oddityState(old), 'Partial coverage')
  assert.equal(oddityState(attention), 'Needs attention')
  assert.equal(oddityState(failed), 'Unavailable')
  assert.equal(oddityState(null), 'Not summarized')
  const rows = withOddities(['clean', 'old', 'attention', 'failed', 'missing'].map(name => ({ input_file: `${name}.tsv` })), summary)
  assert.deepEqual(rows.map(oddityCountLabel), ['0', '0 · partial', '1', 'Unavailable', 'Not summarized'])
  assert.deepEqual(filterDatasets(rows, { ...emptyDatasetFilters(), oddity_state: ['Needs attention'] }), [rows[2]])
  assert.equal(withOddities(rows, null)[2].oddity_count, null, 'cleared summaries must not keep old counts')
})

test('summary validation refuses another run or an unsupported version', () => {
  assert.equal(validatedOddities(summary, 'routine'), summary)
  assert.throws(() => validatedOddities(summary, 'other'), /mismatched/)
  assert.throws(() => validatedOddities({ ...summary, format_version: 1 }, 'routine'), /Unsupported/)
})
