import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'
import { isolatedSource } from './source.mjs'
import * as model from '../../viewer/src/corpus/model.ts'
import * as representation from '../../viewer/src/corpus/representation.ts'
import * as oddities from '../../viewer/src/corpus/oddities.ts'
import { workflowFlow } from '../../viewer/src/corpus/workflow-flow.ts'

class Element extends EventTarget {
  constructor (tag) {
    super()
    this.tag = tag
    this.children = []
    this.dataset = {}
    this.attributes = new Map()
    this.className = ''
    this.hidden = false
    this._text = ''
  }

  set textContent (value) {
    this._text = String(value)
    this.children = []
  }

  get textContent () {
    return this._text + this.children.map(child => child.textContent).join('')
  }

  append (...children) {
    for (const child of children) {
      child.parent = this
      this.children.push(child)
    }
  }

  prepend (...children) {
    for (const child of children) {
      if (child.parent) child.parent.children = child.parent.children.filter(current => current !== child)
      child.parent = this
    }
    this.children.unshift(...children)
  }

  replaceChildren (...children) {
    this._text = ''
    this.children = []
    this.append(...children)
  }

  setAttribute (name, value) { this.attributes.set(name, String(value)) }
  getAttribute (name) { return this.attributes.get(name) ?? null }
  removeAttribute (name) { this.attributes.delete(name) }
  click () { this.dispatchEvent(new Event('click')) }
  focus () {}

  matches (selector) {
    if (selector.startsWith('.')) return this.className.split(' ').includes(selector.slice(1))
    const match = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/)
    if (!match) return false
    const [, name, value] = match
    const actual = name.startsWith('data-')
      ? this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())]
      : this.getAttribute(name)
    return value === undefined ? actual != null : actual === value
  }

  querySelectorAll (selector) {
    const all = this.children.flatMap(child => [child, ...child.querySelectorAll('*')])
    if (selector === '*') return all
    const [parent, child] = selector.split(' > ')
    return child
      ? all.filter(element => element.matches(child) && element.parent?.matches(parent))
      : all.filter(element => element.matches(selector))
  }

  querySelector (selector) { return this.querySelectorAll(selector)[0] ?? null }
}

function controller (read = async () => scientific()) {
  const hosts = Object.fromEntries([
    'show-more', 'file-list', 'detail-title', 'detail-tabs', 'detail-io',
    'detail-files', 'detail-notices', 'detail-diagnostics', 'detail'
  ].map(id => [id, new Element('div')]))
  hosts['show-more'].append(hosts['detail-title'], hosts['detail-tabs'], hosts['detail-io'], hosts.detail)
  hosts['detail-io'].append(hosts['detail-files'], hosts['detail-notices'], hosts['detail-diagnostics'])
  const calls = []
  const app = { hostFor: id => hosts[id], select: tab => calls.push(tab) }
  const document = { createElement: tag => new Element(tag) }
  const node = (tag, text, className = '') => {
    const element = document.createElement(tag)
    element.textContent = text
    element.className = className
    return element
  }
  const context = {
    document, ...model, ...representation, ...oddities, workflowFlow, node,
    columnTitle: field => field,
    fileUrl: path => path,
    sourceUrl: (run, path) => `${run}/${path}`,
    fileLink: (href, name) => { const link = node('a', name); link.setAttribute('href', href); return link },
    jsonTree: data => node('pre', JSON.stringify(data)),
    renderAnnData: async (host, level) => host.replaceChildren(node('p', `AnnData ${level.name}`)),
    renderAnnotationAnnData: async (host, _, table) => host.replaceChildren(node('p', table.name)),
    renderApbMetadata: async host => host.replaceChildren(node('p', 'Metadata')),
    renderAnnDataStructure: async host => host.replaceChildren(node('p', 'Structure')),
    renderRepresentationJson: host => host.replaceChildren(node('p', 'JSON')),
    resizeDetailCharts: () => {},
    read, app, run: 'corpus/routine/convert/hdf5'
  }
  // Exercise the FASTA renderer with the real table adapter in the same small DOM.
  const fastaRenderer = runInNewContext(
    `${isolatedSource('viewer/src/corpus/render/dom.ts')}\n${isolatedSource('viewer/src/corpus/render/scientific.ts')}\nrenderFastaChecks`,
    { document, ...model, ...representation }
  )
  context.renderFastaChecks = fastaRenderer
  context.renderOdditiesDetail = runInNewContext(
    `${isolatedSource('viewer/src/corpus/render/dom.ts')}\n${isolatedSource('viewer/src/corpus/render/oddities.ts')}\nrenderOdditiesDetail`,
    { document, ...oddities }
  )
  const tabs = isolatedSource('viewer/src/corpus/render/tabs.ts')
  const files = isolatedSource('viewer/src/corpus/render/workflow-files.ts')
  const detail = isolatedSource('viewer/src/corpus/panels/detail.ts')
  const panel = runInNewContext(`${tabs}\n${files}\n${detail}\ncreateDetailPanel(app, read, () => run)`, context)
  return { panel, hosts, calls, context }
}

