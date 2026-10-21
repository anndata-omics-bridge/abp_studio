import assert from 'node:assert/strict'
import { test } from 'node:test'
import { rampColour, searchSettingsRows, validatedSearchSettings } from '../../viewer/src/corpus/search-settings.ts'

const settings = [{ name: 'enzyme', label: 'Enzyme' }, { name: 'fixed_mods', label: 'Fixed mods' }]
const summary = {
  format: 'apb-studio-search-settings',
  format_version: 1,
  run_id: 'routine',
  settings,
  datasets: [],
  software: [
    { software_name: 'Free', dataset_count: 2, recorded_count: 0, recovered: { enzyme: 0, fixed_mods: 0 } },
    { software_name: 'Synthetic', dataset_count: 4, recorded_count: 3, recovered: { enzyme: 3, fixed_mods: 1 } }
  ]
}

test('rows count only recorded datasets and print values below 100 percent', () => {
  const rows = searchSettingsRows(summary)

  assert.deepEqual(rows.map(row => row.label), ['Synthetic (3)'])
  assert.deepEqual(rows[0].cells.map(cell => cell.text), ['', '33'])
  assert.deepEqual(rows[0].cells.map(cell => cell.inverse), [true, false])
})

test('the ramp runs from the article figure light end to its dark end', () => {
  assert.equal(rampColour(0), 'rgb(240, 243, 246)')
  assert.equal(rampColour(100), 'rgb(44, 71, 94)')
  assert.equal(rampColour(150), rampColour(100))
})

test('summary validation refuses another run or an unsupported version', () => {
  assert.equal(validatedSearchSettings(summary, 'routine'), summary)
  assert.throws(() => validatedSearchSettings(summary, 'other'), /mismatched/)
  assert.throws(() => validatedSearchSettings({ ...summary, format_version: 2 }, 'routine'), /Unsupported/)
})
