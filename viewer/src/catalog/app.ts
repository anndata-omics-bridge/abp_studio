import './app.css'
import { Bundle, Catalog, catalogue_table, catalogues, DataCatalog, MissingRequiredField, read_parsed_levels, rule_coverage, UnresolvedField } from '../shared/apb-catalog.js'
import type { Tabulator } from '../shared/tabulator.js'
import { appFields, COVERAGE_FIELDS, coverage, keyColumns } from './projections/coverage.js'
import { softwareList, versionEntries } from './projections/software.js'
import { layerTable } from './projections/console.js'
import { CatalogDraft, parseRuleLevels, parseSchemas, READ_ONLY } from './projections/editor.js'
import type { Cells } from './projections/editor.js'
import { cellText, chosen, levelsOf, LOCATIONS, parseResources, storedView, tableOf, tableView } from './projections/tables.js'
import { mountConsole } from './render/console.js'
import { download, mountEditor } from './render/editor.js'
import { mountTable } from './render/tabulator.js'
import './shell/catalog-app.js'
import type { Filter, Resource, Row, Tab, Table, TableView } from './types.js'

// Load the bundle once, through apb-catalog-ts. Every tab is a projection of what it
// holds, mounted the first time it is shown and again when the set, level or location changes.
const DATA_ROOT = 'data'

const VIEWS: Tab[] = [
  { id: 'overview', label: 'Overview', group: 'views', sets: 'none', levels: false, locations: false },
  { id: 'meanings', label: 'Meanings', group: 'views', sets: 'one', levels: true, locations: true },
  { id: 'coverage', label: 'Coverage', group: 'views', sets: 'any', levels: true, locations: true },
  { id: 'long', label: 'Long table', group: 'views', sets: 'any', levels: true, locations: true },
  { id: 'software', label: 'Software', group: 'views', sets: 'any', levels: true, locations: true }
]

/** The bundle's manifest: in `data/` beside the viewer, or in the folder `?bundle=` names. */
function manifestUrl (): string {
  const folder = new URLSearchParams(window.location.search).get('bundle') ?? DATA_ROOT
  return new URL('manifest.json', new URL(folder.endsWith('/') ? folder : `${folder}/`, document.baseURI)).href
}

/** The rules bundle the rules viewer publishes beside this one, or the one `?rules=` names: the
 * columns APB2 writes, offered as the names a catalog row may map. */
function rulesUrl (): string {
  return new URL(new URLSearchParams(window.location.search).get('rules') ?? '../apb-rules/data/levels.json', document.baseURI).href
}

/** The converted APB results published beside the viewer, in `results/`, which `index.json` names;
 * none where no `index.json` is published. `result(name)` is one's manifest URL, for read_parsed_levels. */
