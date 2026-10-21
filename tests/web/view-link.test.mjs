import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parsedViewLink, viewLinkUrl } from '../../viewer/src/corpus/view-link.ts'

const view = {
  run: 'corpus/routine/convert/hdf5',
  tab: 'insights',
  insight: 'search-settings',
  settings: 'workflow-source',
  dataset: 'Results/a b/input.tsv',
  detail: 'scientific-apb-metadata'
}

test('a link carries only the fields its tab uses and round-trips', () => {
  const overview = viewLinkUrl('http://127.0.0.1:8766/#old=1', view)
  assert.equal(overview, 'http://127.0.0.1:8766/#run=corpus%2Froutine%2Fconvert%2Fhdf5&tab=insights&insight=search-settings')
  assert.deepEqual(parsedViewLink(new URL(overview).hash), { ...view, settings: '', dataset: '', detail: '' })

  const files = viewLinkUrl('https://site.example/viewer/', { ...view, tab: 'files' })
  assert.deepEqual(parsedViewLink(new URL(files).hash), { ...view, tab: 'files', insight: '', settings: '' })

  const settings = viewLinkUrl('http://host/', { ...view, insight: 'settings' })
  assert.equal(parsedViewLink(new URL(settings).hash).settings, 'workflow-source')
})

test('a fragment without a run is not a shared view', () => {
  assert.equal(parsedViewLink(''), null)
  assert.equal(parsedViewLink('#tab=files'), null)
})
