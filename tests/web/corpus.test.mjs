import test from 'node:test'
import assert from 'node:assert/strict'
import { chartPoints, chartViews, counts, datasetArtifacts, datasetRows, formatBytes, runChoices, statusFractions, workflowFields, workflowSteps } from '../../viewer/src/corpus/model.ts'
import { alignedSummary, annDataDiagram, apbMetadataScopes, artifactAttemptStorePath, artifactStorePath, expandEmbeddedJsonForDisplay, layerChart, loadRepresentationArtifacts, matrixSummary, preferredLoadedRepresentation, representationArtifacts, representationIonVariables, representationViews, validatedRepresentation } from '../../viewer/src/corpus/representation.ts'
import { validatedToolTimings } from '../../viewer/src/corpus/tool-timings.ts'
import { readFileSync } from 'node:fs'

test('viewer distinguishes pending, running, tool failure and interrupted work', () => {
  const links = ['a', 'b', 'c', 'd'].map(input_file => ({ input_file, path: input_file, progress: `${input_file}.progress` }))
  const manifest = { reports: links }
  const reports = new Map([['a', { status: 'failed', steps: [] }]])
  const progress = new Map([['b.progress', { status: 'running', steps: [{ name: 'convert', status: 'running' }] }]])
  const rows = datasetRows(manifest, [], [], reports, progress, { status: 'running' })
  assert.deepEqual(counts(rows), { failed: 1, running: 1, pending: 2 })
  const stopped = datasetRows(manifest, [], [], reports, progress, { status: 'interrupted' })
  assert.deepEqual(counts(stopped), { failed: 1, interrupted: 3 })
})

test('dataset rows retain the basename and merge workflow fields', () => {
  const manifest = { reports: [{ input_file: 'submissions/hash/input_file.txt', path: 'report', progress: 'progress' }] }
  const corpus = [{
    input_file: 'submissions/hash/input_file.txt', vendor_parameter_file: 'submissions/hash/params.json',
    module: 'dda_qexactive', software_name: 'MaxQuant'
  }]
  const workflowRows = [{ software_name: 'MaxQuant', start_level: 'ion', method: 'mean' }]
  workflowRows.columns = ['software_name', 'start_level', 'method']
  const rows = datasetRows(manifest, corpus, [], new Map(), new Map(), null, workflowRows)
  assert.equal(rows[0].input_file_name, 'input_file.txt')
  assert.equal(rows[0].input_file_parent, 'hash')
  assert.equal(rows[0].start_level, 'ion')
  assert.equal(rows[0].method, 'mean')
  assert.deepEqual(workflowFields(workflowRows), ['start_level', 'method'])
})

test('file sizes use compact binary units', () => {
  assert.equal(formatBytes(100043984), '95.4 MiB')
  assert.equal(formatBytes('1024'), '1.0 KiB')
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(''), '')
})

test('dataset rows expose the final output while the banner owns the step sequence', () => {
  const link = { input_file: 'submissions/hash/input.csv', path: 'report', progress: 'progress' }
  const record = { steps: [
    { name: 'convert', status: 'succeeded', outputs: [{ path: '/artifacts/hash/converted.h5ad', size_bytes: 2048 }] },
    { name: 'aggregate', status: 'succeeded', outputs: [
      { role: 'result', path: '/artifacts/hash/aggregated.h5mu', size_bytes: 4096 },
      { role: 'representation', path: '/artifacts/hash/aggregated.h5mu.apb.json', size_bytes: 512 }
    ] }
  ] }
  const rows = datasetRows({ reports: [link] }, [], [], new Map([['report', record]]), new Map(), null)
  assert.equal(rows[0].output_file_name, 'aggregated.h5mu')
  assert.equal(rows[0].output_file_parent, 'hash')
  assert.equal(rows[0].output_file_size_bytes, 4096)
  assert.deepEqual(workflowSteps(rows), ['convert', 'aggregate'])
})

test('dataset output ignores phantom artifacts from failed and skipped steps', () => {
  const link = { input_file: 'submissions/hash/input.csv', path: 'report', progress: 'progress' }
  const record = { status: 'failed', steps: [
    {
      name: 'convert', status: 'succeeded', outputs: [
        { role: 'converted', path: '/artifacts/hash/converted.h5ad', size_bytes: 2048 }
      ]
    },
    {
      name: 'aggregate', status: 'failed', outputs: [
        { role: 'result', path: '/artifacts/hash/aggregated.h5mu', size_bytes: null }
      ]
    },
    {
      name: 'export', status: 'skipped', outputs: [
        { role: 'result', path: '/artifacts/hash/exported.h5mu', size_bytes: null }
      ]
    }
  ] }

  const [row] = datasetRows(
    { reports: [link] }, [], [], new Map([['report', record]]), new Map(), null
  )

  assert.equal(row.output_file, '/artifacts/hash/converted.h5ad')
  assert.equal(row.output_file_name, 'converted.h5ad')
  assert.equal(row.output_file_size_bytes, 2048)
  assert.deepEqual(
    row.record.steps.flatMap(step => step.outputs.map(output => output.path)),
    [
      '/artifacts/hash/converted.h5ad',
      '/artifacts/hash/aggregated.h5mu',
      '/artifacts/hash/exported.h5mu'
    ]
  )
})

