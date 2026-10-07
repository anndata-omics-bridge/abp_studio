import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { fileLink } from '../../viewer/src/corpus/render/links.ts'

test('readable files open tabs, JSON stays raw, and binary files download without tabs', t => {
  class Anchor extends EventTarget {}
  const previous = globalThis.document
  globalThis.document = {
    baseURI: 'http://localhost:8766/',
    createElement: tag => {
      assert.equal(tag, 'a')
      return new Anchor()
    }
  }
  t.after(() => {
    if (previous === undefined) delete globalThis.document
    else globalThis.document = previous
  })
  for (const label of ['multiqc_report_data', 'multiqc_report.html', 'result.json', 'module.toml', 'reference.fasta']) {
    const link = fileLink(`/data/${label}?view=1`, label)
    assert.equal(link.textContent, label)
    const query = label.endsWith('.json') ? '' : '?view=1'
    assert.equal(link.href, `http://localhost:8766/data/${label}${query}`)
    assert.equal(link.target, '_blank')
    assert.equal(link.rel, 'noopener noreferrer')
    assert.equal(link.download, undefined)
    const event = new Event('click', { cancelable: true })
    const stop = t.mock.method(event, 'stopPropagation')
    link.dispatchEvent(event)
    assert.equal(stop.mock.callCount(), 1)
    assert.equal(event.defaultPrevented, false)
  }
  for (const filename of ['scored.h5mu', 'converted.H5AD', 'result.parquet', 'data.duckdb', 'tables.zip']) {
    for (const href of [`/data/${filename}?view=1`, `/api/source?path=inputs%2F${filename}`]) {
      const link = fileLink(href, filename)
      assert.equal(link.download, filename)
      assert.equal(link.target, undefined)
      assert.equal(link.textContent, filename)
    }
  }
  const folder = fileLink('/data/converted.parquet?view=1', 'converted.parquet', { directory: true })
  assert.equal(folder.target, '_blank')
  assert.equal(folder.download, undefined)
})

test('detail and settings panels link resources and snapshots using the shared tab policy', () => {
  for (const panel of ['detail', 'settings']) {
    const source = readFileSync(`viewer/src/corpus/panels/${panel}.ts`, 'utf8')
    assert.match(source, /import \{ fileLink \}/)
    assert.match(source, /fileUrl\(/)
    assert.match(source, /sourceUrl\(/)
    assert.match(source, /'fasta'/)
    assert.doesNotMatch(source, /\.download\s*=/)
  }
})
