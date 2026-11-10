import assert from 'node:assert/strict'
import { test } from 'node:test'

import { allColumns, allLayers, levelRows, ofLevel, orderedLevels } from '../../viewer/src/rules/projections/across.ts'
import { evidenceLabel, levelPage, summaryRows, variantRows } from '../../viewer/src/rules/projections/level.ts'
import { ruleOption, ruleRows } from '../../viewer/src/rules/projections/rules.ts'
import { cellText, tableOf } from '../../viewer/src/rules/projections/tables.ts'

const ANY = ['DDA', 'DIA', 'unknown'].flatMap(acquisition_method =>
  [true, false, null].map(combine_charge_states => ({ acquisition_method, combine_charge_states })))
const of = method => ANY.filter(evidence => evidence.acquisition_method === method)

// A declaration as apb2 stores it, defaults filled in.
function declaration (primary) {
  return {
    software_name: 'TOOL',
    quantification_level: 'peptidoform_ion',
    axis: { obs_keys: ['Run'], var_keys: ['ProForma_ion'] },
    measurements: {
      primary_layer: primary,
      sample_layer: null,
      repeated_cells: { mode: 'error', by: null, best: null, sum: [] },
      layers: [
        { name: 'Ms1', source: 'Ms1.Area', type: 'number', roles: ['abundance'], missing_values: ['<=0'], missing_tokens: [], note: null },
        { name: 'Precursor', source: 'Precursor.Quantity', type: 'number', roles: ['abundance'], missing_values: ['<=0'], missing_tokens: [], note: null },
        { name: 'Q', source: 'Q.Value', type: 'number', roles: [], missing_values: [], missing_tokens: [], note: null }
      ]
    },
    forbidden_columns: [],
    requires_search_parameters: {},
    modification_map: { 'UniMod:35': 'UNIMOD:35' },
    columns: {
      obs: [{ name: 'Run', source: 'Run', type: 'string', roles: [], note: null }],
      var: [
        { name: 'Protein_Group', source: 'Protein.Group', type: 'string', roles: ['protein_assignment', 'fasta_accessions'], note: null },
        { name: 'ProForma_ion', inputs: ['Modified_Sequence', 'Charge'], how: 'proforma_ion', roles: [], note: null }
      ]
    }
  }
}

const RULES = [
  { rule: 'tool/v2/rules.json', software_name: 'TOOL', software_version_pattern: '^2\\.', schema_version: '0.10', file_version: '3', hierarchy: 'lfq', parameter_file: 'required', categories: ['DDA', 'DIA'], levels: ['protein', 'peptidoform_ion'], tables: [{ levels: ['protein', 'peptidoform_ion'], input: { shape: 'long', extensions: ['.parquet'], without_parameter_file: { required_columns: ['PG.TopN'] } }, preparation: null }] },
  { rule: 'other/rules.json', software_name: 'OTHER', software_version_pattern: '^.*$', schema_version: '0.10', file_version: '1', hierarchy: 'lfq', parameter_file: 'none', categories: ['DDA'], levels: ['peptidoform_ion'], tables: [{ levels: ['peptidoform_ion'], input: { shape: 'wide', extensions: ['.tsv'] }, preparation: 'join' }, { levels: [], input: { shape: 'long', extensions: ['.tsv'] }, preparation: null }] }
]

const LEVELS = [
  { rule: 'tool/v2/rules.json', level: 'protein', declarations: [{ selected_by: ANY, declaration: declaration('Ms1') }] },
  { rule: 'tool/v2/rules.json', level: 'peptidoform_ion', declarations: [{ selected_by: of('DDA'), declaration: declaration('Ms1') }, { selected_by: [...of('DIA'), ...of('unknown')], declaration: declaration('Precursor') }] },
  { rule: 'other/rules.json', level: 'peptidoform_ion', declarations: [{ selected_by: [{ acquisition_method: 'DDA', combine_charge_states: true }], declaration: declaration('Q') }] }
]

test('cells drop empty values and tables drop columns empty in every row', () => {
  assert.equal(cellText({ mode: 'error', by: null, best: null, sum: [] }), 'mode=error')
  assert.equal(cellText({ outer: { inner: 1 } }), 'outer={inner=1}')
  assert.deepEqual(tableOf([{ a: 1, b: null }, { c: [], a: 2 }], ['c', 'a']).columns, ['a'])
})

test('the Rules tab joins the values of a document\'s tables', () => {
  const [tool, other] = ruleRows(RULES).rows
  assert.equal(tool.detection, 'required_columns=PG.TopN')
  assert.equal(other.shape, 'wide | long')
  assert.equal(other.extensions, '.tsv')
  assert.equal(other.preparation, 'join')
})

test('evidence labels name an acquisition method alone when every charge setting selects it', () => {
  assert.equal(evidenceLabel(ANY), 'any search parameters')
  assert.equal(evidenceLabel([...of('DIA'), ...of('unknown')]), 'DIA, unknown')
  assert.equal(evidenceLabel([{ acquisition_method: 'DDA', combine_charge_states: true }, { acquisition_method: 'DDA', combine_charge_states: null }]), 'DDA with combine_charge_states true or null')
})

test('settings come one key deep, without the entries that have their own tables', () => {
  const rows = summaryRows(declaration('Ms1'))
  const settings = Object.fromEntries(rows.map(row => [row.setting, row.value]))
  assert.equal(settings['axis.var_keys'], 'ProForma_ion')
  assert.equal(settings['measurements.repeated_cells'], 'mode=error')
  assert.equal(settings['measurements.primary_layer'], 'Ms1')
  assert.ok(!('measurements.layers' in settings))
  assert.ok(!('columns' in settings) && !('modification_map' in settings) && !('requires_search_parameters' in settings))
})

