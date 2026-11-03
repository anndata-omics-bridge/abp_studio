import './app.css'
import { Bundle, catalogue_table, catalogues, rule_coverage } from '../shared/apb-catalog.js'
import type { Tabulator } from '../shared/tabulator.js'
import { appFields, COVERAGE_FIELDS, coverage, keyColumns } from './projections/coverage.js'
import { softwareList, versionEntries } from './projections/software.js'
import { cellText, inSet, parseResources, storedView, tableOf, tableView } from './projections/tables.js'
import { mountTable } from './render/tabulator.js'
import './shell/catalog-app.js'
import type { Resource, Row, Tab, Table, TableView } from './types.js'

// Load the bundle once, through apb-catalog-ts. Every tab is a projection of what it
// holds, mounted the first time it is shown and again when the catalogue set changes.
const DATA_ROOT = 'data'

const VIEWS: Tab[] = [
  { id: 'overview', label: 'Overview', group: 'views', sets: 'none' },
  { id: 'meanings', label: 'Meanings', group: 'views', sets: 'one' },
  { id: 'coverage', label: 'Coverage', group: 'views', sets: 'any' },
  { id: 'long', label: 'Long table', group: 'views', sets: 'any' },
  { id: 'software', label: 'Software', group: 'views', sets: 'any' }
]

/** The bundle's manifest: in `data/` beside the viewer, or in the folder `?bundle=` names. */
function manifestUrl (): string {
  const folder = new URLSearchParams(window.location.search).get('bundle') ?? DATA_ROOT
  return new URL('manifest.json', new URL(folder.endsWith('/') ? folder : `${folder}/`, document.baseURI)).href
}

const mounted = new Map<HTMLElement, Tabulator[]>()
const generations = new WeakMap<HTMLElement, number>()

async function show (host: HTMLElement, views: TableView[], select?: (row: Row) => void): Promise<void> {
  const generation = (generations.get(host) ?? 0) + 1
  generations.set(host, generation)
  for (const table of mounted.get(host) ?? []) table.destroy()
  mounted.delete(host)
  host.replaceChildren()
  const tables: Tabulator[] = []
  for (const view of views) {
    tables.push(await mountTable(host, view, select))
    if (generations.get(host) !== generation) {
      for (const stale of tables) stale.destroy()
      return
    }
  }
  mounted.set(host, tables)
}

// What the tabs show, computed from the loaded bundle; apb-catalog-ts answers are kept once asked.
class BundleViews {
  readonly bundle: Bundle
  readonly sets: string[]
  readonly resources: Resource[]
  #coverage: Row[] | null = null
  #long: Table | null = null

  constructor (bundle: Bundle) {
    this.bundle = bundle
    this.sets = catalogues(bundle).map(row => cellText(row.catalogue))
    this.resources = parseResources(bundle.json('catalogues', 'datapackage.json'))
  }

  get tabs (): Tab[] {
    return [...VIEWS, ...this.resources.map(({ name, fields }): Tab => ({ id: `table:${name}`, label: name, group: 'tables', sets: fields.some(field => field.name === 'set') ? 'any' : 'none' }))]
  }

  /** Every set's rule_coverage rows, each with its set. */
  get coverage (): Row[] {
    this.#coverage ??= this.sets.flatMap(set => rule_coverage(this.bundle, set).map(row => ({ set, ...row })))
    return this.#coverage
  }

  /** catalogue_table over every set: one row per entry and software version it applies to. */
  get long (): Table {
    this.#long ??= tableOf(catalogue_table(this.bundle))
    return this.#long
  }

