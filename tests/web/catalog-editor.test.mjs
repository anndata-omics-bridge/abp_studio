import assert from 'node:assert/strict'
import { test } from 'node:test'

import { basisStart, CatalogDraft, csvText, parseRuleLevels, parseSchemas, zipFiles } from '../../viewer/src/catalog/projections/editor.ts'

// A catalog of two sets in the shape of apb-catalog's datapackage.json, cut down to what the
// editor reads: columns, keys, a boolean and two patterns.
const DATAPACKAGE = {
  resources: [
    { name: 'sets', path: 'sets.csv', schema: { fields: [{ name: 'set', constraints: { required: true } }, { name: 'prefix', constraints: { pattern: '^[a-z]+$', required: true, unique: true } }], primaryKey: ['set'] } },
    {
      name: 'terms',
      path: 'terms.csv',
      schema: {
        fields: [{ name: 'set' }, { name: 'location' }, { name: 'key' }, { name: 'kind', constraints: { required: true } }, { name: 'requirement', constraints: { pattern: '^(required|recommended|optional)?$' } }],
        primaryKey: ['set', 'location', 'key'],
        foreignKeys: [{ fields: ['set', 'kind'], reference: { resource: 'kinds', fields: ['set', 'kind'] } }]
      }
    },
    { name: 'kinds', path: 'kinds.csv', schema: { fields: [{ name: 'set' }, { name: 'kind' }, { name: 'definition', constraints: { required: true } }], primaryKey: ['set', 'kind'] } },
    {
      name: 'catalog',
      path: 'catalog.csv',
      schema: {
        fields: [{ name: 'set' }, { name: 'software' }, { name: 'location' }, { name: 'key' }, { name: 'fixed', type: 'boolean' }, { name: 'basis' }],
        primaryKey: ['set', 'software', 'location', 'key'],
        foreignKeys: [{ fields: ['set', 'key', 'location'], reference: { resource: 'terms', fields: ['set', 'key', 'location'] } }]
      }
    },
    { name: 'versions', path: 'versions.csv', schema: { fields: [{ name: 'software' }, { name: 'version' }], primaryKey: ['software', 'version'] } }
  ]
}

function draft () {
  return new CatalogDraft(parseSchemas(DATAPACKAGE), new Map([
    ['sets', [{ set: 'abundance', prefix: 'a' }, { set: 'rt', prefix: 'rt' }]],
    ['terms', [
      { set: 'abundance', location: 'peptidoform_ion/layers', key: 'intensity', kind: 'intensity', requirement: 'recommended' },
      { set: 'abundance', location: 'protein/layers', key: 'intensity', kind: 'intensity', requirement: '' },
      { set: 'abundance', location: 'protein/layers', key: 'ibaq', kind: 'ibaq', requirement: '' },
      { set: 'rt', location: 'peptidoform_ion/layers', key: 'retention_time', kind: 'retention_time', requirement: 'required' }
    ]],
    ['kinds', [{ set: 'abundance', kind: 'intensity', definition: 'A signal.' }, { set: 'abundance', kind: 'ibaq', definition: 'iBAQ.' }, { set: 'rt', kind: 'retention_time', definition: 'Where it eluted.' }, { set: 'abundance', kind: 'unknown', definition: 'Not established.' }, { set: 'rt', kind: 'unknown', definition: 'Not established.' }]],
    ['catalog', [{ set: 'abundance', software: 'DIA-NN/*', location: 'peptidoform_ion/layers', key: 'intensity', fixed: 'true', basis: 'DIA-NN: "Quantity", non-normalised' }]],
    ['versions', [{ software: 'DIA-NN', version: '2.x' }]]
  ]))
}

test('every table with a set column refers to sets.csv by it, declared or not', () => {
  const terms = parseSchemas(DATAPACKAGE).find(schema => schema.name === 'terms')
  assert.deepEqual(terms.foreignKeys.map(key => key.resource), ['kinds', 'sets'])
  assert.deepEqual(parseSchemas(DATAPACKAGE).find(schema => schema.name === 'catalog').booleans, ['fixed'])
})

