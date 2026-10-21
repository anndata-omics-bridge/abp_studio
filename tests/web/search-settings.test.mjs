import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  parameterRows, rampColour, searchParametersRecord, searchSettingsRows, validatedSearchSettings
} from '../../viewer/src/corpus/search-settings.ts'

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

test('each recorded parameter reads as text, in apb2 order', () => {
  const rows = parameterRows({
    software_version: '1.0',
    acquisition_method: 'unknown',
    ident_fdr_psm: 0.01,
    enable_match_between_runs: false,
    precursor_mass_tolerance: { mode: 'absolute', value: 10, unit: 'ppm', label: null },
    fragment_mass_tolerance: { mode: 'automatic', value: null, unit: null },
    fixed_mods: [],
    variable_mods: [
      { name: 'Oxidation', target: 'M', position: 'Anywhere' },
      { name: 'Acetyl', target: null, position: 'Protein N-term' }
    ],
    min_precursor_mz: null
  })

  assert.deepEqual(rows, [
    ['Software version', '1.0'],
    ['Acquisition method', 'unknown'],
    ['Ident FDR PSM', '0.01'],
    ['Enable match between runs', 'no'],
    ['Precursor mass tolerance', '10 ppm'],
    ['Fragment mass tolerance', 'automatic'],
    ['Fixed mods', 'None listed'],
    ['Variable mods', 'Oxidation (M); Acetyl (Protein N-term)'],
    ['Min precursor m/z', 'Not recorded']
  ])
})

test('the record lives in the root part; a parameter-free result has none', () => {
  const record = { file_name: 'params.json', sha256: '0'.repeat(64), parameters: {} }
  const result = { root: { apb: { parse: { provenance: { search_parameters: record } } } }, levels: [] }

  assert.equal(searchParametersRecord(result), record)
  assert.equal(searchParametersRecord({ root: { apb: { parse: { provenance: {} } } }, levels: [] }), null)
  assert.equal(searchParametersRecord({ levels: [] }), null)
})
