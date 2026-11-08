// The JavaScript parser CodeMirror's JavaScript mode uses, without an editor: it runs in Node too,
// so code that reads JavaScript's structure is testable there.

import { javascriptLanguage } from '@codemirror/lang-javascript'

export const javascriptParser = javascriptLanguage.parser

/** A parsed piece of code, and one node of it. */
export type Tree = ReturnType<typeof javascriptParser.parse>
export type SyntaxNode = Tree['topNode']