test('a foreign-key cell offers what the referenced table holds for the row\'s other key fields', () => {
  const catalog = draft()
  assert.deepEqual(catalog.choices('catalog', { set: 'abundance', location: 'protein/layers' }, 'key'), ['ibaq', 'intensity'])
  assert.deepEqual(catalog.choices('catalog', { set: 'abundance', key: 'intensity' }, 'location'), ['peptidoform_ion/layers', 'protein/layers'])
  assert.deepEqual(catalog.choices('terms', { set: 'rt' }, 'kind'), ['retention_time', 'unknown'])
})

test('a set, a boolean, a listing pattern and a software cell offer their values; free text offers none', () => {
  const catalog = draft()
  catalog.update('sets', catalog.add('sets').id, 'set', 'peak_qc')
  assert.deepEqual(catalog.choices('terms', {}, 'set'), ['abundance', 'rt', 'peak_qc'])
  assert.deepEqual(catalog.choices('catalog', {}, 'fixed'), ['true', 'false'])
  assert.deepEqual(catalog.choices('terms', {}, 'requirement'), ['required', 'recommended', 'optional'])
  assert.deepEqual(catalog.choices('catalog', {}, 'software'), ['DIA-NN/*', 'DIA-NN/2.x'])
  assert.equal(catalog.choices('catalog', {}, 'basis'), null)
})

test('a repeated primary key, a foreign key no row answers and a broken pattern are problems', () => {
  const catalog = draft()
  assert.deepEqual(catalog.problems(), [])
  const term = catalog.add('terms', 'rt')
  for (const [column, value] of Object.entries({ location: 'peptidoform_ion/layers', key: 'retention_time', kind: 'peak_width' })) {
    catalog.update('terms', term.id, column, value)
  }
  catalog.update('sets', catalog.rows('sets')[1].id, 'prefix', 'RT')
  const messages = catalog.problems().map(problem => `${problem.table}.${problem.column}: ${problem.message}`)
  assert.deepEqual(messages, [
    "sets.prefix: 'RT' does not match ^[a-z]+$",
    'terms.set: repeats the primary key set, location, key of another row',
    'terms.kind: set, kind = rt, peak_width names no row of kinds'
  ])
})

test('a foreign key with an empty field is left unchecked, as a key the row leaves open', () => {
  const catalog = draft()
  catalog.add('catalog', 'abundance')
  assert.deepEqual(catalog.problems().filter(problem => problem.message.includes('names no row')), [])
})

test('saving writes CSV as Python writes it, and one set only its rows of the tables with a set column', () => {
  const catalog = draft()
  assert.equal(csvText(['a', 'b'], [{ a: 'x,y', b: 'say "hi"' }]), 'a,b\n"x,y","say ""hi"""\n')
  assert.deepEqual(catalog.files('rt').map(file => file.name), ['sets.csv', 'terms.csv', 'kinds.csv', 'catalog.csv'])
  assert.equal(catalog.files('rt').find(file => file.name === 'kinds.csv').text, 'set,kind,definition\nrt,retention_time,Where it eluted.\nrt,unknown,Not established.\n')
  assert.equal(catalog.files().length, 5)
})

test('starting empty keeps the read-only versions table', () => {
  const catalog = draft()
  catalog.clear()
  assert.deepEqual(catalog.files().map(file => file.text.split('\n').length - 2), [0, 0, 0, 0, 1])
})

test('the zip stores each file with its CRC-32 and lists it in the central directory', () => {
  const zip = zipFiles([{ name: 'a.csv', text: 'hello' }, { name: 'b.csv', text: '' }])
  const view = new DataView(zip.buffer)
  assert.equal(view.getUint32(0, true), 0x04034B50)
  assert.equal(view.getUint32(14, true), 0x3610A686)
  assert.equal(view.getUint32(zip.length - 22, true), 0x06054B50)
  assert.equal(view.getUint16(zip.length - 12, true), 2)
})

test('an empty required description is incomplete; an empty required key or patterned cell is broken', () => {
  const catalog = draft()
  catalog.update('kinds', catalog.add('kinds', 'rt').id, 'kind', 'peak_width')
  catalog.update('terms', catalog.add('terms', 'rt').id, 'key', 'width')
  catalog.add('sets')
  const found = catalog.problems().map(problem => `${problem.table}.${problem.column} ${problem.level}`)
  assert.deepEqual(found, ['sets.set broken', 'sets.prefix broken', 'terms.kind broken', 'kinds.definition incomplete'])
  assert.deepEqual(catalog.states(), { sets: 'broken', terms: 'broken', kinds: 'incomplete', catalog: 'complete', versions: 'complete' })
})

