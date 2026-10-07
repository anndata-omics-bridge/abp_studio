import assert from 'node:assert/strict'
import { test } from 'node:test'

import { joinSubmissions, parseStoreIndex, parseSubmissionJson, parseSummary, storageRows, summaryPath } from '../../viewer/src/fixture/lib/store.ts'

const CATALOG = [
  {
    module: 'dda_peptidoform',
    repo_name: 'Repo',
    intermediate_hash: 'a',
    software_name: 'WOMBAT',
    software_version: '0.9.11',
    nr_feature: '41314',
    is_temporary: 'False',
    old_new: 'new',
    smallest_per_software_version: 'True',
    smallest_per_software: 'False',
    smallest_per_module: 'True'
  },
  { module: 'dia_aif', repo_name: 'Other', intermediate_hash: 'b', nr_feature: '' }
]

test('a catalogued submission with no summary reads as pending, not as zero', () => {
  const [, pending] = joinSubmissions(CATALOG, [], new Map())
  assert.equal(pending.status, 'not downloaded')
  assert.equal(pending.size_mb, null)
  assert.equal(pending.rows, null)
  assert.equal(pending.nr_feature, null)
  assert.equal(pending.smallest_per_module, false)
})

test("a submission's own summary is what says it is downloaded", () => {
  const summary = {
    input_file: 'submissions/Repo/a/input_file.csv',
    format: 'delimited',
    delimiter: 'comma',
    size_bytes: 5020545,
    rows: 34259,
    columns: 14,
    column_names: 'x|y',
    parameter_file: 'submissions/Repo/a/param_0..yml',
    downloaded_at: '2026-09-04T21:30:00+00:00'
  }
  const [row, missing] = joinSubmissions(CATALOG, [], new Map([['a', summary]]))
  assert.equal(row.status, 'ok')
  assert.equal(row.nr_feature, 41314)
  assert.ok(Math.abs(row.size_mb - 5.020545) < 1e-9)
  assert.equal(row.rows, 34259)
  assert.equal(row.columns, 14)
  assert.equal(row.column_names, 'x|y')
  assert.equal(row.input_file, 'submissions/Repo/a/input_file.csv')
  assert.equal(row.downloaded_at, '2026-09-04T21:30:00+00:00')
  assert.equal(row.downloaded_on, '2026-09-04', 'the day alone, for grouping')
  assert.equal(row.smallest_per_software_version, true)
  assert.equal(row.is_temporary, false)
  assert.equal(missing.status, 'not downloaded')
})

test('downloads.csv is consulted only for what a summary cannot say', () => {
  const refused = [{ intermediate_hash: 'b', status: 'not_on_server' }]
  const [, never] = joinSubmissions(CATALOG, refused, new Map())
  assert.equal(never.status, 'not_on_server')

  const claimed = [{ intermediate_hash: 'a', status: 'ok' }]
  const [gone] = joinSubmissions(CATALOG, claimed, new Map())
  assert.equal(gone.status, 'not downloaded', 'no summary, no download, whatever a table says')
})

test('a summary URL is composed from the pattern the index publishes', () => {
  const pattern = 'submissions/{repo_name}/{intermediate_hash}/summary.json'
  assert.equal(summaryPath(pattern, CATALOG[0]), 'submissions/Repo/a/summary.json')
  assert.equal(summaryPath(pattern, CATALOG[1]), 'submissions/Other/b/summary.json')
})

test('an index missing its byte counts degrades instead of reporting NaN', () => {
  const rows = storageRows({ root: '/store' }, [])
  const byKey = new Map(rows.map((row) => [row.key, row.value]))
  assert.equal(byKey.get('Metadata size'), '0.00 GB')
  assert.equal(byKey.get('FASTA files'), 'none')
  assert.equal(byKey.has('Module TOMLs'), false)
})

test('a bare NaN in a submission document parses as a missing value', () => {
  const document = parseSubmissionJson('{"software_version": NaN, "id": "x", "n": -Infinity}')
  assert.deepEqual(document, { software_version: null, id: 'x', n: null })
  assert.equal(parseSubmissionJson('   '), null)
  assert.deepEqual(parseSubmissionJson('{"note": "NaN stays text"}'), { note: 'NaN stays text' })
  assert.throws(() => parseSubmissionJson('{'), SyntaxError)
})

test('storage rows report sizes in gigabytes and name what is absent', () => {
  assert.deepEqual(storageRows(null), [{ key: 'Store', value: 'index.json not available' }])
  const index = {
    root: '/store',
    fasta: [],
    tables: [{ name: 'catalog.csv', sizeBytes: 27287 }],
    bytes: { metadata: 1e8, fasta: 0 }
  }
  const rows = storageRows(index, [{ size_bytes: 1.5e9 }, { size_bytes: 5e8 }])
  const byKey = new Map(rows.map((row) => [row.key, row.value]))
  assert.equal(byKey.get('Store root'), '/store')
  assert.equal(byKey.get('Submissions on disk'), '2')
  assert.equal(byKey.get('Vendor tables size'), '2.00 GB')
  assert.equal(byKey.get('FASTA files'), 'none')
  assert.equal(byKey.get('catalog.csv'), '27.3 kB')
  assert.equal(new Map(storageRows(index).map((r) => [r.key, r.value])).get('Vendor tables size'), '0.00 GB')
})


test('persisted store JSON is checked at the viewer boundary', () => {
  const index = parseStoreIndex({
    root: '/store', submissionSummary: 'submissions/{repo_name}/{intermediate_hash}/summary.json',
    fasta: ['database.fasta'], bytes: { metadata: 10, fasta: 20 },
    tables: [{ name: 'catalog.csv', sizeBytes: 200, modifiedNs: 123 }], storeVersion: 1
  })
  assert.equal(index.root, '/store')
  assert.deepEqual(index.tables, [{ name: 'catalog.csv', sizeBytes: 200 }])
  assert.equal(parseStoreIndex(null), null)
  assert.throws(() => parseStoreIndex([]), /expected an object/)
  assert.throws(() => parseStoreIndex({ bytes: { metadata: '10' } }), /bytes.metadata: expected a finite number/)
  assert.throws(() => parseStoreIndex({ fasta: [1] }), /array of file names/)
  assert.throws(() => parseStoreIndex({ tables: [{ name: 'catalog.csv' }] }), /name and sizeBytes are required/)
})

test('submission summaries reject malformed facts while permitting absent optional fields', () => {
  assert.equal(parseSummary(null), null)
  const summary = parseSummary({ size_bytes: 120, rows: null, columns: 5, downloaded_at: '2026-10-06' })
  assert.equal(summary.rows, null)
  assert.equal(summary.columns, 5)
  assert.throws(() => parseSummary({ size_bytes: '120' }), /size_bytes: expected a finite number/)
  assert.throws(() => parseSummary({ rows: Infinity }), /rows: expected a finite number/)
  assert.throws(() => parseSummary({ column_names: ['a', 'b'] }), /column_names: expected a string/)
  const [row] = joinSubmissions(CATALOG, [], new Map([['a', parseSummary({})]]))
  assert.equal(row.status, 'ok')
  assert.equal(row.size_mb, null, 'absent size remains absent instead of becoming NaN')
})
