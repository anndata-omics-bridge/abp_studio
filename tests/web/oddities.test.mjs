import assert from 'node:assert/strict'
import { test } from 'node:test'
import { oddityCountLabel, oddityState, validatedOddities, withOddities } from '../../viewer/src/corpus/oddities.ts'
import { emptyDatasetFilters, filterDatasets } from '../../viewer/src/corpus/filters.ts'

const clean = {
  input_file: 'clean.tsv', available: true, findings: [],
  coverage: [{ level: 'ion', numeric: 'recorded', fasta: 'not_checked', annotation_conventions: [] }]
}
const old = { ...clean, input_file: 'old.tsv', coverage: [{ ...clean.coverage[0], numeric: 'not_recorded' }] }
const attention = { ...clean, input_file: 'attention.tsv', findings: [{ kind: 'unmatched_peptides' }] }
const failed = { ...clean, input_file: 'failed.tsv', available: false, coverage: [] }
const summary = { format: 'apb-studio-oddities', format_version: 1, run_id: 'routine', datasets: [clean, old, attention, failed], software: [] }

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
  assert.throws(() => validatedOddities({ ...summary, format_version: 2 }, 'routine'), /Unsupported/)
})