test('resolve adds the rows unanswered foreign keys need, and the rows those need in turn', () => {
  const catalog = draft()
  const term = catalog.add('terms', 'mycatalog')
  for (const [column, value] of Object.entries({ location: 'protein/layers', key: 'hello_world', kind: 'hello' })) catalog.update('terms', term.id, column, value)
  assert.ok(catalog.problems().every(problem => problem.level === 'broken' && problem.resolvable))
  assert.deepEqual(catalog.resolve(), { kinds: 1, sets: 1 })
  assert.deepEqual(catalog.rows('kinds', 'mycatalog').map(row => row.cells), [{ set: 'mycatalog', kind: 'hello', definition: '' }])
  assert.deepEqual(catalog.states(), { sets: 'broken', terms: 'complete', kinds: 'incomplete', catalog: 'complete', versions: 'complete' })
  assert.deepEqual(catalog.resolve(), {})
})

test('a unique column refuses a value another row holds, and key columns carry their marks', () => {
  const catalog = draft()
  const set = catalog.add('sets')
  catalog.update('sets', set.id, 'set', 'alpha')
  catalog.update('sets', set.id, 'prefix', 'a')
  assert.deepEqual(catalog.problems().map(problem => `${problem.table}.${problem.column} ${problem.level}: ${problem.message}`), [
    "sets.prefix broken: 'a' is already the prefix of another row; prefix is unique"
  ])
  assert.deepEqual(catalog.schema('catalog').marks, { set: '[K] [FK]', software: '[K]', location: '[K] [FK]', key: '[K] [FK]' })
  assert.deepEqual(catalog.schema('sets').marks, { set: '[PK]' })
})

test('a set needs no kind unknown, declared alone or with kinds', () => {
  const catalog = draft()
  const set = catalog.add('sets')
  catalog.update('sets', set.id, 'set', 'peak_qc')
  catalog.update('sets', set.id, 'prefix', 'pq')
  assert.deepEqual(catalog.problems(), [])
  const kind = catalog.add('kinds', 'peak_qc')
  catalog.update('kinds', kind.id, 'kind', 'peak_width')
  catalog.update('kinds', kind.id, 'definition', 'The width of the elution peak.')
  assert.deepEqual(catalog.problems(), [])
  assert.deepEqual(catalog.resolve(), {})
})

// A term, the catalog rows that map it, the versions of DIA-NN, and the rules bundle's DIA-NN 2
// protein level: what the name dropdown and the cells filled from the term read.
const MAPPING = {
  resources: [
    { name: 'terms', path: 'terms.csv', schema: { fields: ['set', 'location', 'key', 'kind', 'qualifier', 'value', 'psi_ms'].map(name => ({ name })), primaryKey: ['set', 'location', 'key', 'qualifier'] } },
    {
      name: 'catalog',
      path: 'catalog.csv',
      schema: {
        fields: [{ name: 'set' }, { name: 'software' }, { name: 'location' }, { name: 'name' }, { name: 'key' }, { name: 'kind' }, { name: 'qualifier' }, { name: 'value' }, { name: 'fixed', type: 'boolean' }, { name: 'psi_ms' }, { name: 'basis' }, { name: 'evidence_url' }],
        primaryKey: ['set', 'software', 'location', 'name', 'key', 'qualifier'],
        foreignKeys: [{ fields: ['set', 'key', 'location'], reference: { resource: 'terms', fields: ['set', 'key', 'location'] } }]
      }
    },
    { name: 'versions', path: 'versions.csv', schema: { fields: [{ name: 'software' }, { name: 'version' }, { name: 'software_version_pattern' }] } }
  ]
}
const RULES = {
  levels: [{
    rule: 'diann/v2/rules.json',
    level: 'protein',
    declarations: [{
      declaration: {
        software_name: 'DIA-NN',
        software_version_pattern: '^2\\.',
        quantification_level: 'protein',
        axis: { obs_keys: ['sample'], var_keys: ['ProForma_protein'] },
        columns: { obs: [{ name: 'Run' }], var: [{ name: 'Genes' }] },
        measurements: { layers: [{ name: 'PG_MaxLFQ', source: 'PG.MaxLFQ', note: null }, { name: 'PG_Q_Value', source: 'PG.Q.Value', note: 'Run-specific' }] }
      }
    }]
  }]
}