  views (tab: string, set: string): TableView[] {
    switch (tab) {
      case 'overview': return [
        tableView('sets', 'Catalogue sets', 'Each set of the bundle: its purpose, its users and how many entries it holds.', tableOf(catalogues(this.bundle))),
        tableView('bundle', 'Bundle', this.bundle.url.href, {
          columns: ['key', 'value'],
          rows: Object.entries(this.bundle.manifest).map(([key, value]) => ({ key, value }))
        })
      ]
      case 'meanings': return this.meanings(set)
      case 'coverage': return [tableView('coverage', 'Coverage: what a converted result lacks', 'A gap report. Each row is one software version and level, checked against what its set requires (requirements.csv, per level and slot) and naming the keys it has no column for. Read Spectronaut, 19–20, peptidoform_fragment, warn, SHOULD peptidoform_fragment in var as: a Spectronaut 19–20 result, on its fragment level, has no var column for the key peptidoform_fragment, which apb wants with SHOULD. Only sets with requirements appear, today apb and abundance; the columns a result does have are in Meanings.', coverage(inSet(this.coverage, set)), COVERAGE_FIELDS)]
      case 'long': return [tableView('long', 'Long table', 'One row per entry and software version it applies to, as apb-catalog table prints it.', { columns: this.long.columns, rows: inSet(this.long.rows, set) })]
      case 'software': return [tableView('software', 'Software versions', 'The software versions APB2 supports, from versions.csv, one row per level. entries: how many catalogued columns that version writes on that level, in the chosen set; click a row to list them.', this.software(set))]
    }
    const resource = this.resources.find(({ name }) => tab === `table:${name}`)
    if (!resource) throw new Error(`No catalog tab ${tab}`)
    return [storedView(resource, this.bundle.csv('catalogues', resource.path), set)]
  }

  /** One set's answer to "what does each software version call each key?", and the fields its apps write. */
  meanings (set: string): TableView[] {
    const rows = inSet(this.coverage, set)
    const { table, keys } = keyColumns(rows)
    const views = [tableView(`meanings:${set}`, `${set}: column per key`, 'What each software version calls each key of the set, on each level. Empty: not catalogued; missing MUST, SHOULD or MAY: required but not catalogued.', table, keys)]
    const apps = appFields(rows)
    if (apps.rows.length > 0) views.push(tableView(`apps:${set}`, `${set}: written by apps`, 'Fields an app writes after conversion, the same for every software version; they exist once the app has run.', apps))
    return views
  }

  software (set: string): Table {
    return softwareList(this.bundle.csv('catalogues', 'versions.csv'), this.long.rows, inSet(this.long.rows, set))
  }

  detail (level: Row, set: string): TableView[] {
    const entries = versionEntries({ columns: this.long.columns, rows: inSet(this.long.rows, set) }, level)
    const title = `${cellText(level.software)} ${cellText(level.version)}, ${cellText(level.level)}: ${entries.rows.length} entries`
    const where = set === '' ? 'every set' : `set ${set}`
    return [tableView('version', title, `The entries the count names: each a column this version writes on this level, in ${where}. name is the column, key what it means.`, entries)]
  }
}

async function main (): Promise<void> {
  const app = document.querySelector('catalog-app')
  if (!app) throw new Error('Catalog viewer shell is missing')
  try {
    const catalog = new BundleViews(await Bundle.load(manifestUrl()))
    app.sets = catalog.sets
    app.tabs = catalog.tabs
    app.status = `bundle ${catalog.bundle.version} · ${catalog.sets.length} sets · ${catalog.resources.length} stored tables`
    await app.updateComplete
    const report = (error: unknown): void => { app.error = String(error) }
    // The set each tab was last mounted for; a tab shown again for the same set only resizes.
    // A tab whose rows have no set is mounted once, whatever the set.
    const tabs = new Map(catalog.tabs.map(tab => [tab.id, tab]))
    const shown = new Map<string, string>()
    const render = async (): Promise<void> => {
      const tab = app.tab
      const shownTab = tabs.get(tab)
      if (!shownTab) throw new Error(`No catalog tab ${tab}`)
      const set = app.setFor(shownTab)
      if (shown.get(tab) === set) {
        for (const table of mounted.get(app.hostFor(tab)) ?? []) table.redraw()
        return
      }
      shown.set(tab, set)
      const select = tab === 'software'
        ? (level: Row) => { void show(app.hostFor('software-detail'), catalog.detail(level, app.set)).catch(report) }
        : undefined
      await show(app.hostFor(tab), catalog.views(tab, set), select)
    }
    app.addEventListener('tab-change', () => {
      void app.updateComplete.then(() => { window.requestAnimationFrame(() => { void render().catch(report) }) })
    })
    app.addEventListener('set-change', () => {
      void show(app.hostFor('software-detail'), []).then(render).catch(report)
    })
    await render()
  } catch (error) {
    app.error = String(error)
    throw error
  }
}

void main()
