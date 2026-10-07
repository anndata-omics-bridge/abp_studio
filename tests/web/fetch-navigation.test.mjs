import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { runInNewContext } from 'node:vm'
import { isolatedSource } from './source.mjs'

const SOURCE = fileURLToPath(new URL('../../viewer/src/corpus/lib/fetch.ts', import.meta.url))

function client (development, baseURI) {
  const requested = []
  const context = {
    URL,
    document: { baseURI },
    fetch: async url => {
      requested.push(url)
      return { status: 404 }
    }
  }
  // Vite substitutes this development flag when compiling each entry point.
  const source = isolatedSource(SOURCE).replaceAll('import.meta.env?.DEV', String(development))
  runInNewContext(source, context, { filename: SOURCE })
  return { ...context, requested }
}

test('Vite navigation opens corpus files on the read server while reads remain proxied', async () => {
  const app = client(true, 'http://127.0.0.1:5173/corpus/')
  const path = 'routine/convert/artifacts/input file/parquet'
  const directory = new URL(app.fileUrl(path))
  assert.equal(directory.origin, 'http://127.0.0.1:8766')
  assert.equal(directory.pathname, '/data/routine/convert/artifacts/input%20file/parquet')
  assert.equal(directory.searchParams.get('view'), '1')
  assert.equal(new URL(app.fileUrl('routine/run.json')).search, '')

  const source = new URL(app.sourceUrl('routine/convert', '/fixture/input file.txt'))
  assert.equal(source.origin, 'http://127.0.0.1:8766')
  assert.equal(source.pathname, '/api/source')
  assert.equal(source.searchParams.get('context'), 'routine/convert')
  assert.equal(source.searchParams.get('path'), '/fixture/input file.txt')

  await app.readStore(path, 'text')
  assert.equal(app.requested[0], 'http://127.0.0.1:5173/corpus/data/routine/convert/artifacts/input%20file/parquet')
})

test('production navigation retains the viewer base path and selected server port', () => {
  const app = client(false, 'http://localhost:9321/studio/')
  assert.equal(app.fileUrl('routine/output.h5mu'), 'http://localhost:9321/studio/data/routine/output.h5mu?view=1')
  const source = new URL(app.sourceUrl('routine', '/fixtures/input.txt'))
  assert.equal(source.origin, 'http://localhost:9321')
  assert.equal(source.pathname, '/studio/api/source')
  assert.equal(app.dataUrl('routine/run.json'), 'http://localhost:9321/studio/data/routine/run.json')
})

test('input kind reads are run-scoped and refuse invalid filesystem labels', async () => {
  const app = client(true, 'http://127.0.0.1:5173/corpus/')
  let requested
  app.fetch = async url => {
    requested = new URL(url)
    return { ok: true, json: async () => ({ schema_version: 2, input_kinds: { 'input.parquet': 'file', 'v2.8': 'folder' } }) }
  }
  // Re-evaluate the boundary with the controlled response in the same browser test context.
  const source = isolatedSource(SOURCE).replaceAll('import.meta.env?.DEV', 'true')
  const context = { URL, document: { baseURI: 'http://127.0.0.1:5173/corpus/' }, fetch: app.fetch }
  runInNewContext(source, context)
  const kinds = await context.readInputKinds('routine/convert/hdf5')
  assert.equal(requested.pathname, '/corpus/api/input-kinds')
  assert.equal(requested.searchParams.get('context'), 'routine/convert/hdf5')
  assert.deepEqual({ ...kinds }, { 'input.parquet': 'file', 'v2.8': 'folder' })
  context.fetch = async () => ({ ok: true, json: async () => ({ schema_version: 2, input_kinds: { input: 'guessed' } }) })
  await assert.rejects(context.readInputKinds('routine'), /Invalid input kinds/)
})