function scientific (levels = ['ion', 'protein']) {
  return {
    artifact: { physical_format: 'h5mu' },
    levels: levels.map(name => ({ name })),
    root: { apb: {} }
  }
}

function row (name, status = 'succeeded', hasRepresentation = true) {
  return {
    input_file: `inputs/${name}.tsv`, input_file_name: `${name}.tsv`,
    module: 'dda', software_name: name, status, output_dir: `artifacts/${name}`,
    record: { status, steps: [{ name: 'convert', inputs: [], outputs: hasRepresentation
      ? [{ path: `/store/artifacts/${name}/attempt/converted.h5mu.apb.json`, role: 'representation' }]
      : [] }] }
  }
}

const activeTab = hosts => hosts['detail-tabs'].children
  .find(button => button.getAttribute('aria-selected') === 'true')?.dataset.detailTab
const settle = async () => { for (let index = 0; index < 12; index += 1) await Promise.resolve() }

test('sidebar starts with a scientific file and Show more opens AnnData directly', async () => {
  const { panel, hosts, calls } = controller()
  const pending = { ...row('pending'), status: 'pending', record: null }
  const maxquant = row('MaxQuant')
  await panel.refresh([pending, maxquant, row('Sage')])
  await settle()
  assert.deepEqual(calls, [], 'polling must leave the current main tab alone')
  assert.equal(hosts['file-list'].children.length, 3)
  assert.equal(hosts['file-list'].children[1].getAttribute('aria-current'), 'true')
  assert.equal(activeTab(hosts), 'anndata')
  assert.deepEqual(hosts['detail-tabs'].children.map(button => button.textContent), [
    'AnnData', 'Structure', 'Inputs & outputs', 'Oddities', 'APB metadata', 'Representation JSON'
  ])
  const objectTabs = hosts.detail.querySelector('.representation-tabs')
  assert.deepEqual(objectTabs.children.map(button => button.textContent), ['AnnData · ion', 'AnnData · protein'])
  assert.doesNotMatch(hosts.detail.textContent, /Loading view/)
  hosts['detail-tabs'].children.find(button => button.textContent === 'Inputs & outputs').click()
  const action = panel.columns([])[0]
  assert.equal(action.title, 'Open')
  assert.equal(action.frozen, true, 'the first action column remains visible when the dataset table scrolls')
  const button = action.formatter({ getRow: () => ({ getData: () => maxquant }) })
  assert.equal(button.textContent, 'Show more')
  button.click()
  await settle()
  assert.deepEqual(calls, ['files'])
  assert.equal(activeTab(hosts), 'anndata', 'Show more reopens the scientific tab even after IO was selected')
})

test('FASTA check tab shows the recorded reference beside counts and keeps unrecorded counts unknown', async () => {
  const result = scientific(['ion', 'protein'])
  result.root.apb.fasta = { provenance: { peptide_verification: {
    sources: { 0: { path: 'ProteoBenchFASTA_MixedSpecies_HYE.fasta' } }
  } } }
  result.levels[0].apb = { fasta: { result: { peptide_verification: {
    matched_feature_count: 17469, unmatched_feature_count: 12, il_only_matched_feature_count: 9
  } } } }
  const { panel, hosts } = controller(async () => result)
  await panel.refresh([row('FragPipe')])
  assert.equal(activeTab(hosts), 'anndata')
  const tab = hosts['detail-tabs'].children.find(button => button.textContent === 'FASTA check')
  assert.ok(tab)
  tab.click()
  await settle()
  const table = hosts.detail.querySelector('.fasta-checks').querySelector('.scientific-table')
  assert.deepEqual(table.children[1].children[0].children.map(cell => cell.textContent), [
    'ion', 'ProteoBenchFASTA_MixedSpecies_HYE.fasta', '17,469', '12', '9'
  ])
  assert.equal(table.children[1].children.length, 1, 'unchecked protein level is not reported as verified')

  const unknown = scientific(['ion'])
  unknown.levels[0].apb = { fasta: { result: { peptide_verification: {
    matched_feature_count: 0, unmatched_feature_count: 2
  } } } }
  const next = controller(async () => unknown)
  await next.panel.refresh([row('Other')])
  next.hosts['detail-tabs'].children.find(button => button.textContent === 'FASTA check').click()
  await settle()
  const unknownTable = next.hosts.detail.querySelector('.scientific-table')
  assert.deepEqual(unknownTable.children[1].children[0].children.map(cell => cell.textContent), [
    'ion', 'Not recorded', '0', '2', 'Not recorded'
  ])
})

