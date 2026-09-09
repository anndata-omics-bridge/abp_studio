import test from 'node:test'
import assert from 'node:assert/strict'
import { chartPoints, counts, datasetArtifacts, datasetRows, executionGroups, formatBytes, statusFractions, workflowFields, workflowSteps } from '../../src/apb_studio/corpus_viewer/web/model.js'
import { apbMetadataScopes, expandEmbeddedJsonForDisplay, layerChart, loadRepresentationArtifacts, preferredLoadedRepresentation, representationArtifacts, representationStorePath, representationViews, validatedRepresentation } from '../../src/apb_studio/corpus_viewer/web/representation.js'
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
    format: 'apb2-result-representation', format_version: '2', artifact: { name: 'result.h5mu' },
    levels: [], annotation_tables: [], feature_relations: []
  })
  assert.equal(document.artifact.name, 'result.h5mu')
  assert.throws(() => validatedRepresentation({ format: document.format, format_version: '1' }), /version/)
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

test('representation display expands known embedded JSON objects and arrays', () => {
  const nestedRule = JSON.stringify({ schema_version: '0.3', software_name: 'Sage' })
  const source = {
    format: 'apb2-result-representation', format_version: '2',
    artifact: { name: 'result.h5ad' }, annotation_tables: [], feature_relations: [],
    levels: [{ uns: {
      rule_json: nestedRule,
      plan_json: JSON.stringify({ level: 'ion', provenance: { rule_json: nestedRule } }),
      search_parameters: JSON.stringify({ enzyme: 'Trypsin/P', allowed_miscleavages: 1 })
    }, metadata: {
      aggregate: JSON.stringify([{
        source_level: 'ion', target_level: 'protein', method: 'mean'
      }])
    } }]
  }

  const displayed = validatedRepresentation(source)

  assert.deepEqual(displayed.levels[0].uns.rule_json, {
    schema_version: '0.3', software_name: 'Sage'
  })
  assert.deepEqual(displayed.levels[0].uns.plan_json, {
    level: 'ion',
    provenance: { rule_json: { schema_version: '0.3', software_name: 'Sage' } }
  })
  assert.deepEqual(displayed.levels[0].uns.search_parameters, {
    enzyme: 'Trypsin/P', allowed_miscleavages: 1
  })
  assert.deepEqual(displayed.levels[0].metadata.aggregate, [{
    source_level: 'ion', target_level: 'protein', method: 'mean'
  }])
  assert.equal(source.levels[0].uns.rule_json, nestedRule)
})

test('embedded JSON display preserves malformed, scalar and unrelated strings', () => {
  const source = {
    rule_json: '{not valid JSON',
    plan_json: '42',
    search_parameters: 'null',
    aggregate: '"mean"',
    note: '{"looks":"like JSON"}',
    existing: { rule_json: ['already', { plan_json: '{"level":"protein"}' }] }
  }

  assert.deepEqual(expandEmbeddedJsonForDisplay(source), {
    rule_json: '{not valid JSON',
    plan_json: '42',
    search_parameters: 'null',
    aggregate: '"mean"',
    note: '{"looks":"like JSON"}',
    existing: { rule_json: ['already', { plan_json: { level: 'protein' } }] }
  })
})

