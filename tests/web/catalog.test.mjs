import assert from 'node:assert/strict'
import { test } from 'node:test'

import { appFields, coverage, keyColumns } from '../../viewer/src/catalog/projections/coverage.ts'
import { softwareList, versionEntries } from '../../viewer/src/catalog/projections/software.ts'
import { cellText, chosen, levelsOf, parseResources, storedView, tableOf } from '../../viewer/src/catalog/projections/tables.ts'

const DATAPACKAGE = {
  name: 'apb-catalog',
  resources: [
    {
      name: 'catalog',
      path: 'catalog.csv',
      description: 'One row per catalogued field.',
      schema: { fields: [{ name: 'set', type: 'string', description: 'The catalogue set.' }, { name: 'reference', type: 'string' }] }
    },
    { name: 'rule_levels', path: 'rule_levels.csv', schema: { fields: [{ name: 'software', description: 'The software.' }] } }
  ]
}

// rule_coverage rows as apb-catalog-ts returns them, each with the set it was asked for.
const COVERAGE = [
  { set: 'confidence', software: 'WOMBAT', version: '1.x', software_version_pattern: '^1\\.', level: 'protein', key: 'q_value', kind: 'q_value', qualifiers: 'stage=identification', origin: 'vendor', location: 'layers', table: null, column: 'PG_Q', requirement: null, producer: null, needs: null, verdict: null },
  { set: 'confidence', software: 'WOMBAT', version: '2.x', software_version_pattern: '^2\\.', level: 'protein', key: 'q_value', kind: 'q_value', qualifiers: 'stage=identification', origin: 'vendor', location: 'layers', table: null, column: 'Q', requirement: null, producer: null, needs: null, verdict: null },
  { set: 'confidence', software: 'WOMBAT', version: '2.x', software_version_pattern: '^2\\.', level: 'protein', key: 'q_value', kind: 'q_value', qualifiers: 'stage=identification', origin: 'vendor', location: 'layers', table: null, column: 'Q2', requirement: null, producer: null, needs: null, verdict: null },
  { set: 'apb', software: 'WOMBAT', version: '2.x', software_version_pattern: '^2\\.', level: 'protein', key: 'decoy', kind: 'decoy', qualifiers: null, origin: 'apb2', location: 'var', table: null, column: 'decoy', requirement: 'required', producer: null, needs: null, verdict: 'fail' },
  { set: 'apb', software: 'WOMBAT', version: '2.x', software_version_pattern: '^2\\.', level: 'protein', key: 'group', kind: 'group', qualifiers: 'convention=sdrf', origin: null, location: 'obs', table: null, column: null, requirement: 'required', producer: null, needs: null, verdict: 'fail' },
  { set: 'apb', software: 'WOMBAT', version: '1.x', software_version_pattern: '^1\\.', level: 'protein', key: null, kind: null, qualifiers: null, origin: null, location: null, table: null, column: null, requirement: null, producer: null, needs: null, verdict: 'pass' }
]

// catalogue_table rows: vendor entries once per pattern, the others without one.
const LONG = [
  { set: 'confidence', source: 'WOMBAT', software_version_pattern: '^2\\.', level: 'protein', location: 'layers', table: null, name: 'Q', entry_id: 'a' },
  { set: 'confidence', source: 'WOMBAT', software_version_pattern: '^1\\.', level: 'protein', location: 'layers', table: null, name: 'PG_Q', entry_id: 'b' },
  { set: 'confidence', source: 'OTHER', software_version_pattern: '^2\\.', level: 'protein', location: 'layers', table: null, name: 'Q', entry_id: 'c' },
  { set: 'apb', source: 'annotation:sdrf', software_version_pattern: null, level: '*', location: 'obs', table: null, name: 'prefix:factor_value_', entry_id: 'd' },
  { set: 'apb', source: 'producer:apb-fasta', software_version_pattern: null, level: 'peptide', location: 'varm', table: 'fasta_validation', name: 'match', entry_id: 'e' }
]

// Every set, level and location; tests pick from it.
const EVERY = { set: '', level: '', location: '' }

const VERSIONS = {
  columns: ['software', 'version', 'software_version_pattern'],
  rows: [
    { software: 'WOMBAT', version: '1.x', software_version_pattern: '^1\\.' },
    { software: 'WOMBAT', version: '2.x', software_version_pattern: '^2\\.' }
  ]
}