test('chooser shows software, actual file or folder type and size without repeated paths or status lines', async () => {
  const { panel, hosts } = controller()
  const file = {
    ...row('DIA-NN'), input_file: 'submissions/hash/input_file.parquet',
    input_file_name: 'input_file.parquet', input_file_parent: 'hash',
    input_file_kind: 'file', input_file_size_bytes: 1024, status: 'pending'
  }
  const folder = {
    ...row('MaxQuant'), input_file: 'zenodo/maxquant_v2.8.1.0',
    input_file_kind: 'folder', input_file_size_bytes: 1024 ** 2
  }
  await panel.refresh([file, folder])
  const [fileButton, folderButton] = hosts['file-list'].children
  assert.equal(fileButton.textContent, '📄DIA-NNFile · 1.0 KiB')
  assert.equal(folderButton.textContent, '📁MaxQuantFolder · 1.0 MiB')
  assert.doesNotMatch(fileButton.textContent, /input_file|hash|pending|dda/)
  assert.match(fileButton.title, /submissions\/hash\/input_file.parquet/)
  assert.match(fileButton.getAttribute('aria-label'), /DIA-NN, file, 1.0 KiB, pending/)
  assert.equal(fileButton.children.length, 2)

  await panel.refresh([{ ...file, input_file_size_bytes: 2048 }, folder])
  assert.match(hosts['file-list'].children[0].textContent, /2.0 KiB/)
})

test('repeated software shows modules based on the whole run and keeps them when filtering to one entry', async () => {
  const { panel, hosts } = controller()
  const astral = { ...row('DIA-NN'), input_file: 'inputs/astral.tsv', module: 'dia_astral' }
  const dda = { ...row('DIA-NN'), input_file: 'inputs/dda.tsv', module: 'dda_astral' }
  const sage = { ...row('Sage'), module: 'dda_qexactive' }
  await panel.refresh([astral, dda, sage])
  assert.match(hosts['file-list'].children[0].textContent, /DIA-NN· dia_astral/)
  assert.match(hosts['file-list'].children[1].textContent, /DIA-NN· dda_astral/)
  assert.match(hosts['file-list'].children[0].getAttribute('aria-label'), /DIA-NN, dia_astral,/)
  assert.doesNotMatch(hosts['file-list'].children[2].textContent, /dda_qexactive/)

  await panel.refresh([astral, dda, sage], [astral])
  assert.match(hosts['file-list'].children[0].textContent, /DIA-NN· dia_astral/)
  await panel.refresh([astral, sage], [astral])
  assert.doesNotMatch(hosts['file-list'].children[0].textContent, /dia_astral/, 'a changed run must refresh labels even if its visible rows stay the same')
})

test('inputs and outputs render step handoffs, folded supporting files and unavailable outputs without phantom links', async () => {
  const { panel, hosts } = controller(async () => null)
  const input = '/fixtures/inputs/MaxQuant.tsv'
  const converted = '/store/artifacts/MaxQuant/attempt/converted.h5mu'
  const result = '/store/artifacts/MaxQuant/attempt/aggregated.h5mu'
  const record = {
    status: 'failed', steps: [
      { name: 'convert', status: 'succeeded', inputs: [
        { path: input, role: 'vendor_table', size_bytes: 0 },
        { path: '/fixtures/other/MaxQuant.tsv', role: 'vendor_table', size_bytes: 1024 }
      ], outputs: [
        { path: converted, role: 'converted', format: 'hdf5', size_bytes: 2048 },
        { path: '/store/artifacts/MaxQuant/attempt/timings.json', role: 'tool_timings', size_bytes: 100 }
      ] },
      { name: 'aggregate', status: 'failed', inputs: [{ path: converted, role: 'converted' }], outputs: [{ path: result, role: 'result', format: 'hdf5', size_bytes: null }] }
    ]
  }
  await panel.refresh([{ ...row('MaxQuant'), input_file_size_bytes: 4096, record, status: 'failed' }])
  const flow = hosts['detail-files']
  assert.equal(flow.querySelectorAll('.workflow-step-card').length, 2)
  assert.match(flow.textContent, /Used by step 2 · aggregate/)
  assert.match(flow.textContent, /From step 1 · convert/)
  assert.match(flow.textContent, /Vendor data · 0 B/)
  assert.match(flow.textContent, /Result · Not observed/)
  assert.equal(flow.querySelector('.workflow-supporting').getAttribute('open'), null)
  assert.match(flow.querySelector('.workflow-supporting').textContent, /timings.json/)
  const links = flow.querySelectorAll('*').filter(element => element.tag === 'a')
  assert.equal(links.filter(link => link.textContent === 'MaxQuant.tsv').length, 1, 'a companion path must not link to the primary input')
  assert.equal(links.filter(link => link.textContent === 'converted.h5mu').length, 2, 'generated input and output share a download')
  assert.ok(!links.some(link => link.textContent === 'aggregated.h5mu'), 'missing output remains inspectable without a download')
  assert.ok(flow.querySelectorAll('.workflow-file-details').some(details => details.textContent.includes(result)))
})

