import type { CellComponent, ColumnDefinition, Tabulator } from '../../shared/tabulator.js'
import { TabulatorFull } from '../../shared/tabulator.js'
import type { CatalogDraft, Cells, DraftFile, Problem } from '../projections/editor.js'
import { DERIVED, READ_ONLY, zipFiles } from '../projections/editor.js'

// One editable stored table of the catalog editor demo: a toolbar, the problems the draft has, and
// a Tabulator whose foreign-key columns edit by dropdown. The draft holds every change.

const ID = '_id'

/** What the toolbar asks the composition root to do. */
export interface EditorActions {
  /** Heard after every change, so the shell can offer new sets. */
  changed: () => void
  /** Save every set, or the one given, as a zip. */
  save: (set: string) => void
  /** Empty every editable table and show this one again. */
  clear: () => void
  /** Add the rows the unanswered foreign keys need and show this table again. */
  resolve: () => void
}

/** Offer files to the browser as one zip download, each under the zip's folder. */
export function download (name: string, files: DraftFile[]): void {
  const folder = name.replace(/\.zip$/, '')
  const zip = zipFiles(files.map(file => ({ name: `${folder}/${file.name}`, text: file.text })))
  const url = URL.createObjectURL(new Blob([zip], { type: 'application/zip' }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => { URL.revokeObjectURL(url) }, 1000)
}

function button (text: string, act: () => void): HTMLButtonElement {
  const found = document.createElement('button')
  found.type = 'button'
  found.textContent = text
  found.addEventListener('click', act)
  return found
}

/** Mount one table of the draft, the rows of `set` or of every set; `note` says what the last
 * action did. */
export async function mountEditor (host: HTMLElement, draft: CatalogDraft, table: string, set: string, actions: EditorActions, note = ''): Promise<Tabulator> {
  const schema = draft.schema(table)
  const editable = !READ_ONLY.includes(table)
  const cellsOf = (data: Record<string, unknown>): Cells =>
    Object.fromEntries(schema.columns.map(column => [column, String(data[column] ?? '')]))
  const idOf = (cell: CellComponent): number => Number((cell.getRow().getData() as Record<string, unknown>)[ID])

  const section = document.createElement('section')
  section.className = 'view editor'
  const heading = document.createElement('h3')
  heading.textContent = `${schema.path}${editable ? '' : ' (written from APB2\'s rules, read only)'}`
  const toolbar = document.createElement('div')
  toolbar.className = 'editor-toolbar'
  const status = document.createElement('p')
  status.className = 'editor-problems'
  const done = document.createElement('p')
  done.className = 'editor-note'
  done.textContent = note
  done.hidden = note === ''
  const body = document.createElement('div')
  section.append(heading, toolbar, done, status, body)
  host.append(section)

  let problems = new Map<string, Problem>()
  const formatter = (cell: CellComponent): HTMLElement => {
    const problem = problems.get(`${idOf(cell)}:${cell.getField()}`)
    const element = cell.getElement()
    element.classList.toggle('cell-problem', problem?.level === 'broken')
    element.classList.toggle('cell-missing', problem?.level === 'incomplete')
    element.title = problem?.message ?? ''
    const text = document.createElement('span')
    text.textContent = String(cell.getValue() ?? '')
    return text
  }
  const columns: ColumnDefinition[] = schema.columns.map((column): ColumnDefinition => {
    const mark = schema.marks[column]
    const derived = DERIVED[table]?.includes(column) ?? false
    const description = `${schema.descriptions[column] ?? ''}${derived ? ' The editor fills it from the term in terms.csv.' : ''}`
    const shown: ColumnDefinition = {
      title: `${column}${mark === undefined ? '' : ` ${mark}`}${derived ? ' (from term)' : ''}`,
      field: column,
      minWidth: 90,
      formatter,
      headerFilter: 'input',
      ...(description === '' ? {} : { headerTooltip: description }),
      ...(derived ? { cssClass: 'cell-derived' } : {})
    }
    if (!editable || derived) return shown
    if (draft.choices(table, {}, column) === null) return { ...shown, editor: 'input' }
    return {
      ...shown,
      editor: 'list',
      editorParams: {
        valuesLookup: (cell: CellComponent) => draft.choices(table, cellsOf(cell.getRow().getData() as Record<string, unknown>), column) ?? [],
        autocomplete: true,
        freetext: true,
        allowEmpty: true,
        listOnEmpty: true
      }
    } as ColumnDefinition
  })
  // The rows needing editing lead: broken first, then those missing a description. They are ranked
  // when the table is mounted, so a row being edited stays where it is.
  const rank = new Map<number, number>()
  for (const problem of draft.problems()) {
    if (problem.table !== table) continue
    rank.set(problem.id, Math.min(rank.get(problem.id) ?? 2, problem.level === 'broken' ? 0 : 1))
  }
  const data = draft.rows(table, set)
    .map((row, order) => ({ row, order }))
    .sort((one, other) => (rank.get(one.row.id) ?? 2) - (rank.get(other.row.id) ?? 2) || one.order - other.order)
    .map(({ row }) => ({ [ID]: row.id, ...row.cells }))
  const tabulator = new TabulatorFull(body, {
    layout: 'fitDataFill',
    placeholder: 'No rows: add one',
    maxHeight: '70vh',
    nestedFieldSeparator: false,
    index: ID,
    data,
    columnDefaults: { headerHozAlign: 'left', resizable: true },
    columns: editable
      ? [{ title: '', field: ID, formatter: 'buttonCross', width: 44, hozAlign: 'center', headerSort: false, frozen: true }, ...columns]
      : columns
  })
  await new Promise<void>(resolve => tabulator.on('tableBuilt', resolve))

  const resolve = button('Resolve: add the rows red references need', actions.resolve)
  const refresh = (): void => {
    const all = draft.problems()
    const here = all.filter(problem => problem.table === table)
    problems = new Map(here.map(problem => [`${problem.id}:${problem.column}`, problem]))
    const count = (level: Problem['level']): number => here.filter(problem => problem.level === level).length
    const elsewhere = all.length - here.length
    status.textContent = all.length === 0
      ? 'Complete: every key is answered and every required cell filled.'
      : `In ${table}: ${count('broken')} broken (red), ${count('incomplete')} missing a description (orange); ${elsewhere} in the other tables. Hover a cell for the reason.`
    status.classList.toggle('error', here.some(problem => problem.level === 'broken'))
    resolve.hidden = !all.some(problem => problem.resolvable)
    for (const row of tabulator.getRows()) row.reformat()
  }
  const changed = (): void => { refresh(); actions.changed() }

  if (editable) {
    toolbar.append(button(set === '' ? 'Add row' : `Add row to ${set}`, () => {
      const row = draft.add(table, set)
      void tabulator.addRow({ [ID]: row.id, ...row.cells }, true).then(() => {
        changed()
        void tabulator.scrollToRow(row.id, 'top', false)
      })
    }))
    tabulator.on('cellClick', (_event, cell) => {
      if (cell.getColumn().getDefinition().formatter !== 'buttonCross') return
      draft.remove(table, idOf(cell))
      void cell.getRow().delete().then(changed)
    })
    tabulator.on('cellEdited', cell => {
      const id = idOf(cell)
      draft.update(table, id, cell.getField(), String(cell.getValue() ?? ''))
      void cell.getRow().update({ ...draft.row(table, id).cells }).then(changed)
    })
  }
  if (editable) toolbar.append(resolve)
  toolbar.append(button('Save every set (zip)', () => { actions.save('') }))
  if (set !== '') toolbar.append(button(`Save ${set} (zip)`, () => { actions.save(set) }))
  if (editable) toolbar.append(button('Start empty', actions.clear))
  refresh()
  return tabulator
}