test('stored tables come in datapackage order with each column described', () => {
  const [entries, levels] = parseResources(DATAPACKAGE)
  assert.equal(entries.name, 'catalog')
  assert.equal(entries.description, 'One row per catalogued field.')
  assert.deepEqual(entries.fields, [{ name: 'set', description: 'The catalogue set.' }, { name: 'reference', description: '' }])
  assert.equal(levels.path, 'rule_levels.csv')
  assert.equal(levels.description, '')
})

test('a column header says whether the column is the primary key, part of it, or of a foreign key', () => {
  const schema = (primaryKey) => ({
    fields: [{ name: 'set' }, { name: 'kind' }, { name: 'definition' }],
    primaryKey,
    foreignKeys: [{ fields: ['set'], reference: { resource: 'sets', fields: ['set'] } }]
  })
  const [kinds, single] = parseResources({
    resources: [
      { name: 'kinds', path: 'kinds.csv', schema: schema(['set', 'kind']) },
      { name: 'sets', path: 'sets.csv', schema: schema('kind') }
    ]
  })
  const table = { columns: ['set', 'kind', 'definition'], rows: [] }
  assert.deepEqual(storedView(kinds, table, EVERY).columns.map(({ title }) => title), ['set [K] [FK]', 'kind [K]', 'definition'])
  assert.deepEqual(storedView(single, table, EVERY).columns.map(({ title }) => title), ['set [FK]', 'kind [PK]', 'definition'])
})

test('a datapackage without resources is refused, not shown empty', () => {
  assert.throws(() => parseResources({ name: 'apb-catalog' }), /lists no resources/)
  assert.throws(() => parseResources({ resources: [{ name: 'catalog', path: 'catalog.csv' }] }), /no schema fields/)
})

test('a stored table keeps its stored columns and shows only the chosen set', () => {
  const [entries] = parseResources(DATAPACKAGE)
  const table = { columns: ['set', 'reference'], rows: [{ set: 'apb', reference: 'decoy' }, { set: 'abundance', reference: 'Intensity' }] }
  const view = storedView(entries, table, { ...EVERY, set: 'apb' })
  assert.deepEqual(view.rows, [{ set: 'apb', reference: 'decoy' }])
  assert.deepEqual(view.columns.map(({ field, tooltip }) => [field, tooltip]), [['set', 'The catalogue set.'], ['reference', '']])
  assert.deepEqual(view.legend, [{ name: 'set', description: 'The catalogue set.' }], 'a stored table lists what each described column holds')
  assert.equal(storedView(entries, table, EVERY).rows.length, 2)
  assert.equal(storedView(entries, { columns: ['set'], rows: [] }, { ...EVERY, set: 'apb' }).columns.length, 1)
})

test('a column with many distinct values filters by text, a short one by a value list', () => {
  const [entries] = parseResources(DATAPACKAGE)
  const rows = Array.from({ length: 41 }, (_, index) => ({ set: 'apb', reference: `column_${index}` }))
  const view = storedView(entries, { columns: ['set', 'reference'], rows }, EVERY)
  assert.deepEqual(view.columns.map(({ filter }) => filter), ['list', 'input'])
})

test('a table without a set column is shown whole whatever the set', () => {
  const [, levels] = parseResources(DATAPACKAGE)
  assert.equal(storedView(levels, VERSIONS, { set: 'apb', level: 'protein', location: 'var' }).rows.length, 2)
})

test('stored entries are chosen by the level and location their location names', () => {
  const [entries] = parseResources(DATAPACKAGE)
  const rows = [
    { set: 'abundance', software: 'DIA-NN/*', location: 'protein/layers', name: 'PG_MaxLFQ/-' },
    { set: 'abundance', software: 'DIA-NN/*', location: 'peptidoform_ion/var', name: '-/Precursor_Charge' },
    { set: 'apb', software: 'annotation:sdrf/*', location: '*/obs', name: '-/factor_value_*' }
  ]
  const table = { columns: ['set', 'software', 'location', 'name'], rows }
  const names = (filter) => storedView(entries, table, filter).rows.map(row => row.name)
  assert.deepEqual(names({ ...EVERY, level: 'protein' }), ['PG_MaxLFQ/-', '-/factor_value_*'], 'an entry of every level is on each')
  assert.deepEqual(names({ ...EVERY, location: 'var' }), ['-/Precursor_Charge'])
  assert.deepEqual(names({ set: 'abundance', level: 'protein', location: 'layers' }), ['PG_MaxLFQ/-'])
})

