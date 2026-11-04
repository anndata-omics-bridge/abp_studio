import './app.css'
import type { Tabulator } from '../shared/tabulator.js'
import { RulesBundle } from './bundle.js'
import { ACROSS_COLUMN_FIELDS, ACROSS_LAYER_FIELDS, allColumns, allLayers, LEVEL_FIELDS, levelRows, ofLevel, orderedLevels } from './projections/across.js'
import { levelPage } from './projections/level.js'
import { RULE_FIELDS, ruleLabel, ruleRows } from './projections/rules.js'
import { tableView } from './projections/tables.js'
import { mountJson } from './render/json.js'
import { mountTable } from './render/tabulator.js'
import { DOCUMENT } from './shell/rules-app.js'
import './shell/rules-app.js'
import type { JsonView, Row, Tab, TableView } from './types.js'

// Load the bundle once. Every tab is a projection of what it holds, mounted the first time it
// is shown and again when the rule, its view or the level changes.
const DATA_ROOT = 'data'

const TABS: Tab[] = [
  { id: 'rules', label: 'Rules', levels: false, description: 'One row per packaged parsing rule: the quantification tool and versions it reads, its input and the levels it declares. Click a row to open the rule.' },
  { id: 'rule', label: 'Rule', levels: false, description: 'One rule, level by level, as conversion stores it: the base merged into each level and the search-parameter overrides applied by apb2. rules.json shows the file as packaged.' },
  { id: 'levels', label: 'Levels', levels: true, description: 'Every level of every rule: its keys, primary layer, abundance layers and the columns with the protein_assignment and fasta_accessions roles.' },
  { id: 'layers', label: 'Layers', levels: true, description: 'Every quantity layer of every rule level, with its source, roles and missing-value policy.' },
  { id: 'columns', label: 'Columns', levels: true, description: 'Every feature-table (var) and sample-table (obs) column of every rule level, read or computed.' }
]

/** The bundle's manifest: in `data/` beside the viewer, or in the folder `?bundle=` names. */
function manifestUrl (): string {
  const folder = new URLSearchParams(window.location.search).get('bundle') ?? DATA_ROOT
  return new URL('manifest.json', new URL(folder.endsWith('/') ? folder : `${folder}/`, document.baseURI)).href
}

const mounted = new Map<HTMLElement, Tabulator[]>()
const generations = new WeakMap<HTMLElement, number>()

async function show (host: HTMLElement, views: TableView[], json: JsonView[] = [], select?: (row: Row) => void): Promise<void> {
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
  for (const view of json) mountJson(host, view)
  mounted.set(host, tables)
}

async function main (): Promise<void> {
  const app = document.querySelector('rules-app')
  if (!app) throw new Error('Rules viewer shell is missing')
  try {
    const bundle = await RulesBundle.load(manifestUrl())
    const { rules, levels, manifest } = bundle
    app.tabs = TABS
    app.rules = rules.map(rule => ({ rule: rule.rule, label: ruleLabel(rule), levels: rule.levels }))
    app.levels = orderedLevels(levels)
    app.rule = rules[0]?.rule ?? ''
    app.view = rules[0]?.levels[0] ?? DOCUMENT
    const commit = manifest.apb2_commit === null ? 'no commit' : `commit ${manifest.apb2_commit.slice(0, 7)}${manifest.apb2_commit.endsWith('-dirty') ? ' with local changes' : ''}`
    app.status = `apb2 ${manifest.apb2_version} · ${commit} · ${rules.length} rules · ${levels.length} rule levels`
    await app.updateComplete
    const report = (error: unknown): void => { app.error = String(error) }

    const views = async (): Promise<{ key: string; tables: TableView[]; json: JsonView[]; select?: (row: Row) => void }> => {
      switch (app.tab) {
        case 'rules': return {
          key: 'rules',
          tables: [tableView('rules', 'Parsing rules', `${rules.length} rules.json files, as apb2 packages them.`, ruleRows(rules), RULE_FIELDS)],
          json: [],
          select: (row: Row) => { app.open(String(row.rule)) }
        }
        case 'rule': {
          const key = `rule:${app.rule}:${app.view}`
          if (app.view === DOCUMENT) {
            return { key, tables: [], json: [{ key, title: app.rule, description: 'The rules.json as apb2 packages it: each table\'s input, the base shared by its levels, and each level\'s own declarations.', data: await bundle.document(app.rule) }] }
          }
          const level = levels.find(item => item.rule === app.rule && item.level === app.view)
          if (!level) throw new Error(`No level ${app.view} in ${app.rule}`)
          return { key, ...levelPage(level) }
        }
        case 'levels': return {
          key: `levels:${app.level}`,
          tables: [tableView('levels', 'Rule levels', 'One row per level of each rule; click a row to open it.', levelRows(rules, ofLevel(levels, app.level)), LEVEL_FIELDS)],
          json: [],
          select: (row: Row) => { app.open(String(row.rule), String(row.level)) }
        }
        case 'layers': return {
          key: `layers:${app.level}`,
          tables: [tableView('layers', 'Quantity layers', 'One row per layer of each rule level; click a row to open its level.', allLayers(rules, ofLevel(levels, app.level)), ACROSS_LAYER_FIELDS)],
          json: [],
          select: (row: Row) => { app.open(String(row.rule), String(row.level)) }
        }
        case 'columns': return {
          key: `columns:${app.level}`,
          tables: [tableView('columns', 'Feature-table and sample-table columns', 'One row per column of each rule level; click a row to open its level.', allColumns(rules, ofLevel(levels, app.level)), ACROSS_COLUMN_FIELDS)],
          json: [],
          select: (row: Row) => { app.open(String(row.rule), String(row.level)) }
        }
      }
    }

    // What each tab was last mounted for; a tab shown again for the same state only redraws.
    const shown = new Map<string, string>()
    const render = async (): Promise<void> => {
      const tab = app.tab
      const host = app.hostFor(tab)
      const page = await views()
      if (shown.get(tab) === page.key) {
        for (const table of mounted.get(host) ?? []) table.redraw()
        return
      }
      shown.set(tab, page.key)
      await show(host, page.tables, page.json, page.select)
    }
    const rerender = (): void => {
      void app.updateComplete.then(() => { window.requestAnimationFrame(() => { void render().catch(report) }) })
    }
    app.addEventListener('tab-change', rerender)
    app.addEventListener('rule-view-change', rerender)
    app.addEventListener('level-change', rerender)
    await render()
  } catch (error) {
    app.error = String(error)
    throw error
  }
}

void main()
