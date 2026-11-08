// CodeMirror 6 for JavaScript: a code box, a console input line, and code coloured without an editor.
// Tokens carry `tok-*` classes, so each viewer's stylesheet colours them.

import { defaultKeymap, history, historyKeymap, indentWithTab, insertNewlineAndIndent } from '@codemirror/commands'
import { javascriptLanguage } from '@codemirror/lang-javascript'
import { bracketMatching, indentOnInput, LanguageSupport, syntaxHighlighting } from '@codemirror/language'
import { EditorSelection, EditorState, Prec, type Extension } from '@codemirror/state'
import { drawSelection, EditorView, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers, placeholder } from '@codemirror/view'
import { classHighlighter, highlightCode } from '@lezer/highlight'
import { javascriptParser } from './javascript-parser.js'

/** The code a box holds, read and replaced as a textarea's value is, and the part selected. */
export interface CodeBox {
  value: string
  readonly selection: string
}

// What both boxes share: editing, undo, bracket matching, JavaScript highlighting, an accessible name.
function editing (label: string, changed: () => void): Extension[] {
  return [
    drawSelection(),
    history(),
    indentOnInput(),
    bracketMatching(),
    new LanguageSupport(javascriptLanguage),
    syntaxHighlighting(classHighlighter),
    EditorState.tabSize.of(2),
    keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
    EditorView.contentAttributes.of({ 'aria-label': label }),
    EditorView.updateListener.of(update => { if (update.docChanged) changed() })
  ]
}

function codeBox (view: EditorView): CodeBox {
  return {
    get value () { return view.state.doc.toString() },
    set value (next: string) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: next }, selection: EditorSelection.cursor(next.length) })
    },
    get selection () {
      const { from, to } = view.state.selection.main
      return view.state.sliceDoc(from, to)
    }
  }
}

/** A JavaScript code box in `parent`, holding `text`; ⌘/Ctrl+Enter calls `run`, every edit `changed`. */
export function javascriptBox (parent: HTMLElement, text: string, label: string, run: () => void, changed: () => void): CodeBox {
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc: text,
      extensions: [
        Prec.highest(keymap.of([{ key: 'Mod-Enter', run: () => { run(); return true } }])),
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightActiveLine(),
        ...editing(label, changed)
      ]
    })
  })
  return codeBox(view)
}

/** A console input line in `parent`, showing `hint` while empty: Enter hands its code to `run` and
 * empties it, Shift+Enter adds a line, ↑ on the first line and ↓ on the last walk `history`, which
 * the caller owns and appends to. */
export function javascriptLine (parent: HTMLElement, label: string, hint: string, entries: string[], run: (code: string) => void): CodeBox {
  // The history entry shown, as an index into `entries`; entries.length is the line being written.
  let at = entries.length
  let draft = ''
  const recalled = (view: EditorView): boolean => at < entries.length && view.state.doc.toString() === entries[at]
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc: '',
      extensions: [
        Prec.highest(keymap.of([
          {
            key: 'Enter',
            run: view => {
              const code = view.state.doc.toString()
              if (code.trim() !== '') {
                run(code)
                line.value = ''
                at = entries.length
              }
              return true
            }
          },
          { key: 'Shift-Enter', run: insertNewlineAndIndent },
          {
            key: 'ArrowUp',
            run: view => {
              if (view.state.doc.lineAt(view.state.selection.main.head).number !== 1) return false
              if (!recalled(view)) {
                draft = view.state.doc.toString()
                at = entries.length
              }
              if (at === 0) return false
              at -= 1
              line.value = entries[at] ?? ''
              return true
            }
          },
          {
            key: 'ArrowDown',
            run: view => {
              const { doc, selection } = view.state
              if (doc.lineAt(selection.main.head).number !== doc.lines || !recalled(view)) return false
              at += 1
              line.value = at < entries.length ? entries[at] ?? '' : draft
              return true
            }
          }
        ])),
        placeholder(hint),
        ...editing(label, () => undefined)
      ]
    })
  })
  const line = codeBox(view)
  return line
}

/** Fill `element` with `code`, coloured as the boxes colour it, without an editor. */
export function highlighted (code: string, element: HTMLElement): void {
  highlightCode(code, javascriptParser.parse(code), classHighlighter, (text, classes) => {
    if (classes === '') {
      element.append(text)
      return
    }
    const span = document.createElement('span')
    span.className = classes
    span.textContent = text
    element.append(span)
  }, () => { element.append('\n') })
}