test('failed-step evidence stays in Show More without becoming the summary output', () => {
  const link = { input_file: 'submissions/hash/input.csv', path: 'report', progress: 'progress' }
  const record = { status: 'failed', steps: [
    {
      name: 'convert', status: 'failed', outputs: [
        { role: 'converted', path: '/artifacts/hash/converted.h5ad', size_bytes: 4096 },
        { role: 'representation', path: '/artifacts/hash/converted.h5ad.apb.json', size_bytes: null }
      ]
    },
    {
      name: 'aggregate', status: 'skipped', outputs: [
        { role: 'result', path: '/artifacts/hash/aggregated.h5mu', size_bytes: null }
      ]
    }
  ] }

  const [row] = datasetRows(
    { reports: [link] }, [], [], new Map([['report', record]]), new Map(), null
  )

  assert.equal(row.output_file, '')
  assert.equal(row.output_file_name, '')
  assert.equal(row.output_file_size_bytes, null)
  assert.deepEqual(
    datasetArtifacts(row).filter(artifact => artifact.direction === 'Output'),
    [
      {
        role: 'converted', path: '/artifacts/hash/converted.h5ad', size_bytes: 4096,
        direction: 'Output', step: 'convert'
      },
      {
        role: 'representation', path: '/artifacts/hash/converted.h5ad.apb.json', size_bytes: null,
        direction: 'Output', step: 'convert'
      },
      {
        role: 'result', path: '/artifacts/hash/aggregated.h5mu', size_bytes: null,
        direction: 'Output', step: 'aggregate'
      }
    ]
  )
})

test('representation documents are versioned and projected into labelled Plotly boxes', () => {
  const document = validatedRepresentation({
    format: 'apb2-result-representation', format_version: '4', artifact: { name: 'result.h5mu' },
    levels: [], annotation_tables: [], feature_relations: []
  })
  assert.equal(document.artifact.name, 'result.h5mu')
  assert.equal(representationIonVariables({
    ...document,
    levels: [
      { name: 'ion', dimensions: { observations: 6, variables: 4242 } },
      { name: 'protein', dimensions: { observations: 6, variables: 100 } }
    ]
  }), 4242)
  assert.equal(representationIonVariables({ ...document, levels: [
    { name: 'protein', dimensions: { observations: 6, variables: 100 } }
  ] }), null)
  assert.throws(() => representationIonVariables({ ...document, format_version: '3' }), /version/)
  assert.throws(() => validatedRepresentation({ format: document.format, format_version: '2' }), /version/)
  const chart = layerChart(
    {
      name: 'protein', obs: { key_columns: ['sample'] },
      observations: {
        total_count: 2, emitted_count: 2, truncated: false,
        items: [
          { index: 0, key: { sample: 'run A' }, label: 'run A' },
          { index: 1, key: { sample: 'run B' }, label: 'run B' }
        ]
      }
    },
    {
      name: 'Intensity', value_kind: 'quantitative', unit: 'arbitrary units',
      observation_summaries: {
        total_count: 2, emitted_count: 1, truncated: true,
        items: [{
          observation_index: 0, statistics: {
            minimum: 1, first_quartile: 2, median: 3, third_quartile: 4, maximum: 5, mean: 3
          }
        }]
      }
    }
  )
  assert.ok(chart)
  assert.equal(chart.xTitle, 'sample')
  assert.equal(chart.yTitle, 'Intensity (arbitrary units)')
  assert.equal(chart.trace.type, 'box')
  assert.deepEqual(chart.trace.x, ['run A'])
})

test('representation display expands known embedded JSON and keeps native aggregate history', () => {
  const nestedRule = JSON.stringify({ schema_version: '0.3', software_name: 'Sage' })
  const source = {
    format: 'apb2-result-representation', format_version: '4',
    artifact: { name: 'result.h5ad' }, annotation_tables: [], feature_relations: [],
    levels: [{ apb: { parse: {
      rule_json: nestedRule,
      plan_json: JSON.stringify({ level: 'ion' }),
      search_parameters: JSON.stringify({ enzyme: 'Trypsin/P', allowed_miscleavages: 1 })
    },
      aggregate: [{
        source_level: 'ion', target_level: 'protein', method: 'mean'
      }]
    } }]
  }

  const displayed = validatedRepresentation(source)

  assert.deepEqual(displayed.levels[0].apb.parse.rule_json, {
    schema_version: '0.3', software_name: 'Sage'
  })
  assert.deepEqual(displayed.levels[0].apb.parse.plan_json, { level: 'ion' })
  assert.deepEqual(displayed.levels[0].apb.parse.search_parameters, {
    enzyme: 'Trypsin/P', allowed_miscleavages: 1
  })
  assert.deepEqual(displayed.levels[0].apb.aggregate, [{
    source_level: 'ion', target_level: 'protein', method: 'mean'
  }])
  assert.equal(source.levels[0].apb.parse.rule_json, nestedRule)
})

