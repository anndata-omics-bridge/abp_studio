import './app.css'
import { fetchCsv, fetchJson, fetchText } from './lib/fetch.js'
import { joinSubmissions, parseStoreIndex, parseSubmissionJson, parseSummary, storageRows, summaryPath } from './lib/store.js'
import { catalogView } from './panels/catalog.js'
import { detailViews } from './panels/detail.js'
import { DEFAULT_GROUP, GROUPS, overviewViews } from './panels/overview.js'
import { resourcesView } from './panels/resources.js'
import { storageView } from './panels/storage.js'
import { mountView } from './render/index.js'
import type { FixtureApp } from './shell/fixture-app.js'
import './shell/fixture-app.js'
import type { CsvRow, MountedView, StoreIndex, Submission, SubmissionSummary, TableEvents, View } from './types.js'

// Read the catalogue and persisted acquisition evidence once on load. Regrouping
// uses the loaded rows; a reload sees newly acquired fixtures.
const DATA_ROOT = 'data'
const FETCH_WIDTH = 12

function dataUrl (...parts: string[]): string {
  return new URL([DATA_ROOT, ...parts].join('/'), document.baseURI).href
}

const mounted = new Map<HTMLElement, MountedView[]>()
const generations = new WeakMap<HTMLElement, number>()
let submissions: Submission[] = []
let detailGeneration = 0

async function show (host: HTMLElement, views: View[]): Promise<void> {
  const generation = (generations.get(host) ?? 0) + 1
  generations.set(host, generation)
  for (const view of mounted.get(host) ?? []) view.destroy()
  mounted.delete(host)
  const handles: MountedView[] = []
  try {
    for (const view of views) {
      const handle = await mountView(host, view)
      handles.push(handle)
      if (generations.get(host) !== generation) {
        for (const stale of handles) stale.destroy()
        return
      }
    }
    mounted.set(host, handles)
  } catch (error) {
    for (const handle of handles) handle.destroy()
    throw error
  }
}

function resize (host: HTMLElement): void {
  for (const view of mounted.get(host) ?? []) view.resize()
}

async function showDetail (app: FixtureApp, row: Submission): Promise<void> {
  const generation = ++detailGeneration
  const [metadata, parameters] = await Promise.all([
    fetchText(dataUrl('metadata', row.repo_name, `${row.intermediate_hash}.json`)),
    row.parameter_file ? fetchText(dataUrl(...row.parameter_file.split('/'))) : ''
  ])
  if (generation !== detailGeneration) return
  await show(app.hostFor('detail'), detailViews(row, parseSubmissionJson(metadata), parameters))
}

async function fetchSummaries (catalog: CsvRow[], pattern: string): Promise<Map<string, SubmissionSummary>> {
  const found = new Map<string, SubmissionSummary>()
  // Without the hash placeholder the URL could resolve to the data-root index.
  if (!pattern.includes('{intermediate_hash}')) return found
  for (let start = 0; start < catalog.length; start += FETCH_WIDTH) {
    const batch = catalog.slice(start, start + FETCH_WIDTH)
    const documents = await Promise.all(batch.map(async (row) => parseSummary(await fetchJson(dataUrl(summaryPath(pattern, row))))))
    batch.forEach((row, index) => {
      const summary = documents[index]
      if (summary) found.set(row.intermediate_hash ?? '', summary)
    })
  }
  return found
}

async function refresh (app: FixtureApp, index: StoreIndex | null): Promise<void> {
  const [catalog, downloads, resources] = await Promise.all([
    fetchCsv(dataUrl('catalog.csv')),
    fetchCsv(dataUrl('downloads.csv')),
    fetchCsv(dataUrl('resources.csv'))
  ])
  const pattern = index?.submissionSummary ?? ''
  if (index && !pattern) app.error = 'index.json names no submissionSummary pattern: rewrite it with a writing command'
  const summaries = await fetchSummaries(catalog, pattern)
  submissions = joinSubmissions(catalog, downloads, summaries)
  // Resolve clicks against the rows we supplied, rather than trusting untyped
  // third-party table data to satisfy the submission contract.
  const byHash = new Map(submissions.map((row) => [row.intermediate_hash, row]))
  const events: TableEvents = {
    rowClick: (_event, tableRow) => {
      const index: unknown = tableRow.getIndex()
      if (typeof index !== 'string') return
      const row = byHash.get(index)
      if (row) void showDetail(app, row).catch((error: unknown) => { app.error = String(error) })
    }
  }
  const downloaded = [...summaries.values()]
  await Promise.all([
    show(app.hostFor('catalog'), [catalogView(submissions, events)]),
    show(app.hostFor('overview'), overviewViews(submissions, app.group)),
    show(app.hostFor('resources'), [resourcesView(resources)]),
    show(app.hostFor('storage'), [storageView(storageRows(index, downloaded))])
  ])
  app.status = `${submissions.length} submissions catalogued · ${downloaded.length} on disk`
}

async function main (): Promise<void> {
  const app = document.querySelector('fixture-app')
  if (!app) throw new Error('Fixture viewer shell is missing')
  app.groups = GROUPS
  app.group = DEFAULT_GROUP
  await app.updateComplete
  app.addEventListener('group-change', (event) => {
    void show(app.hostFor('overview'), overviewViews(submissions, event.detail.group)).catch((error: unknown) => { app.error = String(error) })
  })
  app.addEventListener('tab-change', async () => {
    await app.updateComplete
    window.requestAnimationFrame(() => {
      resize(app.hostFor(app.tab))
      if (app.tab === 'catalog') resize(app.hostFor('detail'))
    })
  })
  try {
    const index = parseStoreIndex(await fetchJson(dataUrl('index.json')))
    await refresh(app, index)
  } catch (error) {
    app.error = String(error)
    throw error
  }
}

void main()