async function resultsScope (): Promise<Record<string, unknown>> {
  const folder = new URL('results/', document.baseURI)
  const response = await fetch(new URL('index.json', folder))
  const results: unknown = response.ok ? await response.json() : []
  return {
    results,
    result: (name: string): string => new URL(`${name}.parquet/manifest.json`, folder).href,
    layerTable
  }
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
    return [...this.resources.map(({ name, fields }): Tab => {
      const has = (column: string): boolean => fields.some(field => field.name === column)
      return {
        id: `table:${name}`,
        label: name,
        group: 'tables',
        sets: has('set') ? 'any' : 'none',
        levels: has('level') || has('location'),
        locations: has('location')
      }
    }), ...VIEWS, ...this.resources.map(({ name, fields }): Tab => ({
      id: `edit:${name}`,
      label: READ_ONLY.includes(name) ? `${name} (read only)` : name,
      group: 'editor',
      sets: fields.some(field => field.name === 'set') ? 'any' : 'none',
      levels: false,
      locations: false
    })), { id: 'console', label: 'console', group: 'console', sets: 'none', levels: false, locations: false }]
  }

  /** What the API console's code may name: the apb-catalog-ts API, the loaded bundle, and the
   * editor's draft. read_parsed_levels and DataCatalog read the converted results resultsScope
   * names. */
  get scope (): Record<string, unknown> {
    return { bundle: this.bundle, Bundle, Catalog, DataCatalog, read_parsed_levels, catalogues, rule_coverage, catalogue_table, UnresolvedField, MissingRequiredField, editor: this.draft }
  }

  #draft: CatalogDraft | null = null

  /** The editor's draft: the stored tables as loaded, then as edited. */
  get draft (): CatalogDraft {
    this.#draft ??= new CatalogDraft(
      parseSchemas(this.bundle.json('catalogues', 'datapackage.json')),
      new Map(this.resources.map(({ name, path }) => [name, this.bundle.csv('catalogues', path).rows as Cells[]]))
    )
    return this.#draft
  }

  /** Save every set's tables with datapackage.json, or one set's tables, as a zip. */
  save (set: string): void {
    const files = this.draft.files(set)
    if (set === '') files.push({ name: 'datapackage.json', text: `${JSON.stringify(this.bundle.json('catalogues', 'datapackage.json'), null, 2)}\n` })
    download(set === '' ? 'apb-catalog-tables.zip' : `apb-catalog-${set}.zip`, files)
  }

  /** The levels the entries name, protein first. */
  get levels (): string[] {
    return levelsOf(this.long.rows)
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

  views (tab: string, filter: Filter): TableView[] {
    switch (tab) {
      case 'overview': return [
        tableView('sets', 'Catalogue sets', 'Each set of the bundle: its purpose, its users and how many entries it holds.', tableOf(catalogues(this.bundle))),
        tableView('bundle', 'Bundle', this.bundle.url.href, {
          columns: ['key', 'value'],
          rows: Object.entries(this.bundle.manifest).map(([key, value]) => ({ key, value }))
        })
      ]
      case 'meanings': return this.meanings(filter)
      case 'coverage': return [tableView('coverage', 'Coverage: what a converted result lacks', 'A gap report. Each row is one software version and level, checked against what its set requires (requirements.csv, per level and slot) and naming the keys it has no column for. Read Spectronaut, 19–20, peptidoform_fragment, warn, recommended peptidoform_fragment in var as: a Spectronaut 19–20 result, on its fragment level, has no var column for the key peptidoform_fragment, which apb recommends. Only sets with requirements appear, today apb and abundance; the columns a result does have are in Meanings.', coverage(chosen(this.coverage, filter)), COVERAGE_FIELDS)]
      case 'long': return [tableView('long', 'Long table', 'One row per entry and software version it applies to, as apb-catalog table prints it.', { columns: this.long.columns, rows: chosen(this.long.rows, filter) })]
      case 'software': return [tableView('software', 'Software versions', 'The software versions APB2 supports, from versions.csv, one row per level. entries: how many catalogued columns that version writes on that level, in the chosen set and location; click a row to list them.', this.software(filter))]
    }
    const resource = this.resources.find(({ name }) => tab === `table:${name}`)
    if (!resource) throw new Error(`No catalog tab ${tab}`)
    return [storedView(resource, this.bundle.csv('catalogues', resource.path), filter)]
  }

  /** One set's answer to "what does each software version call each key?", and the fields its apps write. */
  meanings (filter: Filter): TableView[] {
    const { set } = filter
    const rows = chosen(this.coverage, filter)
    const { table, keys } = keyColumns(rows)
    const views = [tableView(`meanings:${set}`, `${set}: column per key`, 'What each software version calls each key of the set, on each level. Empty: not catalogued; missing required, recommended or optional: asked for by the set but not catalogued.', table, keys)]
    const apps = appFields(rows)
    if (apps.rows.length > 0) views.push(tableView(`apps:${set}`, `${set}: written by apps`, 'Fields an app writes after conversion, the same for every software version; they exist once the app has run.', apps))
    return views
  }

  /** Each version's levels, the chosen level only; entries counts what the whole filter chooses. */
  software (filter: Filter): Table {
    const levels = chosen(this.long.rows, { set: '', level: filter.level, location: '' })
    return softwareList(this.bundle.csv('catalogues', 'versions.csv'), levels, chosen(this.long.rows, filter))
  }

  detail (level: Row, filter: Filter): TableView[] {
    const { set, location } = filter
    const entries = versionEntries({ columns: this.long.columns, rows: chosen(this.long.rows, { ...filter, level: '' }) }, level)
    const title = `${cellText(level.software)} ${cellText(level.version)}, ${cellText(level.level)}: ${entries.rows.length} entries`
    const where = `${set === '' ? 'every set' : `set ${set}`}${location === '' ? '' : `, ${location} only`}`
    return [tableView('version', title, `The entries the count names: each a column this version writes on this level, in ${where}. name is the column, key what it means.`, entries)]
  }
}

