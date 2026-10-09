import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'
import { isolatedSource } from './source.mjs'

test('snapshot links belong to their settings tab and optional links clear when changing runs', async () => {
  const hosts = new Map()
  const hostFor = id => {
    if (!hosts.has(id)) hosts.set(id, { children: [], replaceChildren (...children) { this.children = children } })
    return hosts.get(id)
  }
  const context = {
    app: { hostFor },
    emptyCsv: () => [],
    fileUrl: path => `/data/${path}`,
    sourceUrl: path => `/fixtures/${path}`,
    fileLink: (href, label) => ({ href, label }),
    renderJson: (host, data) => { host.data = data },
    readStore: async (_path, kind) => kind === 'text' ? 'workflow source' : [],
    mountTable: async () => ({ destroy () {}, redraw () {} })
  }
  const panel = runInNewContext(`${isolatedSource('viewer/src/corpus/panels/settings.ts')}\ncreateSettingsPanel(app)`, context)
  const manifest = {
    execution_settings: 'execution_settings.json', source_corpus: 'corpus.csv', corpus: 'selected_corpus.csv',
    input_metadata: 'input_metadata.csv', workflow_table: 'workflow.csv', workflow_source: 'workflow_aggregate_medpolish.py'
  }
  const run = { directory: 'routine/aggregate_medpolish/hdf5', storeRoot: '/store', manifest, config: { corpus: '/corpuses/routine.csv' }, corpus: [], inputMetadata: [], workflowRows: [] }
  await panel.renderRun(run)
  const labels = id => [...hostFor(id).children].map(link => link.label)
  assert.deepEqual(labels('workflow-source-links'), ['workflow_aggregate_medpolish.py'])
  assert.deepEqual(labels('execution-settings-links'), ['execution_settings.json'])
  assert.deepEqual(labels('saved-run-links'), ['run.json'])
  assert.deepEqual(labels('corpus-input-links'), ['corpus.csv', 'selected_corpus.csv'])
  assert.deepEqual(labels('input-metadata-links'), ['input_metadata.csv'])
  assert.deepEqual(labels('workflow-input-links'), ['workflow.csv'])
  assert.equal(hostFor('workflow-source-links').children[0].href, '/data/routine/aggregate_medpolish/hdf5/workflow_aggregate_medpolish.py')
  assert.equal(hostFor('source').textContent, 'workflow source')
  await panel.renderRun({ ...run, directory: 'routine/convert/hdf5', manifest: { ...manifest, input_metadata: null, workflow_table: null, source_corpus: 'selected_corpus.csv' } })
  assert.deepEqual(labels('input-metadata-links'), [])
  assert.deepEqual(labels('workflow-input-links'), [])
  assert.deepEqual(labels('corpus-input-links'), ['selected_corpus.csv'])
  panel.clear()
  for (const id of ['workflow-source-links', 'execution-settings-links', 'saved-run-links', 'corpus-input-links', 'input-metadata-links', 'workflow-input-links']) assert.deepEqual(labels(id), [])
})