test('a level with two declarations lists only where they differ', () => {
  const variants = variantRows(LEVELS[1].declarations)
  assert.deepEqual(variants.columns, ['setting', 'DDA', 'DIA, unknown'])
  assert.deepEqual(variants.rows, [{ setting: 'measurements.primary_layer', DDA: 'Ms1', 'DIA, unknown': 'Precursor' }])
})

test('entries of one name, one per version, keep their own rows and variant paths', () => {
  const tagged = newest => {
    const tagged = declaration('Ms1')
    tagged.columns.var.push(
      { name: 'Lead', source: 'Lead Proteins', version: '^1\\.', type: 'string', roles: [], note: null },
      { name: 'Lead', source: newest, version: '^2\\.', type: 'string', roles: [], note: null })
    return tagged
  }
  const variants = variantRows([
    { selected_by: of('DDA'), declaration: tagged('Leading proteins') },
    { selected_by: of('DIA'), declaration: tagged('Leading protein') }
  ])
  assert.deepEqual(variants.rows.map(row => row.setting), ['columns.var[Lead ^2\\.].source'])
  const page = levelPage({ rule: 'tool/v2/rules.json', level: 'protein', declarations: [{ selected_by: ANY, declaration: tagged('Leading proteins') }] })
  const [columns] = page.find(section => section.id === 'var').tables
  assert.deepEqual(columns.columns.map(column => column.field).slice(0, 3), ['name', 'source', 'version'])
  assert.deepEqual(columns.rows.filter(row => row.name === 'Lead').map(row => row.version), ['^1\\.', '^2\\.'])
})

test('a level page has one tab per table: settings, variants, layers with the primary marked, columns, map, stored JSON', () => {
  const page = levelPage(LEVELS[1])
  assert.deepEqual(page.map(section => [section.id, section.label]), [
    ['settings', 'Settings'], ['variants', 'Variants'], ['layers', 'Quantity layers'], ['var', 'Feature table (var)'],
    ['obs', 'Sample table (obs)'], ['modifications', 'Modification map'], ['stored', 'As stored']
  ])
  const [layers] = page[2].tables
  assert.deepEqual(layers.columns.map(column => column.field), ['name', 'primary', 'source', 'roles', 'type', 'missing_values'])
  assert.deepEqual(layers.rows.map(row => row.primary), ['primary', null, null])
  assert.equal(page[0].tables[0].rows[0].value, 'DDA / DIA, unknown')
  assert.ok(page.slice(0, -1).every(section => section.tables.length === 1 && section.json.length === 0))
  assert.equal(page.at(-1).json.length, 2)
  assert.deepEqual(levelPage(LEVELS[0]).map(section => section.id), ['settings', 'layers', 'var', 'obs', 'modifications', 'stored'])
})

test('the rule list names a rule by software and versions, then its levels and input', () => {
  assert.deepEqual(ruleOption(RULES[1]), {
    rule: 'other/rules.json',
    software: 'OTHER',
    versions: '^.*$',
    levels: ['peptidoform_ion'],
    details: ['peptidoform_ion', 'DDA · wide | long · .tsv · parameter file none']
  })
})

test('the tabs across rules give one row per declaration and name it only where a level has several', () => {
  assert.deepEqual(orderedLevels(LEVELS), ['peptidoform_ion', 'protein'])
  const ion = ofLevel(LEVELS, 'peptidoform_ion')
  const levels = levelRows(RULES, ion)
  assert.deepEqual(levels.rows.map(row => [row.software, row.selected_by, row.primary_layer]), [['TOOL', 'DDA', 'Ms1'], ['TOOL', 'DIA, unknown', 'Precursor'], ['OTHER', null, 'Q']])
  assert.deepEqual(levels.rows[0].abundance_layers, ['Ms1', 'Precursor'])
  assert.deepEqual(levels.rows[0].protein_assignment, ['Protein_Group'])
  assert.equal(allLayers(RULES, ion).rows.length, 9)
  const columns = allColumns(RULES, ofLevel(LEVELS, 'protein'))
  assert.deepEqual(columns.rows.map(row => [row.table, row.name]), [['var', 'Protein_Group'], ['var', 'ProForma_ion'], ['obs', 'Run']])
  assert.ok(!columns.columns.includes('selected_by'))
})

test('a level names the column that links it to its gene, and the gene level comes after protein', () => {
  const linked = declaration('Q')
  linked.columns.var.push({ name: 'Genes', source: 'Genes', type: 'string', roles: ['gene_assignment'], note: null })
  const levels = [{ rule: 'other/rules.json', level: 'protein', declarations: [{ selected_by: ANY, declaration: linked }] }]
  assert.deepEqual(levelRows(RULES, levels).rows[0].gene_assignment, ['Genes'])
  assert.ok(!levelRows(RULES, ofLevel(LEVELS, 'peptidoform_ion')).columns.includes('gene_assignment'))
  assert.deepEqual(orderedLevels([{ level: 'gene' }, { level: 'protein' }]), ['protein', 'gene'])
})

test('a level shows the columns that rule a table out, and a table without them no column', () => {
  const refusing = { ...declaration('Q'), forbidden_columns: ['charge'] }
  const levels = [{ rule: 'other/rules.json', level: 'peptidoform', declarations: [{ selected_by: ANY, declaration: refusing }] }]
  assert.deepEqual(levelRows(RULES, levels).rows[0].forbidden_columns, ['charge'])
  const settings = Object.fromEntries(summaryRows(refusing).map(row => [row.setting, row.value]))
  assert.equal(settings.forbidden_columns, 'charge')
  assert.ok(!levelRows(RULES, ofLevel(LEVELS, 'peptidoform_ion')).columns.includes('forbidden_columns'))
})