test('polling retains file, detail tab and object selection; sidebar uses the newest report', async () => {
  const { panel, hosts } = controller()
  const maxquant = row('MaxQuant')
  const sage = row('Sage')
  await panel.refresh([maxquant, sage])
  await settle()
  hosts['file-list'].children[1].click()
  await settle()
  hosts.detail.querySelector('.representation-tabs').children[1].click()
  await settle()
  const replacement = row('Sage')
  replacement.record.note = 'updated'
  await panel.refresh([row('MaxQuant'), replacement])
  await settle()
  assert.equal(hosts['file-list'].children[1].getAttribute('aria-current'), 'true')
  assert.equal(activeTab(hosts), 'anndata')
  assert.equal(hosts.detail.querySelector('.representation-tabs').children[1].getAttribute('aria-selected'), 'true')
  hosts['detail-tabs'].children.find(button => button.textContent === 'Structure').click()
  await panel.refresh([row('MaxQuant'), { ...replacement, record: { ...replacement.record } }])
  await settle()
  assert.equal(activeTab(hosts), 'scientific-anndata-structure')
  const newest = { ...maxquant, record: { ...maxquant.record, note: 'new report' } }
  await panel.refresh([newest, replacement])
  hosts['file-list'].children[0].click()
  await settle()
  assert.match(hosts['detail-diagnostics'].textContent, /new report/)
  panel.reset()
  assert.equal(hosts['file-list'].children.length, 0)
  await panel.refresh([maxquant, replacement])
  assert.equal(activeTab(hosts), 'anndata')
  assert.equal(hosts['file-list'].children[0].getAttribute('aria-current'), 'true')
})

test('chooser filters preserve the opened file, scientific tab and AnnData object', async () => {
  const { panel, hosts, calls } = controller()
  const maxquant = row('MaxQuant')
  const sage = row('Sage')
  await panel.refresh([maxquant, sage])
  await settle()
  hosts.detail.querySelector('.representation-tabs').children[1].click()
  await settle()
  hosts['detail-tabs'].children.find(button => button.textContent === 'Structure').click()

  const replacement = { ...maxquant, record: { ...maxquant.record, note: 'hidden file updated' } }
  await panel.refresh([replacement, sage], [sage])
  await settle()
  assert.deepEqual(hosts['file-list'].children.map(button => button.dataset.inputFile), [sage.input_file])
  assert.equal(hosts['file-list'].children[0].getAttribute('aria-current'), 'false')
  assert.match(hosts['detail-title'].textContent, /MaxQuant/)
  assert.equal(activeTab(hosts), 'scientific-anndata-structure')
  assert.match(hosts['detail-diagnostics'].textContent, /hidden file updated/)
  hosts['detail-tabs'].children.find(button => button.textContent === 'AnnData').click()
  await settle()
  assert.equal(hosts.detail.querySelector('.representation-tabs').children[1].getAttribute('aria-selected'), 'true')
  assert.deepEqual(calls, [], 'filtering must leave the current main tab alone')

  const visibleButton = hosts['file-list'].children[0]
  const newestSage = { ...sage, record: { ...sage.record, note: 'latest filtered report' } }
  await panel.refresh([replacement, newestSage], [newestSage])
  assert.equal(hosts['file-list'].children[0], visibleButton, 'unchanged chooser entries retain their buttons')
  visibleButton.click()
  await settle()
  assert.match(hosts['detail-title'].textContent, /Sage/)
  assert.match(hosts['detail-diagnostics'].textContent, /latest filtered report/)
  assert.equal(visibleButton.getAttribute('aria-current'), 'true')
})

