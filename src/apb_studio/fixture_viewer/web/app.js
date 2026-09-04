import { fetchCsv, fetchJson, fetchText } from './lib/fetch.js'
import { joinSubmissions, parseSubmissionJson, storageRows, summaryPath } from './lib/store.js'
import { catalogView } from './panels/catalog.js'
import { detailViews } from './panels/detail.js'
import { resourcesView } from './panels/resources.js'
import { storageView } from './panels/storage.js'
import { rendererFor } from './render/index.js'
import './shell/fixture-app.js'

// Composition root. Reads the store's tables, hands them to the pure panels, and
// mounts the resulting views into the shell's hosts. Nothing here computes a
// proteomics fact; the Python script wrote them all.
//
// The store is read once, when the page loads: the catalogue, the two tables, and one
// summary document per submission, whose presence is that submission's download status.
// Reload to see what a running command has written since.

const DATA_ROOT = 'data'

// How many summary documents to ask for at once. The store's own files are small; this
// only keeps a 200-submission store from opening 200 sockets in one breath.
const FETCH_WIDTH = 12

/**
 * Build an absolute URL below the data root.
 *
 * @param {...string} parts Path segments.
 * @returns {string} The URL.
 */
function dataUrl (...parts) {
  return new URL([DATA_ROOT, ...parts].join('/'), document.baseURI).href
}

/** @type {Map<HTMLElement, Array<{renderer: object, handle: object}>>} */
const mounted = new Map()

/**
 * Replace whatever a host shows with new views.
 *
 * @param {HTMLElement} host The panel host.
 * @param {object[]} views Views in display order.
 * @returns {Promise<void>} Resolves when every view is mounted.
 */
async function show (host, views) {
  for (const { renderer, handle } of mounted.get(host) ?? []) renderer.destroy(handle)
  const handles = []
  for (const view of views) {
    const renderer = rendererFor(view.backend)
    handles.push({ renderer, handle: await renderer.mount(host, view) })
  }
  mounted.set(host, handles)
}

/**
 * Re-measure the tables inside a host that has just become visible.
 *
 * @param {HTMLElement} host The panel host.
 */
function resize (host) {
  for (const { renderer, handle } of mounted.get(host) ?? []) renderer.resize(handle)
}

/**
 * Load one submission's files and show them in the detail host.
 *
 * @param {HTMLElement} app The shell.
 * @param {object} row The joined submission row.
 * @returns {Promise<void>} Resolves when the detail is shown.
 */
async function showDetail (app, row) {
  const [metadata, parameters] = await Promise.all([
    fetchText(dataUrl('metadata', row.repo_name, `${row.intermediate_hash}.json`)),
    row.parameter_file ? fetchText(dataUrl(...row.parameter_file.split('/'))) : ''
  ])
  await show(app.hostFor('detail'), detailViews(row, parseSubmissionJson(metadata), parameters))
}

/**
 * Ask for every catalogued submission's summary, a few at a time.
 *
 * A summary that is not there answers "not downloaded", which is why absence is not an
 * error here.
 *
 * @param {object[]} catalog Rows of catalog.csv.
 * @param {string} pattern The index's `submissionSummary` pattern.
 * @returns {Promise<Map<string, object|null>>} Summaries by submission hash.
 */
async function fetchSummaries (catalog, pattern) {
  const found = new Map()
  // Without a pattern every URL below would collapse to the data root, which answers with
  // index.json — and every submission would read as downloaded. Nothing is safer to assume.
  if (!pattern.includes('{intermediate_hash}')) return found
  for (let start = 0; start < catalog.length; start += FETCH_WIDTH) {
    const batch = catalog.slice(start, start + FETCH_WIDTH)
    const documents = await Promise.all(
      batch.map((row) => fetchJson(dataUrl(summaryPath(pattern, row))))
    )
    batch.forEach((row, index) => {
      if (documents[index]) found.set(row.intermediate_hash, documents[index])
    })
  }
  return found
}

/**
 * Read the store and put it on screen.
 *
 * @param {HTMLElement} app The shell.
 * @param {object|null} index The index document naming the store's files.
 * @returns {Promise<void>} Resolves once every panel is mounted.
 */
async function refresh (app, index) {
  const [catalog, downloads, resources] = await Promise.all([
    fetchCsv(dataUrl('catalog.csv')),
    fetchCsv(dataUrl('downloads.csv')),
    fetchCsv(dataUrl('resources.csv'))
  ])
  const pattern = index?.submissionSummary ?? ''
  if (index && !pattern) {
    app.error = 'index.json names no submissionSummary pattern: rewrite it with a writing command'
  }
  const summaries = await fetchSummaries(catalog, pattern)
  const submissions = joinSubmissions(catalog, downloads, summaries)
  const events = { rowClick: (_event, tableRow) => showDetail(app, tableRow.getData()) }
  const downloaded = [...summaries.values()]
  await Promise.all([
    show(app.hostFor('catalog'), [catalogView(submissions, events)]),
    show(app.hostFor('resources'), [resourcesView(resources)]),
    show(app.hostFor('storage'), [storageView(storageRows(index, downloaded))])
  ])
  app.status = `${submissions.length} submissions catalogued · ${downloaded.length} on disk`
}

/**
 * Start the viewer.
 *
 * @returns {Promise<void>} Resolves once every panel is mounted.
 */
async function main () {
  const app = document.querySelector('fixture-app')
  await app.updateComplete
  app.addEventListener('tab-change', () => {
    window.requestAnimationFrame(() => {
      for (const id of ['catalog', 'resources', 'storage']) resize(app.hostFor(id))
    })
  })
  try {
    const index = await fetchJson(dataUrl('index.json'))
    await refresh(app, index)
  } catch (error) {
    app.error = String(error)
    throw error
  }
}

main()
