import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readCatalog } from '../../viewer/src/corpus/lib/fetch.ts'
import { runChoices, scientificOutputExtensions } from '../../viewer/src/corpus/model.ts'

const artifact = (path, role = 'result', size_bytes = 10) => ({ path, role, size_bytes, format: 'hdf5' })
const report = (...steps) => ({ status: 'succeeded', steps })
const succeeded = (...outputs) => ({ name: 'run', status: 'succeeded', outputs })

test('observed scientific paths distinguish AnnData, MuData and other storage outputs', () => {
  const records = [
    report(succeeded(artifact('/run/scored.h5ad'))),
    report(succeeded(artifact('/run/converted.h5mu', 'converted'))),
    report(succeeded(artifact('/run/data.duckdb'))),
    report(succeeded(artifact('/run/data.parquet/'))),
    report(succeeded(artifact('/run/export.h5ad', 'export')))
  ]
  assert.deepEqual(scientificOutputExtensions(records), ['.duckdb', '.h5ad', '.h5mu', '.parquet'])
  assert.deepEqual(scientificOutputExtensions([report(succeeded(artifact('/run/table.tsv', 'export')))]), ['.tsv'])
})

test('each dataset contributes its final observed scientific output, excluding sidecars and reports', () => {
  const exported = report(
    succeeded(artifact('/run/converted.h5mu', 'converted')),
    succeeded(artifact('/run/prolfqua.h5ad', 'export'), artifact('/run/prolfqua.h5ad.apb.json', 'representation')),
    succeeded(artifact('/run/timings.h5mu', 'tool_timings'), artifact('/run/report.html', 'pmultiqc_report'),
      artifact('/run/scores.json', 'proteobench_scores'))
  )
  const failed = {
    status: 'failed', steps: [
      succeeded(artifact('/run/converted.h5mu', 'converted')),
      { name: 'aggregate', status: 'failed', outputs: [artifact('/run/aggregated.h5ad', 'result', null)] }
    ]
  }
  assert.deepEqual(scientificOutputExtensions([exported]), ['.h5ad'])
  assert.deepEqual(scientificOutputExtensions([failed]), ['.h5mu'])
  assert.deepEqual(scientificOutputExtensions([exported, failed]), ['.h5ad', '.h5mu'])
})

test('HDF5 configuration and unobserved outputs never fabricate a file extension', () => {
  const pending = {
    format: 'hdf5', status: 'running', steps: [
      { name: 'convert', status: 'running', outputs: [artifact('/run/converted.h5mu', 'result', null)] }
    ]
  }
  assert.deepEqual(scientificOutputExtensions([null, undefined, pending]), [])
  assert.deepEqual(scientificOutputExtensions([report(succeeded(artifact('/run/unknown')))]), [])
})

test('catalog output metadata passes through run choices without changing backend labels', async t => {
  const path = 'routine/export_prolfqua/hdf5/run.json'
  const outputs = { [path]: ['.h5ad'] }
  const originalDocument = globalThis.document
  globalThis.document = { baseURI: 'http://localhost:8766/' }
  t.after(() => {
    if (originalDocument === undefined) delete globalThis.document
    else globalThis.document = originalDocument
  })
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    schema_version: 2, runs: [path], output_extensions: outputs
  })))
  const catalog = await readCatalog()
  const [choice] = runChoices([{
    path, outputExtensions: catalog.output_extensions[path],
    manifest: { corpus_name: 'routine', workflow: 'export_prolfqua', format: 'hdf5' }
  }])
  assert.deepEqual(choice.outputExtensions, ['.h5ad'])
  assert.equal(choice.manifest.format, 'hdf5')
  assert.equal(choice.label, 'routine · export_prolfqua · hdf5')

  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    schema_version: 2, runs: [path], output_extensions: { [path]: 'hdf5' }
  })))
  await assert.rejects(readCatalog(), /Invalid catalog output extensions/)
})
