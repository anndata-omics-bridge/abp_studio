import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  DATASET_FACETS, RUN_FACETS, datasetFacets, emptyDatasetFilters, emptyRunFilters,
  filterDatasets, filterRuns, runFacets
} from '../../viewer/src/corpus/filters.ts'

function run (corpus, workflow, format, overrides = {}) {
  return {
    path: `corpus/${corpus}/${workflow}/${format}/run.json`,
    label: `${corpus} · ${workflow} · ${format}`,
    manifest: {
      corpus_name: corpus, workflow, format, reports: [], created_at: '2026-10-06',
      data_root: '/fixtures', tools: { apb: '/tools/bin/apb' }, ...overrides
    }
  }
}

const RUNS = [
  run('routine', 'convert', 'hdf5'),
  run('routine', 'convert', 'parquet'),
  run('routine', 'export_msmu', 'hdf5'),
  run('proteobench', 'proteobench_pmultiqc', 'hdf5'),
  run('entrapment', 'proteobench_entrapment', 'hdf5')
]

function dataset (software, module, status, name, metadata = {}) {
  return {
    software_name: software, module, status,
    input_file: `submissions/${software}/${name}/input_file.tsv`,
    input_file_name: 'input_file.tsv', input_file_parent: name,
    dataset: name, path: `reports/${name}.json`, ...metadata
  }
}

const DATASETS = [
  dataset('MaxQuant', 'dda', 'succeeded', 'qexactive', { instrument: 'Q Exactive', software_version: '2.4' }),
  dataset('MaxQuant', 'dda', 'failed', 'multifile', { instrument: 'Orbitrap' }),
  dataset('DIA-NN', 'dia', 'succeeded', 'astral', { instrument: 'Astral' }),
  dataset('Spectronaut', 'dia', 'running', 'timstof', { instrument: 'timsTOF' })
]

function options (groups, facet) {
  return Object.fromEntries(groups.find(group => group.key === facet).options.map(({ value, count }) => [value, count]))
}

test('empty filters retain every row in its original order and return independent selections', () => {
  const runFilters = emptyRunFilters()
  const datasetFilters = emptyDatasetFilters()
  assert.deepEqual(filterRuns(RUNS, runFilters), RUNS)
  assert.deepEqual(filterDatasets(DATASETS, datasetFilters), DATASETS)
  assert.notEqual(filterRuns(RUNS, runFilters), RUNS)
  runFilters.corpus.push('routine')
  datasetFilters.status.push('failed')
  assert.deepEqual(emptyRunFilters().corpus, [])
  assert.deepEqual(emptyDatasetFilters().status, [])
  assert.deepEqual(runFacets(RUNS, emptyRunFilters()).map(({ key, label }) => [key, label]), RUN_FACETS)
  assert.deepEqual(datasetFacets(DATASETS, emptyDatasetFilters()).map(({ key, label }) => [key, label]), DATASET_FACETS)
})

test('run facets combine OR selections within a facet and AND selections across facets', () => {
  const filters = { ...emptyRunFilters(), corpus: ['routine', 'entrapment'], format: ['hdf5'] }
  assert.deepEqual(filterRuns(RUNS, filters), [RUNS[0], RUNS[2], RUNS[4]])
  assert.deepEqual(filterRuns(RUNS, { ...filters, workflow: ['convert'] }), [RUNS[0]])
})

test('run search matches every case-insensitive token across labels, paths and recorded metadata', () => {
  assert.deepEqual(filterRuns(RUNS, { ...emptyRunFilters(), search: '  ROUTINE\nparquet ' }), [RUNS[1]])
  assert.deepEqual(filterRuns(RUNS, { ...emptyRunFilters(), search: '/tools/bin APB 2026-10' }), RUNS)
  assert.deepEqual(filterRuns(RUNS, { ...emptyRunFilters(), search: 'routine astral' }), [])
})

test('run facet counts exclude their own selection while respecting other facets and search', () => {
  const filters = { ...emptyRunFilters(), corpus: ['routine'], workflow: ['convert'], format: ['hdf5'] }
  const facets = runFacets(RUNS, filters)
  assert.deepEqual(options(facets, 'corpus'), { entrapment: 0, proteobench: 0, routine: 1 })
  assert.deepEqual(options(facets, 'workflow'), { convert: 1, export_msmu: 1, proteobench_entrapment: 0, proteobench_pmultiqc: 0 })
  assert.deepEqual(options(facets, 'format'), { hdf5: 1, parquet: 1 })
  assert.deepEqual(options(runFacets(RUNS, { ...filters, search: 'parquet' }), 'format'), { hdf5: 0, parquet: 1 })
})