test('representation views separate APB metadata, scientific levels and raw JSON', () => {
  const h5mu = {
    artifact: { name: 'aggregated.h5mu', physical_format: 'h5mu' },
    levels: [{ name: 'protein' }, { name: 'ion' }],
    annotation_tables: [{ name: 'proteins', row_count: 2, key_columns: ['accession'] }]
  }
  const h5muViews = representationViews(h5mu)
  assert.deepEqual(h5muViews.map(({ key, kind, label }) => ({ key, kind, label })), [
    { key: 'apb-metadata', kind: 'apb-metadata', label: 'APB metadata' },
    { key: 'level-0', kind: 'level', label: 'AnnData · ion' },
    { key: 'level-1', kind: 'level', label: 'AnnData · protein' },
    { key: 'annotation-0', kind: 'annotation', label: 'AnnData · annotation/proteins' },
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

test('APB metadata scopes preserve the physical uns namespace and level ownership', () => {
  const representation = {
    artifact: { physical_format: 'h5mu' },
    shared: { uns: { produced_by: 'apb2' }, metadata: { annotation: { version: 1 } } },
    levels: [
      { name: 'ion', uns: { rule_json: { software_name: 'FragPipe' } }, metadata: {} },
      { name: 'protein', uns: { plan_json: { level: 'protein' } }, metadata: { aggregate: [] } }
    ]
  }

  assert.deepEqual(apbMetadataScopes(representation), [
    {
      label: 'MuData',
      value: { uns: { apb: { parse: { produced_by: 'apb2' }, annotation: { version: 1 } } } }
    },
    {
      label: 'ion',
      value: { uns: { apb: {
        parse: { rule_json: { software_name: 'FragPipe' } }, annotation: { version: 1 }
      } } }
    },
    {
      label: 'protein',
      value: { uns: { apb: {
        parse: { plan_json: { level: 'protein' } }, annotation: { version: 1 }, aggregate: []
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
    representationStorePath('run-id', 'artifacts/hash', artifacts[0].path),
    'run-id/artifacts/hash/uuid/converted.h5ad.apb.json'
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

test('execution settings own saved runs and unconfigured historical runs stay hidden', () => {
  const config = { workflow: 'convert', format: 'hdf5', corpus: '/corpuses/routine.csv', workflow_table: null, cores: 2 }
  const runs = [
    { path: 'a/run.json', manifest: { settings_id: 'routine' } },
    { path: 'b/run.json', manifest: { settings_id: 'routine' } },
    { path: 'c/run.json', manifest: { settings_id: 'all' } },
    { path: 'old/run.json', manifest: {} }
  ]
  const settings = new Map([['routine', config], ['all', { ...config, corpus: '/corpuses/all.csv' }]])
  const groups = executionGroups(runs, settings)
  assert.deepEqual(groups.map(group => group.runs.length), [2, 1])
  assert.match(groups[0].label, /routine.csv/)
  assert.equal(groups[0].settings.workflow_table, null)
  assert.ok(groups.every(group => group.settings))
})

test('execution settings remain selectable before their first run', () => {
  const config = { workflow: 'convert', format: 'hdf5', corpus: '/corpuses/all.csv', workflow_table: null, cores: 2 }
  const groups = executionGroups([], new Map([['full', config]]))
  assert.equal(groups.length, 1)
  assert.equal(groups[0].runs.length, 0)
  assert.equal(groups[0].settings.corpus, '/corpuses/all.csv')
})

test('settings use bounded sub-tabs while file links remain outside them', () => {
  const html = readFileSync('src/apb_studio/corpus_viewer/web/index.html', 'utf8')
  assert.equal((html.match(/data-settings-tab=/g) ?? []).length, 6)
  assert.equal((html.match(/class="settings-panel"/g) ?? []).length, 6)
  assert.ok(html.indexOf('id="links"') < html.indexOf('aria-label="Settings and input views"'))
  const stylesheet = html.match(/app\.css\?v=([^"']+)/)?.[1]
  const script = html.match(/app\.js\?v=([^"']+)/)?.[1]
  assert.equal(stylesheet, script)
})

test('run selectors share a compact row below the branding banner', () => {
  const html = readFileSync('src/apb_studio/corpus_viewer/web/index.html', 'utf8')
  const styles = readFileSync('src/apb_studio/corpus_viewer/web/app.css', 'utf8')
  assert.ok(html.indexOf('</header>') < html.indexOf('class="run-controls"'))
  assert.match(html, /class="run-controls"[\s\S]*id="execution"[\s\S]*id="run"[\s\S]*<\/section>/)
  assert.match(styles, /\.run-controls\{[^}]*grid-template-columns:repeat\(2/)
  assert.match(styles, /header\{padding:7px/)
  assert.match(styles, /section\.summary\{[^}]*padding:7px 14px/)
})

test('chart projection preserves per-step and per-output evidence without inventing zeroes', () => {
  const record = {
    steps: [
      {
        name: 'convert', status: 'succeeded', runtime_seconds: 1.5, peak_memory_bytes: 5 * 1024 ** 2,
        outputs: [{ role: 'converted', path: '/result.h5mu', size_bytes: 3 * 1024 ** 2 }]
      },
      {
        name: 'aggregate', status: 'failed', runtime_seconds: 0.75, peak_memory_bytes: 2 * 1024 ** 2,
        outputs: [{ role: 'aggregated', path: '/missing.h5mu', size_bytes: null }]
      },
      { name: 'later', status: 'skipped', runtime_seconds: null, peak_memory_bytes: null, outputs: [] }
    ]
  }
  const rows = [{
    input_file: 'vendor.tsv', input_file_size_bytes: String(10 * 1024 ** 2),
    module: 'dia_aif', software_name: 'DIA-NN', record
  }]

  const points = chartPoints(rows)

  assert.equal(points.steps.length, 2)
  assert.deepEqual(points.steps.map(point => point.status), ['succeeded', 'failed'])
  assert.equal(points.steps[0].input_size_mib, 10)
  assert.equal(points.steps[0].peak_memory_mib, 5)
  assert.equal(points.outputs.length, 1)
  assert.equal(points.outputs[0].output_size_mib, 3)
  assert.deepEqual(chartPoints([{ ...rows[0], input_file_size_bytes: '' }]).steps.map(point => point.input_size_mib), [null, null])
})

test('viewer exposes corpus charts and frozen input metadata', () => {
  const html = readFileSync('src/apb_studio/corpus_viewer/web/index.html', 'utf8')
  const application = readFileSync('src/apb_studio/corpus_viewer/web/app.js', 'utf8')
  assert.match(html, /data-tab="visualizations"/)
  assert.match(html, /id="runtime-chart"/)
  assert.match(html, /id="memory-chart"/)
  assert.match(html, /id="output-chart"/)
  assert.match(html, /data-settings-tab="input-metadata"/)
  assert.match(application, /manifest\.input_metadata/)
  assert.match(application, /Plotly\.react/)
  assert.match(application, /Vendor input size \(MiB\)/)
  assert.match(application, /Runtime \(seconds\)/)
  assert.match(application, /Peak process-tree RSS \(MiB\)/)
  assert.match(application, /Generated artifact size \(MiB\)/)
  assert.match(application, /xaxis: \{ title: \{ text: xTitle, standoff: 14 \}, automargin: true/)
  assert.match(application, /yaxis: \{ title: \{ text: yTitle, standoff: 12 \}, automargin: true/)
})

test('dataset table stays compact while show more exposes every artifact and the persisted report', () => {
  const html = readFileSync('src/apb_studio/corpus_viewer/web/index.html', 'utf8')
  const application = readFileSync('src/apb_studio/corpus_viewer/web/app.js', 'utf8')
  assert.match(html, /id="detail-files"/)
  assert.match(application, /title: 'Input file', field: 'input_file_name'/)
  assert.match(application, /title: 'Output', field: 'output_file_name'/)
  assert.match(application, /fileCell\(row\.input_file, row\.input_file_name, row\.input_file_parent, row\.input_file_size_bytes\)/)
  assert.match(application, /row\.input_file_parent/)
  assert.match(application, /datasetArtifacts\(row\)/)
  assert.match(application, /Complete execution report/)
  assert.match(application, /renderApbMetadata/)
  assert.match(application, /renderRepresentationJson/)
  assert.match(application, /renderAnnData/)
  assert.match(application, /renderAnnotationAnnData/)
  assert.match(application, /representationArtifacts/)
  assert.match(application, /preferredLoadedRepresentation\(row, loaded\)/)
  assert.match(application, /button\.addEventListener\('click',[\s\S]*detail\(cell\.getRow\(\)\.getData\(\), true\)/)
  assert.doesNotMatch(application, /title: 'Step'/)
  assert.doesNotMatch(application, /title: 'Input file', field: 'input_file'/)
})

test('show more presents top-level metadata, AnnData and raw JSON tabs with nested layer tabs', () => {
  const html = readFileSync('src/apb_studio/corpus_viewer/web/index.html', 'utf8')
  const application = readFileSync('src/apb_studio/corpus_viewer/web/app.js', 'utf8')
  const styles = readFileSync('src/apb_studio/corpus_viewer/web/representation.css', 'utf8')
  assert.match(html, /id="detail-tabs"[^>]*role="tablist"/)
  assert.match(html, /id="detail-io"[^>]*data-detail-panel="io"[^>]*role="tabpanel"/)
  assert.match(application, /registerDetailTab\('io', 'Inputs & outputs', ioPanel\)/)
  assert.match(application, /const panelId = panel\.id \|\| `detail-panel-\$\{key\}`/)
  assert.match(application, /\(\) => generation === state\.detailGeneration/)
  assert.match(application, /const detailRun = state\.run[\s\S]*representationStorePath\(detailRun/)
  assert.match(application, /async function loadRun \(path\) \{\n  resetDetailTabs\(\)[\s\S]*state\.manifest = await read\(path\)/)
  const loadRun = application.slice(application.indexOf('async function loadRun'), application.indexOf('async function loadConfiguration'))
  assert.ok(loadRun.indexOf('mounted.destroy()') < loadRun.indexOf('await read(path)'))
  assert.match(application, /representationViews\(selected\.representation\)/)
  assert.match(application, /registerDetailTab\(`scientific-\$\{view\.key\}`, view\.label/)
  assert.match(application, /panel\.setAttribute\('aria-busy', 'true'\)/)
  assert.match(application, /renderNestedTabs\(article, `\$\{level\.name\} AnnData sections`/)
  assert.match(application, /renderNestedTabs\([\s\S]*'APB metadata scopes'/)
  assert.match(application, /await renderApbMetadata/)
  assert.match(application, /\.\.\.level\.layers\.map\(layer => \(\{/)
  assert.match(application, /Plotly\.Plots\.resize\(chart\)/)
  assert.match(styles, /\.detail-subtabs \{[\s\S]*overflow-x: auto/)
  assert.match(styles, /\.representation-tabs \{[\s\S]*overflow-x: auto/)
})

test('structured JSON uses the pinned tree-viewer component', () => {
  const html = readFileSync('src/apb_studio/corpus_viewer/web/index.html', 'utf8')
  const application = readFileSync('src/apb_studio/corpus_viewer/web/app.js', 'utf8')
  const adapter = readFileSync('src/apb_studio/corpus_viewer/web/vendor/json-viewer.js', 'utf8')
  assert.match(html, /json-viewer\.css\?v=14/)
  assert.match(application, /document\.createElement\('json-viewer'\)/)
  assert.match(application, /viewer\.expandAll\(\)/)
  assert.match(application, /viewer\.collapseAll\(\)/)
  assert.match(application, /jsonTree\(scope\.value, \['uns', 'uns\.apb', 'uns\.apb\.parse'\]\)/)
  assert.match(adapter, /@alenaksu\/json-viewer@2\.1\.2/)
})

test('dataset navigation carries status-aware failure styling', () => {
  const application = readFileSync('src/apb_studio/corpus_viewer/web/app.js', 'utf8')
  const styles = readFileSync('src/apb_studio/corpus_viewer/web/app.css', 'utf8')
  assert.match(application, /showMoreTab\.dataset\.status = row\.status/)
  assert.match(application, /button\.dataset\.status = cell\.getRow\(\)\.getData\(\)\.status/)
  assert.match(styles, /button\[data-status=failed\]\[aria-selected=true\]/)
  assert.match(styles, /\.show-more-button\[data-status=failed\]/)
})