test('a catalog row names what APB2 writes there, and takes kind, PSI-MS terms and fixed from its term', () => {
  const draft = new CatalogDraft(parseSchemas(MAPPING), new Map([
    ['terms', [{ set: 'a', location: 'protein/layers', key: 'intensity_norm_settings', kind: 'intensity', qualifier: 'normalization', value: 'run_setting', psi_ms: 'MS:1001850' }]],
    ['versions', [{ software: 'DIA-NN', version: '2.x', software_version_pattern: '^2\\.' }]]
  ]))
  draft.rules = parseRuleLevels(RULES)
  assert.deepEqual(draft.choices('catalog', { software: 'DIA-NN/2.x', location: 'protein/layers' }, 'name'), ['PG_MaxLFQ/-', 'PG_Q_Value/-'])
  assert.deepEqual(draft.choices('catalog', { software: 'DIA-NN/*', location: 'protein/var' }, 'name'), ['-/Genes', '-/ProForma_protein'])
  const row = draft.add('catalog', 'a')
  for (const [column, value] of Object.entries({ software: 'DIA-NN/2.x', location: 'protein/layers', name: 'PG_MaxLFQ/-', key: 'intensity_norm_settings', qualifier: 'normalization', value: 'run_setting' })) {
    draft.update('catalog', row.id, column, value)
  }
  draft.update('catalog', row.id, 'basis', 'PG.MaxLFQ: the protein group MaxLFQ quantity.')
  assert.deepEqual([row.cells.kind, row.cells.psi_ms, row.cells.fixed], ['intensity', 'MS:1001850', 'true'])
  assert.deepEqual(draft.problems(), [])
  draft.update('catalog', row.id, 'value', 'none')
  assert.equal(row.cells.fixed, 'false')
  assert.deepEqual(draft.problems().map(problem => `${problem.column}: ${problem.message}`), ['value: the term intensity_norm_settings fixes normalization = run_setting'])
})

test('naming a field starts its basis from the rule, which stays incomplete until it says what the value means', () => {
  const draft = new CatalogDraft(parseSchemas(MAPPING), new Map([
    ['terms', [{ set: 'a', location: 'protein/layers', key: 'intensity_norm_settings', kind: 'intensity', qualifier: 'normalization', value: 'run_setting', psi_ms: '' }]],
    ['catalog', [{ set: 'a', software: 'DIA-NN/*', location: 'protein/layers', name: 'PG_MaxLFQ/-', key: 'intensity_norm_settings', kind: 'intensity', qualifier: 'normalization', value: 'run_setting', fixed: 'true', psi_ms: '', basis: 'PG.MaxLFQ: MaxLFQ.', evidence_url: 'https://github.com/vdemichev/DiaNN' }]],
    ['versions', [{ software: 'DIA-NN', version: '2.x', software_version_pattern: '^2\\.' }]]
  ]))
  draft.rules = parseRuleLevels(RULES)
  const row = draft.add('catalog', 'a')
  for (const [column, value] of Object.entries({ software: 'DIA-NN/2.x', location: 'protein/layers', name: 'PG_Q_Value/-' })) draft.update('catalog', row.id, column, value)
  assert.equal(row.cells.basis, 'PG.Q.Value (Run-specific):')
  assert.deepEqual(draft.problems().filter(problem => problem.column === 'basis').map(problem => problem.level), ['incomplete'])
  draft.update('catalog', row.id, 'basis', 'PG.Q.Value (Run-specific): the protein group q-value in its run.')
  assert.deepEqual(draft.problems().filter(problem => problem.column === 'basis'), [])
  assert.deepEqual(draft.choices('catalog', { software: 'DIA-NN/2.x' }, 'evidence_url'), ['https://github.com/vdemichev/DiaNN'])
  assert.deepEqual(draft.choices('catalog', { software: 'MaxQuant/*' }, 'evidence_url'), [])
  assert.equal(basisStart({ source: '^(?P<sample>.+)$', note: '' }), '')
})