test('dataset filters combine software, module and result without treating empty selections as none', () => {
  const filters = { ...emptyDatasetFilters(), software_name: ['MaxQuant', 'DIA-NN'], status: ['succeeded'] }
  assert.deepEqual(filterDatasets(DATASETS, filters), [DATASETS[0], DATASETS[2]])
  assert.deepEqual(filterDatasets(DATASETS, { ...filters, module: ['dda'] }), [DATASETS[0]])
  assert.deepEqual(filterDatasets(DATASETS, { ...filters, status: ['failed', 'running'] }), [DATASETS[1]])
})

test('dataset search includes scalar input metadata and full paths without searching nested report text', () => {
  assert.deepEqual(filterDatasets(DATASETS, { ...emptyDatasetFilters(), search: 'MAXQUANT Q EXACTIVE 2.4' }), [DATASETS[0]])
  assert.deepEqual(filterDatasets(DATASETS, { ...emptyDatasetFilters(), search: 'submissions/DIA-NN astral' }), [DATASETS[2]])
  const withReport = { ...DATASETS[0], record: { steps: [{ command: ['unrelated-command'] }] } }
  assert.deepEqual(filterDatasets([withReport], { ...emptyDatasetFilters(), search: 'unrelated-command' }), [])
})

test('dataset counts show alternatives for the chosen facet and respect a metadata query', () => {
  const filters = { ...emptyDatasetFilters(), software_name: ['MaxQuant'], status: ['succeeded'] }
  const facets = datasetFacets(DATASETS, filters)
  assert.deepEqual(options(facets, 'software_name'), { 'DIA-NN': 1, MaxQuant: 1, Spectronaut: 0 })
  assert.deepEqual(options(facets, 'status'), { failed: 1, running: 0, succeeded: 1 })
  assert.deepEqual(options(datasetFacets(DATASETS, { ...filters, search: 'Orbitrap' }), 'status'), { failed: 1, running: 0, succeeded: 0 })
})

test('polling preserves selected options when records disappear or change status', () => {
  const runFilters = { ...emptyRunFilters(), corpus: ['removed'] }
  assert.deepEqual(options(runFacets(RUNS, runFilters), 'corpus'), { entrapment: 1, proteobench: 1, removed: 0, routine: 3 })
  assert.deepEqual(filterRuns(RUNS, runFilters), [])
  const datasetFilters = { ...emptyDatasetFilters(), status: ['running'], software_name: ['Spectronaut'] }
  const settled = DATASETS.map(row => row.status === 'running' ? { ...row, status: 'succeeded' } : row)
  assert.deepEqual(options(datasetFacets(settled, datasetFilters), 'status'), { failed: 0, running: 0, succeeded: 1 })
  assert.deepEqual(filterDatasets(settled, datasetFilters), [])
  assert.deepEqual(options(datasetFacets([], datasetFilters), 'software_name'), { Spectronaut: 0 })
  assert.deepEqual(options(datasetFacets([], datasetFilters), 'status'), { running: 0 })
})

test('no-match queries retain selectable facets with zero counts and never mutate data or filters', () => {
  const runs = structuredClone(RUNS)
  const rows = structuredClone(DATASETS)
  const runFilters = { ...emptyRunFilters(), search: 'absent', corpus: ['routine'] }
  const datasetFilters = { ...emptyDatasetFilters(), search: 'absent', status: ['running'] }
  const before = structuredClone({ runs, rows, runFilters, datasetFilters })
  assert.deepEqual(filterRuns(runs, runFilters), [])
  assert.deepEqual(filterDatasets(rows, datasetFilters), [])
  assert.ok(runFacets(runs, runFilters).every(group => group.options.every(option => option.count === 0)))
  assert.ok(datasetFacets(rows, datasetFilters).every(group => group.options.every(option => option.count === 0)))
  assert.deepEqual({ runs, rows, runFilters, datasetFilters }, before)
})

test('blank recorded facet values remain selectable and numeric labels sort naturally', () => {
  const rows = [dataset('', 'module10', 'pending', 'missing'), dataset('APB', 'module2', 'pending', 'known')]
  assert.deepEqual(filterDatasets(rows, { ...emptyDatasetFilters(), software_name: [''] }), [rows[0]])
  assert.deepEqual(datasetFacets(rows, emptyDatasetFilters()).find(group => group.key === 'module').options.map(option => option.value), ['module2', 'module10'])
})