test('views are chosen by their rows level and location; levels list protein first', () => {
  assert.deepEqual(chosen(LONG, { ...EVERY, level: 'peptide' }).map(row => row.entry_id), ['d', 'e'])
  assert.deepEqual(chosen(LONG, { set: 'confidence', level: '', location: 'layers' }).map(row => row.entry_id), ['a', 'b', 'c'])
  assert.deepEqual(chosen(LONG, { ...EVERY, location: 'varm' }).map(row => row.entry_id), ['e'])
  assert.deepEqual(levelsOf([{ level: 'peptidoform_ion' }, { level: '*' }, { level: 'protein' }, { level: 'custom' }, { level: 'peptide' }]), ['protein', 'peptide', 'peptidoform_ion', 'custom'])
})

test('cells read as text: lists joined, missing values empty', () => {
  assert.equal(cellText(['prolfquapp', 'apb-export']), 'prolfquapp; apb-export')
  assert.equal(cellText(null), '')
  assert.equal(cellText(undefined), '')
  assert.equal(cellText(false), 'false')
  assert.deepEqual(tableOf([{ a: 1 }, { b: 2, a: 3 }]).columns, ['a', 'b'])
})

test('a set\'s keys become columns, each cell naming the column a software version keeps it in', () => {
  const { table, keys } = keyColumns(COVERAGE.filter(row => row.set === 'confidence'))
  assert.deepEqual(table.columns, ['software', 'version', 'level', 'q_value'])
  assert.deepEqual(table.rows, [
    { software: 'WOMBAT', version: '1.x', level: 'protein', q_value: 'PG_Q' },
    { software: 'WOMBAT', version: '2.x', level: 'protein', q_value: 'Q, Q2' }
  ])
  assert.deepEqual(keys, [{ name: 'q_value', description: 'q_value, stage=identification, in layers' }])
})

test('a required key a version lacks reads missing, and a version with no fields keeps its row', () => {
  const { table } = keyColumns(COVERAGE.filter(row => row.set === 'apb'))
  assert.deepEqual(table.columns, ['software', 'version', 'level', 'decoy', 'group'])
  assert.deepEqual(table.rows, [
    { software: 'WOMBAT', version: '2.x', level: 'protein', decoy: 'decoy', group: 'missing required' },
    { software: 'WOMBAT', version: '1.x', level: 'protein' }
  ])
})

test('fields an app writes are listed once, with their levels, not per software version', () => {
  const written = { set: 'apb', software: 'WOMBAT', level: 'peptide', key: 'is_proteotypic', kind: 'is_proteotypic', qualifiers: null, location: 'varm', table: 'fasta_validation', column: 'is_proteotypic', requirement: null, producer: 'apb-fasta', needs: 'run `apb-fasta verify-peptides`', verdict: null }
  const rows = [
    { ...written, version: '1.x' },
    { ...written, version: '2.x' },
    { ...written, version: '2.x', level: 'protein' }
  ]
  assert.deepEqual(appFields(rows).rows, [
    { producer: 'apb-fasta', key: 'is_proteotypic', levels: 'peptide, protein', location: 'varm', table: 'fasta_validation', column: 'is_proteotypic', needs: 'run `apb-fasta verify-peptides`' }
  ])
  assert.deepEqual(keyColumns(rows).table.columns, ['software', 'version', 'level'], 'app fields stay out of the key columns')
})

test('coverage judges each version and level once and names what it misses', () => {
  const table = coverage(COVERAGE)
  assert.deepEqual(table.rows, [
    { set: 'apb', software: 'WOMBAT', version: '2.x', level: 'protein', verdict: 'fail', missing: ['required group in obs'] },
    { set: 'apb', software: 'WOMBAT', version: '1.x', level: 'protein', verdict: 'pass', missing: [] }
  ])
})

test('a software version lists the levels its entries name, and a clicked row lists exactly the entries it counts', () => {
  const list = softwareList(VERSIONS, LONG, LONG.filter(row => row.set === 'apb'))
  assert.deepEqual(list.columns, ['software', 'version', 'software_version_pattern', 'level', 'entries'])
  assert.deepEqual(list.rows.map(row => [row.version, row.level, row.entries]), [['1.x', 'protein', 0], ['2.x', 'protein', 0]])
  const every = softwareList(VERSIONS, LONG, LONG)
  assert.deepEqual(every.rows.map(row => row.entries), [1, 1])
  const entries = versionEntries(tableOf(LONG), every.rows[1])
  assert.equal(entries.rows.length, every.rows[1].entries, 'as many rows as the count says')
  assert.deepEqual(entries.rows.map(row => row.entry_id), ['a'])
  assert.deepEqual(entries.columns, ['set', 'location', 'name', 'entry_id'], 'no columns the version and level fix, none left empty')
})