test('embedded JSON display preserves malformed, scalar and unrelated strings', () => {
  const source = {
    rule_json: '{not valid JSON',
    plan_json: '42',
    search_parameters: 'null',
    note: '{"looks":"like JSON"}',
    existing: { rule_json: ['already', { plan_json: '{"level":"protein"}' }] }
  }

  assert.deepEqual(expandEmbeddedJsonForDisplay(source), {
    rule_json: '{not valid JSON',
    plan_json: '42',
    search_parameters: 'null',
    note: '{"looks":"like JSON"}',
    existing: { rule_json: ['already', { plan_json: { level: 'protein' } }] }
  })
})

test('representation views separate APB metadata, scientific levels and raw JSON', () => {
  const h5mu = {
    artifact: { name: 'aggregated.h5mu', physical_format: 'h5mu' },
    root: { apb: { hierarchy: { name: 'lfq', identities: [['ion', 'ion'], ['protein', 'protein']] } } },
    levels: [{ name: 'protein' }, { name: 'ion' }],
    annotation_tables: [{ name: 'proteins', row_count: 2, key_columns: ['accession'] }]
  }
  const h5muViews = representationViews(h5mu)
  assert.deepEqual(h5muViews.map(({ key, kind, label }) => ({ key, kind, label })), [
    { key: 'apb-metadata', kind: 'apb-metadata', label: 'APB metadata' },
    { key: 'level-0', kind: 'level', label: 'AnnData · ion' },
    { key: 'level-1', kind: 'level', label: 'AnnData · protein' },
    { key: 'annotation-0', kind: 'annotation', label: 'AnnData · annotation/proteins' },
    { key: 'anndata-structure', kind: 'anndata-structure', label: 'Structure' },
    { key: 'representation-json', kind: 'representation-json', label: 'Representation JSON' }
  ])
  assert.equal(h5muViews[0].representation, h5mu)
  assert.equal(h5muViews[1].level, h5mu.levels[1])
  assert.equal(h5muViews[3].annotationTable, h5mu.annotation_tables[0])
  assert.equal(h5muViews[3].referenceLevel, h5mu.levels[1])

  const h5ad = {
    artifact: { name: 'converted.h5ad', physical_format: 'h5ad' },
    levels: [{ name: 'ion' }]
  }
  assert.deepEqual(
    representationViews(h5ad).map(({ kind, label }) => ({ kind, label })),
    [
      { kind: 'apb-metadata', label: 'APB metadata' },
      { kind: 'level', label: 'AnnData · ion' },
      { kind: 'anndata-structure', label: 'Structure' },
      { kind: 'representation-json', label: 'Representation JSON' }
    ]
  )

  const parquet = {
    artifact: { name: 'result.parquet', physical_format: 'parquet' },
    levels: [{ name: 'peptide' }]
  }
  assert.deepEqual(
    representationViews(parquet).map(({ kind, label }) => ({ kind, label })),
    [
      { kind: 'apb-metadata', label: 'APB metadata' },
      { kind: 'level', label: 'Level · peptide' },
      { kind: 'representation-json', label: 'Representation JSON' }
    ]
  )
})

test('AnnData diagram separates X from persisted slots without losing their descriptors', () => {
  const level = {
    name: 'ion',
    dimensions: { observations: 6, variables: 42 },
    primary_layer: 'Intensity',
    obs: { row_count: 6, key_columns: ['raw_file'], columns: [{ name: 'raw_file' }] },
    var: { row_count: 42, key_columns: ['ion'], columns: [{ name: 'ion' }] },
    layers: [
      { name: 'Intensity', primary: true, storage_slot: 'X' },
      { name: 'PEP', primary: false, storage_slot: 'layers' }
    ],
    aligned: { varm: [{ name: 'proteobench', row_count: 42, columns: [] }] },
    apb: { parse: { rule_json: {}, produced_by: 'apb2' }, scoring: {} }
  }
  assert.deepEqual(annDataDiagram(level), {
    name: 'ion',
    dimensions: { observations: 6, variables: 42 },
    x: level.layers[0],
    layers: [level.layers[1]],
    obs: level.obs,
    var: level.var,
    aligned: { obsm: [], varm: level.aligned.varm, obsp: [], varp: [] },
    uns: level.apb
  })
})

test('matrix summaries expose shape, semantics and compact completeness statistics', () => {
  assert.deepEqual(matrixSummary({
    name: 'PEP', role: 'quality', value_kind: 'quantitative', dtype: 'Float64',
    shape: { observations: 6, variables: 42 },
    statistics: {
      total_count: 252, finite_count: 200, null_count: 40, nan_count: 10,
      positive_infinity_count: 1, negative_infinity_count: 1, zero_count: 25,
      mean: 0.12, median: 0.08, minimum: 0, maximum: 1
    }
  }), {
    name: 'PEP', role: 'quality', shape: { observations: 6, variables: 42 },
    dtype: 'Float64', valueKind: 'quantitative', unit: null, scale: null,
    totalCount: 252, finiteCount: 200, missingCount: 50, infiniteCount: 2,
    zeroCount: 25, mean: 0.12, median: 0.08, minimum: 0, maximum: 1
  })
})