test('an empty filtered chooser differs from an empty run and preserves the opened view', async () => {
  const { panel, hosts } = controller()
  const maxquant = row('MaxQuant')
  await panel.refresh([maxquant])
  await settle()
  await panel.refresh([maxquant], [])
  assert.equal(hosts['file-list'].textContent, 'No files match the filters.')
  assert.match(hosts['detail-title'].textContent, /MaxQuant/)
  assert.equal(activeTab(hosts), 'anndata')
  await panel.refresh([])
  assert.equal(hosts['file-list'].textContent, 'No files in this run.')
  await panel.refresh([maxquant], [])
  assert.equal(hosts['file-list'].textContent, 'No files match the filters.')
})

test('failed, missing and pending representations stay inspectable in inputs and outputs', async () => {
  const { panel, hosts, calls } = controller()
  await panel.show(row('failed', 'failed', false), true)
  assert.equal(activeTab(hosts), 'io')
  assert.match(hosts['detail-notices'].textContent, /This file failed/)
  assert.match(hosts['detail-diagnostics'].textContent, /Complete execution report/)
  await panel.show(row('no-sidecar', 'succeeded', false), true)
  assert.match(hosts['detail-notices'].textContent, /No scientific representation/)
  await panel.show({ ...row('pending'), status: 'pending', record: null }, true)
  assert.match(hosts['detail-notices'].textContent, /This file is pending/)
  assert.deepEqual(calls, ['files', 'files', 'files'])
  const missing = controller(async () => null)
  await missing.panel.show(row('missing'))
  assert.match(missing.hosts['detail-notices'].textContent, /Missing representation/)
  assert.equal(activeTab(missing.hosts), 'io')
})

test('empty levels default to Structure and stale loads cannot replace a newer file', async () => {
  const empty = controller(async () => scientific([]))
  await empty.panel.show(row('structure'))
  assert.equal(activeTab(empty.hosts), 'scientific-anndata-structure')
  let resolveOld
  const old = new Promise(resolve => { resolveOld = resolve })
  const { panel, hosts } = controller(path => path.includes('/old/') ? old : Promise.resolve(scientific(['new'])))
  const oldLoad = panel.show(row('old'))
  await panel.show(row('new'))
  resolveOld(scientific(['old']))
  await oldLoad
  await settle()
  assert.match(hosts['detail-title'].textContent, /new/)
  assert.equal(hosts.detail.querySelector('.representation-tabs').children[0].textContent, 'AnnData · new')
  let resolveRun
  const pending = controller(() => new Promise(resolve => { resolveRun = resolve }))
  const load = pending.panel.show(row('old-run'))
  pending.panel.reset()
  pending.context.run = 'corpus/other/convert/hdf5'
  resolveRun(scientific())
  await load
  assert.equal(pending.hosts.detail.children.length, 0)
  assert.equal(pending.hosts['detail-title'].textContent, 'Select a file to inspect its results')
})

test('Oddities renders source evidence and retains its tab when the summary arrives', async () => {
  const { panel, hosts } = controller()
  const dataset = row('Synthetic')
  await panel.show(dataset)
  hosts['detail-tabs'].children.find(button => button.textContent === 'Oddities').click()
  await settle()
  assert.match(hosts.detail.textContent, /Oddities have not been summarized/)
  const updated = { ...dataset, oddities: {
    input_file: dataset.input_file, available: true, source_step: 'convert', source_status: 'succeeded', notes: [],
    metrics: [
      { scope: 'ion', record: 'parse', name: 'unreadable_cells', label: 'Unreadable numeric cells', value: 12, unit: 'cells', status: 'attention', layer: '' },
      { scope: 'ion', record: 'parse', name: 'effectively_empty_layers', label: 'Effectively empty layers', value: null, unit: 'layers', status: 'not_checked', layer: '' }
    ]
  } }
  await panel.show(updated)
  await settle()
  assert.equal(activeTab(hosts), 'oddities')
  assert.match(hosts.detail.textContent, /Source: convert \(succeeded\)/)
  assert.match(hosts.detail.textContent, /Unreadable numeric cells/)
  assert.match(hosts.detail.textContent, /12 cells/)
  assert.match(hosts.detail.textContent, /Not checked/)
  assert.equal(panel.columns([]).find(column => column.title === 'Oddities').sorter, 'number')
})