async function main (): Promise<void> {
  const app = document.querySelector('catalog-app')
  if (!app) throw new Error('Catalog viewer shell is missing')
  try {
    const catalog = new BundleViews(await Bundle.load(manifestUrl()))
    app.sets = catalog.sets
    app.levels = catalog.levels
    app.locations = LOCATIONS
    app.tabs = catalog.tabs
    app.tab = catalog.tabs[0]?.id ?? app.tab
    app.status = `bundle ${catalog.bundle.version} · ${catalog.sets.length} sets · ${catalog.resources.length} catalog tables`
    await app.updateComplete
    const report = (error: unknown): void => { app.error = String(error) }
    // The filter each tab was last mounted for; a tab shown again for the same filter only
    // resizes. A tab that takes no picker is mounted once, whatever is chosen.
    const tabs = new Map(catalog.tabs.map(tab => [tab.id, tab]))
    const shown = new Map<string, string>()
    // An editor tab is mounted again each time it is shown, so its dropdowns and problems
    // follow what the other tables now hold.
    // Each editor tab is coloured by its table's state: complete, missing a description, or broken.
    const colour = (): void => {
      const states = catalog.draft.states()
      app.tabs = app.tabs.map(tab => tab.group === 'editor' ? { ...tab, state: states[tab.id.slice('edit:'.length)] } : tab)
    }
    let rulesAsked = false
    const edit = async (tab: string, set: string, note = ''): Promise<void> => {
      const host = app.hostFor(tab)
      for (const table of mounted.get(host) ?? []) table.destroy()
      host.replaceChildren()
      if (!rulesAsked) {
        rulesAsked = true
        const response = await fetch(rulesUrl())
        if (response.ok) catalog.draft.rules = parseRuleLevels(await response.json())
      }
      colour()
      mounted.set(host, [await mountEditor(host, catalog.draft, tab.slice('edit:'.length), set, {
        changed: () => {
          app.sets = [...new Set([...catalog.sets, ...catalog.draft.sets()])]
          colour()
        },
        save: set => { catalog.save(set) },
        clear: () => {
          if (!window.confirm('Empty every table of the editor? Edits not saved are lost.')) return
          catalog.draft.clear()
          void edit(tab, set).catch(report)
        },
        resolve: () => {
          const added = Object.entries(catalog.draft.resolve()).map(([table, rows]) => `${rows} to ${table}`)
          const note = added.length === 0
            ? 'Resolve added nothing: every red reference needs a value first.'
            : `Resolve added rows: ${added.join(', ')}. Their key cells are filled; fill their orange cells in those tables.`
          app.sets = [...new Set([...catalog.sets, ...catalog.draft.sets()])]
          void edit(tab, set, note).catch(report)
        }
      }, note)])
    }
    window.addEventListener('beforeunload', event => { if (catalog.draft.edited) event.preventDefault() })
    const render = async (): Promise<void> => {
      const tab = app.tab
      const shownTab = tabs.get(tab)
      if (!shownTab) throw new Error(`No catalog tab ${tab}`)
      const filter = app.filterFor(shownTab)
      if (shownTab.group === 'editor') {
        shown.delete(tab)
        await edit(tab, filter.set)
        return
      }
      if (tab === 'console') {
        if (!shown.has(tab)) mountConsole(app.hostFor(tab), { ...catalog.scope, ...(await resultsScope()) })
        shown.set(tab, 'mounted')
        return
      }
      const asked = JSON.stringify(filter)
      if (shown.get(tab) === asked) {
        for (const table of mounted.get(app.hostFor(tab)) ?? []) table.redraw()
        return
      }
      shown.set(tab, asked)
      const select = tab === 'software'
        ? (level: Row) => { void show(app.hostFor('software-detail'), catalog.detail(level, filter)).catch(report) }
        : undefined
      await show(app.hostFor(tab), catalog.views(tab, filter), select)
    }
    app.addEventListener('tab-change', () => {
      void app.updateComplete.then(() => { window.requestAnimationFrame(() => { void render().catch(report) }) })
    })
    app.addEventListener('filter-change', () => {
      void show(app.hostFor('software-detail'), []).then(render).catch(report)
    })
    await render()
  } catch (error) {
    app.error = String(error)
    throw error
  }
}

void main()