test('aligned summaries expose one object shape and its aggregate null burden', () => {
  assert.deepEqual(alignedSummary({
    name: 'proteobench', row_count: 42, key_columns: ['ion'],
    columns: [
      { name: 'included', dtype: 'Boolean', null_count: 0 },
      { name: 'epsilon', dtype: 'Float64', null_count: 7 },
      { name: 'ratio', dtype: 'Float64', null_count: 3 }
    ]
  }), {
    name: 'proteobench', rowCount: 42, columnCount: 3, cellCount: 126,
    nullCount: 10, keyColumns: ['ion'], dtypes: ['Boolean', 'Float64'],
    columns: [
      { name: 'included', dtype: 'Boolean', null_count: 0 },
      { name: 'epsilon', dtype: 'Float64', null_count: 7 },
      { name: 'ratio', dtype: 'Float64', null_count: 3 }
    ]
  })
})

test('APB metadata scopes preserve the physical uns namespace and level ownership', () => {
  const representation = {
    artifact: { physical_format: 'h5mu' },
    root: { apb: { parse: { produced_by: 'apb2' }, proteobench: { provenance: {} } } },
    levels: [
      { name: 'ion', apb: { parse: { rule_json: { software_name: 'FragPipe' } } } },
      { name: 'protein', apb: { parse: { plan_json: { level: 'protein' } }, aggregate: [] } }
    ]
  }

  assert.deepEqual(apbMetadataScopes(representation), [
    {
      label: 'MuData',
      value: { uns: { apb: {
        parse: { produced_by: 'apb2' }, proteobench: { provenance: {} }
      } } }
    },
    {
      label: 'ion',
      value: { uns: { apb: {
        parse: { rule_json: { software_name: 'FragPipe' } }
      } } }
    },
    {
      label: 'protein',
      value: { uns: { apb: {
        parse: { plan_json: { level: 'protein' } }, aggregate: []
      } } }
    }
  ])
})

test('preferred representation matches the displayed output sidecar then falls back to the last readable one', () => {
  const aggregated = {
    artifact: { path: '/artifacts/hash/aggregated.h5mu.apb.json' },
    representation: { artifact: { name: 'aggregated.h5mu' } }
  }
  const converted = {
    artifact: { path: '/artifacts/hash/converted.h5ad.apb.json' },
    representation: { artifact: { name: 'converted.h5ad' } }
  }
  const unreadable = {
    artifact: { path: '/artifacts/hash/missing.h5mu.apb.json' },
    representation: null
  }

  assert.equal(
    preferredLoadedRepresentation(
      { output_file: '/artifacts/hash/aggregated.h5mu' },
      [aggregated, converted, unreadable]
    ),
    aggregated
  )
  assert.equal(
    preferredLoadedRepresentation(
      { output_file: '/artifacts/hash/unknown.h5mu' },
      [aggregated, unreadable, converted]
    ),
    converted
  )
  assert.equal(preferredLoadedRepresentation({}, [unreadable]), null)
})

test('a stale representation request stops before it can populate another dataset', async () => {
  let release
  const deferred = new Promise(resolve => { release = resolve })
  let current = true
  const request = loadRepresentationArtifacts(
    [{ path: 'slow.apb.json' }],
    async () => await deferred,
    () => current
  )

  current = false
  release({ format: 'apb2-result-representation' })

  assert.equal(await request, null)
})

test('categorical layers never become quantitative Plotly boxes', () => {
  const chart = layerChart(
    { name: 'protein', observations: { items: [] } },
    {
      name: 'Match type', value_kind: 'categorical', dtype: 'categorical', category_count: 3,
      counts: { total_count: 20, known_count: 18, missing_or_unknown_count: 2 }
    }
  )

  assert.equal(chart, null)
})

test('show more locates every intermediate and final representation inside the saved run', () => {
  const record = { steps: [
    { name: 'convert', outputs: [
      { role: 'converted', path: '/root/artifacts/hash/uuid/converted.h5ad' },
      { role: 'representation', path: '/root/artifacts/hash/uuid/converted.h5ad.apb.json' }
    ] },
    { name: 'aggregate', outputs: [
      { role: 'representation', path: '/root/artifacts/hash/uuid/aggregated.h5mu.apb.json' }
    ] }
  ] }
  const artifacts = representationArtifacts(record)
  assert.deepEqual(artifacts.map(artifact => artifact.step), ['convert', 'aggregate'])
  assert.equal(
    artifactStorePath('run-id', 'artifacts/hash', artifacts[0].path),
    'run-id/artifacts/hash/uuid/converted.h5ad.apb.json'
  )
  assert.equal(
    artifactAttemptStorePath('run-id', 'artifacts/hash', artifacts[0].path),
    'run-id/artifacts/hash/uuid'
  )
})

test('status fractions preserve succeeded and failed proportions', () => {
  assert.deepEqual(statusFractions({ succeeded: 7, failed: 3 }, 10), {
    succeeded: 0.7, failed: 0.3, running: 0, interrupted: 0
  })
  assert.deepEqual(statusFractions({}, 0), {
    succeeded: 0, failed: 0, running: 0, interrupted: 0
  })
})

test('stable run choices show corpus, workflow and format without hashes', () => {
  const runs = [
    { path: 'routine/convert/hdf5/run.json', manifest: { corpus_name: 'routine', workflow: 'convert', format: 'hdf5' } },
    { path: 'all/aggregate/parquet/run.json', manifest: { corpus_name: 'all', workflow: 'aggregate', format: 'parquet' } }
  ]
  const choices = runChoices(runs)
  assert.deepEqual(choices.map(choice => choice.label), [
    'all · aggregate · parquet',
    'routine · convert · hdf5'
  ])
})

