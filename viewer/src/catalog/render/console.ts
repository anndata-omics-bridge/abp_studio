import { highlighted, javascriptBox, javascriptLine } from '../../shared/codemirror.js'
import type { Tabulator } from '../../shared/tabulator.js'
import { asRows, EXAMPLES, Session, shown } from '../projections/console.js'
import { tableOf, tableView } from '../projections/tables.js'
import { mountTable } from './tabulator.js'

// The API console demo, laid out as RStudio's: the examples and a code editor on top, a console
// below whose transcript keeps each run with what it gave, and an input line under it. One session
// holds the variables both define.

// Transcript entries kept; older ones go, with their tables.
const KEPT = 20

function element<Tag extends keyof HTMLElementTagNameMap> (tag: Tag, className: string, text = ''): HTMLElementTagNameMap[Tag] {
  const found = document.createElement(tag)
  found.className = className
  found.textContent = text
  return found
}

/** One run in the transcript: its element, and the table it shows, if any. */
interface Entry { element: HTMLElement; table: Tabulator | null }

/** Mount the console; `scope` names what the code may use. */
export function mountConsole (host: HTMLElement, scope: Record<string, unknown>): void {
  const session = new Session(scope)
  const history: string[] = []
  const section = element('section', 'view console')
  const names = element('p', 'console-names')
  const showNames = (): void => {
    const yours = session.names()
    names.textContent = `Names: ${Object.keys(scope).join(', ')}, print.${yours.length > 0 ? ` Yours: ${yours.join(', ')}.` : ''} ` +
      'The last expression shows its value. ⌘/Ctrl+Enter runs the editor\'s selection, or all of it; Enter runs the console line, Shift+Enter adds a line, ↑/↓ recall.'
  }
  const toolbar = element('div', 'editor-toolbar')
  const button = (text: string, title: string): HTMLButtonElement => {
    const found = element('button', '', text)
    found.type = 'button'
    found.title = title
    return found
  }
  const runButton = button('Run', 'Run the selection, or all the code (⌘/Ctrl+Enter)')
  const clearButton = button('Clear', 'Empty the console; variables stay')
  const resetButton = button('Reset', 'Empty the console and forget your variables')
  toolbar.append(runButton, clearButton, resetButton)
  // The examples as a table down the left, category then title; a click puts one in the box and runs it.
  const examples = element('table', 'console-list')
  const head = examples.createTHead().insertRow()
  head.append(element('th', '', 'Category'), element('th', '', 'Example'))
  const body = examples.createTBody()
  const picks = EXAMPLES.map(example => {
    const row = body.insertRow()
    const pick = element('button', 'console-pick', example.label)
    pick.type = 'button'
    row.append(element('td', 'console-category', example.category), element('td', ''))
    row.cells[1]?.append(pick)
    return { row, pick, example }
  })
  const box = element('div', 'console-code')
  const editor = element('div', 'console-editor')
  editor.append(toolbar, box)
  const layout = element('div', 'console-layout')
  layout.append(examples, editor)
  const transcript = element('div', 'console-output')
  const input = element('div', 'console-input')
  section.append(names, layout, transcript, input)
  host.append(section)

  const entries: Entry[] = []
  const drop = (entry: Entry): void => {
    entry.table?.destroy()
    entry.element.remove()
  }
  const clear = (): void => {
    for (const entry of entries.splice(0)) drop(entry)
  }
  const bottom = (): void => { transcript.scrollTop = transcript.scrollHeight }
  // Runs one after another, in the order given, so each sees what the one before it defined.
  let queue: Promise<void> = Promise.resolve()
  const submit = (code: string): void => {
    if (history.at(-1) !== code) history.push(code)
    const view = element('div', 'console-entry')
    const source = element('pre', 'console-entry-code')
    highlighted(code, source)
    const status = element('p', 'console-names', 'running…')
    view.append(source, status)
    transcript.append(view)
    const entry: Entry = { element: view, table: null }
    entries.push(entry)
    for (const old of entries.splice(0, Math.max(0, entries.length - KEPT))) drop(old)
    bottom()
    queue = queue.then(async () => {
      const outcome = await session.run(code)
      status.remove()
      if (outcome.printed.length > 0) view.append(element('pre', 'console-printed', outcome.printed.join('\n')))
      if (outcome.error !== null) {
        view.append(element('pre', 'console-error', outcome.error))
      } else if (outcome.value !== undefined) {
        const rows = asRows(outcome.value)
        if (rows === null) view.append(element('pre', 'console-value', shown(outcome.value)))
        else if (view.isConnected) entry.table = await mountTable(view, tableView('console', `${rows.length} rows`, '', tableOf(rows)))
      }
    }).catch((error: unknown) => {
      view.append(element('pre', 'console-error', error instanceof Error ? `${error.name}: ${error.message}` : String(error)))
    }).finally(() => {
      showNames()
      bottom()
    })
  }

  const code = javascriptBox(box, EXAMPLES[0]?.code ?? '', 'Code', () => { run() }, () => { mark() })
  const run = (): void => { submit(code.selection.trim() !== '' ? code.selection : code.value) }
  javascriptLine(input, 'Console input', "diann.levels.get('peptidoform_ion').obs()", history, submit)
  runButton.addEventListener('click', run)
  clearButton.addEventListener('click', clear)
  resetButton.addEventListener('click', () => {
    clear()
    session.reset()
    showNames()
  })
  const mark = (): void => {
    for (const { row, example } of picks) row.toggleAttribute('aria-current', example.code === code.value)
  }
  for (const { pick, example } of picks) {
    pick.addEventListener('click', () => {
      code.value = example.code
      mark()
      submit(example.code)
    })
  }
  mark()
  showNames()
  submit(code.value)
}