test('no stable runs produce no choices', () => {
  assert.deepEqual(runChoices([]), [])
})

test('settings use bounded sub-tabs while file links remain outside them', () => {
  const html = readFileSync('viewer/corpus/index.html', 'utf8')
  const shell = readFileSync('viewer/src/corpus/shell/corpus-app.ts', 'utf8')
  assert.match(shell, /const SETTINGS_TABS = \[[\s\S]*'workflow-source'/)
  assert.equal((shell.match(/class="settings-panel"/g) ?? []).length, 6)
  assert.ok(shell.indexOf('id="links"') < shell.indexOf('aria-label="Settings and input views"'))
  const stylesheet = html.match(/app\.css\?v=([^"']+)/)?.[1]
  const script = html.match(/app\.js\?v=([^"']+)/)?.[1]
  assert.equal(stylesheet, script)
})

test('chart projection preserves per-step and per-output evidence without inventing zeroes', () => {
  const record = {
    status: 'failed',
    steps: [
      {
        name: 'convert', command: ['/tools/apb2', 'convert'], status: 'succeeded', runtime_seconds: 1.5, peak_memory_bytes: 5 * 1024 ** 2,
        outputs: [
          { role: 'converted', path: '/result.h5mu', size_bytes: 3 * 1024 ** 2 },
          { role: 'representation', path: '/result.h5mu.apb.json', size_bytes: 1024 }
        ]
      },
      {
        name: 'aggregate', command: ['C:\\tools\\apb-aggregate'], status: 'failed', runtime_seconds: 0.75, peak_memory_bytes: 2 * 1024 ** 2,
        outputs: [{ role: 'aggregated', path: '/missing.h5mu', size_bytes: null }]
      },
      { name: 'later', command: [], status: 'skipped', runtime_seconds: null, peak_memory_bytes: null, outputs: [] }
    ]
  }
  const rows = [{
    input_file: 'vendor.tsv', input_file_size_bytes: String(10 * 1024 ** 2),
    module: 'dia_aif', software_name: 'DIA-NN', status: 'failed', record
  }]

  const points = chartPoints(rows)

  assert.equal(points.steps.length, 2)
  assert.deepEqual(points.steps.map(point => point.status), ['succeeded', 'failed'])
  assert.equal(points.steps[0].input_size_mib, 10)
  assert.equal(points.steps[0].peak_memory_mib, 5)
  assert.equal(points.outputs.length, 1)
  assert.equal(points.outputs[0].output_size_mib, 3)
  assert.deepEqual(chartPoints([{ ...rows[0], input_file_size_bytes: '' }]).steps.map(point => point.input_size_mib), [null, null])

  const views = chartViews(rows)
  assert.deepEqual(views.map(view => view.label), [
    'Workflow', 'convert · apb2', 'aggregate · apb-aggregate', 'later · unknown tool'
  ])
  assert.equal(views[0].steps[0].runtime_seconds, 2.25)
  assert.equal(views[0].steps[0].peak_memory_mib, 5)
  assert.equal(views[0].steps[0].status, 'failed')
  assert.deepEqual(views[0].outputs.map(point => point.step), ['convert'])
  assert.equal(views[1].steps.length, 1)
  assert.equal(views[2].steps.length, 1)
  assert.equal(views[3].steps.length, 0)
})

test('optional tool timings remain separate from Studio runtime and output size', () => {
  const document = validatedToolTimings({
    format: 'apb-tool-timings', format_version: 1, tool: 'apb2', operation: 'convert',
    phases: [{ name: 'compile', seconds: 2.5 }, { name: 'read', seconds: 1.25 }]
  })
  assert.throws(() => validatedToolTimings({ ...document, format_version: 2 }), /format or version/)
  assert.throws(() => validatedToolTimings({ ...document, phases: [
    { name: 'read', seconds: 1 }, { name: 'read', seconds: 2 }
  ] }), /phase/)
  const record = { steps: [{
    name: 'convert', command: ['/tools/apb2', 'convert'], status: 'succeeded',
    runtime_seconds: 5, outputs: [
      { role: 'result', path: '/run/converted.h5mu', size_bytes: 1024 },
      { role: 'representation', path: '/run/converted.h5mu.apb.json', size_bytes: 300 },
      { role: 'tool_timings', path: '/run/converted.timings.json', size_bytes: 200 }
    ]
  }] }
  const row = {
    input_file: 'vendor.tsv', input_file_size_bytes: 1024 ** 2,
    module: 'dia_aif', software_name: 'DIA-NN', record
  }
  const [dataset] = datasetRows(
    { reports: [{ input_file: 'vendor.tsv', path: 'report' }] }, [], [],
    new Map([['report', record]]), new Map(), null
  )
  assert.equal(dataset.output_file_name, 'converted.h5mu')
  const files = new Map([['/run/converted.timings.json', document]])
  const representations = new Map([['/run/converted.h5mu.apb.json', 4200]])
  const [withCounts] = datasetRows(
    { reports: [{ input_file: 'vendor.tsv', path: 'report' }] }, [], [],
    new Map([['report', record]]), new Map(), null, [], representations
  )
  assert.equal(withCounts.ion_variables, 4200)
  const points = chartPoints([withCounts], files, representations)
  assert.equal(points.timings[0].ion_variables, 4200)
  assert.deepEqual(points.timings.map(point => [point.phase, point.duration_seconds]), [
    ['compile', 2.5], ['read', 1.25]
  ])
  assert.equal(points.steps[0].runtime_seconds, 5)
  assert.deepEqual(points.outputs.map(point => point.output_role), ['result'])
  assert.equal(chartViews([withCounts], files, representations)[1].timingViews.length, 1)
  assert.equal(chartViews([withCounts], files, representations)[1].timingViews[0].label, 'apb2 · convert')
  assert.equal(chartViews([withCounts], files, representations)[1].timingViews[0].points.length, 2)
  assert.equal(chartViews([row])[1].timingViews.length, 0)
})

test('dataset variable count follows the latest successful APB representation', () => {
  const record = { steps: [
    { name: 'convert', status: 'succeeded', outputs: [
      { role: 'result', path: '/run/converted.h5ad', size_bytes: 500 },
      { role: 'representation', path: '/run/converted.h5ad.apb.json', size_bytes: 100 }
    ] },
    { name: 'pmultiqc', status: 'succeeded', outputs: [
      { role: 'pmultiqc_report', path: '/run/report.html', size_bytes: 300 }
    ] }
  ] }
  const representations = new Map([['/run/converted.h5ad.apb.json', 25000]])
  const [row] = datasetRows(
    { reports: [{ input_file: 'vendor.tsv', path: 'report' }] }, [], [],
    new Map([['report', record]]), new Map(), null, [], representations
  )
  assert.equal(row.ion_variables, 25000)
  assert.equal(row.output_file_name, 'converted.h5ad')
  assert.equal(chartPoints([row], new Map(), representations).steps.length, 0)
})

test('pMultiQC reports and data remain inspectable while the dataset output identifies its scientific file', () => {
  const record = { steps: [
    { name: 'convert', status: 'succeeded', outputs: [
      { role: 'result', path: '/run/output.h5ad', size_bytes: 500, format: 'h5ad' }
    ] },
    { name: 'pmultiqc', status: 'succeeded', outputs: [
      { role: 'pmultiqc_report', path: '/run/multiqc_report.html', size_bytes: 300 },
      { role: 'pmultiqc_data', path: '/run/multiqc_report_data', size_bytes: 200 }
    ] }
  ] }
  const [row] = datasetRows(
    { reports: [{ input_file: 'vendor.tsv', path: 'report' }] }, [], [],
    new Map([['report', record]]), new Map(), null
  )
  assert.equal(row.output_file_name, 'output.h5ad')
  assert.equal(row.output_file_size_bytes, 500)
  assert.equal(row.output_file_format, 'h5ad')
  assert.deepEqual(datasetArtifacts(row).map(artifact => artifact.path), [
    '/run/output.h5ad', '/run/multiqc_report.html', '/run/multiqc_report_data'
  ])
  assert.deepEqual(chartPoints([row]).outputs.map(point => point.output_role), ['result', 'pmultiqc_report', 'pmultiqc_data'])
})

test('report-only and legacy unlabelled outputs remain available without a scientific artifact', () => {
  for (const output of [
    { role: 'pmultiqc_report', path: '/run/report.html', size_bytes: 300 },
    { path: '/run/legacy.h5ad', size_bytes: 500 }
  ]) {
    const record = { steps: [{ name: 'report', status: 'succeeded', outputs: [
      output, { role: 'tool_timings', path: '/run/timing.json', size_bytes: 50 }
    ] }] }
    const [row] = datasetRows(
      { reports: [{ input_file: 'vendor.tsv', path: 'report' }] }, [], [],
      new Map([['report', record]]), new Map(), null
    )
    assert.equal(row.output_file, output.path)
    assert.equal(row.output_file_size_bytes, output.size_bytes)
  }
})

test('integrated run groups three tool timing files into separate step subtabs', () => {
  const outputs = [
    ['apb2.convert.timings.json', 'apb2', 'convert', 'read'],
    ['apb-fasta.verify-peptides.timings.json', 'apb-fasta', 'verify-peptides', 'verify_peptides'],
    ['apb-proteobench.benchmark.timings.json', 'apb-proteobench', 'benchmark', 'analyze']
  ]
  const files = new Map(outputs.map(([name, tool, operation, phase]) => [
    `/run/timings/${name}`,
    validatedToolTimings({
      format: 'apb-tool-timings', format_version: 1, tool, operation,
      phases: [{ name: phase, seconds: 1.25 }]
    })
  ]))
  const row = {
    input_file: 'vendor.tsv', input_file_size_bytes: 1024 ** 2,
    module: 'dia_aif', software_name: 'DIA-NN',
    record: { steps: [{
      name: 'run', command: ['/tools/apb-proteobench', 'run'],
      status: 'succeeded', runtime_seconds: 8,
      outputs: outputs.map(([name]) => ({
        role: 'tool_timings', path: `/run/timings/${name}`, size_bytes: 200
      }))
    }] }
  }
  const view = chartViews([row], files)[1]
  assert.deepEqual(view.timingViews.map(timing => timing.label), [
    'apb2 · convert', 'apb-fasta · verify-peptides', 'apb-proteobench · benchmark'
  ])
  assert.deepEqual(view.timingViews.map(timing => timing.points[0].phase), [
    'read', 'verify_peptides', 'analyze'
  ])
  assert.equal(view.steps[0].runtime_seconds, 8)
  assert.equal(view.outputs.length, 0)
})

test('viewer exposes corpus charts and frozen input metadata', () => {
  const shell = readFileSync('viewer/src/corpus/shell/corpus-app.ts', 'utf8')
  const application = readFileSync('viewer/src/corpus/app.ts', 'utf8')
  const visualizations = readFileSync('viewer/src/corpus/panels/visualizations.ts', 'utf8')
  const plotly = readFileSync('viewer/src/corpus/render/plotly.ts', 'utf8')
  const styles = readFileSync('viewer/src/corpus/app.css', 'utf8')
  assert.match(shell, /\['visualizations', 'Visualizations'\]/)
  assert.match(shell, /id="visualization-tabs"[^>]*role="tablist"/)
  assert.match(shell, /id="visualization-chart-panel"[^>]*role="tabpanel"/)
  assert.match(shell, /\['input-metadata', 'Input sizes'\]/)
  assert.match(application, /manifest\.input_metadata/)
  assert.match(visualizations, /renderScalePlot/)
  assert.match(visualizations, /timingFacetFigure\(chart\.points, xAxis\)/)
  assert.match(plotly, /Plotly\.react/)
  assert.match(visualizations, /xAxisChoices\(views\)/)
  assert.match(visualizations, /Total workflow runtime \(seconds\)/)
  assert.match(visualizations, /Step runtime \(seconds\)/)
  assert.match(visualizations, /timingView\.label\} phases by/)
  assert.match(visualizations, /Studio timings/)
  assert.match(visualizations, /tool-timing-tabs/)
  assert.match(visualizations, /Peak process-tree RSS \(MiB\)/)
  assert.match(visualizations, /Maximum step peak RSS \(MiB\)/)
  assert.match(visualizations, /Generated artifact size \(MiB\)/)
  assert.match(visualizations, /stepSeries: workflow/)
  assert.match(visualizations, /name: `\$\{step\} · \$\{name\}`/)
  assert.match(visualizations, /let selectedKey/)
  assert.match(visualizations, /if \(tabs\.dataset\.views === signature\) return/)
  assert.match(visualizations, /panel\.querySelectorAll(?:<[^>]+>)?\('\.chart'\)/)
  assert.match(visualizations, /chartLayout\(chart\.x, chart\.y, Boolean\(traces\.length\)\)/)
  assert.match(styles, /\.subtabs\s*\{[^}]*overflow-x:\s*auto/)
})

test('run selection comes from the live server catalog', () => {
  const application = readFileSync('viewer/src/corpus/app.ts', 'utf8')
  const fetching = readFileSync('viewer/src/corpus/lib/fetch.ts', 'utf8')
  assert.match(fetching, /new URL\(`api\/\$\{path\}`/)
  assert.match(application, /await readCatalog\(\)/)
  assert.doesNotMatch(application, /await read\('index\.json'\)/)
})

test('dataset table stays compact while show more exposes every artifact and the persisted report', () => {
  const shell = readFileSync('viewer/src/corpus/shell/corpus-app.ts', 'utf8')
  const application = readFileSync('viewer/src/corpus/app.ts', 'utf8')
  const detail = readFileSync('viewer/src/corpus/panels/detail.ts', 'utf8')
  assert.match(shell, /id="detail-files"/)
  assert.match(detail, /title: 'Input file',[\s\S]*field: 'input_file_name'/)
  assert.match(detail, /title: 'Output',[\s\S]*field: 'output_file_name'/)
  assert.match(detail, /row\.input_file_parent/)
  assert.match(detail, /datasetArtifacts\(row\)/)
  assert.match(detail, /Complete execution report/)
  assert.match(detail, /renderApbMetadata/)
  assert.match(detail, /renderRepresentationJson/)
  assert.match(detail, /renderAnnDataStructure/)
  assert.match(detail, /renderAnnData/)
  assert.match(detail, /renderAnnotationAnnData/)
  assert.match(detail, /representationArtifacts/)
  assert.match(detail, /preferredLoadedRepresentation\(row, loaded\)/)
  assert.match(detail, /artifactAttemptStorePath\(runPath\(\), row\.output_dir, row\.output_file\)/)
  assert.match(detail, /if \(!changed\) return/)
  assert.doesNotMatch(detail, /if \(!changed\) \{[\s\S]*renderDatasetFiles/)
  assert.match(detail, /button\.addEventListener\('click',[\s\S]*void show\(rowForCell\(cell\), true\)/)
  assert.doesNotMatch(detail, /title: 'Step'/)
  assert.doesNotMatch(detail, /title: 'Input file', field: 'input_file'/)
  assert.doesNotMatch(application, /datasetArtifacts|Complete execution report/)
})

test('file details group AnnData objects into subtabs and open their scientific view directly', () => {
  const shell = readFileSync('viewer/src/corpus/shell/corpus-app.ts', 'utf8')
  const detail = readFileSync('viewer/src/corpus/panels/detail.ts', 'utf8')
  const scientific = readFileSync('viewer/src/corpus/render/scientific.ts', 'utf8')
  const styles = readFileSync('viewer/src/corpus/representation.css', 'utf8')
  assert.match(shell, /id="detail-tabs"[^>]*role="tablist"/)
  assert.match(shell, /id="detail-io"[^>]*data-detail-panel="io"[^>]*role="tabpanel"/)
  assert.match(detail, /registerTab\('io', 'Inputs & outputs', ioPanel\)/)
  assert.match(detail, /const panelId = panel\.id \|\| `detail-panel-\$\{key\}`/)
  assert.match(detail, /activeGeneration === generation/)
  assert.match(detail, /artifactStorePath\(selectedRun, row\.output_dir, artifact\.path\)/)
  assert.match(detail, /representationViews\(preferred\.representation\)/)
  assert.match(detail, /registerTab\(`scientific-\$\{view\.key\}`, view\.label/)
  assert.match(detail, /registerTab\('anndata', label, panel/)
  assert.match(detail, /renderTabs\(host, `\$\{label\} objects`, objects\.map/)
  assert.match(detail, /defaultTab = objects\.length \? 'anndata'/)
  assert.match(detail, /app\.select\('files'\)/)
  assert.match(detail, /panel\.setAttribute\('aria-busy', 'true'\)/)
  assert.match(scientific, /renderNestedTabs\(article, `\$\{level\.name\} AnnData sections`/)
  assert.match(scientific, /renderNestedTabs\([\s\S]*'APB metadata scopes'/)
  assert.match(scientific, /\.\.\.level\.layers\.map\(layer => \(\{/)
  assert.match(scientific, /resizeScalePlot\(chart\)/)
  assert.match(scientific, /\['Logical type', layer\.type \?\? 'number'\]/)
  assert.match(scientific, /\['Matrix dtype', layer\.dtype\]/)
  assert.match(styles, /\.detail-subtabs,[\s\S]*\.representation-tabs \{[\s\S]*overflow-x: auto/)
})

test('structured JSON uses the locally bundled tree-viewer component', () => {
  const application = readFileSync('viewer/src/corpus/app.ts', 'utf8')
  const dom = readFileSync('viewer/src/corpus/render/dom.ts', 'utf8')
  const scientific = readFileSync('viewer/src/corpus/render/scientific.ts', 'utf8')
  const adapter = readFileSync('viewer/src/shared/json-viewer.ts', 'utf8')
  assert.match(application, /import '\.\/json-viewer\.css'/)
  assert.match(dom, /document\.createElement\('json-viewer'\)/)
  assert.match(dom, /viewer\.expandAll\(\)/)
  assert.match(dom, /viewer\.collapseAll\(\)/)
  assert.match(scientific, /jsonTree\(scope\.value, \['uns', 'uns\.apb'\]\)/)
  assert.match(adapter, /import '@alenaksu\/json-viewer'/)
})

test('dataset table and sidebar carry status-aware failure styling', () => {
  const shell = readFileSync('viewer/src/corpus/shell/corpus-app.ts', 'utf8')
  const detail = readFileSync('viewer/src/corpus/panels/detail.ts', 'utf8')
  const styles = readFileSync('viewer/src/corpus/app.css', 'utf8')
  assert.match(shell, /id="file-list"/)
  assert.match(detail, /button\.dataset\.status = rowForCell\(cell\)\.status/)
  assert.match(detail, /button\.className = 'file-list-item'/)
  assert.match(detail, /button\.dataset\.status = row\.status/)
  assert.match(styles, /button\[data-status="failed"\]/)
  assert.match(styles, /\.show-more-button\[data-status="failed"\]/)
})

test('corpus composition keeps rendering inside its panels and adapters', () => {
  const shell = readFileSync('viewer/src/corpus/shell/corpus-app.ts', 'utf8')
  const application = readFileSync('viewer/src/corpus/app.ts', 'utf8')
  assert.match(shell, /extends LitElement/)
  assert.match(shell, /createRenderRoot \(\): HTMLElement \{ return this \}/)
  assert.match(application, /createDetailPanel/)
  assert.match(application, /createSettingsPanel/)
  assert.match(application, /createVisualizationPanel/)
  assert.doesNotMatch(application, /Plotly\.|new Tabulator|extends LitElement/)
})

test('every quantitative Plotly chart switches its value axis between linear and log', () => {
  const plotly = readFileSync('viewer/src/corpus/render/plotly.ts', 'utf8')
  const scientific = readFileSync('viewer/src/corpus/render/scientific.ts', 'utf8')
  const visualizations = readFileSync('viewer/src/corpus/panels/visualizations.ts', 'utf8')
  assert.match(plotly, /\['linear', 'Linear'\], \['log', 'Log'\]/)
  assert.match(plotly, /tracesForScale\(state\.traces, scale\)/)
  assert.match(plotly, /yAxesForScale\(state\.layout, scale\)/)
  assert.match(plotly, /Non-positive values hidden; affected whiskers start at Q1/)
  assert.match(plotly, /button\.disabled = !hasData/)
  assert.match(scientific, /renderScalePlot/)
  assert.match(visualizations, /renderScalePlot/)
})
